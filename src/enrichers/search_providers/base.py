"""
Search provider base interface and lightweight helpers.

This module defines a small, focused abstraction for integrating multiple
web-search / web-enrichment providers. Adapters should subclass `BaseSearchProvider`
and implement the `search` method, returning a `ProviderResponse`.

Goals:
- Normalize provider results into a common structure for scoring/benchmarking
- Provide small utilities for measuring latency, simple retry/backoff, and
  snippet normalization
- Keep dependencies minimal so adapters can be tested in isolation
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


class ProviderError(RuntimeError):
    """Base exception for provider-specific failures (network, auth, parse)."""


@dataclass
class ProviderResult:
    """Single normalized search result item."""

    title: str | None
    snippet: str | None
    url: str | None
    source: str | None = None
    score: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "snippet": self.snippet,
            "url": self.url,
            "source": self.source,
            "score": self.score,
            "metadata": self.metadata,
        }


@dataclass
class ProviderResponse:
    """Normalized provider response.

    Attributes:
        provider: short name of the provider (e.g., 'searxng', 'brave', 'google')
        query: the query string used
        results: list of normalized `ProviderResult`
        citations: optional list of authoritative citations extracted separately
        raw: original provider response (for debugging / replay)
        latency_ms: measured latency for the request in milliseconds
        cost_usd: optional cost estimate for the request (useful for benchmarking)
        metadata: free-form additional metadata (rate-limit headers, request id)
    """

    provider: str
    query: str
    results: list[ProviderResult]
    citations: list[dict[str, Any]] = field(default_factory=list)
    raw: Any | None = None
    latency_ms: float | None = None
    cost_usd: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "query": self.query,
            "results": [r.to_dict() for r in self.results],
            "citations": self.citations,
            "latency_ms": self.latency_ms,
            "cost_usd": self.cost_usd,
            "metadata": self.metadata,
        }


class BaseSearchProvider(ABC):
    """Abstract base class for search provider adapters.

    Subclasses MUST implement the `search` method and are encouraged to use the
    helpers provided here (latency measurement, retry/backoff, normalization).
    """

    def __init__(self, name: str, config: dict[str, Any] | None = None):
        self.name = name
        self.config = config or {}
        self.default_timeout = float(self.config.get("timeout_seconds", 10.0))
        self.max_retries = int(self.config.get("max_retries", 3))
        self.backoff_base = float(self.config.get("backoff_base", 2.0))

    @abstractmethod
    def search(self, query: str, context: dict[str, Any] | None = None) -> ProviderResponse:
        """Execute a search/enrichment request.

        Must return a normalized `ProviderResponse`. Implementations should
        catch provider-specific exceptions and raise `ProviderError` where
        appropriate to provide a consistent error surface.
        """

    # --- Utilities for adapters ------------------------------------------------

    def measure_latency(self, func: Callable[..., Any], *args, **kwargs) -> tuple[Any, float]:
        """Run `func` and measure elapsed time in milliseconds."""
        start = time.time()
        rv = func(*args, **kwargs)
        elapsed_ms = (time.time() - start) * 1000.0
        return rv, elapsed_ms

    def backoff_retry(
        self,
        func: Callable[..., Any],
        args: Iterable[Any] | None = None,
        kwargs: dict[str, Any] | None = None,
        max_retries: int | None = None,
        backoff_base: float | None = None,
        retriable_exceptions: tuple[type, ...] | None = None,
    ) -> Any:
        """Retry call to `func` with exponential backoff.

        Args:
            func: callable to execute
            args: positional args for callable
            kwargs: keyword args for callable
            max_retries: overrides self.max_retries if provided
            backoff_base: override self.backoff_base if provided
            retriable_exceptions: tuple of exception types that should be retried.
                If None, all exceptions are considered retriable.

        Returns:
            The callable return value on success.

        Raises:
            The last exception raised by `func` if all attempts fail.
        """
        args = args or ()
        kwargs = kwargs or {}
        max_retries = max_retries if max_retries is not None else self.max_retries
        backoff_base = backoff_base if backoff_base is not None else self.backoff_base
        retriable_exceptions = retriable_exceptions or (Exception,)

        for attempt in range(1, max_retries + 1):
            try:
                return func(*args, **kwargs)
            except retriable_exceptions as exc:
                if attempt < max_retries:
                    wait = backoff_base ** (attempt - 1)
                    logger.debug(
                        "%s: attempt %d/%d failed (%s); sleeping %.1fs before retry",
                        self.name,
                        attempt,
                        max_retries,
                        exc,
                        wait,
                    )
                    time.sleep(wait)
                else:
                    logger.error(
                        "%s: final attempt %d/%d failed (%s)", self.name, attempt, max_retries, exc
                    )
                    raise

    # --- Light normalization helpers -----------------------------------------

    @staticmethod
    def normalize_snippet(text: str | None, max_length: int | None = 1024) -> str | None:
        """Clean and normalize a snippet/summary returned by providers.

        - Collapse whitespace
        - Trim to max_length if requested
        - Return None if the input is falsy
        """
        if not text:
            return None
        s = " ".join(text.split())
        if max_length is not None and len(s) > max_length:
            return s[: max_length - 1] + "…"
        return s

    @staticmethod
    def pick_top_results(results: Iterable[ProviderResult], top_k: int = 5) -> list[ProviderResult]:
        """Return the top-k results by an available `score` field.

        If scores are not present, preserve original order up to `top_k`.
        """
        rs = list(results)
        if not rs:
            return []
        if all(r.score is None for r in rs):
            return rs[:top_k]
        # Stable sort by score descending
        return sorted(
            rs, key=lambda r: (r.score if r.score is not None else float("-inf")), reverse=True
        )[:top_k]

    @staticmethod
    def extract_urls_from_results(results: Iterable[ProviderResult]) -> list[str]:
        """Collect non-empty URLs from results in order."""
        urls: list[str] = []
        for r in results:
            if r.url:
                urls.append(r.url)
        return urls

    def estimate_request_cost(self, *_, **__) -> float:
        """Return an estimated cost for a single search request.

        Default is 0. Providers that charge per-request can override this.
        """
        return float(self.config.get("unit_cost_usd", 0.0))


# --- Small example helper for testing / mocking -------------------------------
def make_mock_response(
    provider: str, query: str, snippets: Iterable[str], urls: Iterable[str] | None = None
) -> ProviderResponse:
    """Create a lightweight mock ProviderResponse for tests/fixtures."""
    urls_list = list(urls) if urls is not None else [None] * len(list(snippets))
    results: list[ProviderResult] = []
    for idx, (s, u) in enumerate(zip(snippets, urls_list, strict=False)):
        results.append(
            ProviderResult(
                title=f"mock result {idx + 1}",
                snippet=BaseSearchProvider.normalize_snippet(s),
                url=u,
                source=provider,
                score=None,
                metadata={"mock_index": idx},
            )
        )
    return ProviderResponse(
        provider=provider, query=query, results=results, latency_ms=0.0, raw=None
    )
