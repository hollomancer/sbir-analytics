"""Topical-similarity helper for Phase III candidate scoring.

Computes a single float in ``[0, 1]`` from a (prior_award, target) pair using
three cheap v1 features:

- NAICS code agreement (single-code exact match on 6-digit NAICS, credited
  even when only one side carries a value on the basis that NAICS-less
  targets tend to be miscoded rather than mismatched; see design §4 tests).
- PSC code agreement (same, for product/service codes).
- Jaccard token overlap on the union of title and abstract (prior) vs.
  the target description (contracts or opportunities).

The asset factory feeds the resulting float into the existing
``TransitionScorer.score_text_similarity`` — the weight lives on the scorer,
not here. No new scorer method is introduced for this signal.

Defaults reflect the feature contributions and are illustrative:
NAICS: 0.30, PSC: 0.20, Jaccard: 0.50. They sum to 1.0 so the returned score
stays in ``[0, 1]`` when each input is already in ``[0, 1]``.
"""

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
    """1.0 on exact match, 0.0 on explicit mismatch, 0.0 when both missing.

    A one-sided missing code returns 0.0 — conservative; the Jaccard channel
    still contributes when codes are absent.
    """

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
    """Compute a topical-similarity float in ``[0, 1]``.

    Args:
        prior_award: Prior award dict with optional keys
            ``naics_code``, ``psc_code``, ``title``, ``abstract``.
        target: Target dict (contract or opportunity) with optional keys
            ``naics_code``, ``psc_code``, ``description``.
        weights: Optional override of the per-feature weights. Must have keys
            ``naics``, ``psc``, ``jaccard`` and sum to 1.0.

    Returns:
        Similarity score in ``[0, 1]``.
    """

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
