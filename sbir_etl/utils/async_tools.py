"""Async helper utilities shared across modules."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Coroutine
from typing import Any, cast

# Module-level persistent event loop.  Re-using one loop avoids the
# "Event loop is closed" crash that occurs when an httpx.AsyncClient
# created on loop A is later called from loop B (after A was closed by
# ``asyncio.run``).
_loop: asyncio.AbstractEventLoop | None = None
_loop_lock = threading.Lock()


def _get_loop() -> asyncio.AbstractEventLoop:
    """Return (and lazily create) the shared background event loop."""
    global _loop  # noqa: PLW0603
    if _loop is None or _loop.is_closed():
        with _loop_lock:
            # Double-check under lock
            if _loop is None or _loop.is_closed():
                _loop = asyncio.new_event_loop()
    return _loop


def run_sync(coro: Coroutine[Any, Any, Any]) -> Any:
    """Run an async coroutine from synchronous code safely.

    Uses a persistent module-level event loop so that async clients
    (e.g. httpx.AsyncClient) whose transports are bound to a loop
    remain usable across multiple ``run_sync`` calls.
    """
    loop = _get_loop()
    return loop.run_until_complete(cast(Coroutine[Any, Any, Any], coro))
