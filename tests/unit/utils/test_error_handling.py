"""Unit tests for error handling utilities."""

from unittest.mock import MagicMock, patch

import pytest


pytestmark = pytest.mark.fast

from src.utils.error_handling import (
    handle_asset_error,
    log_and_raise,
    retry_with_backoff,
    safe_execute,
)


class TestLogAndRaise:
    """Tests for log_and_raise function."""

    def test_log_and_raise_with_context(self):
        """Test log_and_raise logs error with context."""
        error = ValueError("Test error")

        with pytest.raises(ValueError, match="Test error"):
            log_and_raise(error, context="test_context", reraise=True)

    def test_log_and_raise_with_additional_info(self):
        """Test log_and_raise logs error with additional info."""
        error = ValueError("Test error")
        additional_info = {"key1": "value1", "key2": 123}

        with pytest.raises(ValueError):
            log_and_raise(error, additional_info=additional_info, reraise=True)

    def test_log_and_raise_no_rerais(self):
        """Test log_and_raise doesn't re-raise when reraise=False."""
        error = ValueError("Test error")

        # Should not raise
        log_and_raise(error, reraise=False)


class TestHandleAssetError:
    """Tests for handle_asset_error function."""

    def test_handle_asset_error_raises_by_default(self):
        """Test handle_asset_error raises exception by default."""
        error = ValueError("Test error")

        with pytest.raises(ValueError, match="Test error"):
            handle_asset_error(error, asset_name="test_asset")

    def test_handle_asset_error_with_context(self):
        """Test handle_asset_error uses context for logging."""
        error = ValueError("Test error")
        mock_context = MagicMock()
        mock_context.log = MagicMock()

        with pytest.raises(ValueError):
            handle_asset_error(error, asset_name="test_asset", context=mock_context)

        mock_context.log.error.assert_called_once()

    def test_handle_asset_error_returns_placeholder(self):
        """Test handle_asset_error returns placeholder when requested."""
        error = ValueError("Test error")
        placeholder = {"status": "error"}

        result = handle_asset_error(
            error,
            asset_name="test_asset",
            return_placeholder=True,
            placeholder_value=placeholder,
        )

        assert result == placeholder

    def test_handle_asset_error_logs_warning_on_placeholder(self):
        """Test handle_asset_error logs warning when returning placeholder."""
        error = ValueError("Test error")

        with patch("src.utils.error_handling.logger") as mock_logger:
            handle_asset_error(
                error,
                asset_name="test_asset",
                return_placeholder=True,
                placeholder_value=None,
            )

            mock_logger.warning.assert_called_once()


class TestRetryWithBackoff:
    """Tests for retry_with_backoff decorator."""

    def test_retry_with_backoff_succeeds_on_first_try(self):
        """Test retry_with_backoff succeeds without retries."""
        call_count = 0

        @retry_with_backoff(max_retries=3, initial_delay=0.01)
        def test_func():
            nonlocal call_count
            call_count += 1
            return "success"

        result = test_func()

        assert result == "success"
        assert call_count == 1

    def test_retry_with_backoff_retries_on_exception(self):
        """Test retry_with_backoff retries on specified exceptions."""
        call_count = 0

        @retry_with_backoff(max_retries=2, initial_delay=0.01, exceptions=(ValueError,))
        def test_func():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError("Retry me")
            return "success"

        result = test_func()

        assert result == "success"
        assert call_count == 2

    def test_retry_with_backoff_exceeds_max_retries(self):
        """Test retry_with_backoff raises after max retries."""
        call_count = 0

        @retry_with_backoff(max_retries=2, initial_delay=0.01, exceptions=(ValueError,))
        def test_func():
            nonlocal call_count
            call_count += 1
            raise ValueError("Always fail")

        with pytest.raises(ValueError, match="Always fail"):
            test_func()

        assert call_count == 3  # Initial + 2 retries

    def test_retry_with_backoff_with_callback(self):
        """Test retry_with_backoff calls callback on retry."""
        call_count = 0
        retry_calls = []

        def on_retry(exc, attempt):
            retry_calls.append((exc, attempt))

        @retry_with_backoff(
            max_retries=2, initial_delay=0.01, exceptions=(ValueError,), on_retry=on_retry
        )
        def test_func():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError("Retry me")
            return "success"

        result = test_func()

        assert result == "success"
        assert len(retry_calls) == 1
        assert retry_calls[0][1] == 1  # First retry attempt

    def test_retry_with_backoff_doesnt_retry_other_exceptions(self):
        """Test retry_with_backoff only retries specified exceptions."""
        call_count = 0

        @retry_with_backoff(max_retries=2, initial_delay=0.01, exceptions=(ValueError,))
        def test_func():
            nonlocal call_count
            call_count += 1
            raise KeyError("Don't retry me")

        with pytest.raises(KeyError, match="Don't retry me"):
            test_func()

        assert call_count == 1  # No retries for KeyError


class TestSafeExecute:
    """Tests for safe_execute function."""

    def test_safe_execute_success(self):
        """Test safe_execute returns function result on success."""

        def test_func(x, y):
            return x + y

        result = safe_execute(test_func, 2, 3)

        assert result == 5

    def test_safe_execute_returns_default_on_error(self):
        """Test safe_execute returns default value on error."""

        def test_func():
            raise ValueError("Error")

        result = safe_execute(test_func, default="default_value")

        assert result == "default_value"

    def test_safe_execute_returns_none_without_default(self):
        """Test safe_execute returns None when no default provided."""

        def test_func():
            raise ValueError("Error")

        result = safe_execute(test_func)

        assert result is None

    def test_safe_execute_with_context(self):
        """Test safe_execute logs with context."""

        def test_func():
            raise ValueError("Error")

        with patch("src.utils.error_handling.logger") as mock_logger:
            safe_execute(test_func, context="test_context")

            mock_logger.warning.assert_called_once()
            assert "test_context" in str(mock_logger.warning.call_args)

    def test_safe_execute_with_kwargs(self):
        """Test safe_execute passes kwargs to function."""

        def test_func(x, y=0):
            return x + y

        result = safe_execute(test_func, 5, y=3)

        assert result == 8
