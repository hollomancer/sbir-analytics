"""Heuristic verifier for M&A acquisition signals in text snippets.

Both names must appear in the text and a recognized acquisition verb must
be present. Date extraction is out of scope for this heuristic (always
``"Unknown"`` on confirm). ``KeywordExtractor`` adapts this function onto
the shared structured verdict; the orchestrator still calls it directly.
"""

from __future__ import annotations

from typing import TypedDict


class VerificationResult(TypedDict):
    confirmed: bool
    date: str | None
    value: float | None
    reason: str


def verify_acquisition(company: str, acquirer: str, snippet: str) -> VerificationResult:
    """Return whether ``snippet`` confirms ``company`` was acquired by ``acquirer``."""
    text = snippet.lower()
    c = company.lower()
    a = acquirer.lower()

    keywords = ["acquired", "acquisition", "bought", "merger", "merged", "purchase"]

    if c in text and a in text and any(k in text for k in keywords):
        return {
            "confirmed": True,
            "date": "Unknown",  # LLM would extract; heuristic cannot
            "value": None,
            "reason": "Confirmed via keyword match",
        }

    return {
        "confirmed": False,
        "date": None,
        "value": None,
        "reason": "No clear acquisition signal found",
    }
