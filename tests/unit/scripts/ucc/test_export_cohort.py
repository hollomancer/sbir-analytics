"""Tests for Form D high-confidence cohort export."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "scripts" / "data"))

from ucc.export_cohort import build_cohort_rows  # noqa: E402


def _form_d_record(name, state, zip_code, amount, tier, has_name_match, has_zip_match):
    """Helper to build a minimal form_d_details record for tests."""
    return {
        "company_name": name,
        "issuer_state": state,
        "issuer_zip": zip_code,
        "total_amount_sold": amount,
        "match_confidence": {"tier": tier},
        "name_match": has_name_match,
        "zip_match": has_zip_match,
    }


def test_keeps_high_tier_with_name_match():
    records = [
        _form_d_record("ACME INC", "CA", "94000", 1_000_000, "high",
                       has_name_match=True, has_zip_match=False),
    ]
    sbir_awards = [
        {"company_name": "Acme Inc", "state": "CA", "zip_code": "94000",
         "agency": "DoD", "award_year": 2021, "award_amount": 250000},
    ]
    rows = list(build_cohort_rows(records, sbir_awards))
    assert len(rows) == 1
    assert rows[0]["company_name"] == "Acme Inc"
    assert rows[0]["state"] == "CA"
    assert rows[0]["agency"] == "DoD"


def test_keeps_high_tier_with_zip_match_only():
    records = [
        _form_d_record("ACME PRECISION", "CA", "94000", 5_000_000, "high",
                       has_name_match=False, has_zip_match=True),
    ]
    sbir_awards = [
        {"company_name": "Acme Inc", "state": "CA", "zip_code": "94000",
         "agency": "DoD", "award_year": 2021, "award_amount": 250000},
    ]
    rows = list(build_cohort_rows(records, sbir_awards))
    assert len(rows) == 1


def test_drops_medium_and_low_tier():
    records = [
        _form_d_record("MEDIUM INC", "CA", "94000", 1_000_000, "medium",
                       has_name_match=True, has_zip_match=True),
        _form_d_record("LOW INC", "CA", "94000", 1_000_000, "low",
                       has_name_match=True, has_zip_match=True),
    ]
    sbir_awards = [
        {"company_name": "Medium Inc", "state": "CA", "zip_code": "94000",
         "agency": "DoD", "award_year": 2021, "award_amount": 250000},
        {"company_name": "Low Inc", "state": "CA", "zip_code": "94000",
         "agency": "DoD", "award_year": 2021, "award_amount": 250000},
    ]
    rows = list(build_cohort_rows(records, sbir_awards))
    assert rows == []


def test_aggregates_award_history_per_firm():
    records = [
        _form_d_record("ACME INC", "CA", "94000", 7_000_000, "high",
                       has_name_match=True, has_zip_match=False),
    ]
    sbir_awards = [
        {"company_name": "Acme Inc", "state": "CA", "zip_code": "94000",
         "agency": "DoD", "award_year": 2019, "award_amount": 150_000},
        {"company_name": "Acme Inc", "state": "CA", "zip_code": "94000",
         "agency": "DoD", "award_year": 2022, "award_amount": 1_000_000},
    ]
    rows = list(build_cohort_rows(records, sbir_awards))
    assert len(rows) == 1
    assert rows[0]["first_award_year"] == 2019
    assert rows[0]["last_award_year"] == 2022
    assert rows[0]["total_award_amount"] == 1_150_000
