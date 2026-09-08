"""Tests for SBIR.gov → NIH RePORTER request building."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from sbir_etl.enrichers.nih_reporter.requests import (
    build_nih_reporter_requests,
    frame_to_nih_requests,
    is_nih_reporter_agency,
    load_sbir_award_frame,
    nih_ids_needing_refresh,
)
from sbir_etl.models.enrichment import EnrichmentFreshnessRecord, EnrichmentStatus
from sbir_etl.utils.enrichment.freshness import FreshnessStore


pytestmark = pytest.mark.fast


def _award(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "award_id": "AW-NIH-1",
        "agency": "HHS",
        "branch": "NIAID",
        "contract_number": "1 R43 AI123456-01",
        "agency_tracking_number": "R43AI123456",
        "award_year": 2024,
        "company": "Example Biotech",
    }
    row.update(overrides)
    return row


def test_build_requests_canonicalizes_keys_and_keeps_year() -> None:
    requests, skipped = build_nih_reporter_requests(pd.DataFrame([_award()]))

    assert skipped == 0
    assert requests == [
        {
            "award_id": "AW-NIH-1",
            "project_num": "1R43AI123456-01",
            "project_nums": ["1R43AI123456-01", "R43AI123456"],
            "award_year": 2024,
        }
    ]


def test_non_nih_agencies_are_ignored() -> None:
    requests, skipped = build_nih_reporter_requests(
        pd.DataFrame([_award(agency="DOD", branch="NAVY", award_id="AW-DOD")])
    )
    assert requests == []
    assert skipped == 0


def test_rows_without_project_key_or_year_are_skipped() -> None:
    frame = pd.DataFrame(
        [
            _award(contract_number=None, agency_tracking_number=None, award_id="AW-NO-KEY"),
            _award(award_year=None, award_id="AW-NO-YEAR"),
            _award(agency="NIH", branch=None, award_id="AW-OK"),
        ]
    )
    requests, skipped = build_nih_reporter_requests(frame)
    assert skipped == 2
    assert [request["award_id"] for request in requests] == ["AW-OK"]


def test_fy_window_restricts_award_year_not_calendar_dates() -> None:
    frame = pd.DataFrame(
        [
            _award(award_id="AW-2024", award_year=2024),
            _award(award_id="AW-2019", award_year=2019),
        ]
    )
    requests, skipped = build_nih_reporter_requests(frame, window="fy:2023-2024")
    assert skipped == 0
    assert [request["award_id"] for request in requests] == ["AW-2024"]
    assert "window" not in requests[0]


def test_date_window_is_attached_as_criteria_not_a_local_filter() -> None:
    frame = pd.DataFrame(
        [
            _award(award_id="AW-2024", award_year=2024),
            _award(award_id="AW-2019", award_year=2019),
        ]
    )
    requests, skipped = build_nih_reporter_requests(frame, window="2024-01-01:2024-12-31")
    assert skipped == 0
    assert [request["award_id"] for request in requests] == ["AW-2024", "AW-2019"]
    assert all(request["window"] == "2024-01-01:2024-12-31" for request in requests)


def test_company_name_is_not_a_join_key() -> None:
    requests, _skipped = build_nih_reporter_requests(
        pd.DataFrame([_award(company="Totally Different Name LLC")])
    )
    assert "company" not in requests[0]


@pytest.mark.parametrize(
    ("agency", "branch", "expected"),
    [
        ("HHS", "NIAID", True),
        ("NIH", None, True),
        ("DOD", "NAVY", False),
        ("NSF", None, False),
        ("HHS", "NCI", True),
    ],
)
def test_agency_allowlist(agency: str | None, branch: str | None, expected: bool) -> None:
    assert is_nih_reporter_agency(agency, branch) is expected


def test_missing_sbir_frame_fails_clearly(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="SBIR.gov award CSV"):
        load_sbir_award_frame(tmp_path / "missing.csv")


def test_empty_ledger_selects_every_eligible_id(tmp_path: Path) -> None:
    store = FreshnessStore(tmp_path / "freshness.parquet")
    assert nih_ids_needing_refresh(store, ["AW-1", "AW-2"], sla=7) == {"AW-1", "AW-2"}


def test_fresh_ledger_row_is_skipped_unseen_is_kept(tmp_path: Path) -> None:
    store = FreshnessStore(tmp_path / "freshness.parquet")
    store.save_record(
        EnrichmentFreshnessRecord(
            award_id="AW-1",
            source="nih_reporter",
            last_attempt_at=pd.Timestamp.now().to_pydatetime(),
            last_success_at=pd.Timestamp.now().to_pydatetime(),
            status=EnrichmentStatus.SUCCESS,
        )
    )
    assert nih_ids_needing_refresh(store, ["AW-1", "AW-2"], sla=7) == {"AW-2"}


def test_frame_round_trip_preserves_project_keys() -> None:
    requests, _skipped = build_nih_reporter_requests(pd.DataFrame([_award()]))
    assert frame_to_nih_requests(pd.DataFrame(requests)) == requests
