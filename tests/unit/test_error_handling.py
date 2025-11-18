"""Unit tests for error handling utilities."""

import time
from unittest.mock import Mock

import pytest

from src.utils.error_handling import (
    handle_asset_error,
    log_and_raise,
    retry_with_backoff,
    safe_execute,
)


def test_log_and_raise():
    """Test log_and_raise function."""
    error = ValueError("Test error")
    
    with pytest.raises(ValueError, match="Test error"):
        log_and_raise(error, context="test_context", reraise=True)


def test_log_and_raise_no_rerais():
    """Test log_and_raise without re-raising."""
    error = ValueError("Test error")
    
    # Should not raise
    log_and_raise(error, context="test_context", reraise=False)


def test_handle_asset_error_with_placeholder():
    """Test handle_asset_error with placeholder return."""
    error = ValueError("Test error")
    result = handle_asset_error(
        error,
        asset_name="test_asset",
        return_placeholder=True,
        placeholder_value={"status": "error"},
    )
    
    assert result == {"status": "error"}


def test_handle_asset_error_without_placeholder():
    """Test handle_asset_error without placeholder."""
    error = ValueError("Test error")
    
    with pytest.raises(ValueError, match="Test error"):
        handle_asset_error(
            error,
            asset_name="test_asset",
            return_placeholder=False,
        )


def test_handle_asset_error_with_context():
    """Test handle_asset_error with context."""
    error = ValueError("Test error")
    mock_context = Mock()
    mock_context.log = Mock()
    
    with pytest.raises(ValueError):
        handle_asset_error(error, asset_name="test_asset", context=mock_context)
    
    mock_context.log.error.assert_called_once()


def test_retry_with_backoff_success():
    """Test retry_with_backoff with successful function."""
    call_count = 0
    
    @retry_with_backoff(max_retries=3)
    def successful_func():
        nonlocal call_count
        call_count += 1
        return "success"
    
    result = successful_func()
    assert result == "success"
    assert call_count == 1


def test_retry_with_backoff_retry_then_success():
    """Test retry_with_backoff with retries then success."""
    call_count = 0
    
    @retry_with_backoff(max_retries=3, initial_delay=0.01)
    def retry_func():
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise ValueError("Temporary error")
        return "success"
    
    result = retry_func()
    assert result == "success"
    assert call_count == 2


def test_retry_with_backoff_max_retries():
    """Test retry_with_backoff exceeding max retries."""
    call_count = 0
    
    @retry_with_backoff(max_retries=2, initial_delay=0.01)
    def failing_func():
        nonlocal call_count
        call_count += 1
        raise ValueError("Persistent error")
    
    with pytest.raises(ValueError, match="Persistent error"):
        failing_func()
    
    assert call_count == 3  # Initial + 2 retries


def test_retry_with_backoff_specific_exceptions():
    """Test retry_with_backoff with specific exception types."""
    call_count = 0
    
    @retry_with_backoff(max_retries=2, exceptions=(ValueError,), initial_delay=0.01)
    def func_with_value_error():
        nonlocal call_count
        call_count += 1
        raise ValueError("Value error")
    
    with pytest.raises(ValueError):
        func_with_value_error()
    
    assert call_count == 3


def test_retry_with_backoff_other_exception():
    """Test retry_with_backoff with different exception type."""
    call_count = 0
    
    @retry_with_backoff(max_retries=2, exceptions=(ValueError,), initial_delay=0.01)
    def func_with_type_error():
        nonlocal call_count
        call_count += 1
        raise TypeError("Type error")
    
    # Should not retry, should raise immediately
    with pytest.raises(TypeError, match="Type error"):
        func_with_type_error()
    
    assert call_count == 1


def test_safe_execute_success():
    """Test safe_execute with successful function."""
    def func(x, y):
        return x + y
    
    result = safe_execute(func, 2, 3, default=0)
    assert result == 5


def test_safe_execute_with_error():
    """Test safe_execute with error."""
    def func():
        raise ValueError("Error")
    
    result = safe_execute(func, default="default_value", context="test")
    assert result == "default_value"


def test_safe_execute_with_kwargs():
    """Test safe_execute with keyword arguments."""
    def func(x, y=0):
        return x + y
    
    result = safe_execute(func, 5, y=3, default=0)
    assert result == 8

