"""Tests for patent grant event builder."""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "scripts" / "data"))

from capital_events.sources.patents import (  # noqa: E402
    build_patent_events,
    newest_patent_file,
)


def _patent(grant_num, date, linked_companies=None, assignees=None, title="Test patent"):
    return {
        "grant_number": grant_num,
        "latest_recorded_date": date,
        "title": title,
        "language": "en",
        "assignee_names": assignees or ["ACME INC"],
        "assignor_names": [],
        "assignment_count": 0,
        "linked_companies": linked_companies or ["ACME INC"],
    }


def test_newest_patent_file_picks_latest_mtime(tmp_path):
    older = tmp_path / "patents_20240101T000000.jsonl"
    older.write_text("")
    time.sleep(0.01)
    newer = tmp_path / "patents_20240601T000000.jsonl"
    newer.write_text("")
    assert newest_patent_file(tmp_path) == newer


def test_newest_patent_file_returns_none_when_no_files(tmp_path):
    assert newest_patent_file(tmp_path) is None


def test_emits_one_event_per_linked_patent(cohort, tmp_path):
    src = tmp_path / "patents_20260418T142224.jsonl"
    src.write_text("\n".join(json.dumps(p) for p in [
        _patent("11000001", "2023-05-15", linked_companies=["ACME INC"]),
        _patent("11000002", "2024-02-01", linked_companies=["ACME INC"], title="Better patent"),
    ]) + "\n")
    events = list(build_patent_events(cohort, src))
    assert len(events) == 2
    e = events[0]
    assert e["company_name"] == "ACME INC"
    assert e["event_date"] == "2023-05-15"
    assert e["event_type"] == "patent_grant"
    assert e["event_subtype"] is None
    assert e["amount_usd"] is None
    assert e["counterparty"] is None
    assert e["source_id"] == "11000001"
    meta = json.loads(e["metadata"])
    assert meta["title"] == "Test patent"


def test_emits_one_event_per_cohort_firm_when_multiple_linked(cohort, tmp_path):
    """A patent linked to two cohort firms produces two events (joint assignment)."""
    src = tmp_path / "patents_20260418T142224.jsonl"
    src.write_text(json.dumps(_patent(
        "11000003", "2024-01-01",
        linked_companies=["ACME INC", "OUT-OF-STATE CORP"],
    )) + "\n")
    events = list(build_patent_events(cohort, src))
    assert len(events) == 2
    assert {e["company_name"] for e in events} == {"ACME INC", "OUT-OF-STATE CORP"}


def test_skips_patents_not_linked_to_cohort(cohort, tmp_path):
    src = tmp_path / "patents_20260418T142224.jsonl"
    src.write_text(json.dumps(_patent(
        "11000004", "2024-01-01", linked_companies=["UNRELATED INC"],
    )) + "\n")
    assert list(build_patent_events(cohort, src)) == []


def test_returns_empty_when_file_missing(cohort, tmp_path):
    assert list(build_patent_events(cohort, tmp_path / "nope.jsonl")) == []
