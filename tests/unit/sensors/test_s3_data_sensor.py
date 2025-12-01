"""Tests for S3 data sensor."""

from datetime import datetime, UTC
from unittest.mock import MagicMock, patch

from dagster import build_sensor_context

from src.assets.sensors.s3_data_sensor import _get_latest_s3_file, s3_sbir_data_sensor


class TestGetLatestS3File:
    """Tests for _get_latest_s3_file helper."""

    @patch("src.assets.sensors.s3_data_sensor._get_s3_client")
    def test_returns_latest_file(self, mock_get_client):
        """Should return the most recently modified file."""
        mock_s3 = MagicMock()
        mock_get_client.return_value = mock_s3

        mock_s3.list_objects_v2.return_value = {
            "Contents": [
                {
                    "Key": "raw/awards/2025-11-30/award_data.csv",
                    "LastModified": datetime(2025, 11, 30, tzinfo=UTC),
                    "Size": 100000,
                },
                {
                    "Key": "raw/awards/2025-12-01/award_data.csv",
                    "LastModified": datetime(2025, 12, 1, tzinfo=UTC),
                    "Size": 200000,
                },
            ]
        }

        result = _get_latest_s3_file("test-bucket", "raw/awards/")

        assert result is not None
        assert result["key"] == "raw/awards/2025-12-01/award_data.csv"
        assert result["size"] == 200000

    @patch("src.assets.sensors.s3_data_sensor._get_s3_client")
    def test_returns_none_when_no_files(self, mock_get_client):
        """Should return None when no files exist."""
        mock_s3 = MagicMock()
        mock_get_client.return_value = mock_s3
        mock_s3.list_objects_v2.return_value = {}

        result = _get_latest_s3_file("test-bucket", "raw/awards/")

        assert result is None

    @patch("src.assets.sensors.s3_data_sensor._get_s3_client")
    def test_ignores_directory_markers(self, mock_get_client):
        """Should ignore S3 directory markers (keys ending with /)."""
        mock_s3 = MagicMock()
        mock_get_client.return_value = mock_s3

        mock_s3.list_objects_v2.return_value = {
            "Contents": [
                {
                    "Key": "raw/awards/",
                    "LastModified": datetime(2025, 12, 1, tzinfo=UTC),
                    "Size": 0,
                },
                {
                    "Key": "raw/awards/2025-12-01/award_data.csv",
                    "LastModified": datetime(2025, 11, 30, tzinfo=UTC),
                    "Size": 100000,
                },
            ]
        }

        result = _get_latest_s3_file("test-bucket", "raw/awards/")

        assert result["key"] == "raw/awards/2025-12-01/award_data.csv"


class TestS3SbirDataSensor:
    """Tests for s3_sbir_data_sensor."""

    @patch("src.assets.sensors.s3_data_sensor._get_latest_s3_file")
    def test_skips_when_no_files(self, mock_get_latest):
        """Should skip when no files found in S3."""
        mock_get_latest.return_value = None

        context = build_sensor_context()
        result = s3_sbir_data_sensor(context)

        assert hasattr(result, "skip_message")

    @patch("src.assets.sensors.s3_data_sensor._get_latest_s3_file")
    def test_skips_when_no_new_data(self, mock_get_latest):
        """Should skip when file hasn't changed since last check."""
        mock_get_latest.return_value = {
            "key": "raw/awards/2025-12-01/award_data.csv",
            "last_modified": "2025-12-01T00:00:00+00:00",
            "size": 100000,
        }

        context = build_sensor_context(cursor="2025-12-01T00:00:00+00:00")
        result = s3_sbir_data_sensor(context)

        assert hasattr(result, "skip_message")

    @patch("src.assets.sensors.s3_data_sensor._get_latest_s3_file")
    def test_triggers_run_on_new_data(self, mock_get_latest):
        """Should trigger run when new file detected."""
        mock_get_latest.return_value = {
            "key": "raw/awards/2025-12-01/award_data.csv",
            "last_modified": "2025-12-01T12:00:00+00:00",
            "size": 200000,
        }

        context = build_sensor_context(cursor="2025-12-01T00:00:00+00:00")
        result = s3_sbir_data_sensor(context)

        assert hasattr(result, "run_requests")
        assert len(result.run_requests) == 1
        assert result.cursor == "2025-12-01T12:00:00+00:00"

    @patch("src.assets.sensors.s3_data_sensor._get_latest_s3_file")
    def test_triggers_run_on_first_check(self, mock_get_latest):
        """Should trigger run on first check (no cursor)."""
        mock_get_latest.return_value = {
            "key": "raw/awards/2025-12-01/award_data.csv",
            "last_modified": "2025-12-01T12:00:00+00:00",
            "size": 200000,
        }

        context = build_sensor_context()
        result = s3_sbir_data_sensor(context)

        assert hasattr(result, "run_requests")
        assert len(result.run_requests) == 1
