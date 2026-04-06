"""Async helper utilities shared across modules."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Coroutine
from typing import Any, cast

# ---------------------------------------------------------------------------
# Persistent background event loop
# ---------------------------------------------------------------------------
# A single event loop runs in a dedicated daemon thread.  Synchronous callers
# submit coroutines via ``asyncio.run_coroutine_threadsafe`` which is safe to
# call from *any* thread.  This avoids:
#   1. "Event loop is closed" — the loop stays alive for the process lifetime
#      so httpx.AsyncClient transports bound to it remain usable.
#   2. Thread-safety issues — ``run_coroutine_threadsafe`` is designed for
#      cross-thread scheduling, unlike ``loop.run_until_complete`` which must
#      be called from the thread that owns the loop.
# ---------------------------------------------------------------------------

_loop: asyncio.AbstractEventLoop | None = None
_loop_lock = threading.Lock()


def _get_loop() -> asyncio.AbstractEventLoop:
    """Return (and lazily start) the shared background event loop."""
    global _loop  # noqa: PLW0603
    if _loop is not None and not _loop.is_closed():
        return _loop
    with _loop_lock:
        # Double-check under lock
        if _loop is not None and not _loop.is_closed():
            return _loop
        new_loop = asyncio.new_event_loop()

        def _run_loop() -> None:
            asyncio.set_event_loop(new_loop)
            new_loop.run_forever()

        t = threading.Thread(target=_run_loop, daemon=True, name="async-loop")
        t.start()
        _loop = new_loop
    return _loop


def run_sync(coro: Coroutine[Any, Any, Any]) -> Any:
    """Run an async coroutine from synchronous code, from any thread.

    Submits the coroutine to a persistent background event loop and
    blocks until the result is ready.  Safe to call concurrently from
    multiple threads (e.g. ``ThreadPoolExecutor`` workers).
    """
    loop = _get_loop()
    future = asyncio.run_coroutine_threadsafe(
        cast(Coroutine[Any, Any, Any], coro), loop
    )
    return future.result()
