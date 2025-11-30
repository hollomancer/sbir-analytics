"""Unit tests for Lambda download utilities."""

import hashlib
from datetime import datetime, UTC
from unittest.mock import MagicMock, Mock, patch
from urllib.error import HTTPError

import pytest

# Mock sys.path.insert before importing
import sys
import os

# Add the scripts/lambda directory to path for testing
lambda_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "scripts", "lambda")
sys.path.insert(0, lambda_path)

from common.download_utils import (
    create_standard_response,
    determine_file_extension,
    download_file,
    try_multiple_urls,
)


class TestDetermineFileExtension:
    """Test file extension determination logic."""

    def test_zip_from_url(self):
        """Test ZIP detection from URL."""
        assert determine_file_extension("https://example.com/file.zip", "") == ".zip"

    def test_zip_from_content_type(self):
        """Test ZIP detection from content type."""
        assert determine_file_extension("https://example.com/file", "application/zip") == ".zip"

    def test_csv_from_url(self):
        """Test CSV detection from URL."""
        assert determine_file_extension("https://example.com/data.csv", "") == ".csv"

    def test_csv_from_content_type(self):
        """Test CSV detection from content type."""
        assert determine_file_extension("https://example.com/file", "text/csv") == ".csv"

    def test_tsv_from_url(self):
        """Test TSV detection from URL."""
        assert determine_file_extension("https://example.com/data.tsv", "") == ".tsv"

    def test_tsv_from_content_type(self):
        """Test TSV detection from content type."""
        assert (
            determine_file_extension("https://example.com/file", "text/tab-separated-values")
            == ".tsv"
        )

    def test_json_from_url(self):
        """Test JSON detection from URL."""
        assert determine_file_extension("https://example.com/data.json", "") == ".json"

    def test_dta_from_url(self):
        """Test DTA detection from URL."""
        assert determine_file_extension("https://example.com/data.dta", "") == ".dta"

    def test_unknown_extension(self):
        """Test unknown extension returns empty string."""
        assert determine_file_extension("https://example.com/file", "application/octet-stream") == ""


class TestCreateStandardResponse:
    """Test standard response creation."""

    def test_success_response(self):
        """Test successful response creation."""
        response = create_standard_response(
            success=True,
            s3_bucket="test-bucket",
            s3_key="test/key.csv",
            sha256="abc123",
            file_size=1024,
            source_url="https://example.com/file.csv",
        )

        assert response["statusCode"] == 200
        assert response["body"]["status"] == "success"
        assert response["body"]["s3_bucket"] == "test-bucket"
        assert response["body"]["s3_key"] == "test/key.csv"
        assert response["body"]["sha256"] == "abc123"
        assert response["body"]["file_size"] == 1024
        assert response["body"]["source_url"] == "https://example.com/file.csv"
        assert "downloaded_at" in response["body"]

    def test_success_response_with_extra_fields(self):
        """Test successful response with additional fields."""
        response = create_standard_response(
            success=True,
            s3_bucket="test-bucket",
            s3_key="test/key.csv",
            sha256="abc123",
            file_size=1024,
            source_url="https://example.com/file.csv",
            dataset="test-dataset",
            row_count=100,
        )

        assert response["body"]["dataset"] == "test-dataset"
        assert response["body"]["row_count"] == 100

    def test_error_response(self):
        """Test error response creation."""
        response = create_standard_response(
            success=False,
            error="Something went wrong",
        )

        assert response["statusCode"] == 500
        assert response["body"]["status"] == "error"
        assert response["body"]["error"] == "Something went wrong"
        assert "timestamp" in response["body"]


class TestDownloadFile:
    """Test file download functionality."""

    @patch("common.download_utils.urlopen")
    def test_successful_download(self, mock_urlopen):
        """Test successful file download."""
        # Mock response
        mock_response = MagicMock()
        mock_response.getcode.return_value = 200
        mock_response.headers.get.return_value = "text/csv"
        mock_response.read.return_value = b"test,data\n1,2\n3,4"
        mock_response.__enter__.return_value = mock_response
        mock_response.__exit__.return_value = None
        mock_urlopen.return_value = mock_response

        data, content_type = download_file("https://example.com/file.csv")

        assert data == b"test,data\n1,2\n3,4"
        assert content_type == "text/csv"
        mock_urlopen.assert_called_once()

    @patch("common.download_utils.urlopen")
    def test_download_with_custom_user_agent(self, mock_urlopen):
        """Test download with custom user agent."""
        mock_response = MagicMock()
        mock_response.getcode.return_value = 200
        mock_response.headers.get.return_value = "text/csv"
        mock_response.read.return_value = b"data"
        mock_response.__enter__.return_value = mock_response
        mock_response.__exit__.return_value = None
        mock_urlopen.return_value = mock_response

        download_file("https://example.com/file.csv", user_agent="CustomAgent/1.0")

        # Check that Request was created with custom user agent
        call_args = mock_urlopen.call_args[0][0]
        assert call_args.headers.get("User-agent") == "CustomAgent/1.0"

    @patch("common.download_utils.urlopen")
    def test_download_rejects_html(self, mock_urlopen):
        """Test that HTML responses are rejected."""
        mock_response = MagicMock()
        mock_response.getcode.return_value = 200
        mock_response.headers.get.return_value = "text/html"
        mock_response.__enter__.return_value = mock_response
        mock_response.__exit__.return_value = None
        mock_urlopen.return_value = mock_response

        with pytest.raises(ValueError, match="Received HTML instead of expected file"):
            download_file("https://example.com/file.csv")

    @patch("common.download_utils.urlopen")
    def test_download_enforces_max_size(self, mock_urlopen):
        """Test that max size limit is enforced."""
        mock_response = MagicMock()
        mock_response.getcode.return_value = 200
        mock_response.headers.get.return_value = "text/csv"
        mock_response.read.return_value = b"x" * 6 * 1024 * 1024  # 6 MB
        mock_response.__enter__.return_value = mock_response
        mock_response.__exit__.return_value = None
        mock_urlopen.return_value = mock_response

        with pytest.raises(ValueError, match="File too large"):
            download_file("https://example.com/file.csv", max_size_mb=5)

    @patch("common.download_utils.urlopen")
    def test_download_handles_non_200_status(self, mock_urlopen):
        """Test handling of non-200 HTTP status."""
        mock_response = MagicMock()
        mock_response.getcode.return_value = 404
        mock_response.__enter__.return_value = mock_response
        mock_response.__exit__.return_value = None
        mock_urlopen.return_value = mock_response

        with pytest.raises(ValueError, match="HTTP 404"):
            download_file("https://example.com/file.csv")


class TestTryMultipleUrls:
    """Test multiple URL fallback functionality."""

    def test_first_url_succeeds(self):
        """Test when first URL succeeds."""
        mock_func = Mock(return_value="success")
        urls = ["https://url1.com", "https://url2.com", "https://url3.com"]

        result, successful_url = try_multiple_urls(urls, mock_func, timeout=30)

        assert result == "success"
        assert successful_url == "https://url1.com"
        assert mock_func.call_count == 1

    def test_fallback_to_second_url(self):
        """Test fallback when first URL fails."""
        mock_func = Mock(side_effect=[Exception("Failed"), "success"])
        urls = ["https://url1.com", "https://url2.com"]

        result, successful_url = try_multiple_urls(urls, mock_func)

        assert result == "success"
        assert successful_url == "https://url2.com"
        assert mock_func.call_count == 2

    def test_all_urls_fail(self):
        """Test when all URLs fail."""
        mock_func = Mock(side_effect=Exception("Failed"))
        urls = ["https://url1.com", "https://url2.com"]

        with pytest.raises(Exception, match="Failed to download from all attempted URLs"):
            try_multiple_urls(urls, mock_func)

        assert mock_func.call_count == 2

    def test_403_error_message(self):
        """Test special error message for 403 errors."""
        mock_func = Mock(side_effect=Exception("HTTP Error 403: Forbidden"))
        urls = ["https://url1.com"]

        with pytest.raises(Exception, match="403 Forbidden"):
            try_multiple_urls(urls, mock_func)


class TestStreamDownloadToS3:
    """Test streaming download to S3 functionality."""

    @patch("common.download_utils.s3_client")
    @patch("common.download_utils.urlopen")
    def test_streaming_upload_validates_zip(self, mock_urlopen, mock_s3):
        """Test that ZIP validation works."""
        from common.download_utils import stream_download_to_s3

        # Mock response with valid ZIP header
        mock_response = MagicMock()
        mock_response.headers.get.return_value = "application/zip"
        mock_response.read.side_effect = [
            b"PK\x03\x04" + b"x" * 8188,  # First chunk with ZIP header
            b"y" * 1024 * 1024,  # Second chunk
            b"",  # End of stream
        ]
        mock_response.__enter__.return_value = mock_response
        mock_response.__exit__.return_value = None
        mock_urlopen.return_value = mock_response

        # Mock S3 operations
        mock_s3.create_multipart_upload.return_value = {"UploadId": "test-upload-id"}
        mock_s3.upload_part.return_value = {"ETag": "test-etag"}

        total_size, file_hash = stream_download_to_s3(
            source_url="https://example.com/file.zip",
            s3_bucket="test-bucket",
            s3_key="test/file.zip",
            validate_zip=True,
        )

        # Verify ZIP validation passed and upload completed
        mock_s3.complete_multipart_upload.assert_called_once()
        assert total_size > 0
        assert len(file_hash) == 64  # SHA256 hash length

    @patch("common.download_utils.s3_client")
    @patch("common.download_utils.urlopen")
    def test_streaming_upload_rejects_invalid_zip(self, mock_urlopen, mock_s3):
        """Test that invalid ZIP files are rejected."""
        from common.download_utils import stream_download_to_s3

        # Mock response without ZIP header
        mock_response = MagicMock()
        mock_response.headers.get.return_value = "application/zip"
        mock_response.read.return_value = b"NOT A ZIP FILE"
        mock_response.__enter__.return_value = mock_response
        mock_response.__exit__.return_value = None
        mock_urlopen.return_value = mock_response

        with pytest.raises(ValueError, match="Not a valid ZIP file"):
            stream_download_to_s3(
                source_url="https://example.com/file.zip",
                s3_bucket="test-bucket",
                s3_key="test/file.zip",
                validate_zip=True,
            )

    @patch("common.download_utils.s3_client")
    @patch("common.download_utils.urlopen")
    def test_streaming_upload_enforces_min_size(self, mock_urlopen, mock_s3):
        """Test that minimum size validation works."""
        from common.download_utils import stream_download_to_s3

        # Mock response with small file
        mock_response = MagicMock()
        mock_response.headers.get.return_value = "application/zip"
        mock_response.read.side_effect = [
            b"PK\x03\x04" + b"x" * 100,  # Small file
            b"",  # End of stream
        ]
        mock_response.__enter__.return_value = mock_response
        mock_response.__exit__.return_value = None
        mock_urlopen.return_value = mock_response

        # Mock S3 operations
        mock_s3.create_multipart_upload.return_value = {"UploadId": "test-upload-id"}
        mock_s3.upload_part.return_value = {"ETag": "test-etag"}

        with pytest.raises(ValueError, match="too small"):
            stream_download_to_s3(
                source_url="https://example.com/file.zip",
                s3_bucket="test-bucket",
                s3_key="test/file.zip",
                min_size=1_000_000,  # 1 MB minimum
            )

        # Verify upload was aborted
        mock_s3.abort_multipart_upload.assert_called_once()
