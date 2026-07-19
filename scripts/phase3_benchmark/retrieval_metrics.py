"""Shared retrieval metrics for the research-only Phase III benchmark."""

from __future__ import annotations

import numpy as np


def tie_corrected_auc(positive_score: float, negative_scores: np.ndarray) -> float:
    """Return the Mann-Whitney win probability, assigning score ties one half."""
    negatives = np.asarray(negative_scores, dtype=float)
    if negatives.size == 0:
        raise ValueError("retrieval AUC requires at least one negative score")
    wins = np.greater(positive_score, negatives).astype(float)
    ties = np.equal(positive_score, negatives).astype(float)
    return float((wins + 0.5 * ties).mean())


def tie_rate(positive_score: float, negative_scores: np.ndarray) -> float:
    """Return the share of pairwise comparisons tied with the positive score."""
    negatives = np.asarray(negative_scores, dtype=float)
    if negatives.size == 0:
        raise ValueError("tie rate requires at least one negative score")
    return float(np.equal(positive_score, negatives).mean())


__all__ = ["tie_corrected_auc", "tie_rate"]
