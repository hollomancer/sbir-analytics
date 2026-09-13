"""Pluggable search interface for M&A discovery.

``MockSearchTool`` is the Physical Optics / Mercury Systems fixture used
by tests and when the backend is explicitly ``mock``. Production clients
(Tavily, optional Brave) implement the same ``SearchTool`` shape and are
constructed through ``build_search_tool``.
"""

from __future__ import annotations

import json
import os
from collections import defaultdict
from pathlib import Path
from typing import Any, Protocol

import httpx
from loguru import logger

from sbir_etl.config.loader import get_config
from sbir_etl.config.schemas.domain import MA_DISCOVERY_SEARCH_BACKENDS, MADiscoveryConfig
from sbir_etl.enrichers.base_client import BaseAsyncAPIClient
from sbir_etl.exceptions import ConfigurationError


TAVILY_API_URL = "https://api.tavily.com"
BRAVE_API_URL = "https://api.search.brave.com"
DEFAULT_SEARCH_API_KEY_ENV = "SBIR_ETL__MA_DISCOVERY__SEARCH_API_KEY"
DEFAULT_RATE_LIMIT_PER_MINUTE = 60
DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_MAX_RESULTS = 5


class SearchTool(Protocol):
    async def search(self, query: str) -> list[dict[str, Any]]: ...


def _map_hits(items: Any, *, snippet_key: str, link_key: str) -> list[dict[str, Any]]:
    """Normalize vendor hits to ``{"snippet", "link", "title"?}``."""
    if not isinstance(items, list):
        return []
    mapped: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        link = item.get(link_key) or item.get("link")
        if not link:
            continue
        snippet = item.get(snippet_key) or item.get("snippet") or ""
        hit: dict[str, Any] = {"snippet": str(snippet), "link": str(link)}
        title = item.get("title")
        if title:
            hit["title"] = str(title)
        mapped.append(hit)
    return mapped


class SnippetSearchTool:
    """Replay a frozen search-result cut. No network.

    Accepts JSONL rows ``{query, snippet, link, title?}`` or a JSON list of
    the same shape. Lookups are exact on the stored query string.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self._hits: dict[str, list[dict[str, Any]]] = defaultdict(list)
        text = path.read_text(encoding="utf-8")
        records: list[Any]
        stripped = text.lstrip()
        if stripped.startswith("["):
            loaded = json.loads(text)
            records = loaded if isinstance(loaded, list) else []
        else:
            records = [json.loads(line) for line in text.splitlines() if line.strip()]
        for record in records:
            if not isinstance(record, dict):
                continue
            query = record.get("query")
            link = record.get("link")
            if not isinstance(query, str) or not query or not link:
                continue
            hit: dict[str, Any] = {
                "snippet": str(record.get("snippet") or ""),
                "link": str(link),
            }
            title = record.get("title")
            if title:
                hit["title"] = str(title)
            self._hits[query].append(hit)

    async def search(self, query: str) -> list[dict[str, Any]]:
        return list(self._hits.get(query, []))


class MockSearchTool:
    """In-memory fixture that confirms Physical Optics / Mercury Systems."""

    async def search(self, query: str) -> list[dict[str, Any]]:
        lowered = query.lower()
        if "physical optics" in lowered and "mercury systems" in lowered:
            return [
                {
                    "snippet": (
                        "Mercury Systems announced the acquisition of Physical Optics Corporation."
                    ),
                    "link": "http://example.com",
                    "title": "Mercury Systems acquires Physical Optics",
                }
            ]
        return []


class TavilySearchTool(BaseAsyncAPIClient):
    """Tavily Search API client. POST /search, Bearer token."""

    api_name = "tavily"

    def __init__(
        self,
        *,
        api_key: str,
        timeout: int = DEFAULT_TIMEOUT_SECONDS,
        rate_limit_per_minute: int = DEFAULT_RATE_LIMIT_PER_MINUTE,
        max_results: int = DEFAULT_MAX_RESULTS,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key:
            raise ConfigurationError(
                "Tavily search requires an API key",
                config_key="ma_discovery.search_api_key",
            )
        super().__init__()
        self.base_url = TAVILY_API_URL
        self.rate_limit_per_minute = rate_limit_per_minute
        self._api_key = api_key
        self._max_results = max_results
        self._client = http_client or httpx.AsyncClient(timeout=timeout)

    def _build_headers(self) -> dict[str, str]:
        headers = super()._build_headers()
        headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    async def search(self, query: str) -> list[dict[str, Any]]:
        data = await self._make_request(
            "POST",
            "search",
            params={
                "query": query,
                "search_depth": "basic",
                "max_results": self._max_results,
                "include_answer": False,
            },
        )
        results = data.get("results") if isinstance(data, dict) else None
        return _map_hits(results, snippet_key="content", link_key="url")


class BraveSearchTool(BaseAsyncAPIClient):
    """Brave Web Search API client. GET /res/v1/web/search."""

    api_name = "brave"

    def __init__(
        self,
        *,
        api_key: str,
        timeout: int = DEFAULT_TIMEOUT_SECONDS,
        rate_limit_per_minute: int = DEFAULT_RATE_LIMIT_PER_MINUTE,
        max_results: int = DEFAULT_MAX_RESULTS,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key:
            raise ConfigurationError(
                "Brave search requires an API key",
                config_key="ma_discovery.search_api_key",
            )
        super().__init__()
        self.base_url = BRAVE_API_URL
        self.rate_limit_per_minute = rate_limit_per_minute
        self._api_key = api_key
        self._max_results = max_results
        self._client = http_client or httpx.AsyncClient(timeout=timeout)

    def _build_headers(self) -> dict[str, str]:
        headers = super()._build_headers()
        headers["X-Subscription-Token"] = self._api_key
        return headers

    async def search(self, query: str) -> list[dict[str, Any]]:
        data = await self._make_request(
            "GET",
            "res/v1/web/search",
            params={"q": query, "count": self._max_results},
        )
        web = data.get("web") if isinstance(data, dict) else None
        results = web.get("results") if isinstance(web, dict) else None
        return _map_hits(results, snippet_key="description", link_key="url")


def _load_ma_discovery_config() -> MADiscoveryConfig:
    """Load ``ma_discovery`` from the shared config primitive, with defaults."""
    try:
        loaded = get_config()
    except ConfigurationError:
        logger.debug("M&A discovery config unavailable; using defaults")
        return MADiscoveryConfig()
    cfg = getattr(loaded, "ma_discovery", None)
    if isinstance(cfg, MADiscoveryConfig):
        return cfg
    return MADiscoveryConfig()


def _resolve_api_key(api_key: str | None, cfg: MADiscoveryConfig | None) -> str:
    if isinstance(api_key, str) and api_key.strip():
        return api_key.strip()
    if cfg is None:
        cfg = _load_ma_discovery_config()
    env_name = cfg.api_key_env_var or DEFAULT_SEARCH_API_KEY_ENV
    return (cfg.search_api_key or os.environ.get(env_name) or "").strip()


def build_search_tool(
    name: str | None = None,
    *,
    api_key: str | None = None,
    config: MADiscoveryConfig | None = None,
    http_client: httpx.AsyncClient | None = None,
    snippets_path: Path | str | None = None,
) -> SearchTool:
    """Return a ``SearchTool`` for ``name`` (or the configured backend).

    ``none`` is the fail-closed default and never writes fixture evidence.
    ``mock`` is explicit opt-in. ``snippets`` replays a frozen cut.
    Selecting ``tavily`` or ``brave`` without a key raises ``ConfigurationError``.
    """
    cfg = config if config is not None else _load_ma_discovery_config()
    backend_raw = name.strip() if isinstance(name, str) and name.strip() else ""
    if not backend_raw:
        backend_raw = cfg.search_backend
    backend = backend_raw.strip().lower()

    if backend not in MA_DISCOVERY_SEARCH_BACKENDS:
        known = ", ".join(sorted(MA_DISCOVERY_SEARCH_BACKENDS))
        raise ConfigurationError(
            f"Unknown M&A search backend {backend!r}; expected one of {known}",
            config_key="ma_discovery.search_backend",
        )

    if backend == "none":
        raise ConfigurationError(
            "M&A search backend 'none' is fail-closed; pass --search-backend mock "
            "for fixtures, snippets for a frozen cut, or a live backend with a key",
            config_key="ma_discovery.search_backend",
        )

    if backend == "mock":
        return MockSearchTool()

    if backend == "snippets":
        raw_path = snippets_path if snippets_path is not None else cfg.snippets_path
        if not raw_path:
            raise ConfigurationError(
                "M&A search backend 'snippets' requires snippets_path",
                config_key="ma_discovery.snippets_path",
            )
        path = Path(raw_path)
        if not path.is_file():
            raise ConfigurationError(
                f"M&A snippets cut does not exist: {path}",
                config_key="ma_discovery.snippets_path",
            )
        return SnippetSearchTool(path)

    key = _resolve_api_key(api_key, cfg)
    if not key:
        raise ConfigurationError(
            f"M&A search backend {backend!r} requires an API key",
            config_key="ma_discovery.search_api_key",
        )

    timeout = cfg.timeout_seconds
    rate = cfg.rate_limit_per_minute
    max_results = cfg.max_results
    kwargs: dict[str, Any] = {
        "api_key": key,
        "timeout": timeout,
        "rate_limit_per_minute": rate,
        "max_results": max_results,
        "http_client": http_client,
    }
    if backend == "tavily":
        return TavilySearchTool(**kwargs)
    return BraveSearchTool(**kwargs)
