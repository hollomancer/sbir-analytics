"""Tests for the fixture-only extractor harness.

Numbers are computed from the committed snippets, not hardcoded constants
that would drift if a fixture is added.
"""

from __future__ import annotations

import json

import pytest

from sbir_etl.enrichers.ma_discovery.extractor import KeywordExtractor, LlmExtractor
from sbir_etl.enrichers.ma_discovery.extractor_eval import (
    CaseScore,
    gold_replay_chat,
    load_fixtures,
    score_extractor,
    scores_as_dict,
    scores_from_cases,
)
from sbir_etl.enrichers.ma_discovery.orchestrator import process_batch
from sbir_etl.enrichers.ma_discovery.search import MockSearchTool


pytestmark = pytest.mark.fast


def _expected_counts(cases: list[CaseScore]) -> tuple[int, int, int, int]:
    tp = sum(1 for case in cases if case.expected_confirmed and case.predicted_confirmed)
    fp = sum(1 for case in cases if not case.expected_confirmed and case.predicted_confirmed)
    fn = sum(1 for case in cases if case.expected_confirmed and not case.predicted_confirmed)
    tn = sum(1 for case in cases if not case.expected_confirmed and not case.predicted_confirmed)
    return tp, fp, fn, tn


def test_fixtures_cover_required_categories() -> None:
    fixtures = load_fixtures()
    assert 8 <= len(fixtures) <= 15
    categories = {item.category for item in fixtures}
    assert {
        "slam_dunk",
        "negative",
        "rumor",
        "suffix_mismatch",
        "case_mismatch",
        "missing_date",
        "missing_value",
    } <= categories
    assert all(item.snippet.strip() for item in fixtures)
    assert any(item.expected_confirmed for item in fixtures)
    assert any(not item.expected_confirmed for item in fixtures)


def test_keyword_harness_metrics_match_fixture_counts() -> None:
    fixtures = load_fixtures()
    scores = score_extractor(KeywordExtractor(), fixtures)
    tp, fp, fn, tn = _expected_counts(list(scores.cases))
    assert scores.true_positives == tp
    assert scores.false_positives == fp
    assert scores.false_negatives == fn
    assert scores.true_negatives == tn
    assert scores.n == len(fixtures)
    assert scores.precision == pytest.approx(tp / (tp + fp))
    assert scores.recall == pytest.approx(tp / (tp + fn))
    # Keyword never extracts a date or value, so fill rates on confirms are 0.
    assert scores.date_fill_rate == 0.0
    assert scores.value_fill_rate == 0.0
    mismatch_ids = {case.id for case in scores.confirmed_mismatches}
    assert "suffix_mismatch" in mismatch_ids
    assert "rumor_exploring_merger" in mismatch_ids
    assert "rumor_potential_acquisition" in mismatch_ids


def test_gold_replay_is_perfect_on_labels_not_a_model() -> None:
    fixtures = load_fixtures()
    extractor = LlmExtractor(gold_replay_chat(fixtures))
    scores = score_extractor(extractor, fixtures, name="gold-replay")
    assert scores.precision == 1.0
    assert scores.recall == 1.0
    gold_with_date = [item for item in fixtures if item.expected_acquisition_date]
    gold_with_value = [item for item in fixtures if item.expected_value_usd is not None]
    confirmed = [item for item in fixtures if item.expected_confirmed]
    assert scores.date_fill_rate == pytest.approx(len(gold_with_date) / len(confirmed))
    assert scores.value_fill_rate == pytest.approx(len(gold_with_value) / len(confirmed))
    assert scores.confirmed_mismatches == ()


def test_scores_from_cases_are_not_mystery_constants() -> None:
    cases = (
        CaseScore("a", "slam_dunk", True, True, "ok", "2024-01-01", 1.0),
        CaseScore("b", "rumor", False, True, "fp", None, None),
        CaseScore("c", "suffix_mismatch", True, False, "fn", None, None),
        CaseScore("d", "negative", False, False, "tn", None, None),
    )
    scores = scores_from_cases(cases, name="synthetic")
    assert scores.precision == pytest.approx(0.5)
    assert scores.recall == pytest.approx(0.5)
    assert scores.date_fill_rate == pytest.approx(0.5)
    assert scores.value_fill_rate == pytest.approx(0.5)
    assert [case.id for case in scores.confirmed_mismatches] == ["b", "c"]
    dumped = scores_as_dict(scores)
    assert dumped["mismatch_ids"] == ["b", "c"]
    assert json.loads(json.dumps(dumped)) == dumped


@pytest.mark.asyncio
async def test_orchestrator_still_uses_keyword_not_llm() -> None:
    """Default batch path is still verify_acquisition via MockSearchTool."""
    queries = [
        {
            "company_name": "Physical Optics Corporation",
            "acquirer": "Mercury Systems",
            "query": '"Physical Optics" acquired by "Mercury Systems" press release',
        }
    ]
    verified = await process_batch(queries, MockSearchTool())
    assert len(verified) == 1
    assert verified[0]["date"] == "Unknown"
    assert verified[0]["value"] is None
