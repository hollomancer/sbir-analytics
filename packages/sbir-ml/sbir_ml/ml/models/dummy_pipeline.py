# sbir-analytics/src/ml/models/dummy_pipeline.py
"""
DummyPipeline

A lightweight, pickleable, deterministic "pipeline" used to create synthetic
model artifacts for tests. The real production pipelines are sklearn-based and
complex; for unit/CI tests we only need a reproducible object that implements
the subset of sklearn's interface relied upon by `ApplicabilityModel`:

- .fit(X, y) -> trains the dummy pipeline (no-op but stores fitted flag)
- .predict_proba(texts: List[str]) -> ndarray shape (n_samples, 2) with
  probabilities for [neg_class, pos_class]

Design goals:
- Deterministic scoring based on simple keyword matching (case-insensitive).
- Lightweight and pickle-friendly for bundling into model artifacts used in CI.
- No optional heavy dependencies (pure Python + numpy + re).
"""

import re
from re import Pattern

import numpy as np


class DummyPipeline:
    """
    Dummy binary classifier pipeline for a single CET area.

    Parameters
    ----------
    cet_id : str
        Identifier for the CET area this pipeline represents (for debugging).
    keywords : Optional[List[str]]
        List of keywords indicative of the CET; matching keywords increase
        the positive-class probability.
    keyword_boost : float
        Multiplier applied per matching keyword (used to shape the score).
        Typical test value 1.0 yields fractional scores in [0, 1].
    max_score : float
        Maximum probability to return for positive class (in [0, 1]). Use <1.0
        to simulate imperfect confidence.

    Methods
    -------
    fit(X, y)
        No-op that marks the pipeline as fitted.
    predict_proba(texts)
        Returns np.ndarray of shape (n_samples, 2) with probabilities for
        negative (col 0) and positive (col 1) classes.
    """

    def __init__(
        self,
        cet_id: str,
        keywords: list[str] | None = None,
        keyword_boost: float = 1.0,
        max_score: float = 0.95,
    ) -> None:
        self.cet_id = cet_id
        self.keywords = keywords or []
        # compile regex patterns for deterministic matching (word boundaries)
        self._keyword_patterns: list[Pattern] = [
            re.compile(rf"\b{re.escape(k.lower())}\b") for k in self.keywords if k
        ]
        self.keyword_boost = float(keyword_boost)
        self.max_score = float(max_score)
        self.is_fitted = False

    def fit(self, X: list[str], y) -> "DummyPipeline":
        """
        Fit the dummy pipeline. This is intentionally lightweight: it simply
        records that the pipeline was 'fitted' so tests can assert fitted state.

        Parameters
        ----------
        X : List[str]
            Training texts (ignored).
        y : array-like
            Training labels (ignored).
        """
        self.is_fitted = True
        return self

    def _score_text(self, text: str) -> float:
        """
        Deterministic scoring function based on number of keyword matches.

        Score calculation:
          - Lowercase the text for case-insensitive matching.
          - Count matches for each compiled keyword regex.
          - Raw score = sum(matches) * keyword_boost
          - Normalized score = raw_score / (1 + number_of_keywords)
          - Final probability = min(max_score, normalized_score)

        This yields numbers in [0, max_score] and is stable across runs.
        """
        if not self._keyword_patterns:
            # No keywords defined — always return 0.0 to indicate no match
            return 0.0

        text_lower = (text or "").lower()
        raw_matches = 0
        for pat in self._keyword_patterns:
            # count non-overlapping occurrences
            found = pat.findall(text_lower)
            raw_matches += len(found)

        denom = 1 + len(self._keyword_patterns)
        normalized = (raw_matches * self.keyword_boost) / denom
        prob = float(min(self.max_score, normalized))
        # ensure numeric stability and bounds
        prob = max(0.0, min(1.0, prob))
        return prob

    def predict_proba(self, texts: list[str]) -> np.ndarray:
        """
        Predict probabilities for the positive class for each input text.

        Returns an (n_samples, 2) numpy array where column 0 is P(neg) and
        column 1 is P(pos). P(neg) = 1 - P(pos).

        Parameters
        ----------
        texts : List[str]
            Input documents to score.
        """
        probs = []
        for t in texts:
            p_pos = self._score_text(t)
            p_neg = 1.0 - p_pos
            probs.append((p_neg, p_pos))
        return np.array(probs, dtype=float)

    def __repr__(self) -> str:
        return f"DummyPipeline(cet_id={self.cet_id!r}, keywords={len(self.keywords)} keywords, fitted={self.is_fitted})"
