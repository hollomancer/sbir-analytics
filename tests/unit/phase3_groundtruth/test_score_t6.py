"""Tests for the T6 triangulated scoring harness."""

import pytest

from scripts.phase3_groundtruth.score_t6 import (
    UniverseContract,
    aggregate,
    competition_rank,
    is_substantive,
    sample_decoys,
    score_candidates,
)
from sbir_ml.transition.detection.fusion_model import load_fusion_coefficients

pytestmark = pytest.mark.fast


def _contract(award_id: str, desc: str, agency: str, uei: str = "") -> UniverseContract:
    return UniverseContract(
        award_id=award_id,
        key=award_id,
        recipient_name="DECOY CORP " + award_id,
        recipient_uei=uei or ("U" + award_id),
        description=desc,
        naics="541710",
        award_type="DEFINITIVE CONTRACT",
        awarding_sub_agency=agency,
        funding_sub_agency=agency,
    )


def test_frozen_model_feature_vector_is_length_six():
    """The scorer must faithfully build the 6-feature fusion vector."""
    model = load_fusion_coefficients()
    assert len(model.feature_order) == 6
    assert model.feature_order == (
        "tfidf_word",
        "tfidf_char",
        "after_first",
        "id_cited",
        "naics_len",
        "notice_type",
    )
    # score() raises unless handed exactly six features -> proves the vector length.
    with pytest.raises(ValueError):
        model.score([0.0, 0.0, 1.0])
    assert 0.0 <= model.score([0.1, 0.2, 1.0, 0.0, 6.0, 1.0]) <= 1.0


def test_precision_at_1_from_known_ranking():
    """Two firms whose true contract is the clear text match rank first -> p@1 = 1.0."""
    firm_a_query = "cryogenic superconducting magnet coil for missile defense radar"
    firm_a_true = "high-field superconducting magnet coil assembly for radar systems"
    firm_b_query = "autonomous underwater vehicle sonar mine countermeasure navigation"
    firm_b_true = "autonomous underwater vehicle sonar payload for mine countermeasures"
    decoy_text = "administrative office furniture and janitorial supply services contract"

    ranks = []
    for query, true_text in ((firm_a_query, firm_a_true), (firm_b_query, firm_b_true)):
        targets = [true_text, decoy_text, decoy_text + " east region"]
        scores = score_candidates(query, targets, ["541710"] * 3, "Acme Corp")
        ranks.append(competition_rank(scores[0], scores[1:]))

    assert ranks == [1, 1]
    stats = aggregate(ranks)
    assert stats["p1"] == 1.0
    assert stats["mrr"] == 1.0


def test_competition_rank_is_strict_on_ties():
    assert competition_rank(0.5, [0.4, 0.3]) == 1
    assert competition_rank(0.5, [0.6, 0.3]) == 2
    # a tie at the top does not credit the true item
    assert competition_rank(0.5, [0.5, 0.6]) == 2


def test_is_substantive_rejects_boilerplate_and_short():
    assert not is_substantive("SBIR PHASE III AWARD.")
    assert not is_substantive("x" * 200 and "SBIR PHASE III")
    assert not is_substantive("short text")
    assert is_substantive("A" + " genuine engineering scope of work " * 4)


def test_sample_decoys_prefers_same_agency_then_backfills():
    true = _contract("TRUE1", "real scope of work " * 10, "Missile Defense Agency")
    same = [
        _contract(f"S{i}", "same agency scope " * 10, "Missile Defense Agency") for i in range(6)
    ]
    other = [
        _contract(f"O{i}", "other agency scope " * 10, "Defense Logistics Agency")
        for i in range(20)
    ]
    import random

    decoys = sample_decoys(same + other, true, "FIRM KEY", minimum=80, rng=random.Random(1))
    assert len(decoys) == 9
    assert true.key not in {d.key for d in decoys}
    # all 6 same-agency decoys are used, remainder backfilled from other agencies
    assert sum(1 for d in decoys if d.awarding_sub_agency == "Missile Defense Agency") == 6
