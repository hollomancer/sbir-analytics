"""Tests for the NIH RePORTER derived project table."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from sbir_etl.enrichers.nih_reporter.persist import upsert_nih_reporter_awards
from sbir_etl.enrichers.nih_reporter.schema import NIHReporterRecord


pytestmark = pytest.mark.fast


def _record(
    appl_id: str, project_num: str = "1R43AI123456-01", fy: int = 2024
) -> NIHReporterRecord:
    return NIHReporterRecord(appl_id=appl_id, fy=fy, project_num=project_num)


def test_upsert_replaces_one_key_and_keeps_other_appl_ids(tmp_path: Path) -> None:
    dest = tmp_path / "nih_reporter_awards.parquet"
    upsert_nih_reporter_awards(
        [_record("10"), _record("11")],
        award_id="AW-1",
        path=dest,
    )
    upsert_nih_reporter_awards(
        [_record("12")],
        award_id="AW-1",
        path=dest,
    )
    upsert_nih_reporter_awards(
        [_record("20", project_num="1R44CA000001-01")],
        award_id="AW-2",
        path=dest,
    )
    stored = pd.read_parquet(dest)
    assert set(stored["appl_id"]) == {"12", "20"}
    assert set(stored["upsert_key"]) == {"1R43AI123456-01|2024", "1R44CA000001-01|2024"}


def test_empty_records_do_not_write(tmp_path: Path) -> None:
    dest = tmp_path / "nih_reporter_awards.parquet"
    assert upsert_nih_reporter_awards([], award_id="AW-1", path=dest) is None
    assert not dest.exists()


def test_unreadable_existing_file_raises_instead_of_silently_wiping(tmp_path: Path) -> None:
    """A corrupt/unreadable prior file must fail loudly, not be treated as

    empty -- silently swallowing the read error would replace `dest` with
    only the current batch, discarding every previously persisted row.
    """
    dest = tmp_path / "nih_reporter_awards.parquet"
    dest.write_text("not a parquet file")
    with pytest.raises(Exception):  # noqa: B017 - pandas' parquet engine error type
        upsert_nih_reporter_awards([_record("99")], award_id="AW-1", path=dest)
