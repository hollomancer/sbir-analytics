"""Unit tests for the pure cores of the eval-validity analyses (2x2 + survival + length curve)."""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts" / "phase3_benchmark"))

from auc_by_target_length import auc_by_length_decile, per_firm_auc  # noqa: E402
from dod_transition_inventory import target_text_coverage  # noqa: E402
from dod_within_retrieval import build_asof_pairs, floor_coverage, within_dod_auc  # noqa: E402
from retrieval_metrics import tie_corrected_auc  # noqa: E402
from text_richness_2x2 import (
    _asof_texts,
    _is_sbir,
    firm_retrieval_auc,  # noqa: E402
    longest_shared_word_run,
    metadata_hard_negatives,
    normalize_name,
    paired_bootstrap,
    random_negatives,
)
from transition_survival import build_cohort_frames, kaplan_meier, survival_at  # noqa: E402


def test_normalize_name_strips_suffixes():
    assert normalize_name("Acme Technologies, Inc.") == "ACME"


def test_nasa_textual_phase_is_not_admitted_as_transition_target():
    assert _is_sbir({"phase": "Phase II"})
    assert _is_sbir({"phase": "Phase III"})


def test_nasa_asof_comparison_uses_full_date_not_calendar_year():
    phase2 = pd.DataFrame(
        [
            {
                "UEI": "U1",
                "_award_date": pd.Timestamp("2020-01-01", tz="UTC"),
                "Abstract": "eligible",
            },
            {
                "UEI": "U1",
                "_award_date": pd.Timestamp("2020-12-01", tz="UTC"),
                "Abstract": "future same year",
            },
        ]
    )
    targets = {"U1": {"target_date": pd.Timestamp("2020-06-01", tz="UTC")}}
    assert _asof_texts(phase2, targets, "Abstract", 100)["U1"] == "eligible"


def test_retrieval_auc_perfect_when_query_matches_own_target():
    queries = [f"alpha beta widget {i} unique{i}" for i in range(6)]
    targets = [f"alpha beta widget {i} unique{i}" for i in range(6)]
    auc, top1 = firm_retrieval_auc(queries, targets, random_negatives(6, 5))
    assert auc == 1.0 and top1 == 1.0


def test_retrieval_auc_assigns_half_credit_to_ties():
    queries = ["same text"] * 4
    targets = ["same text"] * 4
    auc, _ = firm_retrieval_auc(queries, targets, random_negatives(4, 3))
    assert auc == 0.5
    assert tie_corrected_auc(0.2, np.array([0.1, 0.2, 0.3])) == 0.5
    expected = roc_auc_score([1, 0, 0, 0], [0.2, 0.1, 0.2, 0.3])
    assert tie_corrected_auc(0.2, np.array([0.1, 0.2, 0.3])) == expected


def test_random_negatives_exclude_self_and_are_fixed_by_seed():
    a = random_negatives(10, 4, seed=1)
    b = random_negatives(10, 4, seed=1)
    assert all(i not in a[i] for i in a)  # never picks self
    assert all(
        np.array_equal(a[i], b[i]) for i in a
    )  # same seed -> identical set (stable across cells)


def test_metadata_hard_negatives_prefer_same_tx_area():
    # firm 0 shares TX area 'TXA' with 1,2,3 (and same year); firm 4 is a different area 'TXB'
    years = np.array([2020, 2020, 2021, 2019, 2020])
    tx = np.array(["TXA", "TXA", "TXA", "TXA", "TXB"])
    negs, hard = metadata_hard_negatives(years, tx, n_neg=3, min_pool=3)
    assert 4 not in negs[0]  # the off-area firm is excluded from firm 0's pool
    assert hard >= 1


def test_metadata_hard_negatives_fall_back_to_random_when_pool_tiny():
    years = np.array([2020, 2020, 2020])
    tx = np.array(["TXA", "TXB", "TXC"])  # no firm shares an area -> fallback
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


def test_longest_shared_word_run_detects_copied_span():
    a = "the quick brown fox jumps over the lazy dog near the river bank"
    copied = "unrelated intro the quick brown fox jumps over the lazy dog trailing"
    disjoint = "completely different words with nothing at all in common here today"
    assert longest_shared_word_run(a, copied) >= 8  # 8-word copied run detected
    assert longest_shared_word_run(a, disjoint) <= 2  # no meaningful shared run


def test_paired_bootstrap_ci_brackets_mean_and_zero_for_null_effect():
    per_firm = np.array([0.01, -0.01, 0.02, -0.02, 0.0, 0.005, -0.005])  # centered near 0
    mean, lo, hi = paired_bootstrap(per_firm, n_boot=500)
    assert lo <= mean <= hi and lo < 0 < hi  # CI straddles 0 for a null effect


def test_floor_coverage_thresholds():
    lengths = np.array([40, 100, 200, 600, 1000])
    cov = floor_coverage(lengths, (150, 900))
    assert cov[150] == 60.0 and cov[900] == 20.0


def test_dod_pairs_are_asof_and_keep_same_target_row_metadata():
    awards = pd.DataFrame(
        [
            {
                "UEI": "UEI000001",
                "Agency": "Department of Defense",
                "Phase": "Phase II",
                "Proposal Award Date": "2020-01-01",
                "Solicitation Year": "2020",
                "Abstract": "eligible prior abstract",
            },
            {
                "UEI": "UEI000001",
                "Agency": "Department of Defense",
                "Phase": "Phase II",
                "Proposal Award Date": "2023-01-01",
                "Solicitation Year": "2023",
                "Abstract": "future leaked abstract",
            },
        ]
    )
    coded = pd.DataFrame(
        [
            {
                "uei": "UEI000001",
                "signed": "2021-10-01",
                "fy": "2022",
                "desc": "short target",
                "psc": "A111",
                "contract_award_unique_key": "K1",
            },
            {
                "uei": "UEI000001",
                "signed": "2022-05-01",
                "fy": "2022",
                "desc": "a much longer target row",
                "psc": "B222",
                "contract_award_unique_key": "K2",
            },
        ]
    )
    pairs = build_asof_pairs(awards, coded)
    assert list(pairs["query"]) == ["eligible prior abstract", "eligible prior abstract"]
    assert list(pairs["target_key"]) == ["K1", "K2"]
    assert list(pairs["psc"]) == ["A111", "B222"]
    assert list(pairs["fy"]) == [2022, 2022]
    assert len(pairs) == 2


def test_dod_auc_excludes_targets_without_hard_pool_instead_of_random_fallback():
    pairs = pd.DataFrame(
        [
            {
                "uei": f"U{i}",
                "query": f"query {i}",
                "description": f"target {i}",
                "fy": 2020,
                "psc": f"P{i}",
            }
            for i in range(4)
        ]
    )
    result = within_dod_auc(pairs, min_pool=2)
    assert result["evaluated_targets"] == 0
    assert result["negative_tier_counts"]["excluded"] == 4


def test_target_text_coverage_flags_empty_descriptions():
    lengths = np.array([40, 42, 30, 200, 500])  # 3 of 5 below the 150 floor
    cov = target_text_coverage(lengths, floor=150)
    assert cov["n"] == 5 and cov["pct_below_floor"] == 60.0 and cov["pct_usable"] == 40.0


def test_kaplan_meier_all_events_no_censoring():
    curve = kaplan_meier(np.array([1, 2, 3, 4]), np.array([True, True, True, True]))
    assert curve[1] == 0.75 and abs(curve[4]) < 1e-9


def test_kaplan_meier_censoring_keeps_survival_above_zero():
    curve = kaplan_meier(np.array([2, 5, 6, 7]), np.array([True, False, False, False]))
    assert curve[2] == 0.75 and survival_at(curve, 7) == 0.75


def test_survival_at_uses_last_known_step():
    curve = {0: 1.0, 2: 0.75, 5: 0.5}
    assert survival_at(curve, 4) == 0.75 and survival_at(curve, 10) == 0.5


def test_survival_uses_phase_ii_and_first_valid_post_entry_action():
    awards = pd.DataFrame(
        [
            {
                "UEI": "UEI000001",
                "Agency": "Department of Defense",
                "Phase": "Phase I",
                "Proposal Award Date": "2017-01-01",
                "Solicitation Year": "2017",
            },
            {
                "UEI": "UEI000001",
                "Agency": "Department of Defense",
                "Phase": "Phase II",
                "Proposal Award Date": "2020-01-01",
                "Solicitation Year": "2020",
            },
        ]
    )
    coded = pd.DataFrame(
        [
            {"uei": "UEI000001", "signed": "2019-01-01"},
            {"uei": "UEI000001", "signed": "2022-01-01"},
        ]
    )
    cohort = build_cohort_frames(awards, coded)
    assert cohort.loc["UEI000001", "entry"] == 2020
    assert cohort.loc["UEI000001", "event_yr"] == 2022
    assert cohort.loc["UEI000001", "lag"] == 2
