"""Unit tests for the tech-area figures audit diff logic.

The full audit needs a data-bearing cohort CSV (gitignored), so here we test the
pure ``verify_composition`` diff against synthetic composition dicts: exact match,
tolerance handling, a numeric mismatch, and a missing-agency row.
"""

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "scripts" / "data" / "verify_tech_area_figures.py"


def _load():
    spec = importlib.util.spec_from_file_location("verify_tech_area_figures", SCRIPT_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


mod = _load()


def _comp():
    return {
        "n_unique_awards": 100,
        "by_agency": {
            "Department of Defense": {
                "awards": 60,
                "share_pct": 60.0,
                "phase2_dollars_m": 90.0,
                "unique_firms": 40,
            },
            "NASA": {
                "awards": 40,
                "share_pct": 40.0,
                "phase2_dollars_m": 50.0,
                "unique_firms": 25,
            },
        },
        "program_split": {"SBIR": 70, "STTR": 30, "sttr_pct": 30.0},
        "by_decade": {"2010s": 40, "2020s": 60},
        "censoring": {"mature_awards": 75, "censored_awards": 25},
        "entity_resolution": {"no_uei_awards": 5, "no_uei_pct": 5.0},
        "firm_concentration": {"top10_award_share_pct": 33.0},
    }


def _exp():
    return {
        "totals_awards": 100,
        "by_agency": {
            "Department of Defense": (60, 60.0, 90.0, 40),
            "NASA": (40, 40.0, 50.0, 25),
        },
        "program": (70, 30, 30.0),
        "decade": {"2010s": 40, "2020s": 60},
        "censoring": (75, 25),
        "no_uei": (5, 5.0),
        "top10_share_pct": 33.0,
    }


def test_exact_match_no_failures():
    assert mod.verify_composition(_comp(), _exp()) == []


def test_dollar_within_tolerance_passes():
    comp = _comp()
    comp["by_agency"]["Department of Defense"]["phase2_dollars_m"] = 91.0  # +1 of 90 (2% tol)
    assert mod.verify_composition(comp, _exp()) == []


def test_award_count_mismatch_flagged():
    comp = _comp()
    comp["by_agency"]["Department of Defense"]["awards"] = 58
    fails = mod.verify_composition(comp, _exp())
    assert any("awards" in f for f in fails)


def test_total_mismatch_flagged():
    comp = _comp()
    comp["n_unique_awards"] = 97
    fails = mod.verify_composition(comp, _exp())
    assert any("total awards" in f for f in fails)


def test_missing_agency_flagged():
    comp = _comp()
    del comp["by_agency"]["NASA"]
    fails = mod.verify_composition(comp, _exp())
    assert any("NASA" in f and "MISSING" in f for f in fails)


def test_expected_tables_present_for_published_areas():
    assert set(mod.EXPECTED) == {"quantum_information_science", "hypersonics"}
    for area in mod.EXPECTED.values():
        assert area["by_agency"] and "totals_awards" in area
