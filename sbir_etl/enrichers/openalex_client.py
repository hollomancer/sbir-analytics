"""OpenAlex API client for researcher author-record lookups.

Queries the `OpenAlex API <https://api.openalex.org/>`_ (a free, open
catalog of scholarly works, authors, and institutions) to find author
profiles and extract institutional affiliations, publication counts,
and any ORCID the author has on record.

No API key is required. OpenAlex offers a "polite pool" with faster,
more reliable rate limits to callers who identify themselves via a
``mailto`` query parameter. Set ``OPENALEX_MAILTO`` (or pass ``mailto``
to the constructor) to opt in; requests are unauthenticated either way.

This client inherits shared rate limiting, retry, and error
translation from :class:`BaseAsyncAPIClient`. Synchronous callers
should use :class:`sbir_etl.enrichers.sync_wrappers.SyncOpenAlexClient`.

Usage (sync)::

    from sbir_etl.enrichers.sync_wrappers import SyncOpenAlexClient

    with SyncOpenAlexClient(mailto="you@example.com") as client:
        record = client.lookup("Jane Smith")
        if record:
            print(record.openalex_id, record.affiliations)
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

import httpx

from sbir_etl.enrichers.base_client import BaseAsyncAPIClient
from sbir_etl.enrichers.rate_limiting import RateLimiter
from sbir_etl.exceptions import APIError

OPENALEX_API_URL = "https://api.openalex.org"
DEFAULT_RATE_LIMIT_PER_MINUTE = 100


@dataclass
class OpenAlexRecord:
    """Key data from an OpenAlex author record."""

    openalex_id: str
    display_name: str | None = None
    affiliations: list[str] = field(default_factory=list)
    orcid: str | None = None
    works_count: int = 0
    cited_by_count: int = 0


def _last_path_segment(value: str | None) -> str | None:
    """Extract the trailing path segment from an OpenAlex/ORCID URL or ID.

    OpenAlex returns IDs and ORCID cross-links as full URLs (e.g.
    ``https://openalex.org/A5110956653``, ``https://orcid.org/0000-...``).
    Bare IDs are passed through unchanged.
    """
    if not value:
        return None
    return value.rstrip("/").rsplit("/", 1)[-1]


def _parse_author(profile: dict[str, Any]) -> OpenAlexRecord:
    """Parse an OpenAlex author API response into an :class:`OpenAlexRecord`."""
    openalex_id = _last_path_segment(profile.get("id")) or str(profile.get("id", ""))

    affiliations: list[str] = []
    for aff in profile.get("affiliations", [])[:10]:
        inst_name = aff.get("institution", {}).get("display_name")
        if inst_name and inst_name not in affiliations:
            affiliations.append(inst_name)

    return OpenAlexRecord(
        openalex_id=openalex_id,
        display_name=profile.get("display_name"),
        affiliations=affiliations,
        orcid=_last_path_segment(profile.get("orcid")),
        works_count=profile.get("works_count", 0) or 0,
        cited_by_count=profile.get("cited_by_count", 0) or 0,
    )


class OpenAlexClient(BaseAsyncAPIClient):
    """Async client for the OpenAlex API.

    Inherits retry, rate limiting, and typed error translation from
    :class:`BaseAsyncAPIClient`. For sync callers, use
    :class:`sbir_etl.enrichers.sync_wrappers.SyncOpenAlexClient`.

    Args:
        mailto: Optional contact email to opt into OpenAlex's "polite
            pool" (faster, more reliable rate limits). Defaults to the
            ``OPENALEX_MAILTO`` environment variable. When unset, no
            ``mailto`` parameter is sent and requests use the common pool.
        timeout: HTTP request timeout in seconds.
        rate_limit_per_minute: Requests per minute when no
            ``shared_limiter`` is provided. Defaults to 100.
        shared_limiter: Optional shared synchronous :class:`RateLimiter` for
            sharing a global budget across worker threads. Dispatched via
            :func:`asyncio.to_thread`.
        http_client: Optional pre-constructed :class:`httpx.AsyncClient`
            (useful for testing).
    """

    api_name = "openalex"

    def __init__(
        self,
        *,
        mailto: str | None = None,
        timeout: int = 30,
        rate_limit_per_minute: int = DEFAULT_RATE_LIMIT_PER_MINUTE,
        shared_limiter: RateLimiter | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(shared_limiter=shared_limiter)
        self.base_url = OPENALEX_API_URL
        self.rate_limit_per_minute = rate_limit_per_minute
        self._mailto = mailto or os.environ.get("OPENALEX_MAILTO", "")
        self._client = http_client or httpx.AsyncClient(timeout=timeout)

    def _with_mailto(self, params: dict[str, Any]) -> dict[str, Any]:
        """Merge the polite-pool ``mailto`` parameter into a query dict."""
        merged = dict(params)
        if self._mailto:
            merged["mailto"] = self._mailto
        return merged

    async def search_authors(self, name: str, limit: int = 5) -> list[dict[str, Any]]:
        """Search for authors by name.

        Returns the ``results`` list from the API response (possibly
        empty). Returns an empty list on 4xx client errors; propagates
        :class:`APIError` on 5xx.
        """
        try:
            data = await self._make_request(
                "GET",
                "authors",
                params=self._with_mailto({"search": name, "per_page": limit}),
            )
        except APIError as e:
            status = e.details.get("http_status")
            if status and 400 <= status < 500:
                return []
            raise
        return data.get("results", []) or []

    async def get_author_details(self, openalex_id: str) -> dict[str, Any] | None:
        """Fetch full author details by OpenAlex ID.

        Accepts either a bare ID (``A5110956653``) or a full OpenAlex
        URL. Returns ``None`` if not found (404); propagates
        :class:`APIError` on other failures.
        """
        short_id = _last_path_segment(openalex_id) or openalex_id
        try:
            return await self._make_request(
                "GET",
                f"authors/{short_id}",
                params=self._with_mailto({}),
            )
        except APIError as e:
            if e.details.get("http_status") == 404:
                return None
            raise

    async def lookup(self, name: str) -> OpenAlexRecord | None:
        """Look up a researcher's OpenAlex author record by full name.

        Searches, then fetches the full record for the best match.
        Returns ``None`` when no match is found. Propagates
        :class:`APIError` on real API failures so callers can
        distinguish.
        """
        name = name.strip()
        if not name:
            return None

        results = await self.search_authors(name)
        if not results:
            return None

        best = results[0]
        short_id = _last_path_segment(best.get("id"))
        if not short_id:
            return None

        profile = await self.get_author_details(short_id)
        if profile is None:
            return None

        return _parse_author(profile)
