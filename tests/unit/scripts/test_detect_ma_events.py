"""Tests for scripts/data/detect_sbir_ma_events.py."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


# Load the script as a module (it lives outside the package tree).
SCRIPT_PATH = Path(__file__).resolve().parents[3] / "scripts" / "data" / "detect_sbir_ma_events.py"
_spec = importlib.util.spec_from_file_location("detect_sbir_ma_events", SCRIPT_PATH)
_mod = importlib.util.module_from_spec(_spec)
sys.modules["detect_sbir_ma_events"] = _mod
_spec.loader.exec_module(_mod)

assign_confidence = _mod.assign_confidence
is_acquirer_side_only = _mod.is_acquirer_side_only
build_signals_dict = _mod.build_signals_dict
extract_efts_signals = _mod.extract_efts_signals
extract_form_d_signals = _mod.extract_form_d_signals
has_business_combination = _mod.has_business_combination
merge_events = _mod.merge_events


def _combo_record(company_name: str, match_confidence: object) -> dict:
    """A form_d_details.jsonl record with one business-combination offering."""
    return {
        "company_name": company_name,
        "match_confidence": match_confidence,
        "offerings": [
            {
                "filing_date": "2020-05-04",
                "is_business_combination": True,
                "total_amount_sold": 2_000_000,
                "related_persons": [],
            }
        ],
    }


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
                    "related_persons": [{"name": "Jane Doe", "title": "Executive Officer"}],
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
    # Tier is "high" on purpose. With a rejected tier the match filter would
    # drop the record before the non-combo branch under test ever runs, and the
    # assertion would pass for the wrong reason.
    records = [
        {
            "company_name": "BORING INC",
            "match_confidence": {"tier": "high"},
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


# --- Form D match-tier filter ---


@pytest.mark.parametrize("tier", ["low", "medium"])
def test_extract_form_d_signals_drops_rejected_tier(tier):
    """The SBIR-to-SEC join is fuzzy; form_d_scoring.py already graded it.

    Before this filter existed, a Form D filed by an unrelated company was
    attributed to an SBIR firm and then graded "high" by assign_confidence,
    which only asks whether a Form D exists.
    """
    records = [_combo_record("MISMATCHED INC", {"tier": tier})]
    assert extract_form_d_signals(records) == []


@pytest.mark.parametrize(
    "match_confidence",
    [
        None,
        {},
        {"tier": None},
        {"tier": ""},
        {"tier": "HIGH"},  # the scorer writes lower-case; the check is exact
    ],
    ids=["null", "empty", "none-tier", "blank-tier", "wrong-case"],
)
def test_extract_form_d_signals_drops_malformed_match_confidence(match_confidence):
    """A record without a usable tier is dropped, not crashed on."""
    records = [_combo_record("MALFORMED INC", match_confidence)]
    assert extract_form_d_signals(records) == []


def test_extract_form_d_signals_drops_record_with_no_match_confidence_key():
    """The key is absent, not just empty. Reading it must not raise."""
    record = _combo_record("NO KEY INC", None)
    del record["match_confidence"]
    assert extract_form_d_signals([record]) == []


def test_extract_form_d_signals_keeps_high_tier_among_rejected():
    """Rejected records must not stop later records from being emitted."""
    records = [
        _combo_record("LOW INC", {"tier": "low"}),
        _combo_record("HIGH INC", {"tier": "high"}),
        _combo_record("MEDIUM INC", {"tier": "medium"}),
    ]
    events = extract_form_d_signals(records)
    assert [e["company_name"] for e in events] == ["HIGH INC"]


def test_extract_form_d_signals_carries_match_scores():
    """The event records which signal earned the high tier.

    ``form_d_scoring.py`` grants "high" on a person match >= 0.7 **or** a ZIP
    match, so "high" alone cannot tell a ZIP-only join from a person-confirmed
    one. Carrying the tier would be constant and therefore useless.
    """
    zip_only = _combo_record(
        "ZIP ONLY INC",
        {"tier": "high", "person_score": None, "address_score": 1.0, "name_score": 0.21},
    )
    person_matched = _combo_record(
        "PERSON INC",
        {"tier": "high", "person_score": 0.92, "address_score": 0.0, "name_score": 0.21},
    )
    events = extract_form_d_signals([zip_only, person_matched])

    assert len(events) == 2
    assert "match_tier" not in events[0]["form_d_detail"]
    assert events[0]["form_d_detail"]["match_person_score"] is None
    assert events[0]["form_d_detail"]["match_address_score"] == 1.0
    assert events[1]["form_d_detail"]["match_person_score"] == 0.92
    assert events[1]["form_d_detail"]["match_address_score"] == 0.0


# --- Drop accounting ---


def test_has_business_combination_counts_the_filter_denominator():
    """main() reports kept vs dropped, so the denominator must ignore tier."""
    records = [
        _combo_record("LOW INC", {"tier": "low"}),
        _combo_record("HIGH INC", {"tier": "high"}),
        {"company_name": "NO OFFERINGS INC", "match_confidence": {"tier": "high"}},
    ]
    combo_records = sum(1 for r in records if has_business_combination(r))
    assert combo_records == 2
    assert combo_records - len(extract_form_d_signals(records)) == 1


# --- Form D date selection ---


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
    fd = [
        {
            "company_name": "ACME",
            "event_date": "2020-03-01",
            "source": "form_d",
            "form_d_detail": {
                "filing_date": "2020-03-01",
                "total_amount_sold": 1e6,
                "combo_count": 1,
                "related_persons": [],
            },
        }
    ]
    efts = [
        {
            "company_name": "ACME",
            "event_date": "2020-01-15",
            "source": "efts",
            "efts_detail": {
                "mention_filers": ["BIG CO"],
                "mention_types": ["ma_definitive"],
                "latest_mention_date": "2020-01-15",
                "efts_tier": "medium",
            },
        }
    ]
    merged = merge_events(fd, efts)
    assert len(merged) == 1
    assert merged[0]["form_d_detail"] is not None
    assert merged[0]["efts_detail"] is not None
    assert merged[0]["event_date"] == "2020-01-15"


def test_merge_events_separate_companies():
    fd = [
        {
            "company_name": "A",
            "event_date": "2020-01-01",
            "source": "form_d",
            "form_d_detail": {
                "filing_date": "2020-01-01",
                "total_amount_sold": None,
                "combo_count": 1,
                "related_persons": [],
            },
        }
    ]
    efts = [
        {
            "company_name": "B",
            "event_date": "2021-06-01",
            "source": "efts",
            "efts_detail": {
                "mention_filers": ["X"],
                "mention_types": ["subsidiary"],
                "latest_mention_date": "2021-06-01",
                "efts_tier": "high",
            },
        }
    ]
    merged = merge_events(fd, efts)
    assert len(merged) == 2


# --- Confidence ---


def test_assign_confidence_form_d_alone_is_low():
    """Superseded 2026-09-09. This asserted "high" and encoded the defect.

    Form D Item 10 is acquirer-side, so the flag is not evidence the SBIR
    firm was acquired and must not grade an exit.
    """
    event = {"form_d_detail": {"filing_date": "2020-01-01"}, "efts_detail": None}
    assert assign_confidence(event) == "low"


def test_assign_confidence_subsidiary_is_high():
    event = {
        "form_d_detail": None,
        "efts_detail": {"mention_types": ["subsidiary", "ma_definitive"]},
    }
    assert assign_confidence(event) == "high"


def test_assign_confidence_acquisition_text_is_medium():
    event = {"form_d_detail": None, "efts_detail": {"mention_types": ["acquisition"]}}
    assert assign_confidence(event) == "medium"


def test_assign_confidence_ma_definitive_alone_is_low():
    event = {"form_d_detail": None, "efts_detail": {"mention_types": ["ma_definitive"]}}
    assert assign_confidence(event) == "low"


def test_assign_confidence_ownership_only_is_low():
    event = {"form_d_detail": None, "efts_detail": {"mention_types": ["ownership_active"]}}
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


def test_form_d_combination_alone_does_not_grade_an_exit() -> None:
    """Form D Item 10 is acquirer-side, so it must not grade an exit.

    It previously returned "high" on its own, ranking a self-reported
    boolean above EFTS full text that names a filer.
    """
    event = {"form_d_detail": {"filing_date": "2020-01-13"}, "efts_detail": None}
    assert assign_confidence(event) == "low"


def test_form_d_combination_is_still_recorded() -> None:
    """Removed from the confidence ladder, retained as a signal.

    It is real evidence of a combination in the other direction, and which
    SBIR firms are acquiring is worth keeping.
    """
    event = {"form_d_detail": {"filing_date": "2020-01-13"}, "efts_detail": None}
    assert build_signals_dict(event)["form_d_business_combination"] is True


def test_efts_evidence_still_grades() -> None:
    """A named-filer EFTS mention keeps its tier; only Form D changed."""
    sub = {"form_d_detail": None, "efts_detail": {"mention_types": ["subsidiary"]}}
    acq = {"form_d_detail": None, "efts_detail": {"mention_types": ["acquisition"]}}
    assert assign_confidence(sub) == "high"
    assert assign_confidence(acq) == "medium"


def test_form_d_does_not_promote_an_efts_medium() -> None:
    """A combination flag beside acquisition text must not lift it to high."""
    event = {
        "form_d_detail": {"filing_date": "2020-01-13"},
        "efts_detail": {"mention_types": ["acquisition"]},
    }
    assert assign_confidence(event) == "medium"


def test_form_d_only_row_is_acquirer_side():
    """Form D Item 10 is acquirer-side; with no EFTS mention there is no
    target-side evidence at all."""
    assert is_acquirer_side_only({"form_d_business_combination": True}) is True


def test_form_d_with_efts_evidence_is_not_excluded():
    """An EFTS mention is target-side evidence and keeps the row in scope."""
    for efts in (
        "efts_subsidiary",
        "efts_ma_definitive",
        "efts_acquisition_text",
        "efts_ma_proxy",
        "efts_ownership_active",
    ):
        signals = {"form_d_business_combination": True, efts: True}
        assert is_acquirer_side_only(signals) is False, efts


def test_row_without_a_form_d_flag_is_never_excluded():
    assert is_acquirer_side_only({"efts_subsidiary": True}) is False
    assert is_acquirer_side_only({}) is False
