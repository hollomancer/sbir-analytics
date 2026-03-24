"""Async helper utilities shared across modules."""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any, cast


def run_sync(coro: Coroutine[Any, Any, Any]) -> Any:
    """Run an async coroutine from synchronous code safely.

    Handles the common case where another event loop is already running
    (e.g., inside IPython) by creating a temporary loop.
    """
    try:
        return asyncio.run(cast(Coroutine[Any, Any, Any], coro))
    except RuntimeError as exc:
        if "asyncio.run()" in str(exc):
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(coro)
            finally:
                loop.close()
        raise
