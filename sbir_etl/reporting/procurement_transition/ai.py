"""Optional evidence-bounded narrative generation for monthly packets."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any

from sbir_etl.enrichers.openai_client import OpenAIClient


_CITATION = re.compile(r"\[(SAM|SBIR|USASPENDING)\]")
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+")

# The packet renders the validated summary verbatim, so validation and display
# share one limit — truncating after validation could cut a sentence's citation
# off and present uncited text as evidence-bounded.
MAX_SUMMARY_CHARS = 600


def _first(row: dict[str, Any], *names: str) -> Any:
    for name in names:
        value = row.get(name)
        if value is not None and str(value).strip().lower() not in {"", "nan", "none", "<na>"}:
            return value
    return None


def _bounded(value: Any, max_chars: int) -> Any:
    if value is None:
        return None
    text = str(value).strip()
    return text if len(text) <= max_chars else f"{text[: max_chars - 1].rstrip()}…"


def _sentences(text: str) -> list[str]:
    """Split into sentences, keeping a trailing citation with the claim it supports.

    "…prototypes. [SAM]" is one cited sentence, not a claim followed by an
    uncited fragment.
    """

    parts = [part for part in _SENTENCE_BOUNDARY.split(text) if part.strip()]
    merged: list[str] = []
    for part in parts:
        if merged and not _is_substantive(part):
            merged[-1] = f"{merged[-1]} {part}"
            continue
        merged.append(part)
    return merged


def _is_substantive(sentence: str) -> bool:
    """True when a sentence asserts something beyond its own citation markers."""

    return len(re.sub(r"[^0-9A-Za-z]+", "", _CITATION.sub("", sentence))) >= 3


def validate_cited_summary(value: str | None, *, max_chars: int = MAX_SUMMARY_CHARS) -> str | None:
    """Accept only short summaries where *every* substantive sentence is cited.

    Counting citations against a sentence total is not enough: two citations in
    one sentence would license an uncited claim in the next. Each sentence must
    carry its own ``[SAM]``/``[SBIR]``/``[USASPENDING]`` marker.
    """

    if not value:
        return None
    text = value.strip()
    if not text or len(text) > max_chars:
        return None
    sentences = _sentences(text)
    if not sentences:
        return None
    for sentence in sentences:
        if _is_substantive(sentence) and not _CITATION.search(sentence):
            return None
    return text


def build_public_evidence_summarizer(api_key: str) -> Callable[[dict[str, Any]], str | None]:
    """Return a callback that summarizes supplied public fields and cannot affect scoring."""

    client = OpenAIClient(api_key=api_key, max_concurrent=1, timeout=30)

    def summarize(row: dict[str, Any]) -> str | None:
        evidence = {
            "company": _bounded(row.get("company"), 300),
            "prior_award_title": _bounded(_first(row, "award_title", "prior_title", "title"), 500),
            "prior_award_abstract": _bounded(
                _first(row, "award_abstract", "prior_abstract", "abstract"), 4_000
            ),
            "phase": _bounded(row.get("phase"), 100),
            "opportunity_title": _bounded(
                _first(row, "opportunity_title", "target_title", "title_opp"), 500
            ),
            "opportunity_description": _bounded(
                _first(row, "opportunity_description", "target_description", "description"),
                6_000,
            ),
            "signal_class": row.get("signal_class"),
            "score": row.get("candidate_score"),
            "sbir_url": _bounded(_first(row, "award_source_url", "prior_source_url"), 2_000),
            "sam_url": _bounded(
                _first(row, "opportunity_source_url", "opportunity_ui_url", "target_source_url"),
                2_000,
            ),
        }
        result = client.chat(
            "Compare what the supplied SBIR/STTR award funded with what the solicitation asks "
            "for. Identify the specific technical overlap and the principal point a procurement "
            "representative must still verify. Do not infer completion or statutory Phase III "
            "status. Write at most two sentences and end every sentence with [SBIR], [SAM], or "
            "both, matching the evidence used. Keep the whole reply under "
            f"{MAX_SUMMARY_CHARS} characters.",
            json.dumps(evidence, default=str),
            temperature=0.0,
        )
        return validate_cited_summary(result)

    return summarize


__all__ = ["MAX_SUMMARY_CHARS", "build_public_evidence_summarizer", "validate_cited_summary"]
