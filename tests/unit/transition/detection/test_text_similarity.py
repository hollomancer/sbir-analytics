"""Tests for the sparse lexical text-similarity core (ported ranker helper)."""

from __future__ import annotations

import numpy as np
import pytest

from sbir_ml.transition.detection.text_similarity import (
    paired_tfidf_cosine,
    tfidf_cosine_matrix,
)


pytestmark = pytest.mark.fast


def test_matrix_prefers_the_on_topic_target():
    queries = ["hypersonic thermal protection ceramic tiles"]
    targets = ["procurement of office chairs", "hypersonic thermal protection ceramic system"]
    sims = tfidf_cosine_matrix(queries, targets)
    assert sims.shape == (1, 2)
    assert sims[0, 1] > sims[0, 0]


def test_matrix_handles_empty_and_stopword_only_corpora():
    assert tfidf_cosine_matrix([], ["anything"]).shape == (0, 1)
    assert tfidf_cosine_matrix(["anything"], []).shape == (1, 0)
    zeros = tfidf_cosine_matrix(["", None], ["something concrete"])  # type: ignore[list-item]
    assert zeros.shape == (2, 1) and not zeros.any()
    stop_only = tfidf_cosine_matrix(["the of and"], ["the of and"])
    assert stop_only.shape == (1, 1) and not stop_only.any()


def test_paired_diagonal_matches_matrix_diagonal():
    queries = ["scramjet combustor liner", "autonomous ground robot"]
    targets = ["scramjet combustor demonstration", "pediatric oncology trial"]
    matrix = tfidf_cosine_matrix(queries, targets)
    paired = paired_tfidf_cosine(queries, targets)
    assert np.allclose(paired, [matrix[0, 0], matrix[1, 1]])
    assert paired[0] > paired[1]


def test_paired_requires_aligned_lengths():
    with pytest.raises(ValueError):
        paired_tfidf_cosine(["a"], ["b", "c"])
    assert paired_tfidf_cosine([], []).shape == (0,)
