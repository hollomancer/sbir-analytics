"""Tests for the versioned Form D high-tier cohort export."""

from types import SimpleNamespace

import pytest

from sbir_etl.enrichers.sec_edgar.form_d_scoring import FORM_D_TIER_RULE_VERSION
from sbir_etl.ucc import export_cohort as _mod
from sbir_etl.ucc.export_cohort import build_cohort_rows


def _form_d_record(name, state, zip_code, amount, tier, has_name_match, has_zip_match):
    """Helper to build a minimal form_d_details record for tests."""
    return {
        "company_name": name,
        "issuer_state": state,
        "issuer_zip": zip_code,
        "total_amount_sold": amount,
        "match_confidence": {
            "rule_version": FORM_D_TIER_RULE_VERSION,
            "tier": tier,
        },
        "name_match": has_name_match,
        "zip_match": has_zip_match,
    }


def test_keeps_high_tier_with_name_match():
    records = [
        _form_d_record(
            "ACME INC", "CA", "94000", 1_000_000, "high", has_name_match=True, has_zip_match=False
        ),
    ]
    sbir_awards = [
        {
            "company_name": "Acme Inc",
            "state": "CA",
            "zip_code": "94000",
            "agency": "DoD",
            "award_year": 2021,
            "award_amount": 250000,
        },
    ]
    rows = list(build_cohort_rows(records, sbir_awards))
    assert len(rows) == 1
    assert rows[0]["company_name"] == "Acme Inc"
    assert rows[0]["state"] == "CA"
    assert rows[0]["agency"] == "DoD"
    assert rows[0]["form_d_tier_rule_version"] == FORM_D_TIER_RULE_VERSION


def test_keeps_high_tier_with_zip_match_only():
    records = [
        _form_d_record(
            "ACME PRECISION",
            "CA",
            "94000",
            5_000_000,
            "high",
            has_name_match=False,
            has_zip_match=True,
        ),
    ]
    sbir_awards = [
        {
            "company_name": "Acme Inc",
            "state": "CA",
            "zip_code": "94000",
            "agency": "DoD",
            "award_year": 2021,
            "award_amount": 250000,
        },
    ]
    rows = list(build_cohort_rows(records, sbir_awards))
    assert len(rows) == 1


def test_drops_medium_and_low_tier():
    records = [
        _form_d_record(
            "MEDIUM INC",
            "CA",
            "94000",
            1_000_000,
            "medium",
            has_name_match=True,
            has_zip_match=True,
        ),
        _form_d_record(
            "LOW INC", "CA", "94000", 1_000_000, "low", has_name_match=True, has_zip_match=True
        ),
    ]
    sbir_awards = [
        {
            "company_name": "Medium Inc",
            "state": "CA",
            "zip_code": "94000",
            "agency": "DoD",
            "award_year": 2021,
            "award_amount": 250000,
        },
        {
            "company_name": "Low Inc",
            "state": "CA",
            "zip_code": "94000",
            "agency": "DoD",
            "award_year": 2021,
            "award_amount": 250000,
        },
    ]
    rows = list(build_cohort_rows(records, sbir_awards))
    assert rows == []


def test_aggregates_award_history_per_firm():
    records = [
        _form_d_record(
            "ACME INC", "CA", "94000", 7_000_000, "high", has_name_match=True, has_zip_match=False
        ),
    ]
    sbir_awards = [
        {
            "company_name": "Acme Inc",
            "state": "CA",
            "zip_code": "94000",
            "agency": "DoD",
            "award_year": 2019,
            "award_amount": 150_000,
        },
        {
            "company_name": "Acme Inc",
            "state": "CA",
            "zip_code": "94000",
            "agency": "DoD",
            "award_year": 2022,
            "award_amount": 1_000_000,
        },
    ]
    rows = list(build_cohort_rows(records, sbir_awards))
    assert len(rows) == 1
    assert rows[0]["first_award_year"] == 2019
    assert rows[0]["last_award_year"] == 2022
    assert rows[0]["total_award_amount"] == 1_150_000


def test_refuses_unversioned_details():
    record = _form_d_record("ACME INC", "CA", "94000", 1_000_000, "high", True, False)
    del record["match_confidence"]["rule_version"]

    with pytest.raises(ValueError, match="Rescore the complete input"):
        list(build_cohort_rows([record], []))


def test_closed_parent_study_blocks_cohort_materialization(monkeypatch):
    manifest = SimpleNamespace(
        study_id="form-d-fundraising",
        materialization=SimpleNamespace(allowed=False, blockers=["issuer-scope review required"]),
    )
    monkeypatch.setattr(_mod, "load_study_manifest", lambda _path: manifest)

    with pytest.raises(RuntimeError, match="issuer-scope review required"):
        _mod.require_materialization_allowed()
