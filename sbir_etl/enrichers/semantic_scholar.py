"""Semantic Scholar API client for researcher publication lookups.

Queries the `Semantic Scholar Academic Graph API
<https://api.semanticscholar.org/>`_ to find author profiles and
retrieve publication statistics (h-index, citation count, paper
titles, affiliations). No API key is required for basic access
(rate limited to ~100 req/min). Set ``SEMANTIC_SCHOLAR_API_KEY``
for higher limits.

This client inherits shared rate limiting, retry, and error
translation from :class:`BaseAsyncAPIClient`. Synchronous callers
(scripts, notebooks, Dagster ops) should use
:class:`sbir_etl.enrichers.sync_wrappers.SyncSemanticScholarClient`
rather than running an event loop by hand.

Usage (async)::

    client = SemanticScholarClient()
    try:
        record = await client.lookup_author("Jane Smith")
    finally:
        await client.aclose()

Usage (sync)::

    from sbir_etl.enrichers.sync_wrappers import SyncSemanticScholarClient

    with SyncSemanticScholarClient() as client:
        record = client.lookup_author("Jane Smith")
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from typing import Any

import httpx

from sbir_etl.enrichers.base_client import BaseAsyncAPIClient
from sbir_etl.enrichers.rate_limiting import RateLimiter
from sbir_etl.exceptions import APIError

SEMANTIC_SCHOLAR_API_URL = "https://api.semanticscholar.org/graph/v1"
DEFAULT_RATE_LIMIT_PER_MINUTE = 100


@dataclass
class PublicationRecord:
    """Summary of a researcher's publication history."""

    total_papers: int
    h_index: int | None
    citation_count: int
    sample_titles: list[str]
    affiliations: list[str]


class SemanticScholarClient(BaseAsyncAPIClient):
    """Async client for the Semantic Scholar Academic Graph API.

    Inherits retry, rate limiting, and typed error translation from
    :class:`BaseAsyncAPIClient`.

    Args:
        api_key: Optional API key. Defaults to the ``SEMANTIC_SCHOLAR_API_KEY``
            environment variable. Sent as the ``x-api-key`` header.
        timeout: HTTP request timeout in seconds.
        rate_limit_per_minute: Requests per minute when no ``shared_limiter``
            is provided. Defaults to 100 (Semantic Scholar free-tier rate).
        shared_limiter: Optional shared synchronous :class:`RateLimiter`.
            When provided, overrides the base client's per-instance async
            limiter so that multiple client instances (e.g. across worker
            threads in a :class:`concurrent.futures.ThreadPoolExecutor`)
            can share a single global rate budget. The blocking
            ``wait_if_needed`` call is dispatched via :func:`asyncio.to_thread`
            so it does not block the shared background event loop.
        http_client: Optional pre-constructed :class:`httpx.AsyncClient`
            (useful for testing).
    """

    api_name = "semantic_scholar"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        timeout: int = 30,
        rate_limit_per_minute: int = DEFAULT_RATE_LIMIT_PER_MINUTE,
        shared_limiter: RateLimiter | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__()
        self.base_url = SEMANTIC_SCHOLAR_API_URL
        self.rate_limit_per_minute = rate_limit_per_minute
        self._shared_limiter = shared_limiter
        self._api_key = api_key or os.environ.get("SEMANTIC_SCHOLAR_API_KEY", "")
        self._client = http_client or httpx.AsyncClient(timeout=timeout)

    def _build_headers(self) -> dict[str, str]:
        """Extend base headers with the API key when set."""
        headers = super()._build_headers()
        if self._api_key:
            headers["x-api-key"] = self._api_key
        return headers

    async def _wait_for_rate_limit(self) -> None:
        """Use the injected shared limiter if present, else the base async limiter.

        The shared limiter is a synchronous :class:`RateLimiter` whose
        ``wait_if_needed`` call is blocking. We dispatch it via
        :func:`asyncio.to_thread` so it runs in a worker thread and does
        not block the process-wide background event loop that the sync
        facade (:func:`run_sync`) schedules coroutines onto.
        """
        if self._shared_limiter is not None:
            await asyncio.to_thread(self._shared_limiter.wait_if_needed)
            return
        await super()._wait_for_rate_limit()

    async def search_author(
        self, name: str, limit: int = 5
    ) -> list[dict[str, Any]]:
        """Search for authors by name.

        Returns the ``data`` list from the API response (possibly empty).
        Propagates :class:`APIError` on transport/server failures; 400
        responses (malformed query) return an empty list.
        """
        try:
            data = await self._make_request(
                "GET",
                "author/search",
                params={"query": name, "limit": limit},
            )
        except APIError as e:
            if e.details.get("http_status") == 400:
                return []
            raise
        return data.get("data", [])

    async def get_author_details(
        self, author_id: str
    ) -> dict[str, Any] | None:
        """Fetch author details including papers, h-index, and affiliations.

        Returns ``None`` if the author is not found (404); propagates
        :class:`APIError` on other failures.
        """
        try:
            return await self._make_request(
                "GET",
                f"author/{author_id}",
                params={
                    "fields": (
                        "name,hIndex,citationCount,affiliations,"
                        "papers.title,papers.year"
                    ),
                },
            )
        except APIError as e:
            if e.details.get("http_status") == 404:
                return None
            raise

    async def lookup_author(self, name: str) -> PublicationRecord | None:
        """Look up a researcher's publication profile by name.

        Two-step: author search → author details. Returns ``None`` when
        no match is found. Propagates :class:`APIError` for transport or
        server failures so callers can distinguish "no match" from
        "lookup failed".
        """
        authors = await self.search_author(name)
        if not authors:
            return None

        author_id = authors[0].get("authorId")
        if not author_id:
            return None

        details = await self.get_author_details(author_id)
        if details is None:
            return None

        papers = details.get("papers", [])
        sample_titles = [p["title"] for p in papers[:5] if p.get("title")]
        affiliations = details.get("affiliations", []) or []

        return PublicationRecord(
            total_papers=len(papers),
            h_index=details.get("hIndex"),
            citation_count=details.get("citationCount", 0),
            sample_titles=sample_titles,
            affiliations=affiliations,
        )
