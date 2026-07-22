from datetime import date

import pandas as pd
import pytest

from sbir_etl.reporting.dod_supply_chain_baseline import (
    build_baseline,
    latest_complete_fiscal_year,
    write_baseline_outputs,
)


def _awards() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "award_id": "A1",
                "agency": "DOD",
                "award_date": "2020-09-30",
                "company_name": "Acme, Inc.",
                "uei": "UEI-1",
                "award_amount": 100.0,
                "phase": "II",
                "state": "CA",
                "congressional_district": "CA-01",
            },
            {
                "award_id": "A2",
                "agency": "Department of Defense",
                "award_date": "2021-10-01",
                "company_name": "Acme Inc",
                "uei": "UEI-1",
                "award_amount": 300.0,
                "phase": "Phase II",
                "state": "CA",
                "congressional_district": "CA-01",
            },
            {
                "award_id": "A3",
                "agency": "Defense Department",
                "fiscal_year": 2025,
                "company_name": "Beta Systems LLC",
                "duns": "123456789",
                "award_amount": 600.0,
                "phase": "2",
                "state": "TX",
                "congressional_district": None,
            },
            {
                "award_id": "A4",
                "agency": "NASA",
                "fiscal_year": 2025,
                "company_name": "Space Co",
                "award_amount": 999.0,
            },
            {
                "award_id": "A5",
                "agency": "DOD",
                "fiscal_year": 2026,
                "company_name": "Future Co",
                "award_amount": 999.0,
            },
        ]
    )


def _classifications() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"award_id": "A1", "primary_cet": "ai", "primary_score": 80.0, "taxonomy_version": "NSTC-2025Q1"},
            # Duplicate classification must not double-count award dollars.
            {"award_id": "A1", "primary_cet": "quantum", "primary_score": 70.0, "taxonomy_version": "NSTC-2025Q1"},
            {"award_id": "A2", "primary_cet": "ai", "primary_score": 60.0, "taxonomy_version": "NSTC-2025Q1"},
            {"award_id": "A3", "primary_cet": "ai", "primary_score": 40.0, "taxonomy_version": "NSTC-2025Q1"},
            {"award_id": "A4", "primary_cet": "space", "primary_score": 90.0, "taxonomy_version": "NSTC-2025Q1"},
            {"award_id": "A5", "primary_cet": "ai", "primary_score": 90.0, "taxonomy_version": "NSTC-2025Q1"},
        ]
    )


def test_latest_complete_federal_fiscal_year() -> None:
    assert latest_complete_fiscal_year(date(2026, 7, 20)) == 2025
    assert latest_complete_fiscal_year(date(2026, 10, 1)) == 2026


def test_builds_dod_facts_and_latest_window_metrics_without_double_counting() -> None:
    survival = pd.DataFrame(
        [
            {"phase_ii_award_id": "A2", "event_observed": True, "time_days": 1000},
            {"phase_ii_award_id": "A3", "event_observed": False, "time_days": 1000},
        ]
    )
    result = build_baseline(
        _awards(), _classifications(), survival=survival, as_of=date(2026, 7, 20)
    )

    assert result.award_facts["award_id"].tolist() == ["A1", "A2", "A3"]
    assert result.award_facts["fiscal_year"].tolist() == [2020, 2022, 2025]
    assert result.award_facts["organization_id"].tolist()[:2] == ["uei:UEI-1", "uei:UEI-1"]
    assert result.award_facts.loc[2, "identity_method"] == "duns"

    latest = result.cet_metrics.loc[
        (result.cet_metrics["period_type"] == "latest_complete_window")
        & (result.cet_metrics["cet_area"] == "ai")
    ].iloc[0]
    assert latest["period_start_fy"] == 2021
    assert latest["award_count"] == 2
    assert latest["award_dollars"] == pytest.approx(900.0)
    assert latest["distinct_firms"] == 2
    assert latest["dollar_hhi"] == pytest.approx((1 / 3) ** 2 + (2 / 3) ** 2)
    assert latest["top1_dollar_share"] == pytest.approx(2 / 3)
    assert latest["thin_base"]
    assert latest["dominant_firm"]
    assert latest["entrant_firm_share"] == pytest.approx(0.5)
    assert latest["transition_eligible"] == 1
    assert latest["transition_observed_5yr"] == 1
    assert latest["transition_immature_censored"] == 1
    assert latest["transition_rate_5yr"] == pytest.approx(1.0)
    assert latest["transition_ci95_low"] < latest["transition_ci95_high"]
    assert latest["acp10_screening_flag"]


def test_missing_transition_is_not_zero_and_missingness_is_reported() -> None:
    awards = _awards()
    awards.loc[awards["award_id"] == "A3", "award_amount"] = None
    result = build_baseline(awards, _classifications(), as_of=date(2026, 7, 20))
    latest = result.cet_metrics.loc[
        result.cet_metrics["period_type"] == "latest_complete_window"
    ].iloc[0]
    assert latest["transition_status"] == "not_computed"
    assert pd.isna(latest["transition_rate_5yr"])
    assert pd.isna(latest["acp10_screening_flag"])
    assert latest["missing_amount_share"] == pytest.approx(0.5)
    assert latest["missing_district_share"] == pytest.approx(0.5)


def test_required_inputs_fail_loudly() -> None:
    with pytest.raises(ValueError, match="awards are required"):
        build_baseline(pd.DataFrame(), _classifications(), as_of=date(2026, 7, 20))
    with pytest.raises(ValueError, match="classifications are required"):
        build_baseline(_awards(), pd.DataFrame(), as_of=date(2026, 7, 20))


def test_duplicate_award_rows_fail_instead_of_double_counting() -> None:
    awards = pd.concat([_awards(), _awards().iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="double-count"):
        build_baseline(awards, _classifications(), as_of=date(2026, 7, 20))


def test_string_false_transition_is_not_treated_as_an_event() -> None:
    survival = pd.DataFrame(
        [{"phase_ii_award_id": "A2", "event_observed": "False", "time_days": 2000}]
    )
    result = build_baseline(
        _awards(), _classifications(), survival=survival, as_of=date(2026, 7, 20)
    )
    latest = result.cet_metrics.loc[
        result.cet_metrics["period_type"] == "latest_complete_window"
    ].iloc[0]
    assert latest["transition_eligible"] == 1
    assert latest["transition_observed_5yr"] == 0
    assert latest["transition_rate_5yr"] == 0


def test_writes_three_public_interfaces_and_metadata(tmp_path) -> None:
    result = build_baseline(_awards(), _classifications(), as_of=date(2026, 7, 20))
    paths = write_baseline_outputs(result, tmp_path)
    assert len(paths) == 7
    assert all((tmp_path / path.split("/")[-1]).exists() for path in paths.values())
    round_trip = pd.read_parquet(paths["dod_supply_chain_award_facts_parquet"])
    assert round_trip["award_id"].tolist() == ["A1", "A2", "A3"]
