"""Unit tests for the pure cores of the eval-validity analyses (2x2 + survival)."""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts" / "phase3_benchmark"))

from text_richness_2x2 import firm_retrieval_auc, normalize_name  # noqa: E402
from transition_survival import kaplan_meier, survival_at  # noqa: E402


def test_normalize_name_strips_suffixes():
    assert normalize_name("Acme Technologies, Inc.") == "ACME"


def test_retrieval_auc_perfect_when_query_matches_own_target():
    # each firm's query is lexically identical to its own target and disjoint from others -> AUC 1.0
    queries = [f"alpha beta widget {i} unique{i}" for i in range(6)]
    targets = [f"alpha beta widget {i} unique{i}" for i in range(6)]
    auc, top1 = firm_retrieval_auc(queries, targets, n_neg=5)
    assert auc == 1.0 and top1 == 1.0


def test_kaplan_meier_all_events_no_censoring():
    # 4 firms, events at t=1,2,3,4 -> S drops 1/n each step, reaches 0
    lag = np.array([1, 2, 3, 4])
    is_event = np.array([True, True, True, True])
    curve = kaplan_meier(lag, is_event)
    assert curve[1] == 0.75 and abs(curve[4]) < 1e-9


def test_kaplan_meier_censoring_keeps_survival_above_zero():
    # only 1 of 4 experiences the event (at t=2); the rest are censored later -> S never reaches 0
    lag = np.array([2, 5, 6, 7])
    is_event = np.array([True, False, False, False])
    curve = kaplan_meier(lag, is_event)
    assert curve[2] == 0.75
    assert survival_at(curve, 7) == 0.75  # censored firms never pull survival below the single event


def test_survival_at_uses_last_known_step():
    curve = {0: 1.0, 2: 0.75, 5: 0.5}
    assert survival_at(curve, 4) == 0.75 and survival_at(curve, 10) == 0.5
