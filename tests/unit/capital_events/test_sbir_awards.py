"""Tests for SBIR award capital-event builder."""

import csv
import json
from pathlib import Path


from sbir_etl.capital_events.sources.sbir_awards import (
    build_sbir_award_events,
    classify_phase,
)


def _write_awards_csv(path: Path, rows: list[dict]) -> None:
    headers = [
        "Company",
        "Agency",
        "Branch",
        "Phase",
        "Award Year",
        "Award Amount",
        "Proposal Award Date",
        "Agency Tracking Number",
        "Solicitation Number",
        "Solicitation Year",
        "City",
        "State",
        "Zip",
        "Contract",
    ]
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=headers)
        w.writeheader()
        for row in rows:
            w.writerow({h: row.get(h, "") for h in headers})


def test_classify_phase():
    assert classify_phase("Phase I") == "sbir_phase_i"
    assert classify_phase("Phase II") == "sbir_phase_ii"
    assert classify_phase("Phase III") == "sbir_phase_iii"
    assert classify_phase("PHASE II") == "sbir_phase_ii"
    assert classify_phase("Phase I-Direct") == "sbir_phase_i"
    assert classify_phase("") == "sbir_phase_unknown"
    assert classify_phase(None) == "sbir_phase_unknown"


def test_emits_one_event_per_matching_award(cohort, tmp_path):
    csv_path = tmp_path / "awards.csv"
    _write_awards_csv(
        csv_path,
        [
            {
                "Company": "Acme Inc",
                "Agency": "Department of Defense",
                "Branch": "Army",
                "Phase": "Phase I",
                "Award Year": "2018",
                "Award Amount": "150000",
                "Proposal Award Date": "2018-06-15",
                "Agency Tracking Number": "ATN-001",
                "Solicitation Number": "SBIR-18-001",
                "Solicitation Year": "2018",
                "City": "San Diego",
                "State": "California",
                "Zip": "92101",
                "Contract": "W56HZV-18-C-0001",
            },
            {
                "Company": "Acme Inc",
                "Agency": "Department of Defense",
                "Branch": "Army",
                "Phase": "Phase II",
                "Award Year": "2020",
                "Award Amount": "1000000",
                "Proposal Award Date": "2020-09-01",
                "Agency Tracking Number": "ATN-002",
                "Solicitation Number": "SBIR-20-002",
                "Solicitation Year": "2020",
                "City": "San Diego",
                "State": "California",
                "Zip": "92101",
                "Contract": "W56HZV-20-C-0002",
            },
        ],
    )
    events = list(build_sbir_award_events(cohort, csv_path))
    assert len(events) == 2
    by_phase = {e["event_subtype"]: e for e in events}
    p1 = by_phase["sbir_phase_i"]
    assert p1["company_name"] == "ACME INC"
    assert p1["event_date"] == "2018-06-15"
    assert p1["event_type"] == "sbir_award"
    assert p1["amount_usd"] == 150000.0
    assert p1["counterparty"] == "Department of Defense"
    assert p1["source_id"] == "ATN-001"
    meta = json.loads(p1["metadata"])
    assert meta["branch"] == "Army"
    assert meta["solicitation_year"] == 2018


def test_falls_back_to_contract_id_when_atn_missing(cohort, tmp_path):
    csv_path = tmp_path / "awards.csv"
    _write_awards_csv(
        csv_path,
        [
            {
                "Company": "Boring LLC",
                "Agency": "National Science Foundation",
                "Branch": "",
                "Phase": "Phase I",
                "Award Year": "2020",
                "Award Amount": "250000",
                "Proposal Award Date": "2020-04-01",
                "Agency Tracking Number": "",
                "Solicitation Number": "NSF-20-501",
                "Solicitation Year": "2020",
                "City": "Austin",
                "State": "Texas",
                "Zip": "73301",
                "Contract": "NSF-2020-100",
            },
        ],
    )
    events = list(build_sbir_award_events(cohort, csv_path))
    assert len(events) == 1
    assert events[0]["source_id"] == "NSF-2020-100"


def test_skips_non_cohort_firms(cohort, tmp_path):
    csv_path = tmp_path / "awards.csv"
    _write_awards_csv(
        csv_path,
        [
            {
                "Company": "Unrelated Inc",
                "Agency": "DoD",
                "Branch": "",
                "Phase": "Phase I",
                "Award Year": "2020",
                "Award Amount": "100000",
                "Proposal Award Date": "2020-01-01",
                "Agency Tracking Number": "X",
                "Solicitation Number": "",
                "Solicitation Year": "",
                "City": "",
                "State": "",
                "Zip": "",
                "Contract": "",
            },
        ],
    )
    assert list(build_sbir_award_events(cohort, csv_path)) == []


def test_returns_empty_when_file_missing(cohort, tmp_path):
    assert list(build_sbir_award_events(cohort, tmp_path / "nope.csv")) == []
