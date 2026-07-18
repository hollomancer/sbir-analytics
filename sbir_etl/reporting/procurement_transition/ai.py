"""Optional evidence-bounded narrative generation for monthly packets."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any

from sbir_etl.enrichers.openai_client import OpenAIClient


_CITATION = re.compile(r"\[(SAM|SBIR|USASPENDING)\]")


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


def validate_cited_summary(value: str | None) -> str | None:
    """Accept only short summaries whose substantive sentences cite supplied evidence."""

    if not value or len(value) > 1200:
        return None
    sentence_count = max(1, len(re.findall(r"[.!?](?=\s|$)", value)))
    citation_count = len(_CITATION.findall(value))
    return value.strip() if citation_count >= sentence_count else None


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
            "both, matching the evidence used.",
            json.dumps(evidence, default=str),
            temperature=0.0,
        )
        return validate_cited_summary(result)

    return summarize


__all__ = ["build_public_evidence_summarizer", "validate_cited_summary"]
