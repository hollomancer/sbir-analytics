"""Tests for the CA-organized cohort filter."""

import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "scripts" / "data"))

from ucc.cohort_state_filter import (  # noqa: E402
    is_ca_organized,
    narrow_to_ca_organized,
    pick_best_match,
)


def test_ca_organized_when_california_domestic():
    record = {"FORMED_IN": "CALIFORNIA", "ENTITY_TYPE": "Stock Corporation - CA - Stock"}
    assert is_ca_organized(record) is True


def test_ca_organized_when_california_llc():
    record = {"FORMED_IN": "CALIFORNIA", "ENTITY_TYPE": "Limited Liability Company"}
    assert is_ca_organized(record) is True


def test_not_ca_organized_when_foreign_in_ca():
    record = {"FORMED_IN": "CALIFORNIA", "ENTITY_TYPE": "Stock Corporation - Out of State - Stock"}
    assert is_ca_organized(record) is False


def test_not_ca_organized_when_formed_in_delaware():
    record = {"FORMED_IN": "DELAWARE", "ENTITY_TYPE": "Stock Corporation - Out of State - Stock"}
    assert is_ca_organized(record) is False


def test_not_ca_organized_when_record_none():
    assert is_ca_organized(None) is False


def test_not_ca_organized_when_record_empty():
    assert is_ca_organized({}) is False


def test_pick_best_match_prefers_active_status():
    rows = {
        "1": {"STATUS": "Terminated", "FORMED_IN": "CALIFORNIA"},
        "2": {"STATUS": "Active", "FORMED_IN": "CALIFORNIA"},
    }
    best = pick_best_match(rows)
    assert best["STATUS"] == "Active"


def test_pick_best_match_returns_none_for_empty():
    assert pick_best_match({}) is None


def test_pick_best_match_returns_first_active_then_first_overall():
    rows = {
        "1": {"STATUS": "Terminated", "SORT_INDEX": 1, "FORMED_IN": "CALIFORNIA"},
        "2": {"STATUS": "Terminated", "SORT_INDEX": 0, "FORMED_IN": "CALIFORNIA"},
    }
    # No Active — should return SORT_INDEX 0
    best = pick_best_match(rows)
    assert best["SORT_INDEX"] == 0


def test_narrow_to_ca_organized_keeps_ca_drops_de():
    cohort = [
        {"company_name": "CA Co", "state": "CA"},
        {"company_name": "DE Co", "state": "CA"},
        {"company_name": "No Match Co", "state": "TX"},
    ]
    lookups = iter([
        {"FORMED_IN": "CALIFORNIA", "ENTITY_TYPE": "Limited Liability Company"},
        {"FORMED_IN": "DELAWARE", "ENTITY_TYPE": "Stock Corporation - Out of State - Stock"},
        None,
    ])
    fn = MagicMock(side_effect=lambda name: next(lookups))

    kept, lookups_done = narrow_to_ca_organized(cohort, lookup_fn=fn, delay_seconds=0)
    assert [r["company_name"] for r in kept] == ["CA Co"]
    assert lookups_done == 3


def test_narrow_to_ca_organized_skips_checkpointed(tmp_path):
    cohort = [
        {"company_name": "CA Co", "state": "CA"},
        {"company_name": "Skip Me", "state": "CA"},
    ]
    checkpoint = tmp_path / "ckpt.jsonl"
    # Pre-populate checkpoint with "Skip Me" as CA-organized
    import json
    checkpoint.write_text(json.dumps({
        "company_name": "Skip Me",
        "is_ca_organized": True,
        "business_record": {"FORMED_IN": "CALIFORNIA", "ENTITY_TYPE": "LLC"},
    }) + "\n")

    lookups = iter([
        {"FORMED_IN": "CALIFORNIA", "ENTITY_TYPE": "LLC"},
    ])
    fn = MagicMock(side_effect=lambda name: next(lookups))

    kept, lookups_done = narrow_to_ca_organized(
        cohort, lookup_fn=fn, delay_seconds=0, checkpoint_path=checkpoint,
    )
    names = [r["company_name"] for r in kept]
    assert "CA Co" in names
    assert "Skip Me" in names  # restored from checkpoint
    assert lookups_done == 1   # only CA Co triggered a lookup
