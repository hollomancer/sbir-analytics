"""Tests for the load-only fusion-coefficient scorer."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sbir_ml.transition.detection.fusion_model import (
    DEFAULT_COEFFICIENTS_PATH,
    FROZEN_CORPUS_FRAME_HASH,
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


def test_frozen_hash_matches_the_shipped_coefficients():
    """The pinned hash must describe the coefficients that actually ship.

    Without this, `FROZEN_CORPUS_FRAME_HASH` could drift from the file it guards
    and the armed check in `score_pairs_with_fusion` would reject the repo's own
    coefficients — or, worse, a swapped file could be accompanied by an updated
    constant and pass silently.
    """

    shipped = json.loads(DEFAULT_COEFFICIENTS_PATH.read_text(encoding="utf-8"))
    assert shipped["corpus_frame_hash"] == FROZEN_CORPUS_FRAME_HASH


def test_frozen_hash_matches_the_committed_provenance_record():
    """The pin must agree with the only in-repo witness to what was fit.

    The corpus parquet is gitignored (`*.parquet`), so `corpus.manifest.json` is
    the sole committed record of the frame the coefficients were fit on. If the
    coefficients are ever refit, this test fails until the manifest is updated
    too — which is the point: the artifact and its provenance move together or
    not at all.
    """

    repo_root = Path(__file__).resolve().parents[4]
    manifest_path = repo_root / "specs" / "phase3-notice-corpus-fusion" / "corpus.manifest.json"
    assert manifest_path.is_file(), f"provenance record missing: {manifest_path}"

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["frame_hash"] == FROZEN_CORPUS_FRAME_HASH


def test_production_scoring_refuses_coefficients_from_another_corpus(tmp_path):
    """The armed guard must actually reject a swapped coefficient set."""

    from sbir_ml.transition.detection.fusion_scoring import score_pairs_with_fusion

    shipped = json.loads(DEFAULT_COEFFICIENTS_PATH.read_text(encoding="utf-8"))
    impostor = dict(shipped, corpus_frame_hash="0" * 64)
    path = tmp_path / "fusion_coefficients.json"
    path.write_text(json.dumps(impostor), encoding="utf-8")

    with pytest.raises(ValueError, match="different corpus"):
        score_pairs_with_fusion(
            ["autonomous ground robot lidar"],
            ["autonomous ground vehicle lidar integration"],
            ["541715"],
            ["Solicitation"],
            coefficients_path=path,
        )

    # Opting out is possible, but only explicitly.
    scores = score_pairs_with_fusion(
        ["autonomous ground robot lidar"],
        ["autonomous ground vehicle lidar integration"],
        ["541715"],
        ["Solicitation"],
        coefficients_path=path,
        expected_corpus_hash=None,
    )
    assert len(scores) == 1
