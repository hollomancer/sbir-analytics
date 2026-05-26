"""Tests for USAspending Phase 3 contract event builder."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "scripts" / "data"))

from capital_events.sources.usaspending import build_usaspending_events  # noqa: E402


def _contract(recipient, award_id, start, amount, agency="Department of Defense"):
    return {
        "Recipient Name": recipient,
        "Award ID": award_id,
        "Award Amount": amount,
        "Start Date": start,
        "End Date": "",
        "Funding Agency": agency,
        "Funding Sub Agency": "Army",
        "Awarding Agency": agency,
        "Awarding Sub Agency": "Army",
        "Description": "Phase III commercialization contract",
        "NAICS": "541715",
        "generated_internal_id": f"GEN-{award_id}",
        "internal_id": f"INT-{award_id}",
        "agency_slug": "dod",
        "awarding_agency_id": 9700,
    }


def test_emits_one_event_per_contract(cohort, tmp_path):
    src = tmp_path / "usaspending.jsonl"
    src.write_text("\n".join(json.dumps(c) for c in [
        _contract("ACME INC", "W56HZV-22-D-0001", "2022-06-01", 5_000_000.0),
        _contract("ACME INC", "W56HZV-23-D-0002", "2023-09-15", 8_000_000.0),
    ]) + "\n")

    events = list(build_usaspending_events(cohort, src))
    assert len(events) == 2
    e = events[0]
    assert e["company_name"] == "ACME INC"
    assert e["event_date"] == "2022-06-01"
    assert e["event_type"] == "usaspending_contract"
    assert e["amount_usd"] == 5_000_000.0
    assert e["counterparty"] == "Department of Defense"
    assert e["source_id"] == "W56HZV-22-D-0001"


def test_falls_back_to_generated_internal_id_when_award_id_missing(cohort, tmp_path):
    src = tmp_path / "usaspending.jsonl"
    contract = _contract("ACME INC", "", "2022-06-01", 1_000_000.0)
    contract["Award ID"] = ""
    src.write_text(json.dumps(contract) + "\n")
    events = list(build_usaspending_events(cohort, src))
    assert events[0]["source_id"] == "GEN-"


def test_metadata_carries_naics_and_subagency(cohort, tmp_path):
    src = tmp_path / "usaspending.jsonl"
    src.write_text(json.dumps(_contract("ACME INC", "AW1", "2023-01-01", 100.0)) + "\n")
    meta = json.loads(list(build_usaspending_events(cohort, src))[0]["metadata"])
    assert meta["naics"] == "541715"
    assert meta["funding_sub_agency"] == "Army"
    assert meta["description"] == "Phase III commercialization contract"


def test_skips_non_cohort_firms(cohort, tmp_path):
    src = tmp_path / "usaspending.jsonl"
    src.write_text(json.dumps(_contract("UNRELATED INC", "X", "2023-01-01", 100.0)) + "\n")
    assert list(build_usaspending_events(cohort, src)) == []


def test_returns_empty_when_file_missing(cohort, tmp_path):
    assert list(build_usaspending_events(cohort, tmp_path / "nope.jsonl")) == []


def test_matches_recipient_name_case_insensitive(cohort, tmp_path):
    """Phase 3 USAspending may have varied casing; cohort key is uppercase."""
    src = tmp_path / "usaspending.jsonl"
    src.write_text(json.dumps(_contract("Acme Inc", "X", "2023-01-01", 100.0)) + "\n")
    events = list(build_usaspending_events(cohort, src))
    assert len(events) == 1
    assert events[0]["company_name"] == "ACME INC"
