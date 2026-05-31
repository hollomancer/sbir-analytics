"""End-to-end test for the capital-events orchestrator."""

import csv
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd


def _write_cohort(path: Path, rows: list[dict]) -> None:
    with path.open("w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def test_orchestrator_end_to_end(tmp_path, monkeypatch):
    """Synthetic data in all 5 active sources → parquet output with expected rows."""
    monkeypatch.setenv("SBIR_DATA_DIR", str(tmp_path))

    cohort_path = tmp_path / "form_d_high_conf_cohort.jsonl"
    _write_cohort(
        cohort_path,
        [
            {
                "company_name": "ACME INC",
                "state": "California",
                "city": "SAN DIEGO",
                "zip_code": "92101",
                "agency": "Department of Defense",
                "first_award_year": 2018,
                "last_award_year": 2023,
                "total_award_amount": 1_500_000.0,
                "form_d_filing_count": 1,
                "form_d_total_raised": 25_000_000.0,
            }
        ],
    )

    awards_path = tmp_path / "raw" / "sbir" / "award_data.csv"
    awards_path.parent.mkdir(parents=True, exist_ok=True)
    with awards_path.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
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
            ],
        )
        w.writeheader()
        w.writerow(
            {
                "Company": "Acme Inc",
                "Agency": "Department of Defense",
                "Branch": "Army",
                "Phase": "Phase II",
                "Award Year": "2020",
                "Award Amount": "1000000",
                "Proposal Award Date": "2020-09-01",
                "Agency Tracking Number": "ATN-1",
                "Solicitation Number": "S1",
                "Solicitation Year": "2020",
                "City": "San Diego",
                "State": "California",
                "Zip": "92101",
                "Contract": "C1",
            }
        )

    form_d_path = tmp_path / "form_d_details.jsonl"
    form_d_path.write_text(
        json.dumps(
            {
                "company_name": "ACME INC",
                "match_confidence": {"tier": "high", "person_score": 1.0, "address_score": 1},
                "total_raised": 5_000_000.0,
                "offering_count": 1,
                "form_d_cik": "0001",
                "offerings": [
                    {
                        "accession_number": "A1",
                        "filing_date": "2023-01-15",
                        "total_amount_sold": 5_000_000.0,
                        "securities_types": ["Equity"],
                        "is_business_combination": False,
                        "is_amendment": False,
                        "minimum_investment": 25000,
                        "num_investors": 5,
                        "related_persons": [],
                    }
                ],
            }
        )
        + "\n"
    )

    ma_path = tmp_path / "enriched_sbir_ma_events.jsonl"
    ma_path.write_text(
        json.dumps(
            {
                "company_name": "ACME INC",
                "event_date": "2024-02-01",
                "confidence": "high",
                "acquirer": "GiantCo",
                "signals": {},
                "press_wire_signals": {},
                "signal_count": 1,
                "form_d_detail": None,
                "efts_detail": None,
                "sbir_context": {"agency": "DoD"},
                "enriched": True,
            }
        )
        + "\n"
    )

    us_dir = tmp_path / "processed" / "sbir_phase3"
    us_dir.mkdir(parents=True, exist_ok=True)
    (us_dir / "usaspending_phase3_contracts.jsonl").write_text(
        json.dumps(
            {
                "Recipient Name": "ACME INC",
                "Award ID": "AW1",
                "Award Amount": 2_000_000.0,
                "Start Date": "2022-06-01",
                "End Date": "",
                "Funding Agency": "Department of Defense",
                "Funding Sub Agency": "Army",
                "Awarding Agency": "Department of Defense",
                "Awarding Sub Agency": "Army",
                "Description": "Phase III",
                "NAICS": "541715",
                "generated_internal_id": "GEN1",
                "internal_id": "INT1",
                "agency_slug": "dod",
                "awarding_agency_id": 9700,
            }
        )
        + "\n"
    )

    pat_dir = tmp_path / "transformed" / "uspto"
    pat_dir.mkdir(parents=True, exist_ok=True)
    (pat_dir / "patents_20260418T142224.jsonl").write_text(
        json.dumps(
            {
                "grant_number": "11000001",
                "latest_recorded_date": "2023-05-15",
                "title": "Test",
                "language": "en",
                "assignee_names": ["ACME INC"],
                "assignor_names": [],
                "assignment_count": 0,
                "linked_companies": ["ACME INC"],
            }
        )
        + "\n"
    )

    result = subprocess.run(
        [sys.executable, "scripts/data/build_capital_events.py"],
        env={"SBIR_DATA_DIR": str(tmp_path), "PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"orchestrator failed:\n{result.stderr}"

    events_parquet = tmp_path / "capital_events.parquet"
    summary_parquet = tmp_path / "capital_events_per_firm.parquet"
    sample_jsonl = tmp_path / "capital_events_sample.jsonl"
    assert events_parquet.exists()
    assert summary_parquet.exists()
    assert sample_jsonl.exists()

    events = pd.read_parquet(events_parquet)
    assert set(events.columns) == {
        "company_name",
        "event_date",
        "event_type",
        "event_subtype",
        "amount_usd",
        "counterparty",
        "source_id",
        "metadata",
    }
    assert len(events) == 5
    assert set(events["event_type"]) == {
        "sbir_award",
        "form_d_filing",
        "ma_event",
        "usaspending_contract",
        "patent_grant",
    }
    assert events["event_date"].is_monotonic_increasing  # all same firm

    summary = pd.read_parquet(summary_parquet)
    assert len(summary) == 1
    row = summary.iloc[0]
    assert row["company_name"] == "ACME INC"
    assert row["sbir_award_count"] == 1
    assert row["form_d_filing_count"] == 1
    assert row["ma_event_count"] == 1
    assert row["usaspending_contract_count"] == 1
    assert row["patent_count"] == 1
    assert bool(row["has_ma_event"]) is True
    assert bool(row["has_ucc_match"]) is False
