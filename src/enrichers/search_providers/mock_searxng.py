sbir - etl / src / enrichers / search_providers / mock_searxng.py
"""Mock SearXNG-like search provider for local testing and benchmarks.

This module provides a lightweight, deterministic mock provider that mimics
the basic shape of a SearXNG response and normalizes it into the project's
`ProviderResponse` structure. The mock can either load a JSON fixture file
or synthesize results on the fly. It supports configurable simulated latency,
result counts, and deterministic seeding to make tests repeatable.

Configuration keys (passed via the `config` dict):
- fixture_path: Optional[str] path to a JSON file with an array of items,
    each item expected to be {"title": "...", "snippet": "...", "url": "..."}.
- simulated_latency_ms: float (default 20.0) base latency to sleep (ms).
- jitter_ms: float (default 10.0) additional random jitter (ms).
- result_count: int (default 5) number of results to return when synthesizing.
- seed: Optional[int] seed for deterministic random behavior.
- include_titles: bool (default True) whether synthesized results include titles.
"""
from __future__ import annotations

import json
import random
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .base import BaseSearchProvider, ProviderResponse, ProviderResult


class MockSearxngProvider(BaseSearchProvider):
    """SearXNG-like mock provider used for unit tests and local evaluation.

    Example:
        provider = MockSearxngProvider(config={"simulated_latency_ms": 50, "result_count": 3})
        resp = provider.search("Acme Corp")
    """

    DEFAULTS = {
        "simulated_latency_ms": 20.0,
        "jitter_ms": 10.0,
        "result_count": 5,
        "include_titles": True,
        "fixture_path": None,
        "seed": None,
    }

    def __init__(self, name: str = "searxng-mock", config: Optional[Dict[str, Any]] = None):
        super().__init__(name=name, config=config or {})
        # Apply defaults to config
        for k, v in self.DEFAULTS.items():
            self.config.setdefault(k, v)

        seed = self.config.get("seed")
        if seed is not None:
            random.seed(int(seed))

        self._fixture_data: Optional[List[Dict[str, Any]]] = None
        fixture_path = self.config.get("fixture_path")
        if fixture_path:
            self._fixture_data = self._try_load_fixture(Path(fixture_path))

    def _try_load_fixture(self, path: Path) -> Optional[List[Dict[str, Any]]]:
        """Attempt to load a JSON fixture containing an array of result objects.

        Returns None on failure.
        """
        try:
            if not path.exists():
                return None
            with path.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, list):
                return data
            return None
        except Exception:
            # Do not raise in mocks; treat as no fixture available
            return None

    def _synthesize_results(self, query: str, k: int) -> List[ProviderResult]:
        """Create k synthetic results that include the query in snippets."""
        results: List[ProviderResult] = []
        include_titles = bool(self.config.get("include_titles", True))
        base_url = "https://example.com/search"
        for i in range(1, k + 1):
            title = f"{query} — SearxNG result {i}" if include_titles else None
            snippet = f"Mocked snippet for '{query}' (source: searxng-mock). Result {i}."
            snippet = self.normalize_snippet(snippet)
            url = f"{base_url}/{query.replace(' ', '_')}/{i}"
            results.append(
                ProviderResult(
                    title=title,
                    snippet=snippet,
                    url=url,
                    source="searxng",
                    metadata={"rank": i, "mock": True},
                )
            )
        return results

    def _results_from_fixture(self, query: str, k: int) -> List[ProviderResult]:
        """Select up to k results from loaded fixture, preferring entries that
        contain the query substring, otherwise returning the head of the fixture.
        """
        assert self._fixture_data is not None
        # Case-insensitive substring match on title or snippet
        matches: List[Dict[str, Any]] = []
        ql = query.lower()
        for item in self._fixture_data:
            title = (item.get("title") or "").lower()
            snippet = (item.get("snippet") or "").lower()
            if ql in title or ql in snippet:
                matches.append(item)
        source_list = matches or self._fixture_data
        out: List[ProviderResult] = []
        for idx, item in enumerate(source_list[:k], start=1):
            out.append(
                ProviderResult(
                    title=item.get("title"),
                    snippet=self.normalize_snippet(item.get("snippet")),
                    url=item.get("url"),
                    source=item.get("source") or "searxng-fixture",
                    metadata={"fixture_index": idx},
                )
            )
        return out

    def search(self, query: str, context: Optional[Dict[str, Any]] = None) -> ProviderResponse:
        """Return a normalized ProviderResponse.

        The method simulates real request characteristics:
        - Sleeps for configured latency + jitter
        - Produces deterministic results when `seed` is set
        - Uses fixture file if provided
        """
        # Measure wall-clock latency for the simulated request
        base_ms = float(self.config.get("simulated_latency_ms", 20.0))
        jitter_ms = float(self.config.get("jitter_ms", 10.0))
        sleep_ms = max(0.0, base_ms + random.uniform(-jitter_ms, jitter_ms))
        start = time.time()
        time.sleep(sleep_ms / 1000.0)

        # Build results
        k = int(self.config.get("result_count", 5))
        results: List[ProviderResult]
        fixture_used = False
        if self._fixture_data:
            results = self._results_from_fixture(query, k)
            fixture_used = True
        else:
            results = self._synthesize_results(query, k)

        # Optionally shuffle when seed is not set to mimic non-determinism
        if self.config.get("seed") is None:
            random.shuffle(results)

        latency_ms = (time.time() - start) * 1000.0
        resp = ProviderResponse(
            provider=self.name,
            query=query,
            results=results,
            citations=[{"url": r.url, "title": r.title} for r in results[:1] if r.url],
            raw={"simulated": True, "fixture_used": fixture_used, "sleep_ms": sleep_ms},
            latency_ms=latency_ms,
            cost_usd=self.estimate_request_cost(),
            metadata={"fixture_used": fixture_used, "result_count": len(results)},
        )
        return resp


# Simple factory for tests
def make_mock_searxng(config: Optional[Dict[str, Any]] = None) -> MockSearxngProvider:
    """Create a configured MockSearxngProvider for tests or CLI runs."""
    return MockSearxngProvider(config=config or {})


__all__ = ["MockSearxngProvider", "make_mock_searxng"]
