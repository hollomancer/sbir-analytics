"""Topical-similarity helper (NAICS + PSC code agreement + Jaccard token overlap) for Phase III candidate scoring."""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

DEFAULT_WEIGHTS: dict[str, float] = {
    "naics": 0.30,
    "psc": 0.20,
    "jaccard": 0.50,
}

_TOKEN_RE = re.compile(r"[A-Za-z0-9]+")

# Stop words intentionally narrow — we want genuine content tokens to drive
# Jaccard, but "the"/"of"/"and" noise distorts short-description overlap.
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


def _normalize_code(value: Any) -> str | None:
    """Return a trimmed, uppercase code string, or None if missing/blank."""

    if value is None:
        return None
    s = str(value).strip().upper()
    return s or None


def _code_similarity(prior: Any, target: Any) -> float:
    """1.0 on exact match, 0.0 otherwise (including when either side is missing)."""

    a = _normalize_code(prior)
    b = _normalize_code(target)
    if a is None or b is None:
        return 0.0
    return 1.0 if a == b else 0.0


def _tokenize(text: str | None) -> set[str]:
    if not text:
        return set()
    tokens = {m.group(0).lower() for m in _TOKEN_RE.finditer(text)}
    return {t for t in tokens if t not in _STOPWORDS and len(t) > 2}


def _jaccard(a: Iterable[str], b: Iterable[str]) -> float:
    sa, sb = set(a), set(b)
    if not sa and not sb:
        return 0.0
    union = sa | sb
    if not union:
        return 0.0
    return len(sa & sb) / len(union)


def compute_topical_similarity(
    prior_award: dict[str, Any],
    target: dict[str, Any],
    *,
    weights: dict[str, float] | None = None,
) -> float:
    """Return a weighted NAICS + PSC + Jaccard topical similarity in ``[0, 1]``."""

    w = weights if weights is not None else DEFAULT_WEIGHTS

    naics_sim = _code_similarity(prior_award.get("naics_code"), target.get("naics_code"))
    psc_sim = _code_similarity(prior_award.get("psc_code"), target.get("psc_code"))

    prior_tokens = _tokenize(prior_award.get("title")) | _tokenize(prior_award.get("abstract"))
    target_tokens = _tokenize(target.get("description"))
    jaccard = _jaccard(prior_tokens, target_tokens)

    score = (
        w.get("naics", 0.0) * naics_sim
        + w.get("psc", 0.0) * psc_sim
        + w.get("jaccard", 0.0) * jaccard
    )
    # Guard against user-supplied weights that sum > 1.
    return max(0.0, min(score, 1.0))


__all__ = [
    "DEFAULT_WEIGHTS",
    "compute_topical_similarity",
]
