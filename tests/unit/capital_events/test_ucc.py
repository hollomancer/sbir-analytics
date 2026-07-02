"""Tests for UCC capital-event builder."""

import json


from sbir_etl.capital_events.sources.ucc import build_ucc_events


def test_returns_empty_when_file_missing(cohort, tmp_path):
    missing = tmp_path / "nope.jsonl"
    events = list(build_ucc_events(cohort, missing))
    assert events == []


def test_yields_one_event_per_match(cohort, tmp_path):
    src = tmp_path / "ucc1_pilot_matches.jsonl"
    src.write_text(
        json.dumps(
            {
                "cohort_company_name": "ACME INC",
                "match_confidence": "high",
                "match_score": 1.0,
                "filing": {
                    "filing_number": "U240107248023",
                    "filing_type": "initial",
                    "filing_date": "2024-01-30",
                    "debtor_name": "ACME INC",
                    "debtor_address": "SAN DIEGO, CA",
                    "secured_party_name": "LEAF CAPITAL FUNDING, LLC",
                    "secured_party_address": "PHILADELPHIA, PA",
                    "status_portal": "Active",
                    "lapse_date": "2029-01-30",
                    "source": "CA",
                },
            }
        )
        + "\n"
    )

    events = list(build_ucc_events(cohort, src))
    assert len(events) == 1
    e = events[0]
    assert e["company_name"] == "ACME INC"
    assert e["event_date"] == "2024-01-30"
    assert e["event_type"] == "ucc_filing"
    assert e["event_subtype"] == "initial"
    assert e["amount_usd"] is None
    assert e["counterparty"] == "LEAF CAPITAL FUNDING, LLC"
    assert e["source_id"] == "U240107248023"
    meta = json.loads(e["metadata"])
    assert meta["secured_party_address"] == "PHILADELPHIA, PA"
    assert meta["match_confidence"] == "high"


def test_skips_filings_for_non_cohort_firms(cohort, tmp_path):
    src = tmp_path / "ucc1_pilot_matches.jsonl"
    src.write_text(
        json.dumps(
            {
                "cohort_company_name": "UNRELATED INC",
                "match_confidence": "high",
                "match_score": 1.0,
                "filing": {
                    "filing_number": "X",
                    "filing_type": "initial",
                    "filing_date": "2024-01-01",
                    "debtor_name": "UNRELATED INC",
                    "debtor_address": "",
                    "secured_party_name": "BANK",
                    "secured_party_address": "",
                    "status_portal": "Active",
                    "lapse_date": None,
                    "source": "CA",
                },
            }
        )
        + "\n"
    )
    assert list(build_ucc_events(cohort, src)) == []
