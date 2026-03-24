"""SBIR.gov Awards API client for cross-referencing SBIR/STTR awards.

The SBIR.gov API (https://api.www.sbir.gov/public/api/) provides authoritative
SBIR/STTR award data across all participating agencies.  This client is used to:

1. Validate SBIR/STTR identification from FPDS/FABS data
2. Enrich awards with fields not available in USAspending (topic codes, abstracts)
3. Provide a canonical SBIR award reference for HHS/NIH grants where ALN-based
   identification alone is ambiguous

API Docs: https://www.sbir.gov/api
No authentication required.  No documented rate limit (be respectful).

Bulk downloads: https://www.sbir.gov/data-resources
  - Award data with abstracts (~290 MB JSON)
  - Award data without abstracts (~65 MB JSON)
"""

from __future__ import annotations

import json
from pathlib import Path
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

    @staticmethod
    def build_lookup_index(
        awards: list[dict[str, Any]],
    ) -> "SbirGovLookupIndex":
        """Build a multi-key lookup index from SBIR.gov award data.

        Creates indexes keyed by contract/award number, UEI, and DUNS for
        cross-referencing with USAspending data.

        Args:
            awards: List of SBIR.gov award records.

        Returns:
            ``SbirGovLookupIndex`` supporting lookup by contract, UEI, or DUNS.
        """
        return SbirGovLookupIndex(awards)

    # ------------------------------------------------------------------
    # Bulk download support
    # ------------------------------------------------------------------

    def load_bulk_awards(self, path: Path | str) -> list[dict[str, Any]]:
        """Load SBIR.gov awards from a bulk download JSON file.

        SBIR.gov provides full award exports at https://www.sbir.gov/data-resources.
        Download the JSON format (~65 MB without abstracts, ~290 MB with).

        Args:
            path: Path to the downloaded JSON file.

        Returns:
            List of award dicts (same schema as the API).
        """
        path = Path(path)
        logger.info(f"Loading SBIR.gov bulk awards from {path}")

        with open(path) as f:
            data = json.load(f)

        # File may be a list directly or wrapped in a dict
        if isinstance(data, list):
            awards = data
        elif isinstance(data, dict):
            awards = data.get("results") or data.get("data") or data.get("awards") or []
        else:
            awards = []

        logger.info(f"Loaded {len(awards)} awards from bulk file")
        return awards

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class SbirGovLookupIndex:
    """Multi-key lookup index for SBIR.gov award cross-referencing.

    Supports lookup by contract/award number, UEI, or DUNS — whichever
    identifier is available on the USAspending record being validated.
    """

    def __init__(self, awards: list[dict[str, Any]]) -> None:
        self.by_contract: dict[str, dict[str, Any]] = {}
        self.by_uei: dict[str, dict[str, Any]] = {}
        self.by_duns: dict[str, dict[str, Any]] = {}
        self._size = 0

        for award in awards:
            self._size += 1
            contract = award.get("contract", "")
            if contract:
                self.by_contract[str(contract).strip().upper()] = award
            uei = award.get("uei", "")
            if uei:
                self.by_uei[str(uei).strip().upper()] = award
            duns = award.get("duns", "")
            if duns:
                digits = "".join(ch for ch in str(duns) if ch.isdigit())
                if digits:
                    self.by_duns[digits] = award

        logger.debug(
            f"SbirGovLookupIndex built: {len(self.by_contract)} contracts, "
            f"{len(self.by_uei)} UEIs, {len(self.by_duns)} DUNS from {self._size} awards"
        )

    def lookup(
        self,
        *,
        contract: str | None = None,
        uei: str | None = None,
        duns: str | None = None,
    ) -> dict[str, Any] | None:
        """Look up an award by any available identifier.

        Checks contract number first (most specific), then UEI, then DUNS.

        Returns:
            The matching SBIR.gov award dict, or ``None``.
        """
        if contract:
            hit = self.by_contract.get(str(contract).strip().upper())
            if hit:
                return hit
        if uei:
            hit = self.by_uei.get(str(uei).strip().upper())
            if hit:
                return hit
        if duns:
            digits = "".join(ch for ch in str(duns) if ch.isdigit())
            if digits:
                hit = self.by_duns.get(digits)
                if hit:
                    return hit
        return None

    def __len__(self) -> int:
        return self._size

    def __bool__(self) -> bool:
        return self._size > 0


__all__ = [
    "SbirGovClient",
    "SbirGovLookupIndex",
    "SBIR_GOV_API_BASE",
    "SBIR_PARTICIPATING_AGENCIES",
]
