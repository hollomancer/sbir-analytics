"""Unit tests for the local USAspending dump download.

Covers URL resolution, the SSD checkpoint sidecar that replaces the S3
`.checkpoints/` prefix, the free-space guard, and Range-based resume.
Network access is always mocked.
"""

import json
from collections import namedtuple
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts.usaspending.download_database import (
    USASPENDING_DB_BASE_URL,
    check_free_space,
    clear_local_checkpoint,
    download_local,
    get_checkpoint_path,
    load_local_checkpoint,
    resolve_source_url,
    save_local_checkpoint,
)

Usage = namedtuple("Usage", "total used free")
URL = f"{USASPENDING_DB_BASE_URL}/usaspending-db_20260101.zip"
BODY = b"x" * 4096


class TestResolveSourceUrl:
    def test_explicit_url_wins(self):
        assert resolve_source_url(source_url="https://example.test/a.zip") == (
            "https://example.test/a.zip"
        )

    def test_builds_url_from_date(self):
        url = resolve_source_url(database_type="full", date_str="20260101")
        assert url == URL

    def test_subset_url_for_test_type(self):
        url = resolve_source_url(database_type="test", date_str="20260101")
        assert "usaspending-db-subset_20260101.zip" in url

    def test_unknown_type_raises(self):
        with pytest.raises(ValueError, match="Unknown database_type"):
            resolve_source_url(database_type="bogus", date_str="20260101")

    def test_discovers_latest_when_no_date(self):
        with patch(
            "scripts.usaspending.download_database.find_latest_available_file",
            return_value={"source_url": URL},
        ):
            assert resolve_source_url(database_type="full") == URL

    def test_raises_when_discovery_finds_nothing(self):
        with patch(
            "scripts.usaspending.download_database.find_latest_available_file",
            return_value=None,
        ):
            with pytest.raises(FileNotFoundError, match="No available full database"):
                resolve_source_url(database_type="full")


class TestCheckpointSidecar:
    def test_path_sits_beside_partial_file(self, tmp_path):
        assert get_checkpoint_path(tmp_path / "dump.zip") == tmp_path / "dump.zip.checkpoint"

    def test_absent_checkpoint_returns_none(self, tmp_path):
        assert load_local_checkpoint(tmp_path / "nope.checkpoint") is None

    def test_roundtrip(self, tmp_path):
        cp = tmp_path / "d.zip.checkpoint"
        save_local_checkpoint(cp, 1234, URL, 9999)

        loaded = load_local_checkpoint(cp)
        assert loaded["bytes_downloaded"] == 1234
        assert loaded["source_url"] == URL
        assert loaded["total_bytes"] == 9999
        assert loaded["timestamp"]

    def test_corrupt_checkpoint_returns_none(self, tmp_path):
        cp = tmp_path / "d.zip.checkpoint"
        cp.write_text("{not json")
        assert load_local_checkpoint(cp) is None

    def test_clear_is_idempotent(self, tmp_path):
        cp = tmp_path / "d.zip.checkpoint"
        save_local_checkpoint(cp, 1, URL, 2)
        clear_local_checkpoint(cp)
        clear_local_checkpoint(cp)  # must not raise
        assert not cp.exists()


class TestFreeSpaceGuard:
    def test_passes_with_headroom(self, tmp_path):
        with patch("shutil.disk_usage", return_value=Usage(100, 0, 100)):
            check_free_space(tmp_path, 10)  # needs 15, has 100

    def test_raises_without_headroom(self, tmp_path):
        with patch("shutil.disk_usage", return_value=Usage(100, 95, 5)):
            with pytest.raises(OSError, match="Insufficient disk space"):
                check_free_space(tmp_path, 10)  # needs 15, has 5

    def test_accounts_for_multiplier(self, tmp_path):
        # 10 bytes free would pass at 1x but not at the 1.5x default.
        with patch("shutil.disk_usage", return_value=Usage(100, 90, 10)):
            with pytest.raises(OSError):
                check_free_space(tmp_path, 10)

    def test_unknown_size_skips_check(self, tmp_path):
        with patch("shutil.disk_usage", side_effect=AssertionError("must not be called")):
            check_free_space(tmp_path, 0)


def _mock_response(body: bytes, status: int = 200):
    resp = MagicMock()
    resp.status_code = status
    resp.iter_content.return_value = [body]
    resp.__enter__ = lambda self: self
    resp.__exit__ = lambda self, *a: False
    return resp


class TestDownloadLocal:
    @pytest.fixture
    def availability(self):
        with patch(
            "scripts.usaspending.download_database.check_file_availability",
            return_value={"available": True, "content_length": len(BODY)},
        ) as m:
            yield m

    def test_downloads_to_dest(self, tmp_path, availability):
        session = MagicMock()
        session.get.return_value = _mock_response(BODY)

        with (
            patch("requests.Session", return_value=session),
            patch("shutil.disk_usage", return_value=Usage(10**9, 0, 10**9)),
        ):
            result = download_local(tmp_path, source_url=URL)

        assert result["status"] == "success"
        written = Path(result["path"])
        assert written.read_bytes() == BODY
        assert written.name == "usaspending-db_20260101.zip"

    def test_clears_checkpoint_on_success(self, tmp_path, availability):
        session = MagicMock()
        session.get.return_value = _mock_response(BODY)

        with (
            patch("requests.Session", return_value=session),
            patch("shutil.disk_usage", return_value=Usage(10**9, 0, 10**9)),
        ):
            result = download_local(tmp_path, source_url=URL)

        assert not get_checkpoint_path(Path(result["path"])).exists()

    def test_unavailable_source_raises(self, tmp_path):
        with patch(
            "scripts.usaspending.download_database.check_file_availability",
            return_value={"available": False, "content_length": None},
        ):
            with pytest.raises(FileNotFoundError, match="not available"):
                download_local(tmp_path, source_url=URL)

    def test_complete_file_is_skipped(self, tmp_path, availability):
        (tmp_path / "usaspending-db_20260101.zip").write_bytes(BODY)

        with patch("requests.Session", side_effect=AssertionError("must not download")):
            result = download_local(tmp_path, source_url=URL)

        assert result["status"] == "skipped"

    def test_partial_file_resumes_with_range_header(self, tmp_path, availability):
        dest = tmp_path / "usaspending-db_20260101.zip"
        (tmp_path / "usaspending-db_20260101.zip.part").write_bytes(BODY[:1000])

        session = MagicMock()
        session.get.return_value = _mock_response(BODY[1000:], status=206)

        with (
            patch("requests.Session", return_value=session),
            patch("shutil.disk_usage", return_value=Usage(10**9, 0, 10**9)),
        ):
            result = download_local(tmp_path, source_url=URL)

        headers = session.get.call_args.kwargs["headers"]
        assert headers["Range"] == "bytes=1000-"
        assert result["status"] == "success"
        assert dest.read_bytes() == BODY

    def test_server_ignoring_range_restarts_cleanly(self, tmp_path, availability):
        dest = tmp_path / "usaspending-db_20260101.zip"
        (tmp_path / "usaspending-db_20260101.zip.part").write_bytes(b"stale" * 200)

        # Range was requested but the server answered 200 with the whole body.
        session = MagicMock()
        session.get.return_value = _mock_response(BODY, status=200)

        with (
            patch("requests.Session", return_value=session),
            patch("shutil.disk_usage", return_value=Usage(10**9, 0, 10**9)),
        ):
            result = download_local(tmp_path, source_url=URL)

        assert result["status"] == "success"
        assert dest.read_bytes() == BODY  # not appended to the stale prefix

    def test_checkpoint_for_other_url_restarts(self, tmp_path, availability):
        dest = tmp_path / "usaspending-db_20260101.zip"
        dest.write_bytes(b"old" * 100)
        save_local_checkpoint(get_checkpoint_path(dest), 300, "https://example.test/other.zip", 999)

        session = MagicMock()
        session.get.return_value = _mock_response(BODY)

        with (
            patch("requests.Session", return_value=session),
            patch("shutil.disk_usage", return_value=Usage(10**9, 0, 10**9)),
        ):
            result = download_local(tmp_path, source_url=URL)

        assert "Range" not in session.get.call_args.kwargs["headers"]
        assert dest.read_bytes() == BODY
        assert result["status"] == "success"

    def test_short_download_raises(self, tmp_path, availability):
        session = MagicMock()
        session.get.return_value = _mock_response(BODY[:100])

        with (
            patch("requests.Session", return_value=session),
            patch("shutil.disk_usage", return_value=Usage(10**9, 0, 10**9)),
        ):
            with pytest.raises(OSError, match="Download incomplete"):
                download_local(tmp_path, source_url=URL)

    def test_incomplete_download_keeps_checkpoint_for_resume(self, tmp_path, availability):
        session = MagicMock()
        session.get.return_value = _mock_response(BODY[:100])

        with (
            patch("requests.Session", return_value=session),
            patch("shutil.disk_usage", return_value=Usage(10**9, 0, 10**9)),
        ):
            with pytest.raises(OSError):
                download_local(tmp_path, source_url=URL)

        cp = get_checkpoint_path(tmp_path / "usaspending-db_20260101.zip")
        assert json.loads(cp.read_text())["bytes_downloaded"] == 100

    def test_force_refresh_discards_existing(self, tmp_path, availability):
        dest = tmp_path / "usaspending-db_20260101.zip"
        dest.write_bytes(BODY)  # already complete

        session = MagicMock()
        session.get.return_value = _mock_response(BODY)

        with (
            patch("requests.Session", return_value=session),
            patch("shutil.disk_usage", return_value=Usage(10**9, 0, 10**9)),
        ):
            result = download_local(tmp_path, source_url=URL, force_refresh=True)

        assert result["status"] == "success"
        session.get.assert_called_once()

    def test_creates_missing_dest(self, tmp_path, availability):
        session = MagicMock()
        session.get.return_value = _mock_response(BODY)

        with (
            patch("requests.Session", return_value=session),
            patch("shutil.disk_usage", return_value=Usage(10**9, 0, 10**9)),
        ):
            download_local(tmp_path / "nested" / "usaspending", source_url=URL)

        assert (tmp_path / "nested" / "usaspending").is_dir()

    def test_insufficient_space_aborts_before_download(self, tmp_path, availability):
        with (
            patch("requests.Session", side_effect=AssertionError("must not download")),
            patch("shutil.disk_usage", return_value=Usage(100, 99, 1)),
        ):
            with pytest.raises(OSError, match="Insufficient disk space"):
                download_local(tmp_path, source_url=URL)


class TestDiscoverySignature:
    """Guards the call into check_new_file against signature drift.

    `find_latest_available_file` lost its `s3_bucket` parameter when the AWS
    paths were removed; the call site kept passing it, so the no-date path
    raised TypeError before any download started.
    """

    def test_no_date_path_calls_current_signature(self):
        from unittest.mock import create_autospec

        import scripts.usaspending.check_new_file as check_new_file

        autospec = create_autospec(check_new_file.find_latest_available_file)
        autospec.return_value = {"source_url": URL}

        with patch("scripts.usaspending.download_database.find_latest_available_file", autospec):
            assert resolve_source_url(database_type="full") == URL

        # An autospec mock raises TypeError on an argument the real function
        # does not accept, so this asserts the call site matches the signature.
        autospec.assert_called_once_with(database_type="full")


class TestPartialIsNotDiscoverable:
    """An in-progress download must not be selectable as a finished dump."""

    def test_incomplete_download_leaves_no_final_name(self, tmp_path):
        from scripts.usaspending.download_database import download_local

        session = MagicMock()
        session.get.return_value = _mock_response(BODY[:100])

        with (
            patch(
                "scripts.usaspending.download_database.check_file_availability",
                return_value={"available": True, "content_length": len(BODY)},
            ),
            patch("requests.Session", return_value=session),
            patch("shutil.disk_usage", return_value=Usage(10**9, 0, 10**9)),
        ):
            with pytest.raises(OSError):
                download_local(tmp_path, source_url=URL)

        assert not (tmp_path / "usaspending-db_20260101.zip").exists()
        assert (tmp_path / "usaspending-db_20260101.zip.part").exists()

    def test_partial_is_invisible_to_dump_discovery(self, tmp_path):
        from sbir_etl.utils.cloud_storage import find_latest_usaspending_dump

        d = tmp_path / "usaspending"
        d.mkdir(parents=True)
        (d / "usaspending-db_20260101.zip.part").write_bytes(b"partial")

        assert find_latest_usaspending_dump(tmp_path, "full") is None
