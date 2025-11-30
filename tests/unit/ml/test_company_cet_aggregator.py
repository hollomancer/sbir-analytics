"""Tests for company cet aggregator."""

from datetime import datetime

import pandas as pd
import pytest


pytestmark = pytest.mark.fast

from src.transformers.company_cet_aggregator import CompanyCETAggregator


def test_aggregate_single_company_basic():
    """
    Basic aggregation for a single company:
    - two awards with primary CETs and one award without CET
    - assert coverage, dominant CET, cet_scores, specialization (HHI) and date range
    """
    data = [
        {
            "award_id": "A1",
            "company_id": "C1",
            "company_name": "Acme Corp",
            "primary_cet": "cet_a",
            "primary_score": 80,
            "supporting_cets": [],
            "award_date": "2020-01-15",
            "classified_at": "2020-01-16",
        },
        {
            "award_id": "A2",
            "company_id": "C1",
            "company_name": "Acme Corp",
            "primary_cet": "cet_b",
            "primary_score": 20,
            "supporting_cets": [],
            "award_date": "2021-06-01",
            "classified_at": "2021-06-02",
        },
        {
            "award_id": "A3",
            "company_id": "C1",
            "company_name": "Acme Corp",
            # no CET on this award
            "primary_cet": None,
            "primary_score": None,
            "supporting_cets": [],
            "award_date": "2022-03-10",
            "classified_at": None,
        },
    ]

    df = pd.DataFrame(data)
    agg = CompanyCETAggregator(df)
    df_comp = agg.to_dataframe()

    # One company
    assert len(df_comp) == 1

    row = df_comp.iloc[0]
    assert row["company_id"] == "C1"
    assert row["company_name"] == "Acme Corp"
    assert row["total_awards"] == 3
    assert row["awards_with_cet"] == 2
    assert pytest.approx(row["coverage"]) == 2 / 3

    # CET scores and dominant
    expected_scores = {"cet_a": 80.0, "cet_b": 20.0}
    assert row["cet_scores"] == expected_scores
    assert row["dominant_cet"] == "cet_a"
    assert pytest.approx(row["dominant_score"]) == 80.0

    # HHI: (0.8^2 + 0.2^2) = 0.64 + 0.04 = 0.68
    assert pytest.approx(row["specialization_score"], rel=1e-6) == pytest.approx(0.68, rel=1e-6)

    # Date range (first and last award_date)
    assert pd.to_datetime(row["first_award_date"]).date() == datetime(2020, 1, 15).date()
    assert pd.to_datetime(row["last_award_date"]).date() == datetime(2022, 3, 10).date()

    # Trend should include years as keys (strings) with dict values
    assert isinstance(row["cet_trend"], dict)
    # We expect keys for 2020 and 2021 and 2022 (2022 has no CETs so it may be empty)
    assert "2020" in row["cet_trend"]
    assert "2021" in row["cet_trend"]


def test_include_supporting_cets_affects_scores_and_specialization():
    """
    When supporting CETs are present, they should be included in aggregation (default behavior).
    This test verifies supporting CETs contribute to per-CET aggregates.
    """
    data = [
        {
            "award_id": "B1",
            "company_id": "C2",
            "company_name": "Beta LLC",
            "primary_cet": "cet_x",
            "primary_score": 60,
            "supporting_cets": [{"cet_id": "cet_y", "score": 40}, {"cet_id": "cet_x", "score": 20}],
            "award_date": "2019-05-20",
        }
    ]

    df = pd.DataFrame(data)
    agg = CompanyCETAggregator(df)
    df_comp = agg.to_dataframe()

    assert len(df_comp) == 1
    row = df_comp.iloc[0]
    # cet_x has scores [60,20] -> mean 40.0 ; cet_y has [40] -> mean 40.0
    cet_scores = row["cet_scores"]
    assert pytest.approx(cet_scores["cet_x"]) == 40.0
    assert pytest.approx(cet_scores["cet_y"]) == 40.0

    # specialization HHI for two equal shares -> 0.5
    assert pytest.approx(row["specialization_score"], rel=1e-6) == pytest.approx(0.5, rel=1e-6)


def test_no_cets_results_in_empty_scores_and_zero_coverage():
    """
    If a company has awards but none have CETs, aggregator should produce coverage=0,
    awards_with_cet=0 and empty cet_scores with no dominant CET.
    """
    data = [
        {"award_id": "C1", "company_id": "C3", "company_name": "Gamma Inc", "primary_cet": None},
        {"award_id": "C2", "company_id": "C3", "company_name": "Gamma Inc", "primary_cet": None},
    ]
    df = pd.DataFrame(data)
    agg = CompanyCETAggregator(df)
    df_comp = agg.to_dataframe()

    assert len(df_comp) == 1
    row = df_comp.iloc[0]
    assert row["total_awards"] == 2
    assert row["awards_with_cet"] == 0
    assert row["coverage"] == 0.0
    assert row["cet_scores"] == {}
    assert row["dominant_cet"] is None
    assert row["dominant_score"] is None
    assert row["specialization_score"] == 0.0


def test_trend_by_phase_preference_over_year():
    """
    When awards contain a `phase` value, trend should be returned keyed by phase (I/II/III)
    rather than by year. Verify phase keys and that shares sum to 1 for a populated phase.
    """
    data = [
        {
            "award_id": "D1",
            "company_id": "C4",
            "company_name": "Delta Co",
            "primary_cet": "cet_m",
            "primary_score": 50,
            "phase": "I",
            "award_date": "2018-02-02",
        },
        {
            "award_id": "D2",
            "company_id": "C4",
            "company_name": "Delta Co",
            "primary_cet": "cet_n",
            "primary_score": 50,
            "phase": "II",
            "award_date": "2019-07-07",
        },
    ]
    df = pd.DataFrame(data)
    agg = CompanyCETAggregator(df)
    df_comp = agg.to_dataframe()

    assert len(df_comp) == 1
    row = df_comp.iloc[0]

    # Expect both phases present as keys in cet_trend
    assert "I" in row["cet_trend"]
    assert "II" in row["cet_trend"]

    # For phase "I", only cet_m with score 50 -> share 1.0
    phase_i = row["cet_trend"]["I"]
    assert isinstance(phase_i, dict)
    assert pytest.approx(sum(phase_i.values()), rel=1e-6) == pytest.approx(1.0, rel=1e-6)
    assert "cet_m" in phase_i

    # For phase "II", only cet_n with score 50 -> share 1.0
    phase_ii = row["cet_trend"]["II"]
    assert pytest.approx(sum(phase_ii.values()), rel=1e-6) == pytest.approx(1.0, rel=1e-6)
    assert "cet_n" in phase_ii
