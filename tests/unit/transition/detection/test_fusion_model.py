"""Tests for the load-only fusion-coefficient scorer."""

from __future__ import annotations

import json

import pytest

from sbir_ml.transition.detection.fusion_model import (
    DEFAULT_COEFFICIENTS_PATH,
    FusionCoefficients,
    load_fusion_coefficients,
)


pytestmark = pytest.mark.fast


def test_frozen_coefficients_load_and_expose_the_corpus_hash():
    coefficients = load_fusion_coefficients()
    assert coefficients.feature_order[0] == "tfidf_word"
    assert len(coefficients.coefficients) == len(coefficients.feature_order)
    assert len(coefficients.scaler_mean) == len(coefficients.feature_order)
    assert coefficients.corpus_frame_hash  # non-empty provenance hash


def test_hash_mismatch_is_refused():
    with pytest.raises(ValueError, match="different corpus"):
        load_fusion_coefficients(expected_corpus_hash="not-the-frozen-hash")


def test_matching_hash_is_accepted():
    embedded = json.loads(DEFAULT_COEFFICIENTS_PATH.read_text())["corpus_frame_hash"]
    coefficients = load_fusion_coefficients(expected_corpus_hash=embedded)
    assert coefficients.corpus_frame_hash == embedded


def test_score_is_a_probability_and_monotone_in_text_similarity():
    model = load_fusion_coefficients()
    n = len(model.feature_order)

    def vec(word_sim: float) -> list[float]:
        v = [0.0] * n
        v[0] = word_sim  # tfidf_word is feature 0
        return v

    low, high = model.score(vec(0.0)), model.score(vec(0.8))
    assert 0.0 <= low <= 1.0 and 0.0 <= high <= 1.0
    # tfidf_word carries a positive weight, so more text overlap scores higher.
    assert high > low


def test_wrong_feature_count_is_rejected():
    model = load_fusion_coefficients()
    with pytest.raises(ValueError, match="expected"):
        model.score([0.1, 0.2])


def test_score_handles_zero_variance_feature_without_dividing_by_zero():
    coefficients = FusionCoefficients(
        feature_order=("a", "b"),
        coefficients=(1.0, 1.0),
        intercept=0.0,
        scaler_mean=(0.0, 5.0),
        scaler_scale=(1.0, 0.0),  # b has zero variance
        corpus_frame_hash="x",
    )
    assert 0.0 <= coefficients.score([2.0, 5.0]) <= 1.0
