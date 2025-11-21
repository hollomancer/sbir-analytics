"""Unit tests for cloud storage utilities."""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


pytestmark = pytest.mark.fast

from src.utils.cloud_storage import build_s3_path, get_s3_bucket_from_env, resolve_data_path


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

        with patch("src.utils.cloud_storage.S3Path") as mock_s3:
            result = resolve_data_path(
                "s3://bucket/path.txt", local_fallback=local_file, prefer_local=True
            )

            assert result == local_file
            mock_s3.assert_not_called()

    @patch("src.utils.cloud_storage.S3Path")
    def test_resolve_s3_path_exists(self, mock_s3_path_class, tmp_path):
        """Test resolve_data_path with existing S3 path."""
        mock_s3_path = MagicMock()
        mock_s3_path.exists.return_value = True
        mock_s3_path.name = "test.txt"
        mock_s3_path_class.return_value = mock_s3_path

        with patch("src.utils.cloud_storage._download_s3_to_temp") as mock_download:
            mock_download.return_value = tmp_path / "downloaded.txt"

            result = resolve_data_path("s3://bucket/path.txt")

            assert result == tmp_path / "downloaded.txt"
            mock_s3_path_class.assert_called_once_with("s3://bucket/path.txt")

    @patch("src.utils.cloud_storage.S3Path")
    def test_resolve_s3_path_fallback_to_local(self, mock_s3_path_class, tmp_path):
        """Test resolve_data_path falls back to local when S3 fails."""
        mock_s3_path = MagicMock()
        mock_s3_path.exists.side_effect = Exception("S3 error")
        mock_s3_path_class.return_value = mock_s3_path

        local_fallback = tmp_path / "fallback.txt"
        local_fallback.write_text("fallback")

        result = resolve_data_path("s3://bucket/path.txt", local_fallback=local_fallback)

        assert result == local_fallback

    @patch("src.utils.cloud_storage.S3Path")
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
        with patch("src.utils.cloud_storage.get_s3_bucket_from_env", return_value="env-bucket"):
            result = build_s3_path("data/raw/file.csv")

            assert result == "s3://env-bucket/data/raw/file.csv"

    def test_build_s3_path_removes_leading_slash(self):
        """Test build_s3_path removes leading slash from path."""
        result = build_s3_path("/data/raw/file.csv", bucket="my-bucket")

        assert result == "s3://my-bucket/data/raw/file.csv"

    def test_build_s3_path_raises_when_no_bucket(self):
        """Test build_s3_path raises when no bucket configured."""
        with patch("src.utils.cloud_storage.get_s3_bucket_from_env", return_value=None):
            with pytest.raises(ValueError, match="S3 bucket not configured"):
                build_s3_path("data/raw/file.csv")
