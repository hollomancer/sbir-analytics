"""Tests for frozen-fusion candidate scoring."""

from __future__ import annotations

import pytest

from sbir_ml.transition.detection.fusion_scoring import score_pairs_with_fusion


pytestmark = pytest.mark.fast


def test_on_topic_pair_outscores_off_topic():
    awards = [
        "autonomous ground robot obstacle mapping with electro-optical and lidar sensing",
        "autonomous ground robot obstacle mapping with electro-optical and lidar sensing",
    ]
    targets = [
        "integration of autonomous ground vehicles that map obstacles and fuse lidar",
        "janitorial services and office furniture procurement for a federal building",
    ]
    scores = score_pairs_with_fusion(
        awards, targets, ["541715", "561720"], ["Solicitation", "Award Notice"]
    )
    assert len(scores) == 2
    assert all(0.0 <= s <= 1.0 for s in scores)
    assert scores[0] > scores[1]  # topical match ranks above the unrelated notice


def test_ranks_a_firms_candidates_by_technical_overlap():
    award = "hypersonic scramjet thermal protection ceramic matrix composite liner"
    targets = [
        "supply of office chairs",
        "hypersonic propulsion thermal protection demonstration using ceramic composites",
        "routine grounds maintenance",
    ]
    scores = score_pairs_with_fusion([award] * 3, targets, ["541715"] * 3, ["Solicitation"] * 3)
    assert scores[1] == max(scores)  # the on-topic hypersonic notice ranks first


def test_empty_and_mismatched_inputs():
    assert score_pairs_with_fusion([], [], [], []) == []
    with pytest.raises(ValueError, match="same length"):
        score_pairs_with_fusion(["a"], ["b", "c"], ["1"], ["Solicitation"])
