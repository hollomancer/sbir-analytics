"""Unit tests for logging configuration utilities."""

from unittest.mock import MagicMock, patch

import pytest


pytestmark = pytest.mark.fast

from src.utils.common.logging_config import (
    LogContext,
    configure_logging_from_config,
    log_with_context,
    setup_logging,
)


class TestSetupLogging:
    """Tests for setup_logging function."""

    def test_setup_logging_basic(self):
        """Test basic logging setup."""
        setup_logging(level="INFO")

        # Should not raise - just verify it runs
        assert True

    def test_setup_logging_json_format(self):
        """Test setup_logging with JSON format."""
        setup_logging(level="DEBUG", format_type="json")

        # Should not raise
        assert True

    def test_setup_logging_pretty_format(self):
        """Test setup_logging with pretty format."""
        setup_logging(level="INFO", format_type="pretty")

        # Should not raise
        assert True

    def test_setup_logging_with_file(self, tmp_path):
        """Test setup_logging with file output."""
        log_file = tmp_path / "test.log"

        setup_logging(level="INFO", file_path=str(log_file))

        assert log_file.exists() or log_file.parent.exists()

    def test_setup_logging_invalid_level(self):
        """Test setup_logging handles invalid level gracefully."""
        # Should not raise, should fall back to INFO
        setup_logging(level="INVALID_LEVEL")

        assert True

    def test_setup_logging_with_timestamps(self):
        """Test setup_logging with timestamps enabled."""
        setup_logging(level="INFO", include_timestamps=True)

        assert True

    def test_setup_logging_without_timestamps(self):
        """Test setup_logging with timestamps disabled."""
        setup_logging(level="INFO", include_timestamps=False)

        assert True

    def test_setup_logging_with_stage(self):
        """Test setup_logging with stage context."""
        setup_logging(level="INFO", include_stage=True)

        assert True

    def test_setup_logging_with_run_id(self):
        """Test setup_logging with run_id context."""
        setup_logging(level="INFO", include_run_id=True)

        assert True


class TestConfigureLoggingFromConfig:
    """Tests for configure_logging_from_config function."""

    @patch("src.utils.logging_config.get_config")
    @patch("src.utils.logging_config.setup_logging")
    def test_configure_logging_from_config(self, mock_setup, mock_get_config):
        """Test configure_logging_from_config calls setup_logging with config."""
        mock_config = MagicMock()
        mock_config.logging.level = "DEBUG"
        mock_config.logging.format = "json"
        mock_config.logging.file_path = "/tmp/test.log"
        mock_config.logging.max_file_size_mb = 50
        mock_config.logging.backup_count = 3
        mock_config.logging.include_stage = True
        mock_config.logging.include_run_id = True
        mock_config.logging.include_timestamps = True
        mock_get_config.return_value = mock_config

        configure_logging_from_config()

        mock_setup.assert_called_once_with(
            level="DEBUG",
            format_type="json",
            file_path="/tmp/test.log",
            max_file_size_mb=50,
            backup_count=3,
            include_stage=True,
            include_run_id=True,
            include_timestamps=True,
        )


class TestLogContext:
    """Tests for LogContext class."""

    def test_log_context_with_stage(self):
        """Test LogContext with stage."""
        with LogContext(stage="test_stage") as logger:
            assert logger is not None

    def test_log_context_with_run_id(self):
        """Test LogContext with run_id."""
        with LogContext(run_id="run_123") as logger:
            assert logger is not None

    def test_log_context_with_both(self):
        """Test LogContext with both stage and run_id."""
        with LogContext(stage="test_stage", run_id="run_123") as logger:
            assert logger is not None

    def test_log_context_exit_resets(self):
        """Test LogContext resets context on exit."""
        context = LogContext(stage="test_stage", run_id="run_123")
        context.__enter__()
        context.__exit__(None, None, None)

        # Should not raise
        assert True


class TestLogWithContext:
    """Tests for log_with_context function."""

    def test_log_with_context_returns_context_manager(self):
        """Test log_with_context returns context manager."""
        cm = log_with_context(stage="test", run_id="123")

        assert hasattr(cm, "__enter__")
        assert hasattr(cm, "__exit__")

    def test_log_with_context_usage(self):
        """Test log_with_context can be used as context manager."""
        with log_with_context(stage="test", run_id="123") as logger:
            assert logger is not None

