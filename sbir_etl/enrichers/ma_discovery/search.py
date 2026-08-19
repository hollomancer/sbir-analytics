"""Pluggable search interface for M&A discovery.

``MockSearchTool`` is the Physical Optics / Mercury Systems fixture used
by tests and the runtime default when no backend key is configured.
Production clients (Tavily, optional Brave) implement the same
``SearchTool`` shape and are constructed through ``build_search_tool``.
"""

from __future__ import annotations

import os
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
) -> SearchTool:
    """Return a ``SearchTool`` for ``name`` (or the configured backend).

    Missing keys fall back to ``MockSearchTool`` with a warning so tests and
    local CLI runs do not require credentials. Unknown backend names raise
    ``ConfigurationError``.
    """
    cfg = config
    backend_raw = name.strip() if isinstance(name, str) and name.strip() else ""
    if not backend_raw:
        if cfg is None:
            cfg = _load_ma_discovery_config()
        backend_raw = cfg.search_backend
    backend = backend_raw.strip().lower()

    if backend not in MA_DISCOVERY_SEARCH_BACKENDS:
        known = ", ".join(sorted(MA_DISCOVERY_SEARCH_BACKENDS))
        raise ConfigurationError(
            f"Unknown M&A search backend {backend!r}; expected one of {known}",
            config_key="ma_discovery.search_backend",
        )

    if backend == "mock":
        return MockSearchTool()

    key = _resolve_api_key(api_key, cfg)
    if not key:
        logger.warning(
            "M&A search backend '{}' selected but no API key is set; using MockSearchTool",
            backend,
        )
        return MockSearchTool()

    timeout = cfg.timeout_seconds if cfg is not None else DEFAULT_TIMEOUT_SECONDS
    rate = cfg.rate_limit_per_minute if cfg is not None else DEFAULT_RATE_LIMIT_PER_MINUTE
    max_results = cfg.max_results if cfg is not None else DEFAULT_MAX_RESULTS
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
