"""Tests for the shared synchronous :class:`RateLimiter`.

Covers sliding-window eviction, under/at-limit behavior, and thread
safety (basic concurrent access). The class previously lived inside
``patentsview.py`` without direct test coverage.
"""

from __future__ import annotations

import threading
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from sbir_etl.enrichers.rate_limiting import RateLimiter

pytestmark = pytest.mark.fast


class TestInitialState:
    def test_default_rate_limit(self) -> None:
        limiter = RateLimiter()
        assert limiter.rate_limit_per_minute == 60
        assert len(limiter.request_times) == 0

    def test_custom_rate_limit(self) -> None:
        limiter = RateLimiter(rate_limit_per_minute=120)
        assert limiter.rate_limit_per_minute == 120

    def test_request_times_maxlen_matches_rate_limit(self) -> None:
        """Deque maxlen bounds memory growth to the rate limit."""
        limiter = RateLimiter(rate_limit_per_minute=5)
        assert limiter.request_times.maxlen == 5


class TestUnderLimit:
    def test_under_limit_does_not_sleep(self) -> None:
        limiter = RateLimiter(rate_limit_per_minute=60)
        # Add 10 recent requests — well under the limit
        for _ in range(10):
            limiter.request_times.append(datetime.now())

        with patch("sbir_etl.enrichers.rate_limiting.time.sleep") as mock_sleep:
            limiter.wait_if_needed()

        mock_sleep.assert_not_called()
        assert len(limiter.request_times) == 11

    def test_records_timestamp_on_every_call(self) -> None:
        limiter = RateLimiter(rate_limit_per_minute=60)
        assert len(limiter.request_times) == 0

        limiter.wait_if_needed()
        assert len(limiter.request_times) == 1

        limiter.wait_if_needed()
        assert len(limiter.request_times) == 2


class TestEviction:
    def test_evicts_timestamps_older_than_sixty_seconds(self) -> None:
        """Old timestamps are purged before the saturation check."""
        # rate_limit=5 — a deque maxlen=5 will be used
        limiter = RateLimiter(rate_limit_per_minute=5)
        old = datetime.now() - timedelta(seconds=90)
        # Fill the window with old timestamps
        for _ in range(5):
            limiter.request_times.append(old)

        with patch("sbir_etl.enrichers.rate_limiting.time.sleep") as mock_sleep:
            limiter.wait_if_needed()

        mock_sleep.assert_not_called()
        # All old evicted, new request recorded
        assert len(limiter.request_times) == 1

    def test_keeps_recent_timestamps(self) -> None:
        limiter = RateLimiter(rate_limit_per_minute=10)
        # 3 old, 2 recent
        old = datetime.now() - timedelta(seconds=75)
        for _ in range(3):
            limiter.request_times.append(old)
        for _ in range(2):
            limiter.request_times.append(datetime.now())

        with patch("sbir_etl.enrichers.rate_limiting.time.sleep") as mock_sleep:
            limiter.wait_if_needed()

        mock_sleep.assert_not_called()
        # 3 old evicted, 2 recent kept, 1 new recorded
        assert len(limiter.request_times) == 3


class TestAtLimit:
    def test_waits_until_oldest_slot_expires(self) -> None:
        """When saturated, sleep until the oldest timestamp falls out of window."""
        limiter = RateLimiter(rate_limit_per_minute=5)
        # All 5 slots used 20 seconds ago → oldest frees at t+40
        base = datetime.now() - timedelta(seconds=20)
        for i in range(5):
            limiter.request_times.append(base + timedelta(seconds=i))

        with patch("sbir_etl.enrichers.rate_limiting.time.sleep") as mock_sleep:
            limiter.wait_if_needed()

        mock_sleep.assert_called_once()
        wait_seconds = mock_sleep.call_args[0][0]
        # wait ≈ 60 - 20 + 0.5 = 40.5 (small tolerance)
        assert 39.0 <= wait_seconds <= 41.5


class TestBackwardCompatImport:
    """Lock in that the old import path from ``patentsview`` no longer exists.

    If someone re-adds a shim, this test fails — keeping the coupling
    one-way (patentsview imports rate_limiting, not the reverse).
    """

    def test_patentsview_does_not_redefine_ratelimiter(self) -> None:
        from sbir_etl.enrichers import patentsview, rate_limiting

        # Both should refer to the same class object
        assert patentsview.RateLimiter is rate_limiting.RateLimiter


class TestThreadSafety:
    """Basic concurrent-access test: no deadlocks, no lost writes."""

    def test_concurrent_wait_if_needed(self) -> None:
        limiter = RateLimiter(rate_limit_per_minute=1000)
        call_count = 50
        threads: list[threading.Thread] = []

        def worker() -> None:
            limiter.wait_if_needed()

        for _ in range(call_count):
            t = threading.Thread(target=worker)
            threads.append(t)
            t.start()

        for t in threads:
            t.join(timeout=5.0)
            assert not t.is_alive(), "worker thread deadlocked"

        assert len(limiter.request_times) == call_count
