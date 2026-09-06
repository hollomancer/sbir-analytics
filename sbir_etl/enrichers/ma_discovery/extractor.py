"""Typed snippet extractor contract and deterministic adapters for M&A discovery.

Epistemic tier: pipelines. This module holds only deterministic code: the
``ExtractionInput`` / ``ExtractionVerdict`` types, the ``SnippetExtractor``
protocol, ``KeywordExtractor`` over the existing ``verify_acquisition``
heuristic, and the JSON payload parsing and validation that turns a model
response into a verdict. Model inference lives in ``llm_extractor.py``
(exploratory tier); the pipelines tier must not perform inference, so that
module is not re-exported from the package.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from datetime import date
from typing import Any, Protocol

from sbir_etl.enrichers.ma_discovery.verifier import verify_acquisition
from sbir_etl.identity import CompanyNameProfile, normalize_company_name


EPISTEMIC_TIER = "pipelines"

UNKNOWN_DATE = "Unknown"
MAX_REASON_CHARS = 500

_JSON_FENCE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)


class SnippetExtractor(Protocol):
    """Shared extractor surface for keyword and LLM adapters."""

    def extract(self, item: ExtractionInput) -> ExtractionVerdict: ...


@dataclass(frozen=True)
class ExtractionInput:
    """One snippet to score against a named (company, acquirer) pair."""

    company: str
    acquirer: str
    snippet: str
    source_url: str | None = None


@dataclass(frozen=True)
class ExtractionVerdict:
    """Structured acquisition verdict for one snippet.

    Field names match the design schema plus ``confirmed`` and ``reason``.
    """

    confirmed: bool
    reason: str
    matched_company: str | None = None
    matched_acquirer: str | None = None
    acquisition_date: str | None = None
    value_usd: float | None = None
    citation_url: str | None = None


def is_filled_date(value: str | None) -> bool:
    """True when ``value`` is a real date, not the keyword heuristic's placeholder."""
    if value is None:
        return False
    stripped = value.strip()
    return bool(stripped) and stripped.casefold() != UNKNOWN_DATE.casefold()


def is_filled_value(value: float | None) -> bool:
    """True when a numeric deal value was extracted."""
    return value is not None


def parse_llm_payload(raw: str | None) -> dict[str, Any] | None:
    """Parse a JSON object from a model response, including fenced blocks."""
    if raw is None:
        return None
    text = raw.strip()
    if not text:
        return None
    fenced = _JSON_FENCE.search(text)
    if fenced:
        text = fenced.group(1).strip()
    if text.startswith("["):
        # The contract is one JSON object. A list is not silently unwrapped.
        return None
    start = text.find("{")
    if start < 0:
        return None
    # raw_decode stops at the end of the first complete object, so trailing
    # prose (even prose containing braces) does not turn a valid verdict into
    # "unparseable", and nested objects are not cut short by a regex.
    try:
        parsed, _ = json.JSONDecoder().raw_decode(text[start:])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _same_firm(requested: str | None, returned: str | None) -> bool:
    """Compare a requested and a returned firm name on the canonical profile.

    ``RECIPIENT_V1`` strips legal suffixes and folds case, so the suffix and
    case variation the prompt permits still matches, while a different firm
    does not. It is the same profile ``queries.py`` uses to build the query
    strings these snippets come from, so extractor and query generator agree
    on identity. An empty normalization on either side is a mismatch.
    """
    left = normalize_company_name(requested, profile=CompanyNameProfile.RECIPIENT_V1)
    right = normalize_company_name(returned, profile=CompanyNameProfile.RECIPIENT_V1)
    return bool(left) and bool(right) and left == right


def verdict_from_payload(
    payload: dict[str, Any] | None,
    *,
    item: ExtractionInput,
    parse_failure_reason: str = "Unparseable LLM response",
) -> ExtractionVerdict:
    """Map a parsed JSON object onto ``ExtractionVerdict``.

    Missing or malformed payloads are unconfirmed; they are never guessed. A
    confirmation is accepted only for the pair in ``item``: callers key
    verdicts by the *requested* pair, so a response about other firms would
    otherwise be recorded as a confirmation of this one. Provenance stays
    authoritative -- the citation is the search result's own URL, never a URL
    the model produced.
    """
    if payload is None:
        return ExtractionVerdict(confirmed=False, reason=parse_failure_reason)

    confirmed = payload.get("confirmed")
    if not isinstance(confirmed, bool):
        return ExtractionVerdict(
            confirmed=False,
            reason="LLM JSON missing boolean 'confirmed'",
        )

    matched_company = _as_optional_str(payload.get("matched_company"))
    matched_acquirer = _as_optional_str(payload.get("matched_acquirer"))
    if confirmed and not (
        _same_firm(item.company, matched_company) and _same_firm(item.acquirer, matched_acquirer)
    ):
        return ExtractionVerdict(
            confirmed=False,
            reason=(
                "LLM confirmed a different pair than requested: asked "
                f"{item.company!r}/{item.acquirer!r}, got "
                f"{matched_company!r}/{matched_acquirer!r}"
            ),
            matched_company=matched_company,
            matched_acquirer=matched_acquirer,
            citation_url=item.source_url,
        )

    return ExtractionVerdict(
        confirmed=confirmed,
        reason=(_as_optional_str(payload.get("reason")) or "LLM structured verdict")[
            :MAX_REASON_CHARS
        ],
        matched_company=matched_company,
        matched_acquirer=matched_acquirer,
        acquisition_date=_parse_iso_date(payload.get("acquisition_date")),
        value_usd=_parse_value_usd(payload.get("value_usd")),
        citation_url=item.source_url,
    )


class KeywordExtractor:
    """Adapter around ``verify_acquisition``. Does not change the heuristic."""

    name = "keyword"

    def extract(self, item: ExtractionInput) -> ExtractionVerdict:
        result = verify_acquisition(item.company, item.acquirer, item.snippet)
        confirmed = bool(result["confirmed"])
        raw_date = result["date"]
        date = raw_date if is_filled_date(raw_date) else None
        return ExtractionVerdict(
            confirmed=confirmed,
            reason=result["reason"],
            matched_company=item.company if confirmed else None,
            matched_acquirer=item.acquirer if confirmed else None,
            acquisition_date=date,
            value_usd=result["value"],
            citation_url=item.source_url,
        )


def _as_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return None


def _parse_iso_date(value: Any) -> str | None:
    """Accept only canonical ISO ``YYYY-MM-DD``. Invalid dates become null."""
    text = _as_optional_str(value)
    if text is None or not is_filled_date(text):
        return None
    try:
        parsed = date.fromisoformat(text)
    except ValueError:
        return None
    canonical = parsed.isoformat()
    return canonical if canonical == text else None


def _parse_value_usd(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    parsed: float | None
    if isinstance(value, (int, float)):
        parsed = float(value)
    elif isinstance(value, str):
        cleaned = value.strip().replace(",", "").replace("$", "")
        if not cleaned:
            return None
        try:
            parsed = float(cleaned)
        except ValueError:
            return None
    else:
        return None
    if not math.isfinite(parsed) or parsed < 0:
        return None
    return parsed
