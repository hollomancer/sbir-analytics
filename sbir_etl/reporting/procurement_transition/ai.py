"""Optional evidence-bounded narrative generation for monthly packets."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any

from sbir_etl.enrichers.openai_client import OpenAIClient


_CITATION = re.compile(r"\[(SAM|SBIR|USASPENDING)\]")


def validate_cited_summary(value: str | None) -> str | None:
    """Accept only short summaries whose substantive sentences cite supplied evidence."""

    if not value or len(value) > 1200:
        return None
    sentence_count = max(1, len(re.findall(r"[.!?](?=\s|$)", value)))
    citation_count = len(_CITATION.findall(value))
    return value.strip() if citation_count >= sentence_count else None


def build_public_evidence_summarizer(api_key: str) -> Callable[[dict[str, Any]], str | None]:
    """Return a callback that summarizes supplied public fields and cannot affect scoring."""

    client = OpenAIClient(api_key=api_key, max_concurrent=1)

    def summarize(row: dict[str, Any]) -> str | None:
        evidence = {
            "company": row.get("company"),
            "prior_award_title": row.get("title"),
            "phase": row.get("phase"),
            "opportunity_title": row.get("title_opp"),
            "opportunity_description": row.get("description"),
            "signal_class": row.get("signal_class"),
            "score": row.get("candidate_score"),
            "sam_url": row.get("source_url") or row.get("ui_url"),
        }
        result = client.chat(
            "Summarize only the supplied public evidence. Do not infer statutory Phase III "
            "status. Write at most two sentences and end every sentence with [SAM] or [SBIR].",
            json.dumps(evidence, default=str),
            temperature=0.0,
        )
        return validate_cited_summary(result)

    return summarize


__all__ = ["build_public_evidence_summarizer", "validate_cited_summary"]
