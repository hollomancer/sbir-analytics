"""SBIR.gov Awards API client for cross-referencing SBIR/STTR awards.

The SBIR.gov API (https://api.www.sbir.gov/public/api/) provides authoritative
SBIR/STTR award data across all participating agencies.  This client is used to:

1. Validate SBIR/STTR identification from FPDS/FABS data
2. Enrich awards with fields not available in USAspending (topic codes, abstracts)
3. Provide a canonical SBIR award reference for HHS/NIH grants where ALN-based
   identification alone is ambiguous

API Docs: https://www.sbir.gov/api
No authentication required.  No documented rate limit (be respectful).
"""

from __future__ import annotations

from typing import Any

import httpx
from loguru import logger
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from ..exceptions import APIError

SBIR_GOV_API_BASE = "https://api.www.sbir.gov/public/api"

# Agencies that participate in SBIR/STTR
SBIR_PARTICIPATING_AGENCIES = [
    "DOD",
    "DOE",
    "HHS",
    "NASA",
    "NSF",
    "USDA",
    "EPA",
    "DOC",
    "ED",
    "DHS",
    "DOT",
]


class SbirGovClient:
    """Client for the SBIR.gov public awards API."""

    def __init__(
        self,
        *,
        base_url: str = SBIR_GOV_API_BASE,
        timeout: float = 30.0,
        http_client: httpx.Client | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client = http_client

    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=self.timeout)
        return self._client

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    # ------------------------------------------------------------------
    # Core query methods
    # ------------------------------------------------------------------

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=2, max=30),
        retry=retry_if_exception_type((httpx.TransportError, httpx.TimeoutException)),
    )
    def query_awards(
        self,
        *,
        agency: str | None = None,
        firm: str | None = None,
        year: int | None = None,
        start: int = 0,
        rows: int = 100,
    ) -> list[dict[str, Any]]:
        """Query SBIR.gov awards.

        Args:
            agency: Agency abbreviation (e.g. ``"DOE"``, ``"DOD"``).
            firm: Company name (partial match).
            year: Award year.
            start: Pagination offset.
            rows: Number of results per page (max varies).

        Returns:
            List of award dicts from the API.

        Raises:
            APIError: If the request fails after retries.
        """
        params: dict[str, str | int] = {"start": start, "rows": rows}
        if agency:
            params["agency"] = agency
        if firm:
            params["firm"] = firm
        if year:
            params["year"] = year

        url = f"{self.base_url}/awards"
        logger.debug(f"SBIR.gov API request: {url} params={params}")

        response = self.client.get(url, params=params)

        if response.status_code != 200:
            raise APIError(
                f"SBIR.gov API returned {response.status_code}: {response.text[:200]}",
                status_code=response.status_code,
            )

        data = response.json()

        # API returns a list directly or a dict with results
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            # Guard against keys present but set to None
            return data.get("results") or data.get("data") or []
        return []

    def query_all_awards(
        self,
        *,
        agency: str | None = None,
        firm: str | None = None,
        year: int | None = None,
        max_results: int = 10000,
        page_size: int = 100,
    ) -> list[dict[str, Any]]:
        """Paginate through all matching awards.

        Args:
            agency: Agency filter.
            firm: Firm name filter.
            year: Year filter.
            max_results: Safety cap on total results.
            page_size: Results per API call.

        Returns:
            Combined list of all matching awards.
        """
        all_awards: list[dict[str, Any]] = []
        offset = 0

        while offset < max_results:
            page = self.query_awards(
                agency=agency,
                firm=firm,
                year=year,
                start=offset,
                rows=page_size,
            )
            if not page:
                break

            all_awards.extend(page)
            offset += len(page)

            if len(page) < page_size:
                break  # last page

            logger.debug(f"SBIR.gov: fetched {len(all_awards)} awards so far")

        logger.info(f"SBIR.gov: fetched {len(all_awards)} total awards")
        return all_awards

    # ------------------------------------------------------------------
    # Cross-reference helpers
    # ------------------------------------------------------------------

    def build_lookup_index(
        self,
        awards: list[dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        """Build a lookup index from SBIR.gov award data.

        Creates an index keyed by contract/award number for
        cross-referencing with USAspending data.

        Args:
            awards: List of SBIR.gov award records.

        Returns:
            Dict keyed by contract number (uppercased, stripped).
        """
        index: dict[str, dict[str, Any]] = {}
        for award in awards:
            contract = award.get("contract", "")
            if contract:
                key = str(contract).strip().upper()
                index[key] = award
        return index

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


__all__ = ["SbirGovClient", "SBIR_GOV_API_BASE", "SBIR_PARTICIPATING_AGENCIES"]
