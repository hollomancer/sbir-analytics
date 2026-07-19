"""Unit tests for the pure cores of the structure-stratified capture model (vehicle_mse)."""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts" / "phase3_benchmark"))

from vehicle_mse import (CELL_ORDER, block_bootstrap_ci, build_units, chapman,  # noqa: E402
                         coded_key, described_key, loglinear_dark, stratified_dark)


def test_described_key_parses_award_and_parent():
    assert described_key("CONT_AWD_W123_9700_FA1_9700") == ("W123", "FA1")
    assert described_key("CONT_AWD_W123_9700_-NONE-_-NONE-") == ("W123", "NONE")
    assert described_key("garbage") is None


def test_coded_key_standalone_marks_none_parent():
    assert coded_key("W1", "None") == ("W1", "NONE")
    assert coded_key("W1", "FA-1") == ("W1", "FA1")


def test_build_units_respects_structural_zero():
    a = {("O1", "NONE"), ("O2", "V1")}
    b = {("O1", "NONE")}
    c = {("O2", "V1"), ("O3", "V1")}
    units = build_units(a, b, c)
    stand = units[units["standalone"]]
    assert not stand["c"].any()                      # standalone can never be C-captured
    assert len(units) == 3


def test_chapman_matches_known_value():
    # classic LP example: n1=6351, n2=962, m=821 -> Chapman ~7441
    assert abs(chapman(6351, 962, 821) - 7441) < 1


def test_loglinear_recovers_exact_independence_cells():
    # construct exact expected cells from an independence model with known n000
    pa, pb, pc, N = 0.5, 0.2, 0.1, 10000
    cells = []
    for p in CELL_ORDER:
        prob = (pa if p[0] else 1 - pa) * (pb if p[1] else 1 - pb) * (pc if p[2] else 1 - pc)
        cells.append(N * prob)
    fitted = loglinear_dark(np.array(cells), [])
    expected_000 = N * (1 - pa) * (1 - pb) * (1 - pc)
    assert abs(fitted["n000"] - expected_000) / expected_000 < 0.01


def test_stratified_dark_sums_both_strata():
    rng = np.random.RandomState(3)
    rows = []
    # standalone: independent AB, capture 0.6 / 0.3, N=1000 -> ~120 truly dark (unobserved)
    for _ in range(1000):
        a, b = rng.rand() < 0.6, rng.rand() < 0.3
        if a or b:
            rows.append({"parent": "NONE", "a": a, "b": b, "c": False, "standalone": True})
    # task orders: independent ABC on 50 vehicles
    for v in range(50):
        for _ in range(20):
            a, b, c = rng.rand() < 0.6, rng.rand() < 0.3, rng.rand() < 0.4
            if a or b or c:
                rows.append({"parent": f"V{v}", "a": a, "b": b, "c": c, "standalone": False})
    units = pd.DataFrame(rows)
    fitted = stratified_dark(units, [])
    true_dark = 1000 * 0.4 * 0.7 + 1000 * 0.4 * 0.7 * 0.6   # unobserved in each stratum
    assert abs(fitted["dark_total"] - true_dark) / true_dark < 0.30  # loose: sampling noise
    lo, hi = block_bootstrap_ci(units, [], n_boot=60)
    assert lo < fitted["dark_total"] < hi
