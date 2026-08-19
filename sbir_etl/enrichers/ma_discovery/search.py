"""Pluggable search interface for M&A discovery.

Real search-API clients (Tavily / Brave / Bing) are out of scope here.
``MockSearchTool`` is the Physical Optics / Mercury Systems fixture used
by tests and the optional CLI.
"""

from __future__ import annotations

from typing import Any, Protocol


class SearchTool(Protocol):
    async def search(self, query: str) -> list[dict[str, Any]]: ...


class MockSearchTool:
    """In-memory fixture that confirms Physical Optics / Mercury Systems."""

    async def search(self, query: str) -> list[dict[str, Any]]:
        if "Physical Optics" in query and "Mercury Systems" in query:
            return [
                {
                    "snippet": (
                        "Mercury Systems announced the acquisition of "
                        "Physical Optics Corporation."
                    ),
                    "link": "http://example.com",
                }
            ]
        return []
