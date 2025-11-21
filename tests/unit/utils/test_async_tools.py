"""Unit tests for async tools utilities."""

import asyncio
from unittest.mock import patch

import pytest


pytestmark = pytest.mark.fast

from src.utils.async_tools import run_sync


async def simple_coro(value: int) -> int:
    """Simple async coroutine for testing."""
    await asyncio.sleep(0.01)
    return value * 2


async def failing_coro() -> None:
    """Async coroutine that raises an exception."""
    await asyncio.sleep(0.01)
    raise ValueError("Test error")


class TestRunSync:
    """Tests for run_sync function."""

    def test_run_sync_basic(self):
        """Test basic synchronous execution of async coroutine."""
        result = run_sync(simple_coro(5))
        assert result == 10

    def test_run_sync_with_exception(self):
        """Test run_sync handles exceptions from coroutine."""
        with pytest.raises(ValueError, match="Test error"):
            run_sync(failing_coro())

    def test_run_sync_with_existing_loop(self):
        """Test run_sync handles case where event loop already exists."""
        # Create an event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            # This should work even with an existing loop
            result = run_sync(simple_coro(7))
            assert result == 14
        finally:
            loop.close()
            asyncio.set_event_loop(None)

    def test_run_sync_with_runtime_error(self):
        """Test run_sync handles RuntimeError from asyncio.run()."""
        with patch("asyncio.run", side_effect=RuntimeError("asyncio.run() cannot be called")):
            # Should fall back to new_event_loop approach
            result = run_sync(simple_coro(3))
            assert result == 6

    def test_run_sync_with_other_runtime_error(self):
        """Test run_sync re-raises non-asyncio RuntimeErrors."""
        with patch("asyncio.run", side_effect=RuntimeError("Different error")):
            with pytest.raises(RuntimeError, match="Different error"):
                run_sync(simple_coro(1))

