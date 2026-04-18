"""Rate-limiting utilities for synchronous enricher API clients.

Provides :class:`RateLimiter`, a thread-safe sliding-window rate limiter
used by the synchronous enricher clients (PatentsView, company/federal
lookups, PI enrichment). The asynchronous equivalent is baked into
:class:`sbir_etl.enrichers.base_client.BaseAsyncAPIClient`.

This module exists so that rate-limiting infrastructure is not buried
inside a domain-specific client (previously it lived in
``patentsview.py`` and was imported from there by unrelated modules).

Usage::

    from sbir_etl.enrichers.rate_limiting import RateLimiter

    limiter = RateLimiter(rate_limit_per_minute=60)
    for item in items:
        limiter.wait_if_needed()
        call_api(item)
"""

from __future__ import annotations

import threading
import time
from collections import deque
from datetime import datetime, timedelta

from loguru import logger


class RateLimiter:
    """Thread-safe sliding-window rate limiter for synchronous API calls.

    Tracks request timestamps over the last 60 seconds and blocks the
    caller if issuing another request would exceed the configured
    requests-per-minute quota. Safe for use from multiple threads
    concurrently — the internal lock is released during sleep so other
    threads can still probe the state.
    """

    def __init__(self, rate_limit_per_minute: int = 60) -> None:
        """Initialize rate limiter.

        Args:
            rate_limit_per_minute: Maximum requests allowed per 60-second window.
        """
        self.rate_limit_per_minute = rate_limit_per_minute
        self.request_times: deque[datetime] = deque(maxlen=rate_limit_per_minute)
        self._lock = threading.Lock()

    def wait_if_needed(self) -> None:
        """Block until a request slot is available, then record the request.

        Removes timestamps older than 60 seconds, and if the window is
        saturated, sleeps until the oldest slot expires. Thread-safe.
        """
        with self._lock:
            now = datetime.now()
            # Remove requests older than 1 minute
            cutoff_time = now - timedelta(seconds=60)
            while self.request_times and self.request_times[0] < cutoff_time:
                self.request_times.popleft()

            # If we're at the limit, wait until the oldest request is 60 seconds old
            if len(self.request_times) >= self.rate_limit_per_minute:
                oldest = self.request_times[0]
                wait_seconds = 60 - (now - oldest).total_seconds() + 0.5  # 0.5s buffer
                if wait_seconds > 0:
                    logger.debug(
                        f"Rate limit reached ({self.rate_limit_per_minute}/min), "
                        f"waiting {wait_seconds:.1f} seconds"
                    )
                    # Release lock during sleep to allow other threads to check
                    self._lock.release()
                    try:
                        time.sleep(wait_seconds)
                    finally:
                        self._lock.acquire()
                    # Recalculate after sleep
                    now = datetime.now()
                    cutoff_time = now - timedelta(seconds=60)
                    while self.request_times and self.request_times[0] < cutoff_time:
                        self.request_times.popleft()

            # Record this request
            self.request_times.append(datetime.now())
