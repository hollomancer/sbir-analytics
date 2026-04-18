"""ORCID public API client for researcher profile lookups.

Queries the `ORCID public API <https://pub.orcid.org/>`_ to find
researcher profiles and extract affiliations, works, funding, and
keywords.

No API key is required for basic access. Set ``ORCID_ACCESS_TOKEN``
for higher rate limits (generate via client credentials grant with a
free ORCID Public API application).

This client inherits shared rate limiting, retry, and error
translation from :class:`BaseAsyncAPIClient`. Synchronous callers
should use :class:`sbir_etl.enrichers.sync_wrappers.SyncORCIDClient`.

Usage (sync)::

    from sbir_etl.enrichers.sync_wrappers import SyncORCIDClient

    with SyncORCIDClient() as client:
        record = client.lookup("Jane Smith")
        if record:
            print(record.orcid_id, record.works_count)
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

import httpx

from sbir_etl.enrichers.base_client import BaseAsyncAPIClient
from sbir_etl.enrichers.rate_limiting import RateLimiter
from sbir_etl.exceptions import APIError

ORCID_API_URL = "https://pub.orcid.org/v3.0"
DEFAULT_RATE_LIMIT_PER_MINUTE = 60


@dataclass
class ORCIDRecord:
    """Key data from an ORCID researcher profile."""

    orcid_id: str
    given_name: str | None = None
    family_name: str | None = None
    affiliations: list[str] = field(default_factory=list)
    works_count: int = 0
    sample_work_titles: list[str] = field(default_factory=list)
    funding_count: int = 0
    keywords: list[str] = field(default_factory=list)


def _parse_profile(
    orcid_id: str, search_result: dict, profile: dict
) -> ORCIDRecord:
    """Parse an ORCID profile response into an :class:`ORCIDRecord`."""
    # Affiliations
    affiliations: list[str] = []
    affiliation_groups = (
        profile.get("activities-summary", {})
        .get("employments", {})
        .get("affiliation-group", [])
    )
    for group in affiliation_groups[:10]:
        for s in group.get("summaries", []):
            org_name = (
                s.get("employment-summary", {})
                .get("organization", {})
                .get("name", "")
            )
            if org_name and org_name not in affiliations:
                affiliations.append(org_name)

    # Works
    works_group = (
        profile.get("activities-summary", {})
        .get("works", {})
        .get("group", [])
    )
    sample_titles: list[str] = []
    for wg in works_group[:5]:
        summaries = wg.get("work-summary", [])
        if summaries:
            title_val = (
                summaries[0].get("title", {}).get("title", {}).get("value", "")
            )
            if title_val:
                sample_titles.append(title_val)

    # Funding
    funding_group = (
        profile.get("activities-summary", {})
        .get("fundings", {})
        .get("group", [])
    )

    # Keywords
    keyword_list = (
        profile.get("person", {}).get("keywords", {}).get("keyword", [])
    )
    keywords = [
        kw.get("content", "") for kw in keyword_list[:10] if kw.get("content")
    ]

    return ORCIDRecord(
        orcid_id=orcid_id,
        given_name=search_result.get("given-names"),
        family_name=search_result.get("family-names"),
        affiliations=affiliations,
        works_count=len(works_group),
        sample_work_titles=sample_titles,
        funding_count=len(funding_group),
        keywords=keywords,
    )


class ORCIDClient(BaseAsyncAPIClient):
    """Async client for the ORCID public API.

    Inherits retry, rate limiting, and typed error translation from
    :class:`BaseAsyncAPIClient`. For sync callers, use
    :class:`sbir_etl.enrichers.sync_wrappers.SyncORCIDClient`.

    Args:
        access_token: Optional OAuth token. Defaults to ``ORCID_ACCESS_TOKEN``
            environment variable. When set, sent as ``Authorization: Bearer``.
        timeout: HTTP request timeout in seconds.
        rate_limit_per_minute: Requests per minute when no ``shared_limiter``
            is provided. Defaults to 60.
        shared_limiter: Optional shared synchronous :class:`RateLimiter` for
            sharing a global budget across worker threads. Dispatched via
            :func:`asyncio.to_thread`.
        http_client: Optional pre-constructed :class:`httpx.AsyncClient`
            (useful for testing).
    """

    api_name = "orcid"

    def __init__(
        self,
        *,
        access_token: str | None = None,
        timeout: int = 30,
        rate_limit_per_minute: int = DEFAULT_RATE_LIMIT_PER_MINUTE,
        shared_limiter: RateLimiter | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(shared_limiter=shared_limiter)
        self.base_url = ORCID_API_URL
        self.rate_limit_per_minute = rate_limit_per_minute
        self._access_token = access_token or os.environ.get(
            "ORCID_ACCESS_TOKEN", ""
        )
        self._client = http_client or httpx.AsyncClient(timeout=timeout)

    def _build_headers(self) -> dict[str, str]:
        headers = super()._build_headers()
        if self._access_token:
            headers["Authorization"] = f"Bearer {self._access_token}"
        return headers

    async def search(
        self,
        family_name: str,
        given_names: str | None = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Search for researchers by name.

        Returns the ``expanded-result`` list from the ORCID API
        (possibly empty). Returns an empty list on 4xx client errors;
        propagates :class:`APIError` on 5xx.
        """
        query = f"family-name:{family_name}"
        if given_names:
            # Literal " AND " — httpx encodes spaces in query params
            # automatically. The old "+AND+" was double-encoded
            # (%2BAND%2B) which caused ORCID to return 500.
            query += f" AND given-names:{given_names}"

        try:
            data = await self._make_request(
                "GET",
                "expanded-search/",
                params={"q": query, "rows": limit},
            )
        except APIError as e:
            status = e.details.get("http_status")
            if status and 400 <= status < 500:
                return []
            raise
        return data.get("expanded-result", []) or []

    async def get_profile(self, orcid_id: str) -> dict[str, Any] | None:
        """Fetch a full ORCID profile by ID.

        Returns ``None`` if not found (404); propagates :class:`APIError`
        on other failures.
        """
        try:
            return await self._make_request("GET", f"{orcid_id}/record")
        except APIError as e:
            if e.details.get("http_status") == 404:
                return None
            raise

    async def lookup(self, name: str) -> ORCIDRecord | None:
        """Look up a researcher's ORCID profile by full name.

        Splits *name* into given/family components, searches, then
        fetches the full profile for the best match. Returns ``None``
        when no match is found. Propagates :class:`APIError` on real
        API failures so callers can distinguish.
        """
        parts = name.strip().split()
        if not parts:
            return None
        family = parts[-1]
        given = " ".join(parts[:-1]) if len(parts) > 1 else None

        results = await self.search(family, given)
        if not results:
            return None

        best = results[0]
        orcid_id = best.get("orcid-id", "")
        if not orcid_id:
            return None

        profile = await self.get_profile(orcid_id)
        if profile is None:
            return None

        return _parse_profile(orcid_id, best, profile)
