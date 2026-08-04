from datetime import date

import pandas as pd
import pytest

from sbir_etl.supply_chain.nsf_direct import (
    build_nsf_sbir_baseline,
    classify_nsf_award_status,
    reconcile_nsf_sbir_awards,
    requested_nsf_award_ids,
)


def _baseline() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Company": "Current Materials, Inc.",
                "Award Title": "SBIR Phase II: Baseline title",
                "Agency": "NSF",
                "Phase": "Phase II",
                "Program": "SBIR",
                "Agency Tracking Number": "0512345",
                "Contract": "620588",
                "Proposal Award Date": "2024-06-01",
                "Contract End Date": "2026-05-31",
                "Award Year": "1900",
                "Award Amount": "900000",
                "UEI": "ABCDEFGHIJKL",
                "Duns": "012345678",
                "Abstract": "Baseline abstract",
            },
            {
                "Company": "Former Security LLC",
                "Award Title": "STTR Phase I: Secure component",
                "Agency": "National Science Foundation",
                "Phase": "Phase I",
                "Program": "STTR",
                "Agency Tracking Number": "1234567",
                "Contract": None,
                "Proposal Award Date": "2020-01-01",
                "Contract End Date": "2021-12-31",
                "Award Year": "2020",
                "Award Amount": "250000",
                "UEI": "MNOPQRSTUVWX",
                "Abstract": "Secure component abstract",
            },
            {
                "Company": "Unvalidated Robotics Inc",
                "Award Title": "SBIR Phase I: Robotics",
                "Agency": "NSF",
                "Phase": "Phase I",
                "Program": "SBIR",
                "Contract": "2345678",
                "Award Year": "2025",
            },
            {"Company": "Excluded", "Agency": "DOE", "Program": "SBIR", "Contract": "9"},
        ]
    )


def _direct() -> pd.DataFrame:
    common = {
        "source_kind": "nsf_award_search_api",
        "source_path": "snapshot/award.json",
        "source_record_sha256": "abcdef",
        "source_retrieved_at": "2026-08-03T00:00:00Z",
        "source_url": "https://api.nsf.gov/award",
    }
    return pd.DataFrame(
        [
            {
                **common,
                "nsf_award_id": "0620588",
                "nsf_award_title": "SBIR Phase II: Direct title",
                "nsf_award_abstract": "Direct abstract",
                "nsf_program": "SBIR",
                "nsf_phase": "II",
                "nsf_award_date": "2024-06-01",
                "nsf_start_date": "2024-06-01",
                "nsf_end_date": "2027-05-31",
                "nsf_estimated_total_amount": 1_000_000,
                "nsf_obligated_amount": 900_000,
                "nsf_awardee_name": "Current Materials, Inc.",
                "nsf_awardee_legal_business_name": "Current Materials Inc",
                "nsf_awardee_uei": "ABCDEFGHIJKL",
            },
            {
                **common,
                "nsf_award_id": "1234567",
                "nsf_award_title": "STTR Phase I: Secure component",
                "nsf_award_abstract": "Secure component abstract",
                "nsf_program": "STTR",
                "nsf_phase": "I",
                "nsf_award_date": "2020-01-01",
                "nsf_start_date": "2020-01-01",
                "nsf_end_date": "2021-12-31",
                "nsf_estimated_total_amount": 250_000,
                "nsf_obligated_amount": 250_000,
                "nsf_awardee_name": "Former Security LLC",
                "nsf_awardee_legal_business_name": "Former Security LLC",
                "nsf_awardee_uei": "MNOPQRSTUVWX",
            },
            {
                **common,
                "nsf_award_id": "7654321",
                "nsf_award_title": "SBIR Phase I: Future manufacturing",
                "nsf_award_abstract": "Future work",
                "nsf_program": "SBIR",
                "nsf_phase": "I",
                "nsf_award_date": "2028-01-01",
                "nsf_start_date": "2028-01-01",
                "nsf_end_date": "2029-01-01",
                "nsf_estimated_total_amount": 300_000,
                "nsf_obligated_amount": 0,
                "nsf_awardee_name": "Future Manufacturing Corp",
                "nsf_awardee_legal_business_name": "Future Manufacturing Corp",
                "nsf_awardee_uei": "FUTUREUEI001",
            },
        ]
    )


def test_baseline_normalizes_primary_ids_and_retains_conflict() -> None:
    baseline = build_nsf_sbir_baseline(_baseline())
    assert len(baseline) == 3
    assert requested_nsf_award_ids(baseline) == ["0620588", "1234567", "2345678"]
    current = baseline.loc[baseline["sbir_gov_nsf_award_id"] == "0620588"].iloc[0]
    assert current["sbir_gov_award_id_source"] == "contract_number"
    assert current["sbir_gov_award_id_conflict"]
    assert baseline["sbir_gov_record_id"].is_unique


@pytest.mark.parametrize(
    ("start", "end", "expected"),
    [
        ("2025-01-01", "2027-01-01", "active"),
        ("2027-01-01", "2028-01-01", "upcoming"),
        ("2020-01-01", "2025-12-31", "expired"),
        (None, "2027-01-01", "indeterminate"),
    ],
)
def test_status_uses_direct_dates_only(start: object, end: object, expected: str) -> None:
    assert classify_nsf_award_status(start, end, date(2026, 8, 3)) == expected


def test_reconciliation_emits_dispositions_discrepancies_and_statuses() -> None:
    result = reconcile_nsf_sbir_awards(
        build_nsf_sbir_baseline(_baseline()), _direct(), analysis_date=date(2026, 8, 3)
    )
    rows = result.reconciliation
    current = rows.loc[rows["nsf_award_id"] == "0620588"].iloc[0]
    former = rows.loc[rows["nsf_award_id"] == "1234567"].iloc[0]
    missing = rows.loc[rows["sbir_gov_nsf_award_id"] == "2345678"].iloc[0]
    future = rows.loc[rows["nsf_award_id"] == "7654321"].iloc[0]
    assert current["match_method"] == "exact_contract_award_id"
    assert current["organization_match_method"] == "exact_uei"
    assert current["nsf_awardee_status"] == "current"
    assert "title" in current["reconciliation_discrepancy_fields"]
    assert former["match_method"] == "exact_agency_tracking_award_id"
    assert former["nsf_awardee_status"] == "former"
    assert missing["reconciliation_disposition"] == "no_direct_record"
    assert future["reconciliation_disposition"] == "direct_only"
    assert future["nsf_awardee_status"] == "upcoming_only"
    assert result.quality["quality_gates_passed"] is True


def test_duplicate_direct_award_ids_fail_closed() -> None:
    direct = pd.concat([_direct(), _direct().iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="not unique"):
        reconcile_nsf_sbir_awards(
            build_nsf_sbir_baseline(_baseline()), direct, analysis_date=date(2026, 8, 3)
        )
