"""Unit tests for local-first SBIR awards download.

Covers the vintage/history layout and sha256 change detection that replace the
S3 dated-key scheme. Network access is always mocked.
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.data.download_sbir import (
    CSV_NAME,
    META_NAME,
    download_sbir_awards,
    find_latest_vintage,
)

CSV_A = b"award_id,company\n1,Acme\n"
CSV_B = b"award_id,company\n1,Acme\n2,Globex\n"


@pytest.fixture
def fake_fetch():
    """Patch the network fetch, returning whatever payload the test sets."""
    with patch("scripts.data.download_sbir._fetch") as m:
        yield m


def _set(fake_fetch, payload: bytes) -> str:
    import hashlib

    digest = hashlib.sha256(payload).hexdigest()
    fake_fetch.return_value = (payload, digest)
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
        assert vintage_csv.parent.parent == tmp_path / "history"

    def test_writes_metadata_sidecar(self, tmp_path, fake_fetch):
        digest = _set(fake_fetch, CSV_A)

        result = download_sbir_awards(tmp_path)

        meta = json.loads((Path(result["vintage"]) / META_NAME).read_text())
        assert meta["sha256"] == digest
        assert meta["size"] == len(CSV_A)
        assert meta["source_url"].startswith("http")
        assert meta["downloaded_at"]

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
        assert [d.name for d in (tmp_path / "history").iterdir()] == [Path(first["vintage"]).name]

    def test_changed_payload_creates_new_vintage(self, tmp_path, fake_fetch):
        _set(fake_fetch, CSV_A)
        download_sbir_awards(tmp_path)

        _set(fake_fetch, CSV_B)
        # Force a distinct vintage date so the two do not collide.
        with patch("scripts.data.download_sbir.datetime") as dt:
            dt.now.return_value.strftime.return_value = "2026-01-02"
            dt.now.return_value.isoformat.return_value = "2026-01-02T00:00:00+00:00"
            result = download_sbir_awards(tmp_path)

        assert result["changed"] is True
        assert (tmp_path / CSV_NAME).read_bytes() == CSV_B
        assert len(list((tmp_path / "history").iterdir())) == 2

    def test_missing_sidecar_forces_redownload(self, tmp_path, fake_fetch):
        _set(fake_fetch, CSV_A)
        first = download_sbir_awards(tmp_path)
        (Path(first["vintage"]) / META_NAME).unlink()

        result = download_sbir_awards(tmp_path)

        assert result["changed"] is True

    def test_corrupt_sidecar_forces_redownload(self, tmp_path, fake_fetch):
        _set(fake_fetch, CSV_A)
        first = download_sbir_awards(tmp_path)
        (Path(first["vintage"]) / META_NAME).write_text("{not json")

        result = download_sbir_awards(tmp_path)

        assert result["changed"] is True


class TestFindLatestVintage:
    def test_returns_none_when_absent(self, tmp_path):
        assert find_latest_vintage(tmp_path / "history") is None

    def test_ignores_vintage_without_csv(self, tmp_path):
        history = tmp_path / "history"
        (history / "2026-01-01").mkdir(parents=True)
        assert find_latest_vintage(history) is None

    def test_picks_newest_by_date_name(self, tmp_path):
        history = tmp_path / "history"
        for date in ("2026-01-01", "2026-03-05", "2026-02-09"):
            d = history / date
            d.mkdir(parents=True)
            (d / CSV_NAME).write_bytes(CSV_A)

        assert find_latest_vintage(history).name == "2026-03-05"


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
