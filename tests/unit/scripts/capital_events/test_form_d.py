"""Tests for Form D capital-event builder."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "scripts" / "data"))

from capital_events.sources.form_d import (  # noqa: E402
    build_form_d_events,
    classify_securities_types,
)


def _form_d(name, tier, offerings):
    return {
        "company_name": name,
        "form_d_cik": "0001234567",
        "match_confidence": {"tier": tier, "person_score": 1.0, "address_score": 1},
        "offering_count": len(offerings),
        "total_raised": sum(o.get("total_amount_sold") or 0 for o in offerings),
        "offerings": offerings,
    }


def _offering(accession, filing_date, amount, securities=None, is_combo=False, **kw):
    return {
        "accession_number": accession,
        "filing_date": filing_date,
        "total_amount_sold": amount,
        "securities_types": securities or ["Equity"],
        "is_business_combination": is_combo,
        "is_amendment": False,
        "minimum_investment": 25000,
        "num_investors": 5,
        "related_persons": [],
        **kw,
    }


def test_classify_securities_types():
    assert classify_securities_types(["Equity"]) == "equity"
    assert classify_securities_types(["Debt"]) == "debt"
    assert classify_securities_types(["Option, Warrant or Other Right to Acquire Another Security"]) == "option_warrant"
    assert classify_securities_types(["Equity", "Debt"]) == "other"
    assert classify_securities_types([]) == "other"
    assert classify_securities_types(None) == "other"


def test_emits_one_event_per_offering(cohort, tmp_path):
    src = tmp_path / "form_d.jsonl"
    src.write_text(json.dumps(_form_d("ACME INC", "high", [
        _offering("ACC-1", "2023-01-15", 5_000_000.0),
        _offering("ACC-2", "2023-08-22", 10_000_000.0, securities=["Debt"]),
    ])) + "\n")

    events = list(build_form_d_events(cohort, src))
    assert len(events) == 2
    e1 = events[0]
    assert e1["company_name"] == "ACME INC"
    assert e1["event_date"] == "2023-01-15"
    assert e1["event_type"] == "form_d_filing"
    assert e1["event_subtype"] == "equity"
    assert e1["amount_usd"] == 5_000_000.0
    assert e1["counterparty"] is None
    assert e1["source_id"] == "ACC-1"

    e2 = events[1]
    assert e2["event_subtype"] == "debt"


def test_business_combination_overrides_subtype(cohort, tmp_path):
    src = tmp_path / "form_d.jsonl"
    src.write_text(json.dumps(_form_d("ACME INC", "high", [
        _offering("ACC-3", "2024-05-01", 50_000_000.0, securities=["Equity"], is_combo=True),
    ])) + "\n")
    events = list(build_form_d_events(cohort, src))
    assert events[0]["event_subtype"] == "combination"


def test_drops_non_high_tier_records(cohort, tmp_path):
    src = tmp_path / "form_d.jsonl"
    src.write_text("\n".join([
        json.dumps(_form_d("ACME INC", "medium", [_offering("ACC-A", "2024-01-01", 1_000_000.0)])),
        json.dumps(_form_d("OUT-OF-STATE CORP", "high", [_offering("ACC-B", "2023-01-01", 5_000_000.0)])),
    ]) + "\n")
    events = list(build_form_d_events(cohort, src))
    assert len(events) == 1
    assert events[0]["company_name"] == "OUT-OF-STATE CORP"


def test_skips_non_cohort_firms(cohort, tmp_path):
    src = tmp_path / "form_d.jsonl"
    src.write_text(json.dumps(_form_d("UNRELATED INC", "high", [
        _offering("ACC-X", "2024-01-01", 1_000_000.0),
    ])) + "\n")
    assert list(build_form_d_events(cohort, src)) == []


def test_metadata_carries_offering_extras(cohort, tmp_path):
    src = tmp_path / "form_d.jsonl"
    src.write_text(json.dumps(_form_d("ACME INC", "high", [
        _offering("ACC-1", "2024-01-01", 5_000_000.0, minimum_investment=50000, num_investors=8),
    ])) + "\n")
    events = list(build_form_d_events(cohort, src))
    meta = json.loads(events[0]["metadata"])
    assert meta["minimum_investment"] == 50000
    assert meta["num_investors"] == 8
    assert meta["business_combination"] is False
