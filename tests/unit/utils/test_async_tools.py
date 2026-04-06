"""Unit tests for async tools utilities."""

import asyncio
from concurrent.futures import ThreadPoolExecutor

import pytest


pytestmark = pytest.mark.fast

from sbir_etl.utils.async_tools import run_sync


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
        """Test run_sync works even when the calling thread has its own loop."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            result = run_sync(simple_coro(7))
            assert result == 14
        finally:
            loop.close()
            asyncio.set_event_loop(None)

    def test_run_sync_multiple_calls_reuse_loop(self):
        """Test that multiple run_sync calls reuse the same background loop."""
        r1 = run_sync(simple_coro(3))
        r2 = run_sync(simple_coro(4))
        assert r1 == 6
        assert r2 == 8

    def test_run_sync_thread_safety(self):
        """Test that run_sync can be called safely from multiple threads."""
        def call_from_thread(val: int) -> int:
            return run_sync(simple_coro(val))

        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = [pool.submit(call_from_thread, i) for i in range(8)]
            results = [f.result(timeout=10) for f in futures]

        assert results == [i * 2 for i in range(8)]
