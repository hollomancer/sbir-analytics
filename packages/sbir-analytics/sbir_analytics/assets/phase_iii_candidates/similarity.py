"""Topical-similarity helper (NAICS + PSC code agreement + TF-IDF text cosine) for Phase III candidate scoring.

The text component is corpus-fitted word (1,2)-gram TF-IDF cosine
(`sbir_ml.transition.detection.text_similarity`), which beat token Jaccard on
the frozen Phase III benchmark's rich-text subset (AUC 0.710 vs 0.644-0.651)
while sitting on the same score scale (pos p90 = 0.028 for both), so the HIGH
thresholds are unchanged. See
docs/superpowers/specs/2026-07-30-why-it-connects-explanation-design.md.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from sbir_ml.transition.detection.text_similarity import paired_tfidf_cosine


DEFAULT_WEIGHTS: dict[str, float] = {
    "naics": 0.30,
    "psc": 0.20,
    "text": 0.50,
}


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


def _text(value: Any) -> str:
    if value is None:
        return ""
    try:
        if bool(pd.isna(value)):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value)


def _query_text(prior_award: dict[str, Any]) -> str:
    return " ".join(
        part
        for part in (_text(prior_award.get("title")), _text(prior_award.get("abstract")))
        if part
    )


def _combine(
    prior_award: dict[str, Any],
    target: dict[str, Any],
    text_similarity: float,
    weights: dict[str, float],
) -> float:
    naics_sim = _code_similarity(prior_award.get("naics_code"), target.get("naics_code"))
    psc_sim = _code_similarity(prior_award.get("psc_code"), target.get("psc_code"))
    score = (
        weights.get("naics", 0.0) * naics_sim
        + weights.get("psc", 0.0) * psc_sim
        + weights.get("text", 0.0) * text_similarity
    )
    # Guard against user-supplied weights that sum > 1.
    return max(0.0, min(score, 1.0))


def compute_text_similarity_batch(pairs: pd.DataFrame) -> list[float]:
    """Row-aligned TF-IDF text similarity for a pre-filtered pair frame.

    The vectorizer is fitted over every prior-award text and target description
    in the frame, so idf reflects the run's corpus — score all rows of a run in
    one call rather than pair-by-pair.
    """

    if pairs.empty:
        return []
    queries = [
        _query_text({"title": row.get("prior_title"), "abstract": row.get("prior_abstract")})
        for _, row in pairs.iterrows()
    ]
    targets = [_text(row.get("target_description")) for _, row in pairs.iterrows()]
    return [float(value) for value in paired_tfidf_cosine(queries, targets)]


def compute_topical_similarity(
    prior_award: dict[str, Any],
    target: dict[str, Any],
    *,
    weights: dict[str, float] | None = None,
    text_similarity: float | None = None,
) -> float:
    """Return a weighted NAICS + PSC + text topical similarity in ``[0, 1]``.

    Pass ``text_similarity`` when it was already computed corpus-fitted (the
    batch path). Without it, the TF-IDF fit degenerates to the two texts —
    fine for a single pair; batch scoring should use
    :func:`compute_text_similarity_batch` and pass the values through.
    """

    w = weights if weights is not None else DEFAULT_WEIGHTS
    if text_similarity is None:
        sims = paired_tfidf_cosine([_query_text(prior_award)], [_text(target.get("description"))])
        text_similarity = float(sims[0]) if len(sims) else 0.0
    return _combine(prior_award, target, text_similarity, w)


__all__ = [
    "DEFAULT_WEIGHTS",
    "compute_text_similarity_batch",
    "compute_topical_similarity",
]
