"""Shared deterministic text signals for procurement-transition screening."""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

import pandas as pd


DIRECTED_LINEAGE_TERMS: tuple[str, ...] = (
    "phase iii",
    "phase 3",
    "derives from",
    "prototype transition",
    "follow-on production",
    "continuation of",
    "sole source",
    "notice of intent",
)

SCORING_LINEAGE_PHRASES: tuple[str, ...] = (
    "phase iii",
    "phase 3",
    "derives from",
    "extends",
    "completes",
    "prototype transition",
    "follow-on production",
    "continuation of",
    "technical data package",
    "interface control document",
    "source code",
    "government purpose rights",
    "unlimited rights",
)
PUBLIC_LINEAGE_PHRASES: tuple[str, ...] = tuple(
    dict.fromkeys((*SCORING_LINEAGE_PHRASES, *DIRECTED_LINEAGE_TERMS))
)

_TOKEN_RE = re.compile(r"[A-Za-z0-9]+")
_STOPWORDS: frozenset[str] = frozenset(
    {
        "a",
        "an",
        "the",
        "of",
        "and",
        "or",
        "for",
        "to",
        "in",
        "on",
        "at",
        "with",
        "by",
        "is",
        "are",
        "be",
        "as",
        "this",
        "that",
        "these",
        "those",
        "from",
        "we",
        "our",
    }
)


def _coerce_text(value: Any) -> str | None:
    if value is None:
        return None
    try:
        if bool(pd.isna(value)):
            return None
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    return text if text and text.lower() not in {"nan", "nat", "none", "<na>"} else None


def tokenize_technical_text(text: Any) -> set[str]:
    """Return the content tokens used by procurement topical-similarity scoring."""

    normalized = _coerce_text(text)
    if normalized is None:
        return set()
    tokens = {match.group(0).lower() for match in _TOKEN_RE.finditer(normalized)}
    return {token for token in tokens if token not in _STOPWORDS and len(token) > 2}


def find_lineage_phrases(
    text: Any,
    *,
    phrases: Iterable[str] = PUBLIC_LINEAGE_PHRASES,
) -> tuple[str, ...]:
    """Return distinct lineage phrases present in text, preserving vocabulary order."""

    normalized = _coerce_text(text)
    if normalized is None:
        return ()
    return tuple(
        phrase
        for phrase in phrases
        if re.search(r"\b" + re.escape(phrase) + r"\b", normalized, flags=re.IGNORECASE)
    )


__all__ = [
    "DIRECTED_LINEAGE_TERMS",
    "PUBLIC_LINEAGE_PHRASES",
    "SCORING_LINEAGE_PHRASES",
    "find_lineage_phrases",
    "tokenize_technical_text",
]
