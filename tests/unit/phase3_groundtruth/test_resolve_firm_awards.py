"""Tests for success-story firm -> SBIR award resolution."""

from __future__ import annotations

import pandas as pd
import pytest

from scripts.phase3_groundtruth.resolve_firm_awards import normalize_name, resolve_firm


pytestmark = pytest.mark.fast


@pytest.fixture
def award_csv(tmp_path):
    path = tmp_path / "award_data.csv"
    pd.DataFrame(
        [
            {
                "Company": "Acme Photonics, Inc.",
                "UEI": "UEI000000001",
                "Contract": "N00014-20-C-0055",
                "Topic Code": "N201-001",
                "Agency": "DOD",
                "Branch": "NAVY",
                "Phase": "Phase II",
            },
            {
                "Company": "ACME PHOTONICS INC",
                "UEI": "UEI000000001",
                "Contract": "N00014-22-C-9000",
                "Topic Code": "N221-010",
                "Agency": "DOD",
                "Branch": "NAVY",
                "Phase": "Phase II",
            },
            {
                "Company": "Acme Robotics LLC",
                "UEI": "UEI000000009",
                "Contract": "W911NF-21-C-0001",
                "Topic Code": "A214-001",
                "Agency": "DOD",
                "Branch": "ARMY",
                "Phase": "Phase I",
            },
        ]
    ).to_csv(path, index=False)
    return str(path)


def test_normalize_name_strips_suffix_and_punctuation():
    assert normalize_name("Acme Photonics, Inc.") == "ACME PHOTONICS"
    assert normalize_name("ACME PHOTONICS INC") == "ACME PHOTONICS"


def test_exact_match_collects_all_of_a_firms_awards(award_csv):
    r = resolve_firm("Acme Photonics", award_csv)
    assert r.match_method == "exact"
    assert r.award_count == 2  # both spellings collapse to one firm
    assert r.contracts == ["N00014-20-C-0055", "N00014-22-C-9000"]
    assert r.ueis == ["UEI000000001"]


def test_fuzzy_does_not_confuse_distinct_firms(award_csv):
    # "Acme Photonics Corporation" -> Acme Photonics, never Acme Robotics.
    r = resolve_firm("Acme Photonics Corporation", award_csv)
    assert r.matched_company is not None
    assert "PHOTONICS" in normalize_name(r.matched_company)
    assert "N00014-20-C-0055" in r.contracts


def test_unknown_firm_returns_none(award_csv):
    r = resolve_firm("Completely Unrelated Widgets", award_csv)
    assert r.match_method == "none"
    assert r.contracts == []
