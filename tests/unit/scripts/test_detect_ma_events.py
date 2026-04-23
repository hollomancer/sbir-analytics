"""Tests for M&A event detection."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts" / "data"))

from detect_sbir_ma_events import extract_form_d_signals


def test_extract_form_d_signals_finds_business_combination():
    records = [
        {
            "company_name": "ACME INC",
            "match_confidence": {"tier": "high"},
            "offerings": [
                {
                    "filing_date": "2019-03-15",
                    "is_business_combination": True,
                    "total_amount_sold": 25_000_000,
                    "related_persons": [
                        {"name": "Jane Doe", "title": "Executive Officer"}
                    ],
                },
                {
                    "filing_date": "2020-01-01",
                    "is_business_combination": False,
                    "total_amount_sold": 5_000_000,
                    "related_persons": [],
                },
            ],
        }
    ]
    events = extract_form_d_signals(records)
    assert len(events) == 1
    e = events[0]
    assert e["company_name"] == "ACME INC"
    assert e["event_date"] == "2019-03-15"
    assert e["form_d_detail"]["total_amount_sold"] == 25_000_000
    assert e["form_d_detail"]["related_persons"][0]["name"] == "Jane Doe"


def test_extract_form_d_signals_skips_non_combo():
    records = [
        {
            "company_name": "BORING INC",
            "match_confidence": {"tier": "medium"},
            "offerings": [
                {
                    "filing_date": "2020-06-01",
                    "is_business_combination": False,
                    "total_amount_sold": 1_000_000,
                    "related_persons": [],
                }
            ],
        }
    ]
    events = extract_form_d_signals(records)
    assert len(events) == 0


def test_extract_form_d_signals_uses_earliest_combo_date():
    records = [
        {
            "company_name": "MULTI INC",
            "match_confidence": {"tier": "high"},
            "offerings": [
                {
                    "filing_date": "2021-06-01",
                    "is_business_combination": True,
                    "total_amount_sold": 10_000_000,
                    "related_persons": [{"name": "A", "title": "Director"}],
                },
                {
                    "filing_date": "2020-01-15",
                    "is_business_combination": True,
                    "total_amount_sold": 5_000_000,
                    "related_persons": [{"name": "B", "title": "Director"}],
                },
            ],
        }
    ]
    events = extract_form_d_signals(records)
    assert len(events) == 1
    assert events[0]["event_date"] == "2020-01-15"
