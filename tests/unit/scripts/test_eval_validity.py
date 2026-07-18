"""Unit tests for the pure cores of the eval-validity analyses (2x2 + survival + length curve)."""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts" / "phase3_benchmark"))

from auc_by_target_length import auc_by_length_decile, per_firm_auc  # noqa: E402
from text_richness_2x2 import (firm_retrieval_auc, metadata_hard_negatives,  # noqa: E402
                               normalize_name, random_negatives)
from transition_survival import kaplan_meier, survival_at  # noqa: E402


def test_normalize_name_strips_suffixes():
    assert normalize_name("Acme Technologies, Inc.") == "ACME"


def test_retrieval_auc_perfect_when_query_matches_own_target():
    queries = [f"alpha beta widget {i} unique{i}" for i in range(6)]
    targets = [f"alpha beta widget {i} unique{i}" for i in range(6)]
    auc, top1 = firm_retrieval_auc(queries, targets, random_negatives(6, 5))
    assert auc == 1.0 and top1 == 1.0


def test_random_negatives_exclude_self_and_are_fixed_by_seed():
    a = random_negatives(10, 4, seed=1)
    b = random_negatives(10, 4, seed=1)
    assert all(i not in a[i] for i in a)                      # never picks self
    assert all(np.array_equal(a[i], b[i]) for i in a)         # same seed -> identical set (stable across cells)


def test_metadata_hard_negatives_prefer_same_tx_area():
    # firm 0 shares TX area 'TXA' with 1,2,3 (and same year); firm 4 is a different area 'TXB'
    years = np.array([2020, 2020, 2021, 2019, 2020])
    tx = np.array(["TXA", "TXA", "TXA", "TXA", "TXB"])
    negs, hard = metadata_hard_negatives(years, tx, n_neg=3, min_pool=3)
    assert 4 not in negs[0]                                   # the off-area firm is excluded from firm 0's pool
    assert hard >= 1


def test_metadata_hard_negatives_fall_back_to_random_when_pool_tiny():
    years = np.array([2020, 2020, 2020])
    tx = np.array(["TXA", "TXB", "TXC"])                      # no firm shares an area -> fallback
    negs, hard = metadata_hard_negatives(years, tx, n_neg=2, min_pool=2)
    assert hard == 0 and all(len(negs[i]) == 2 for i in negs)


def test_auc_by_length_decile_orders_and_covers():
    aucs = np.array([0.6, 0.7, 0.8, 0.9])
    lengths = np.array([100, 200, 300, 400])
    rows = auc_by_length_decile(aucs, lengths, n_bins=2)
    assert len(rows) == 2 and rows[0]["len_lo"] == 100 and rows[-1]["len_hi"] == 400
    assert sum(r["n"] for r in rows) == 4


def test_per_firm_auc_returns_one_score_per_firm():
    q = [f"widget {i} zzz{i}" for i in range(5)]
    t = [f"widget {i} zzz{i}" for i in range(5)]
    scores = per_firm_auc(q, t, random_negatives(5, 4))
    assert scores.shape == (5,) and scores.max() <= 1.0


def test_kaplan_meier_all_events_no_censoring():
    curve = kaplan_meier(np.array([1, 2, 3, 4]), np.array([True, True, True, True]))
    assert curve[1] == 0.75 and abs(curve[4]) < 1e-9


def test_kaplan_meier_censoring_keeps_survival_above_zero():
    curve = kaplan_meier(np.array([2, 5, 6, 7]), np.array([True, False, False, False]))
    assert curve[2] == 0.75 and survival_at(curve, 7) == 0.75


def test_survival_at_uses_last_known_step():
    curve = {0: 1.0, 2: 0.75, 5: 0.5}
    assert survival_at(curve, 4) == 0.75 and survival_at(curve, 10) == 0.5
