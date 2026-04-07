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
Set ``OPENCORPORATES_API_TOKEN`` for higher limits.

Usage::

    from sbir_etl.enrichers.opencorporates import OpenCorporatesClient

    client = OpenCorporatesClient()
    record = client.lookup_company("Acme Defense Systems", jurisdiction="us_va")
    if record:
        print(record.incorporation_date, record.status)
        print(record.officers)
        if record.parent_company:
            print(f"Subsidiary of {record.parent_company}")
    client.close()
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Any

import httpx
from loguru import logger

OPENCORPORATES_API_URL = "https://api.opencorporates.com/v0.4"
MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 2  # seconds


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


class OpenCorporatesClient:
    """Client for querying the OpenCorporates API.

    Args:
        rate_limiter: Optional rate limiter with ``wait_if_needed()`` method.
        api_token: Optional API token. Defaults to ``OPENCORPORATES_API_TOKEN`` env var.
        timeout: HTTP request timeout in seconds.
    """

    def __init__(
        self,
        rate_limiter: Any | None = None,
        api_token: str | None = None,
        timeout: int = 30,
    ) -> None:
        self._limiter = rate_limiter
        self._timeout = timeout
        self._token = api_token or os.environ.get("OPENCORPORATES_API_TOKEN", "")
        self._client = httpx.Client(timeout=timeout)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> OpenCorporatesClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _wait(self) -> None:
        if self._limiter is not None:
            self._limiter.wait_if_needed()

    def _get_with_retry(
        self, url: str, params: dict[str, Any] | None = None
    ) -> dict | None:
        """GET with retry on 429/5xx."""
        params = dict(params or {})
        if self._token:
            params["api_token"] = self._token

        for attempt in range(MAX_RETRIES):
            self._wait()
            try:
                resp = self._client.get(url, params=params)
                if resp.status_code == 429:
                    wait = RETRY_BACKOFF_BASE ** (attempt + 1)
                    logger.debug(f"OpenCorporates 429, retrying in {wait}s")
                    time.sleep(wait)
                    continue
                if resp.status_code == 404:
                    return None
                if resp.status_code != 200:
                    logger.debug(f"OpenCorporates returned {resp.status_code}")
                    return None
                return resp.json()
            except httpx.HTTPError as e:
                logger.debug(f"OpenCorporates request error: {e}")
                time.sleep(RETRY_BACKOFF_BASE ** (attempt + 1))
        return None

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search_companies(
        self,
        name: str,
        jurisdiction: str | None = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Search for companies by name, optionally filtered by jurisdiction.

        Jurisdiction codes use OpenCorporates format, e.g. ``us_va``, ``us_de``.
        """
        params: dict[str, Any] = {"q": name, "per_page": limit}
        if jurisdiction:
            params["jurisdiction_code"] = jurisdiction

        data = self._get_with_retry(
            f"{OPENCORPORATES_API_URL}/companies/search",
            params=params,
        )
        if data is None:
            return []
        companies = data.get("results", {}).get("companies", [])
        return [c.get("company", c) for c in companies]

    # ------------------------------------------------------------------
    # Company details
    # ------------------------------------------------------------------

    def get_company(
        self, jurisdiction: str, company_number: str
    ) -> dict[str, Any] | None:
        """Fetch full company details by jurisdiction and company number."""
        return self._get_with_retry(
            f"{OPENCORPORATES_API_URL}/companies/{jurisdiction}/{company_number}",
        )

    def get_officers(
        self, jurisdiction: str, company_number: str
    ) -> list[Officer]:
        """Fetch officers for a company."""
        data = self._get_with_retry(
            f"{OPENCORPORATES_API_URL}/companies/{jurisdiction}/{company_number}/officers",
        )
        if data is None:
            return []

        officers_raw = (
            data.get("results", {}).get("officers", [])
        )
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

    def get_corporate_grouping(
        self, jurisdiction: str, company_number: str
    ) -> tuple[str | None, str | None]:
        """Check if a company belongs to a corporate grouping (parent).

        Returns (parent_name, parent_jurisdiction) or (None, None).
        """
        data = self.get_company(jurisdiction, company_number)
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

    def lookup_company(
        self,
        name: str,
        jurisdiction: str | None = None,
    ) -> CorporateRecord | None:
        """Look up a company's corporate record by name.

        Two-step: search → detail fetch with officers and groupings.
        Returns ``None`` if no match found.
        """
        results = self.search_companies(name, jurisdiction=jurisdiction, limit=3)
        if not results:
            return None

        # Take the first result
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
        detail_data = self.get_company(jur, num)
        company = {}
        if detail_data:
            company = (
                detail_data.get("results", {})
                .get("company", detail_data.get("company", {}))
            )

        # Officers
        officers = self.get_officers(jur, num)

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
