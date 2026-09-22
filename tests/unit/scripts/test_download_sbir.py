"""Unit tests for local-first, pinned SBIR award-export capture."""

import csv
import io
import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from sbir_etl.extractors.source_downloads.sbir import (
    CSV_NAME,
    LEGACY_VINTAGE_DIR,
    META_NAME,
    VINTAGE_DIR,
    download_sbir_awards,
    find_latest_vintage,
)
from sbir_etl.extractors.sbir_award_export import SBIR_GOV_SOURCE_COLUMNS


def _csv_bytes(companies: list[str]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(SBIR_GOV_SOURCE_COLUMNS)
    for index, company in enumerate(companies, start=1):
        values = dict.fromkeys(SBIR_GOV_SOURCE_COLUMNS, "")
        values.update(
            {
                "Company": company,
                "Agency Tracking Number": f"TRACK-{index}",
                "Award Year": "2026",
                "Award Amount": "1",
            }
        )
        writer.writerow([values[column] for column in SBIR_GOV_SOURCE_COLUMNS])
    return output.getvalue().encode("utf-8")


CSV_A = _csv_bytes(["Acme"])
CSV_B = _csv_bytes(["Acme", "Globex"])


@pytest.fixture
def fake_fetch():
    """Patch the network fetch, returning whatever payload the test sets."""
    with patch("sbir_etl.extractors.source_downloads.sbir._fetch") as m:
        yield m


def _set(fake_fetch, payload: bytes) -> str:
    import hashlib

    digest = hashlib.sha256(payload).hexdigest()
    fake_fetch.return_value = (payload, digest, {})
    return digest


class TestFirstDownload:
    def test_writes_canonical_and_vintage(self, tmp_path, fake_fetch):
        digest = _set(fake_fetch, CSV_A)

        result = download_sbir_awards(tmp_path)

        assert result["changed"] is True
        assert result["sha256"] == digest

        canonical = tmp_path / CSV_NAME
        assert canonical.read_bytes() == CSV_A

        vintage_csv = Path(result["vintage"]) / CSV_NAME
        assert vintage_csv.read_bytes() == CSV_A
        assert vintage_csv.parent.parent == tmp_path / VINTAGE_DIR

    def test_writes_metadata_sidecar(self, tmp_path, fake_fetch):
        digest = _set(fake_fetch, CSV_A)

        result = download_sbir_awards(tmp_path)

        meta = json.loads((Path(result["vintage"]) / META_NAME).read_text())
        assert meta["sha256"] == digest
        assert meta["size_bytes"] == len(CSV_A)
        assert meta["row_count"] == 1
        assert meta["column_count"] == 42
        assert len(meta["ordered_schema_sha256"]) == 64
        assert meta["source_url"].startswith("http")
        assert meta["retrieved_at"]
        assert meta["operator_identity"] == "automation:sbir-awards-download"

    def test_creates_missing_destination(self, tmp_path, fake_fetch):
        _set(fake_fetch, CSV_A)
        dest = tmp_path / "nested" / "sbir"

        download_sbir_awards(dest)

        assert (dest / CSV_NAME).is_file()


class TestChangeDetection:
    def test_unchanged_payload_is_not_rewritten(self, tmp_path, fake_fetch):
        _set(fake_fetch, CSV_A)
        first = download_sbir_awards(tmp_path)

        second = download_sbir_awards(tmp_path)

        assert second["changed"] is False
        # No second vintage directory was created.
        assert [d.name for d in (tmp_path / VINTAGE_DIR).iterdir()] == [Path(first["vintage"]).name]

    def test_changed_payload_creates_new_vintage(self, tmp_path, fake_fetch):
        with patch(
            "sbir_etl.extractors.source_downloads.sbir._utc_now",
            side_effect=(
                datetime(2026, 9, 21, tzinfo=UTC),
                datetime(2026, 9, 22, tzinfo=UTC),
            ),
        ):
            _set(fake_fetch, CSV_A)
            download_sbir_awards(tmp_path)

            _set(fake_fetch, CSV_B)
            result = download_sbir_awards(tmp_path)

        assert result["changed"] is True
        assert (tmp_path / CSV_NAME).read_bytes() == CSV_B
        assert len(list((tmp_path / VINTAGE_DIR).iterdir())) == 2

    def test_missing_sidecar_refuses_same_day_overwrite(self, tmp_path, fake_fetch):
        _set(fake_fetch, CSV_A)
        first = download_sbir_awards(tmp_path)
        (Path(first["vintage"]) / META_NAME).unlink()

        with pytest.raises(FileExistsError, match="refusing to overwrite"):
            download_sbir_awards(tmp_path)

    def test_corrupt_sidecar_refuses_same_day_overwrite(self, tmp_path, fake_fetch):
        _set(fake_fetch, CSV_A)
        first = download_sbir_awards(tmp_path)
        (Path(first["vintage"]) / META_NAME).write_text("{not json")

        with pytest.raises(FileExistsError, match="refusing to overwrite"):
            download_sbir_awards(tmp_path)

    def test_changed_payload_refuses_same_day_overwrite(self, tmp_path, fake_fetch):
        _set(fake_fetch, CSV_A)
        download_sbir_awards(tmp_path)
        _set(fake_fetch, CSV_B)

        with pytest.raises(FileExistsError, match="refusing to overwrite"):
            download_sbir_awards(tmp_path)


class TestFindLatestVintage:
    def test_returns_none_when_absent(self, tmp_path):
        assert find_latest_vintage(tmp_path / VINTAGE_DIR) is None

    def test_ignores_vintage_without_csv(self, tmp_path):
        history = tmp_path / VINTAGE_DIR
        (history / "2026-01-01").mkdir(parents=True)
        assert find_latest_vintage(history) is None

    def test_picks_newest_by_date_name(self, tmp_path):
        history = tmp_path / VINTAGE_DIR
        for date in ("2026-01-01", "2026-03-05", "2026-02-09"):
            d = history / date
            d.mkdir(parents=True)
            (d / CSV_NAME).write_bytes(CSV_A)

        assert find_latest_vintage(history).name == "2026-03-05"

    def test_legacy_history_remains_undisturbed(self, tmp_path):
        legacy = tmp_path / LEGACY_VINTAGE_DIR / "2026-01-01"
        legacy.mkdir(parents=True)
        (legacy / CSV_NAME).write_bytes(CSV_A)

        assert find_latest_vintage(tmp_path / LEGACY_VINTAGE_DIR) == legacy


class TestCanonicalRepair:
    """An unchanged upstream must still repair a bad canonical file."""

    def test_missing_canonical_is_recreated(self, tmp_path, fake_fetch):
        _set(fake_fetch, CSV_A)
        download_sbir_awards(tmp_path)
        (tmp_path / CSV_NAME).unlink()

        result = download_sbir_awards(tmp_path)

        assert result["changed"] is False
        assert (tmp_path / CSV_NAME).read_bytes() == CSV_A

    def test_truncated_canonical_is_repaired(self, tmp_path, fake_fetch):
        _set(fake_fetch, CSV_A)
        download_sbir_awards(tmp_path)
        (tmp_path / CSV_NAME).write_bytes(CSV_A[:3])

        result = download_sbir_awards(tmp_path)

        assert result["changed"] is False
        assert (tmp_path / CSV_NAME).read_bytes() == CSV_A

    def test_intact_canonical_is_left_alone(self, tmp_path, fake_fetch):
        _set(fake_fetch, CSV_A)
        download_sbir_awards(tmp_path)

        result = download_sbir_awards(tmp_path)

        assert result["changed"] is False
        assert (tmp_path / CSV_NAME).read_bytes() == CSV_A
