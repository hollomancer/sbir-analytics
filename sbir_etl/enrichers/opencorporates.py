"""OpenCorporates API client for state corporation filing lookups.

Queries the `OpenCorporates API <https://api.opencorporates.com/>`_ to
retrieve incorporation details, officers, and corporate groupings that
are not available from SAM.gov.

**Unique value over SAM.gov:**

- Incorporation date (firm age at time of award)
- Subsidiary / parent relationships (shell detection)
- Officer names (cross-company overlap / fraud signals)
- State-level entity status (vs. SAM registration status)
- Multi-state filing visibility

No API key is required for the free tier (~500 requests/month).
Set ``OPENCORPORATES_API_TOKEN`` for higher limits — the token is
sent as the ``api_token`` query parameter per OpenCorporates docs.

This client inherits shared rate limiting, retry, and error
translation from :class:`BaseAsyncAPIClient`. Synchronous callers
should use :class:`sbir_etl.enrichers.sync_wrappers.SyncOpenCorporatesClient`.

Usage (sync)::

    from sbir_etl.enrichers.sync_wrappers import SyncOpenCorporatesClient

    with SyncOpenCorporatesClient() as client:
        record = client.lookup_company("Acme Defense Systems", jurisdiction="us_va")
        if record:
            print(record.incorporation_date, record.status)
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from typing import Any

import httpx
from loguru import logger

from sbir_etl.enrichers.base_client import BaseAsyncAPIClient
from sbir_etl.enrichers.rate_limiting import RateLimiter
from sbir_etl.exceptions import APIError

OPENCORPORATES_API_URL = "https://api.opencorporates.com/v0.4"
DEFAULT_RATE_LIMIT_PER_MINUTE = 30  # Free tier: ~500/month


@dataclass
class Officer:
    """A company officer from state filings."""

    name: str
    position: str | None = None
    start_date: str | None = None
    end_date: str | None = None


@dataclass
class CorporateRecord:
    """Parsed company record from OpenCorporates."""

    company_name: str
    jurisdiction: str
    company_number: str
    incorporation_date: str | None = None
    dissolution_date: str | None = None
    status: str | None = None
    company_type: str | None = None
    registered_address: str | None = None
    agent_name: str | None = None
    officers: list[Officer] = field(default_factory=list)
    parent_company: str | None = None
    parent_jurisdiction: str | None = None
    opencorporates_url: str | None = None


class OpenCorporatesClient(BaseAsyncAPIClient):
    """Async client for the OpenCorporates API.

    Inherits retry, rate limiting, and typed error translation from
    :class:`BaseAsyncAPIClient`. For sync callers, use
    :class:`sbir_etl.enrichers.sync_wrappers.SyncOpenCorporatesClient`.

    Args:
        api_token: Optional API token. Defaults to
            ``OPENCORPORATES_API_TOKEN`` environment variable. Sent as
            the ``api_token`` query parameter (OpenCorporates convention,
            not a bearer header).
        timeout: HTTP request timeout in seconds.
        rate_limit_per_minute: Requests per minute when no
            ``shared_limiter`` is provided. Defaults to 30 (the free-tier
            quota works out to ~17/min over 30 days — we leave headroom).
        shared_limiter: Optional shared synchronous :class:`RateLimiter`
            for sharing a global rate budget across worker threads.
            Dispatched via :func:`asyncio.to_thread`.
        http_client: Optional pre-constructed :class:`httpx.AsyncClient`
            (useful for testing).
    """

    api_name = "opencorporates"

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
        self.base_url = OPENCORPORATES_API_URL
        self.rate_limit_per_minute = rate_limit_per_minute
        self._shared_limiter = shared_limiter
        self._token = api_token or os.environ.get(
            "OPENCORPORATES_API_TOKEN", ""
        )
        self._client = http_client or httpx.AsyncClient(timeout=timeout)

    async def _wait_for_rate_limit(self) -> None:
        if self._shared_limiter is not None:
            await asyncio.to_thread(self._shared_limiter.wait_if_needed)
            return
        await super()._wait_for_rate_limit()

    async def _get(
        self, endpoint: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        """GET wrapper that injects the ``api_token`` query param.

        Returns ``None`` for 404 responses (not found) and propagates
        :class:`APIError` for other failures. Callers that care about
        distinguishing "not found" from "failed" should use
        :meth:`_make_request` directly.
        """
        merged = dict(params or {})
        if self._token:
            merged["api_token"] = self._token
        try:
            return await self._make_request("GET", endpoint, params=merged)
        except APIError as e:
            if e.details.get("http_status") == 404:
                return None
            raise

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    async def search_companies(
        self,
        name: str,
        jurisdiction: str | None = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Search for companies by name, optionally filtered by jurisdiction.

        Jurisdiction codes use OpenCorporates format, e.g. ``us_va``, ``us_de``.
        Short-circuits and returns an empty list if no API token is configured
        (search requires a token).
        """
        if not self._token:
            logger.debug(
                "OpenCorporates: no API token configured, skipping search"
            )
            return []
        params: dict[str, Any] = {"q": name, "per_page": limit}
        if jurisdiction:
            params["jurisdiction_code"] = jurisdiction

        data = await self._get("companies/search", params=params)
        if data is None:
            return []
        companies = data.get("results", {}).get("companies", [])
        return [c.get("company", c) for c in companies]

    # ------------------------------------------------------------------
    # Company details
    # ------------------------------------------------------------------

    async def get_company(
        self, jurisdiction: str, company_number: str
    ) -> dict[str, Any] | None:
        """Fetch full company details by jurisdiction and company number."""
        return await self._get(f"companies/{jurisdiction}/{company_number}")

    async def get_officers(
        self, jurisdiction: str, company_number: str
    ) -> list[Officer]:
        """Fetch officers for a company."""
        data = await self._get(
            f"companies/{jurisdiction}/{company_number}/officers"
        )
        if data is None:
            return []

        officers_raw = data.get("results", {}).get("officers", [])
        officers: list[Officer] = []
        for entry in officers_raw:
            o = entry.get("officer", entry)
            officers.append(
                Officer(
                    name=o.get("name", ""),
                    position=o.get("position"),
                    start_date=o.get("start_date"),
                    end_date=o.get("end_date"),
                )
            )
        return officers

    async def get_corporate_grouping(
        self, jurisdiction: str, company_number: str
    ) -> tuple[str | None, str | None]:
        """Check if a company belongs to a corporate grouping (parent).

        Returns ``(parent_name, parent_jurisdiction)`` or ``(None, None)``.
        """
        data = await self.get_company(jurisdiction, company_number)
        if data is None:
            return None, None

        company = data.get("results", {}).get("company", data.get("company", {}))
        groupings = company.get("corporate_groupings", [])
        if groupings:
            first = groupings[0]
            cg = first.get("corporate_grouping", first)
            return cg.get("name"), cg.get("jurisdiction_code")
        return None, None

    # ------------------------------------------------------------------
    # High-level lookup
    # ------------------------------------------------------------------

    async def lookup_company(
        self,
        name: str,
        jurisdiction: str | None = None,
    ) -> CorporateRecord | None:
        """Look up a company's corporate record by name.

        Two-step: search → detail fetch with officers and groupings.
        Returns ``None`` if no match found. Propagates :class:`APIError`
        on transport/server failures so callers can distinguish.
        """
        results = await self.search_companies(
            name, jurisdiction=jurisdiction, limit=3
        )
        if not results:
            return None

        best = results[0]
        jur = best.get("jurisdiction_code", "")
        num = best.get("company_number", "")

        if not jur or not num:
            # Build a minimal record from search results
            return CorporateRecord(
                company_name=best.get("name", name),
                jurisdiction=jur,
                company_number=num,
                incorporation_date=best.get("incorporation_date"),
                status=best.get("current_status"),
                company_type=best.get("company_type"),
                opencorporates_url=best.get("opencorporates_url"),
            )

        # Fetch full details
        detail_data = await self.get_company(jur, num)
        company = {}
        if detail_data:
            company = (
                detail_data.get("results", {})
                .get("company", detail_data.get("company", {}))
            )

        # Officers
        officers = await self.get_officers(jur, num)

        # Parent / corporate grouping
        parent_name, parent_jur = None, None
        groupings = company.get("corporate_groupings", [])
        if groupings:
            first = groupings[0]
            cg = first.get("corporate_grouping", first)
            parent_name = cg.get("name")
            parent_jur = cg.get("jurisdiction_code")

        # Registered address
        addr = company.get("registered_address", {}) or {}
        address_str = None
        if addr:
            parts = [
                addr.get("street_address", ""),
                addr.get("locality", ""),
                addr.get("region", ""),
                addr.get("postal_code", ""),
            ]
            address_str = ", ".join(p for p in parts if p) or None

        return CorporateRecord(
            company_name=company.get("name", best.get("name", name)),
            jurisdiction=jur,
            company_number=num,
            incorporation_date=company.get("incorporation_date"),
            dissolution_date=company.get("dissolution_date"),
            status=company.get("current_status"),
            company_type=company.get("company_type"),
            registered_address=address_str,
            agent_name=company.get("agent_name"),
            officers=officers,
            parent_company=parent_name,
            parent_jurisdiction=parent_jur,
            opencorporates_url=company.get("opencorporates_url"),
        )
