#!/usr/bin/env python3
"""Heuristic verifier for M&A acquisition signals in text snippets.

Given a candidate (company, acquirer) pair and a text snippet (e.g. a search
result or press release excerpt), returns a structured verdict on whether the
snippet confirms the acquisition. Used by `ma_discovery_orchestrator.py` as a
pluggable verification step.

Current implementation is a keyword heuristic — both names must appear in the
text and a recognized acquisition verb must be present. In production this
should be replaced by an LLM call that can also extract date and deal value.
"""
from __future__ import annotations

from typing import TypedDict


class VerificationResult(TypedDict):
    confirmed: bool
    date: str | None
    value: float | None
    reason: str


def verify_acquisition(company: str, acquirer: str, snippet: str) -> VerificationResult:
    """Return whether `snippet` confirms `company` was acquired by `acquirer`."""
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
