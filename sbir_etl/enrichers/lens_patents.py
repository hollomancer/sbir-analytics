"""Lens.org Scholarly & Patent API client for patent fallback lookups.

The Lens.org API (https://www.lens.org/lens/api) provides free access to
patent and scholarly data. It serves as a fallback when the USPTO ODP
(PatentsView) API is unavailable or the API key is missing.

Free tier: 50 requests/minute, 1000/day with a free account.
Set ``LENS_API_TOKEN`` environment variable for authentication.

This client inherits shared rate limiting, retry, and error
translation from :class:`BaseAsyncAPIClient`. Synchronous callers
should use :class:`sbir_etl.enrichers.sync_wrappers.SyncLensPatentClient`.

Usage (sync)::

    from sbir_etl.enrichers.sync_wrappers import SyncLensPatentClient

    with SyncLensPatentClient() as client:
        patents = client.search_patents_by_assignee("Acme Defense Systems")
        for p in patents:
            print(p.title, p.assignee)
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from typing import Any

import httpx
from loguru import logger

from sbir_etl.enrichers.base_client import BaseAsyncAPIClient
from sbir_etl.enrichers.rate_limiting import RateLimiter
from sbir_etl.exceptions import APIError

LENS_API_URL = "https://api.lens.org/patent/search"
DEFAULT_RATE_LIMIT_PER_MINUTE = 50  # Free tier: 50/min


@dataclass
class LensPatentRecord:
    """Normalized patent record from Lens.org."""

    patent_number: str
    title: str
    assignee: str | None = None
    inventor_names: list[str] | None = None
    filing_date: str | None = None
    grant_date: str | None = None
    publication_date: str | None = None


def _parse_records(data: dict) -> list[LensPatentRecord]:
    """Parse Lens.org API response into a list of :class:`LensPatentRecord`.

    Extracted as a module-level function so it's unit-testable without
    constructing a full async client.
    """
    records: list[LensPatentRecord] = []
    for hit in data.get("data", []):
        # Extract title
        title = ""
        title_obj = hit.get("title")
        if isinstance(title_obj, list) and title_obj:
            title = title_obj[0].get("text", "")
        elif isinstance(title_obj, str):
            title = title_obj

        # Extract assignee/applicant
        assignee = None
        applicants = hit.get("applicant", [])
        if applicants and isinstance(applicants, list):
            first = applicants[0]
            assignee = (
                first.get("name") if isinstance(first, dict) else str(first)
            )

        # Extract inventors
        inventor_names: list[str] = []
        for inv in hit.get("inventor", []):
            if isinstance(inv, dict):
                name = inv.get("name", "")
                if name:
                    inventor_names.append(name)

        records.append(
            LensPatentRecord(
                patent_number=hit.get("lens_id", ""),
                title=title,
                assignee=assignee,
                inventor_names=inventor_names,
                filing_date=hit.get("filing_date"),
                # Lens doesn't distinguish grant vs publication
                grant_date=None,
                publication_date=hit.get("date_published"),
            )
        )

    return records


class LensPatentClient(BaseAsyncAPIClient):
    """Async client for the Lens.org Patent Search API.

    Inherits retry, rate limiting, and typed error translation from
    :class:`BaseAsyncAPIClient`. Lens uses POST with a JSON body for
    search — the base client's POST path sends the ``params`` dict as
    the request body (same convention as USAspending's POST endpoints).
    For sync callers, use
    :class:`sbir_etl.enrichers.sync_wrappers.SyncLensPatentClient`.

    Args:
        api_token: Optional API token. Defaults to ``LENS_API_TOKEN``
            environment variable. Sent as ``Authorization: Bearer``.
            Required — without a token the search methods short-circuit
            and return an empty list.
        timeout: HTTP request timeout in seconds.
        rate_limit_per_minute: Requests per minute when no
            ``shared_limiter`` is provided. Defaults to 50 (free tier).
        shared_limiter: Optional shared synchronous :class:`RateLimiter`
            for sharing a global rate budget across worker threads.
            Dispatched via :func:`asyncio.to_thread`.
        http_client: Optional pre-constructed :class:`httpx.AsyncClient`
            (useful for testing).
    """

    api_name = "lens_patents"

    def __init__(
        self,
        *,
        api_token: str | None = None,
        timeout: int = 30,
        rate_limit_per_minute: int = DEFAULT_RATE_LIMIT_PER_MINUTE,
        shared_limiter: RateLimiter | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__()
        # LENS_API_URL is the full endpoint — pass as absolute URL to
        # _make_request so base_url can stay empty.
        self.base_url = ""
        self.rate_limit_per_minute = rate_limit_per_minute
        self._shared_limiter = shared_limiter
        self._token = api_token or os.environ.get("LENS_API_TOKEN", "")
        if not self._token:
            logger.debug(
                "LENS_API_TOKEN not set — Lens.org patent lookups will short-circuit"
            )
        self._client = http_client or httpx.AsyncClient(timeout=timeout)

    def _build_headers(self) -> dict[str, str]:
        headers = super()._build_headers()
        headers["Content-Type"] = "application/json"
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    async def _wait_for_rate_limit(self) -> None:
        if self._shared_limiter is not None:
            await asyncio.to_thread(self._shared_limiter.wait_if_needed)
            return
        await super()._wait_for_rate_limit()

    async def _search(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        """POST a search payload to the Lens API.

        Returns ``None`` without hitting the network if no token is
        configured (search requires authentication). On API errors,
        returns ``None`` to preserve the legacy "errors as None"
        contract — callers (``pi_enrichment.lookup_pi_patents_with_fallback``)
        already wrap in ``try/except Exception``.
        """
        if not self._token:
            return None

        try:
            return await self._make_request("POST", LENS_API_URL, params=payload)
        except APIError as e:
            logger.debug("Lens.org API error: {}", e)
            return None

    async def search_patents_by_assignee(
        self,
        company_name: str,
        max_results: int = 100,
    ) -> list[LensPatentRecord]:
        """Search for patents by assignee name."""
        payload: dict[str, Any] = {
            "query": {
                "match": {
                    "applicant.name": company_name,
                }
            },
            "size": min(max_results, 100),
            "sort": [{"date_published": "desc"}],
            "include": [
                "lens_id",
                "title",
                "applicant",
                "inventor",
                "date_published",
                "filing_date",
                "publication_type",
            ],
        }

        data = await self._search(payload)
        if data is None:
            return []
        return _parse_records(data)

    async def search_patents_by_inventor(
        self,
        inventor_name: str,
        max_results: int = 50,
    ) -> list[LensPatentRecord]:
        """Search for patents by inventor name."""
        payload: dict[str, Any] = {
            "query": {
                "match": {
                    "inventor.name": inventor_name,
                }
            },
            "size": min(max_results, 50),
            "sort": [{"date_published": "desc"}],
            "include": [
                "lens_id",
                "title",
                "applicant",
                "inventor",
                "date_published",
                "filing_date",
            ],
        }

        data = await self._search(payload)
        if data is None:
            return []
        return _parse_records(data)
