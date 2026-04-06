"""Unit tests for cloud storage utilities."""

import os
from datetime import datetime, timedelta, UTC
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.fast

from sbir_etl.utils.cloud_storage import (
    SbirAwardsSource,
    build_s3_path,
    check_sbir_data_freshness,
    get_s3_bucket_from_env,
    resolve_data_path,
)


class TestResolveDataPath:
    """Tests for resolve_data_path function."""

    def test_resolve_local_path_exists(self, tmp_path):
        """Test resolve_data_path with existing local path."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")

        result = resolve_data_path(test_file)

        assert result == test_file
        assert result.exists()

    def test_resolve_local_path_with_fallback(self, tmp_path):
        """Test resolve_data_path uses fallback when main path doesn't exist."""
        main_path = tmp_path / "nonexistent.txt"
        fallback = tmp_path / "fallback.txt"
        fallback.write_text("fallback content")

        result = resolve_data_path(main_path, local_fallback=fallback)

        assert result == fallback

    def test_resolve_local_path_raises_when_not_found(self, tmp_path):
        """Test resolve_data_path raises when neither path exists."""
        main_path = tmp_path / "nonexistent.txt"
        fallback = tmp_path / "also_nonexistent.txt"

        with pytest.raises(FileNotFoundError):
            resolve_data_path(main_path, local_fallback=fallback)

    def test_resolve_prefer_local(self, tmp_path):
        """Test resolve_data_path prefers local when prefer_local=True."""
        local_file = tmp_path / "local.txt"
        local_file.write_text("local content")

        with patch("sbir_etl.utils.cloud_storage.S3Path") as mock_s3:
            result = resolve_data_path(
                "s3://bucket/path.txt", local_fallback=local_file, prefer_local=True
            )

            assert result == local_file
            mock_s3.assert_not_called()

    @patch("sbir_etl.utils.cloud_storage.S3Path")
    def test_resolve_s3_path_exists(self, mock_s3_path_class, tmp_path):
        """Test resolve_data_path with existing S3 path."""
        mock_s3_path = MagicMock()
        mock_s3_path.exists.return_value = True
        mock_s3_path.name = "test.txt"
        mock_s3_path_class.return_value = mock_s3_path

        with patch("sbir_etl.utils.cloud_storage._download_s3_to_temp") as mock_download:
            mock_download.return_value = tmp_path / "downloaded.txt"

            result = resolve_data_path("s3://bucket/path.txt")

            assert result == tmp_path / "downloaded.txt"
            mock_s3_path_class.assert_called_once_with("s3://bucket/path.txt")

    @patch("sbir_etl.utils.cloud_storage.S3Path")
    def test_resolve_s3_path_fallback_to_local(self, mock_s3_path_class, tmp_path):
        """Test resolve_data_path falls back to local when S3 fails."""
        mock_s3_path = MagicMock()
        mock_s3_path.exists.side_effect = Exception("S3 error")
        mock_s3_path_class.return_value = mock_s3_path

        local_fallback = tmp_path / "fallback.txt"
        local_fallback.write_text("fallback")

        result = resolve_data_path("s3://bucket/path.txt", local_fallback=local_fallback)

        assert result == local_fallback

    @patch("sbir_etl.utils.cloud_storage.S3Path")
    def test_resolve_s3_path_raises_when_both_fail(self, mock_s3_path_class):
        """Test resolve_data_path raises when both S3 and local fail."""
        mock_s3_path = MagicMock()
        mock_s3_path.exists.side_effect = Exception("S3 error")
        mock_s3_path_class.return_value = mock_s3_path

        local_fallback = Path("/nonexistent/fallback.txt")

        with pytest.raises(FileNotFoundError):
            resolve_data_path("s3://bucket/path.txt", local_fallback=local_fallback)


class TestGetS3BucketFromEnv:
    """Tests for get_s3_bucket_from_env function."""

    def test_get_s3_bucket_from_env_primary(self):
        """Test get_s3_bucket_from_env gets primary env var."""
        with patch.dict(os.environ, {"SBIR_ANALYTICS_S3_BUCKET": "test-bucket-primary"}):
            result = get_s3_bucket_from_env()

            assert result == "test-bucket-primary"

    def test_get_s3_bucket_from_env_fallback(self):
        """Test get_s3_bucket_from_env falls back to S3_BUCKET."""
        with patch.dict(os.environ, {"S3_BUCKET": "test-bucket-fallback"}, clear=True):
            result = get_s3_bucket_from_env()

            assert result == "test-bucket-fallback"

    def test_get_s3_bucket_from_env_primary_precedence(self):
        """Test get_s3_bucket_from_env prefers primary over fallback."""
        with patch.dict(
            os.environ,
            {
                "SBIR_ANALYTICS_S3_BUCKET": "primary",
                "S3_BUCKET": "fallback",
            },
        ):
            result = get_s3_bucket_from_env()

            assert result == "primary"

    def test_get_s3_bucket_from_env_none(self):
        """Test get_s3_bucket_from_env returns None when not set."""
        with patch.dict(os.environ, {}, clear=True):
            result = get_s3_bucket_from_env()

            assert result is None


class TestBuildS3Path:
    """Tests for build_s3_path function."""

    def test_build_s3_path_with_bucket(self):
        """Test build_s3_path with explicit bucket."""
        result = build_s3_path("data/raw/file.csv", bucket="my-bucket")

        assert result == "s3://my-bucket/data/raw/file.csv"

    def test_build_s3_path_with_env_bucket(self):
        """Test build_s3_path uses env var when bucket not provided."""
        with patch("sbir_etl.utils.cloud_storage.get_s3_bucket_from_env", return_value="env-bucket"):
            result = build_s3_path("data/raw/file.csv")

            assert result == "s3://env-bucket/data/raw/file.csv"

    def test_build_s3_path_removes_leading_slash(self):
        """Test build_s3_path removes leading slash from path."""
        result = build_s3_path("/data/raw/file.csv", bucket="my-bucket")

        assert result == "s3://my-bucket/data/raw/file.csv"

    def test_build_s3_path_raises_when_no_bucket(self):
        """Test build_s3_path raises when no bucket configured."""
        with patch("sbir_etl.utils.cloud_storage.get_s3_bucket_from_env", return_value=None):
            with pytest.raises(ValueError, match="S3 bucket not configured"):
                build_s3_path("data/raw/file.csv")


# ==================== Freshness Checking Tests ====================


class TestCheckSbirDataFreshness:
    """Tests for check_sbir_data_freshness function."""

    def _recent_date(self, days_ago: int = 1) -> str:
        # Use noon UTC to avoid midnight-boundary flakiness
        ref = datetime.now(UTC).replace(hour=12, minute=0, second=0, microsecond=0)
        return (ref - timedelta(days=days_ago)).strftime("%Y-%m-%d")

    def test_fresh_data_no_warnings(self):
        source = SbirAwardsSource(
            path=Path("/tmp/test.csv"), origin="s3", s3_key_date=self._recent_date(2)
        )
        warnings = check_sbir_data_freshness(source, self._recent_date(2), days=7)
        assert warnings == []

    def test_stale_s3_key_date(self):
        source = SbirAwardsSource(
            path=Path("/tmp/test.csv"), origin="s3", s3_key_date=self._recent_date(30)
        )
        warnings = check_sbir_data_freshness(source, self._recent_date(1), days=7)
        assert len(warnings) == 1
        assert "S3 data is" in warnings[0]

    def test_stale_max_award_date(self):
        source = SbirAwardsSource(path=Path("/tmp/test.csv"), origin="download")
        warnings = check_sbir_data_freshness(source, self._recent_date(30), days=7)
        assert len(warnings) == 1
        assert "Most recent award" in warnings[0]

    def test_both_stale(self):
        source = SbirAwardsSource(
            path=Path("/tmp/test.csv"), origin="s3", s3_key_date=self._recent_date(30)
        )
        warnings = check_sbir_data_freshness(source, self._recent_date(30), days=7)
        assert len(warnings) == 2

    def test_no_s3_key_date_skips_check(self):
        source = SbirAwardsSource(path=Path("/tmp/test.csv"), origin="download")
        warnings = check_sbir_data_freshness(source, self._recent_date(1), days=7)
        assert warnings == []

    def test_no_max_award_date_skips_check(self):
        source = SbirAwardsSource(
            path=Path("/tmp/test.csv"), origin="s3", s3_key_date=self._recent_date(1)
        )
        warnings = check_sbir_data_freshness(source, None, days=7)
        assert warnings == []

    def test_custom_slack_days(self):
        source = SbirAwardsSource(
            path=Path("/tmp/test.csv"), origin="s3", s3_key_date=self._recent_date(12)
        )
        # Default slack is 3, so 12 days > 7+3=10 → stale
        warnings_default = check_sbir_data_freshness(source, None, days=7)
        assert len(warnings_default) == 1

        # With slack=10, 12 days < 7+10=17 → fresh
        warnings_custom = check_sbir_data_freshness(
            source, None, days=7, s3_slack_days=10
        )
        assert warnings_custom == []

    def test_edge_case_exactly_at_threshold(self):
        # days=7, slack=3 → threshold=10; age=10 → NOT stale (> not >=)
        source = SbirAwardsSource(
            path=Path("/tmp/test.csv"), origin="s3", s3_key_date=self._recent_date(10)
        )
        warnings = check_sbir_data_freshness(source, None, days=7)
        assert warnings == []
