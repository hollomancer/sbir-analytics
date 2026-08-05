"""Fixture tests for the transition-ranker scoring core (self-contained, no external data)."""

from __future__ import annotations

import numpy as np

from scripts.phase3_benchmark.transition_ranker import (
    award_similarity,
    evaluate,
    id_xref,
    notice_type_ordinal,
    temporal_features,
)


def test_temporal_floor_is_first_award_and_gap_is_unbounded() -> None:
    # Phase I in 2005; a 2020 notice is 15y later — after_first holds and the long gap is NOT capped.
    feats = temporal_features(2020, firm_award_years=[2005, 2008])
    assert feats["after_first"] == 1.0
    assert feats["gap"] == 12.0  # 2020 - max(2005, 2008)
    # A notice predating the firm's earliest award cannot be a transition.
    assert temporal_features(2003, [2005, 2008])["after_first"] == 0.0
    # Unknown year -> neutral.
    assert temporal_features(None, [2005])["after_first"] == 0.5


def test_id_xref_matches_firm_identifier_in_notice() -> None:
    ids = {"N0001420C0055", "AF151020"}
    assert id_xref("...award under contract N00014-20-C-0055 for...", ids) == 1.0
    assert id_xref("unrelated sources sought notice", ids) == 0.0
    assert id_xref("mentions AF15", {"AF15"}) == 0.0  # too short (<6) is ignored


def test_notice_type_ordinal_ranks_jna_above_award_notice() -> None:
    assert notice_type_ordinal("Justification and Approval (J&A)") == 3.0
    assert notice_type_ordinal("Award Notice") == 1.0
    assert notice_type_ordinal("Widget") == 0.0


def test_award_similarity_prefers_the_matching_notice() -> None:
    queries = ["hypersonic thermal protection ceramic tiles"]
    notices = ["procurement of office chairs", "hypersonic thermal protection ceramic system"]
    sims = award_similarity(queries, notices)
    assert sims.shape == (1, 2)
    assert sims[0, 1] > sims[0, 0]  # the on-topic notice scores higher


def _candidate_sets(n_firms: int, separable: bool, rng: np.random.Generator):
    """One true + 5 negatives per firm; if separable, the true row carries a high signal feature."""
    feats, labels, groups, owners = [], [], [], []
    for firm in range(n_firms):
        for k in range(6):
            is_true = k == 0
            signal = (1.0 if is_true else 0.0) if separable else rng.random()
            feats.append([signal, rng.random()])
            labels.append(1 if is_true else 0)
            groups.append(f"UEI{firm}")
            owners.append(firm)
    return (np.array(feats), np.array(labels), np.array(groups), np.array(owners))


def test_evaluate_separates_true_from_negatives_and_is_grouped_by_firm() -> None:
    rng = np.random.default_rng(0)
    strong = evaluate(*_candidate_sets(12, separable=True, rng=rng))
    assert strong["firms"] == 12
    assert strong["auc"] >= 0.95 and strong["top1"] >= 0.9

    noise = evaluate(*_candidate_sets(24, separable=False, rng=rng))
    assert noise["auc"] < strong["auc"] - 0.3  # noise is far from the separable signal (~chance)
