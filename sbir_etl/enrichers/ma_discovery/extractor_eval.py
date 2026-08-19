"""Fixture-only M&A extractor evaluation.

Epistemic tier: exploratory. Scores are computed from the committed snippet
fixtures and are not citable findings. No network calls.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sbir_etl.enrichers.ma_discovery.extractor import (
    ChatFn,
    ExtractionInput,
    ExtractionVerdict,
    SnippetExtractor,
    is_filled_date,
    is_filled_value,
)


EPISTEMIC_TIER = "exploratory"

_FIXTURE_RELATIVE = Path("tests/fixtures/ma_discovery/snippets.json")


@dataclass(frozen=True)
class FixtureCase:
    """One labeled snippet used by the extractor harness."""

    id: str
    category: str
    company: str
    acquirer: str
    snippet: str
    source_url: str | None
    expected_confirmed: bool
    expected_acquisition_date: str | None
    expected_value_usd: float | None

    def as_input(self) -> ExtractionInput:
        return ExtractionInput(
            company=self.company,
            acquirer=self.acquirer,
            snippet=self.snippet,
            source_url=self.source_url,
        )


@dataclass(frozen=True)
class CaseScore:
    """Extractor output for one fixture, aligned to the gold label."""

    id: str
    category: str
    expected_confirmed: bool
    predicted_confirmed: bool
    reason: str
    acquisition_date: str | None
    value_usd: float | None


@dataclass(frozen=True)
class ExtractorScores:
    """Precision/recall on ``confirmed`` plus date/value fill rates.

    Fill rates are the share of *extractor-confirmed* rows with a real date
    or numeric value. They are fixture diagnostics, not live-web recall.
    """

    name: str
    n: int
    true_positives: int
    false_positives: int
    false_negatives: int
    true_negatives: int
    precision: float
    recall: float
    date_fill_rate: float
    value_fill_rate: float
    cases: tuple[CaseScore, ...]

    @property
    def confirmed_mismatches(self) -> tuple[CaseScore, ...]:
        return tuple(
            case for case in self.cases if case.expected_confirmed != case.predicted_confirmed
        )


def default_fixtures_path(start: Path | None = None) -> Path:
    """Locate the committed snippet fixture file from this tree."""
    origin = start or Path(__file__).resolve()
    for candidate in (origin, *origin.parents):
        path = candidate / _FIXTURE_RELATIVE
        if path.is_file():
            return path
    raise FileNotFoundError(f"Could not find {_FIXTURE_RELATIVE}")


def load_fixtures(path: Path | None = None) -> list[FixtureCase]:
    """Load labeled snippets from JSON."""
    fixture_path = path or default_fixtures_path()
    raw = json.loads(fixture_path.read_text())
    if not isinstance(raw, list):
        raise ValueError(f"{fixture_path} must contain a JSON array")
    return [_fixture_from_mapping(item, index=index) for index, item in enumerate(raw)]


def score_extractor(
    extractor: SnippetExtractor,
    fixtures: Sequence[FixtureCase],
    *,
    name: str | None = None,
) -> ExtractorScores:
    """Run ``extractor`` over ``fixtures`` and score ``confirmed`` plus fill rates."""
    cases = tuple(_score_case(extractor.extract(item.as_input()), item) for item in fixtures)
    return scores_from_cases(
        cases, name=name or getattr(extractor, "name", extractor.__class__.__name__)
    )


def scores_from_cases(cases: Sequence[CaseScore], *, name: str) -> ExtractorScores:
    """Compute harness metrics from already-aligned case rows."""
    tp = sum(1 for case in cases if case.expected_confirmed and case.predicted_confirmed)
    fp = sum(1 for case in cases if not case.expected_confirmed and case.predicted_confirmed)
    fn = sum(1 for case in cases if case.expected_confirmed and not case.predicted_confirmed)
    tn = sum(1 for case in cases if not case.expected_confirmed and not case.predicted_confirmed)
    predicted_pos = [case for case in cases if case.predicted_confirmed]
    date_filled = sum(1 for case in predicted_pos if is_filled_date(case.acquisition_date))
    value_filled = sum(1 for case in predicted_pos if is_filled_value(case.value_usd))
    return ExtractorScores(
        name=name,
        n=len(cases),
        true_positives=tp,
        false_positives=fp,
        false_negatives=fn,
        true_negatives=tn,
        precision=_ratio(tp, tp + fp),
        recall=_ratio(tp, tp + fn),
        date_fill_rate=_ratio(date_filled, len(predicted_pos)),
        value_fill_rate=_ratio(value_filled, len(predicted_pos)),
        cases=tuple(cases),
    )


def gold_replay_chat(fixtures: Sequence[FixtureCase]) -> ChatFn:
    """Echo gold labels as JSON. Not a model; do not quote as an LLM result."""
    by_pair = {(item.company, item.acquirer): item for item in fixtures}

    def _chat(system: str, user: str) -> str | None:
        del system
        company, acquirer = _parse_pair_from_prompt(user)
        item = by_pair.get((company, acquirer))
        if item is None:
            return json.dumps(
                {
                    "confirmed": False,
                    "matched_company": None,
                    "matched_acquirer": None,
                    "acquisition_date": None,
                    "value_usd": None,
                    "citation_url": None,
                    "reason": "Gold replay has no fixture for this pair",
                }
            )
        return json.dumps(
            {
                "confirmed": item.expected_confirmed,
                "matched_company": item.company if item.expected_confirmed else None,
                "matched_acquirer": item.acquirer if item.expected_confirmed else None,
                "acquisition_date": item.expected_acquisition_date,
                "value_usd": item.expected_value_usd,
                "citation_url": item.source_url,
                "reason": "Gold-label replay (not a live model)",
            }
        )

    return _chat


def scores_as_dict(scores: ExtractorScores) -> dict[str, Any]:
    """JSON-friendly view of harness totals. Non-citable."""
    return {
        "name": scores.name,
        "n": scores.n,
        "true_positives": scores.true_positives,
        "false_positives": scores.false_positives,
        "false_negatives": scores.false_negatives,
        "true_negatives": scores.true_negatives,
        "precision": scores.precision,
        "recall": scores.recall,
        "date_fill_rate": scores.date_fill_rate,
        "value_fill_rate": scores.value_fill_rate,
        "mismatch_ids": [case.id for case in scores.confirmed_mismatches],
    }


def _score_case(verdict: ExtractionVerdict, item: FixtureCase) -> CaseScore:
    return CaseScore(
        id=item.id,
        category=item.category,
        expected_confirmed=item.expected_confirmed,
        predicted_confirmed=verdict.confirmed,
        reason=verdict.reason,
        acquisition_date=verdict.acquisition_date,
        value_usd=verdict.value_usd,
    )


def _fixture_from_mapping(item: Any, *, index: int) -> FixtureCase:
    if not isinstance(item, dict):
        raise ValueError(f"fixture[{index}] must be an object")
    try:
        fixture_id = str(item["id"])
        category = str(item["category"])
        company = str(item["company"])
        acquirer = str(item["acquirer"])
        snippet = str(item["snippet"])
        expected_confirmed = item["expected_confirmed"]
    except KeyError as exc:
        raise ValueError(f"fixture[{index}] missing {exc}") from exc
    if not isinstance(expected_confirmed, bool):
        raise ValueError(f"fixture[{index}] expected_confirmed must be a bool")
    value = item.get("expected_value_usd")
    if value is not None and not isinstance(value, (int, float)):
        raise ValueError(f"fixture[{index}] expected_value_usd must be a number or null")
    return FixtureCase(
        id=fixture_id,
        category=category,
        company=company,
        acquirer=acquirer,
        snippet=snippet,
        source_url=_optional_str(item.get("source_url")),
        expected_confirmed=expected_confirmed,
        expected_acquisition_date=_optional_str(item.get("expected_acquisition_date")),
        expected_value_usd=None if value is None else float(value),
    )


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _parse_pair_from_prompt(user: str) -> tuple[str, str]:
    company = ""
    acquirer = ""
    for line in user.splitlines():
        if line.startswith("Company:"):
            company = line.partition(":")[2].strip()
        elif line.startswith("Acquirer:"):
            acquirer = line.partition(":")[2].strip()
    return company, acquirer


def _ratio(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return numerator / denominator
