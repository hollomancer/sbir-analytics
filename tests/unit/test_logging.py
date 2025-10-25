"""Unit tests for logging configuration."""

import tempfile
from pathlib import Path
from unittest.mock import patch

from src.utils.logging_config import (
    LogContext,
    configure_logging_from_config,
    log_with_context,
    setup_logging,
)


class TestSetupLogging:
    """Test logging setup functionality."""

    def test_setup_logging_console_only(self):
        """Test setting up logging with console only."""
        setup_logging(level="INFO", format_type="pretty")

        # Should not raise any exceptions
        assert True

    def test_setup_logging_with_file(self):
        """Test setting up logging with file output."""
        with tempfile.TemporaryDirectory() as temp_dir:
            log_file = Path(temp_dir) / "test.log"

            setup_logging(level="INFO", format_type="json", file_path=str(log_file))

            # Should not raise any exceptions
            assert True

    def test_setup_logging_invalid_level(self):
        """Test setting up logging with invalid level."""
        # loguru should handle invalid levels gracefully
        setup_logging(level="INVALID")

        # Should not raise any exceptions
        assert True


class TestLogContext:
    """Test log context functionality."""

    def test_log_context_empty(self):
        """Test log context with no parameters."""
        context = LogContext()
        logger = context.__enter__()
        assert logger is not None
        context.__exit__(None, None, None)

    def test_log_context_with_stage(self):
        """Test log context with stage parameter."""
        context = LogContext(stage="extract")
        logger = context.__enter__()
        assert logger is not None
        context.__exit__(None, None, None)

    def test_log_context_with_run_id(self):
        """Test log context with run_id parameter."""
        context = LogContext(run_id="run-123")
        logger = context.__enter__()
        assert logger is not None
        context.__exit__(None, None, None)

    def test_log_context_with_both(self):
        """Test log context with both stage and run_id."""
        context = LogContext(stage="transform", run_id="run-456")
        logger = context.__enter__()
        assert logger is not None
        context.__exit__(None, None, None)

    def test_log_with_context_function(self):
        """Test log_with_context convenience function."""
        context = log_with_context(stage="validate", run_id="run-789")
        logger = context.__enter__()
        assert logger is not None
        context.__exit__(None, None, None)


class TestConfigureLoggingFromConfig:
    """Test configuration-based logging setup."""

    @patch("src.utils.logging_config.get_config")
    def test_configure_from_config(self, mock_get_config):
        """Test configuring logging from configuration."""
        # Mock configuration
        mock_config = type("MockConfig", (), {})()
        mock_config.logging = type("MockLogging", (), {})()
        mock_config.logging.level = "DEBUG"
        mock_config.logging.format = "pretty"
        mock_config.logging.file_path = None
        mock_config.logging.max_file_size_mb = 50
        mock_config.logging.backup_count = 3
        mock_config.logging.include_stage = True
        mock_config.logging.include_run_id = True
        mock_config.logging.include_timestamps = True

        mock_get_config.return_value = mock_config

        configure_logging_from_config()

        # Should not raise any exceptions
        assert True


class TestLogFunctions:
    """Test convenience logging functions."""

    def test_log_functions_exist(self):
        """Test that all log functions are available."""
        from src.utils.logging_config import (
            log_debug,
            log_error,
            log_exception,
            log_info,
            log_warning,
        )

        # Functions should exist
        assert callable(log_debug)
        assert callable(log_info)
        assert callable(log_warning)
        assert callable(log_error)
        assert callable(log_exception)

    def test_log_functions_no_exception(self):
        """Test that log functions don't raise exceptions."""
        from src.utils.logging_config import (
            log_debug,
            log_error,
            log_info,
            log_warning,
        )

        # These should not raise exceptions
        log_debug("Test debug message")
        log_info("Test info message")
        log_warning("Test warning message")
        log_error("Test error message")

        assert True
