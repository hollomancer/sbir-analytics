"""Tests for M&A event detection."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts" / "data"))

from detect_sbir_ma_events import (
    assign_confidence,
    build_signals_dict,
    extract_efts_signals,
    extract_form_d_signals,
    merge_events,
)


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


# --- EFTS extraction ---


def test_extract_efts_signals_subsidiary():
    records = [
        {
            "company_name": "TARGET INC",
            "mention_types": ["subsidiary", "filing_mention"],
            "mention_filers": ["BIG CORP"],
            "latest_mention_date": "2020-06-15",
        }
    ]
    events = extract_efts_signals(records)
    assert len(events) == 1
    assert events[0]["efts_detail"]["efts_tier"] == "high"
    assert events[0]["efts_detail"]["mention_filers"] == ["BIG CORP"]


def test_extract_efts_signals_skips_passive():
    records = [
        {
            "company_name": "PASSIVE INC",
            "mention_types": ["ownership_passive"],
            "mention_filers": ["FUND LP"],
            "latest_mention_date": "2021-01-01",
        }
    ]
    events = extract_efts_signals(records)
    assert len(events) == 0


def test_extract_efts_signals_no_ma_types():
    records = [
        {
            "company_name": "BORING INC",
            "mention_types": ["filing_mention", "disclosure"],
            "mention_filers": ["SOMEONE"],
            "latest_mention_date": "2020-01-01",
        }
    ]
    events = extract_efts_signals(records)
    assert len(events) == 0


# --- Merge ---


def test_merge_events_both_sources():
    fd = [{"company_name": "ACME", "event_date": "2020-03-01", "source": "form_d",
           "form_d_detail": {"filing_date": "2020-03-01", "total_amount_sold": 1e6,
                             "combo_count": 1, "related_persons": []}}]
    efts = [{"company_name": "ACME", "event_date": "2020-01-15", "source": "efts",
             "efts_detail": {"mention_filers": ["BIG CO"], "mention_types": ["ma_definitive"],
                             "latest_mention_date": "2020-01-15", "efts_tier": "medium"}}]
    merged = merge_events(fd, efts)
    assert len(merged) == 1
    assert merged[0]["form_d_detail"] is not None
    assert merged[0]["efts_detail"] is not None
    assert merged[0]["event_date"] == "2020-01-15"


def test_merge_events_separate_companies():
    fd = [{"company_name": "A", "event_date": "2020-01-01", "source": "form_d",
           "form_d_detail": {"filing_date": "2020-01-01", "total_amount_sold": None,
                             "combo_count": 1, "related_persons": []}}]
    efts = [{"company_name": "B", "event_date": "2021-06-01", "source": "efts",
             "efts_detail": {"mention_filers": ["X"], "mention_types": ["subsidiary"],
                             "latest_mention_date": "2021-06-01", "efts_tier": "high"}}]
    merged = merge_events(fd, efts)
    assert len(merged) == 2


# --- Confidence ---


def test_assign_confidence_form_d_is_high():
    event = {"form_d_detail": {"filing_date": "2020-01-01"}, "efts_detail": None}
    assert assign_confidence(event) == "high"


def test_assign_confidence_subsidiary_is_high():
    event = {"form_d_detail": None,
             "efts_detail": {"mention_types": ["subsidiary", "ma_definitive"]}}
    assert assign_confidence(event) == "high"


def test_assign_confidence_ma_definitive_only_is_medium():
    event = {"form_d_detail": None,
             "efts_detail": {"mention_types": ["ma_definitive"]}}
    assert assign_confidence(event) == "medium"


def test_assign_confidence_ownership_only_is_low():
    event = {"form_d_detail": None,
             "efts_detail": {"mention_types": ["ownership_active"]}}
    assert assign_confidence(event) == "low"


# --- Signals dict ---


def test_build_signals_dict():
    event = {
        "form_d_detail": {"filing_date": "2020-01-01"},
        "efts_detail": {"mention_types": ["subsidiary", "ma_definitive"]},
    }
    signals = build_signals_dict(event)
    assert signals["form_d_business_combination"] is True
    assert signals["efts_subsidiary"] is True
    assert signals["efts_ma_definitive"] is True
    assert signals["efts_acquisition_text"] is False
