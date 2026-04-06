"""SEC EDGAR API client for company filing data.

Provides an async client for querying SEC EDGAR APIs:
- Full-text search (EFTS) for CIK resolution by company name
- Company facts (XBRL) for standardized financial data
- Filing index for recent filings by type

Respects SEC fair-access policy: 10 requests/second, with User-Agent
containing a contact email address.
"""

from __future__ import annotations

import os
from typing import Any, cast

import httpx
from loguru import logger

from ...config.loader import get_config
from ...exceptions import APIError
from ..base_client import BaseAsyncAPIClient


class EdgarAPIClient(BaseAsyncAPIClient):
    """Async client for SEC EDGAR APIs.

    Uses three EDGAR endpoints:
    - EFTS full-text search: company name → CIK resolution
    - Company facts: CIK → XBRL financial data
    - Filing index: CIK → recent filings by type
    """

    api_name = "sec_edgar"

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        *,
        http_client: httpx.AsyncClient | None = None,
    ):
        super().__init__()

        if config is None:
            cfg = get_config()
            self.api_config = cfg.enrichment.sec_edgar
        else:
            self.api_config = config

        self.base_url = str(
            self.api_config.get("base_url", "https://efts.sec.gov/LATEST")
        )
        self.facts_base_url = str(
            self.api_config.get("facts_base_url", "https://data.sec.gov/api/xbrl")
        )
        self.filings_base_url = str(
            self.api_config.get("filings_base_url", "https://data.sec.gov/submissions")
        )
        self.timeout = cast(int, self.api_config.get("timeout_seconds", 30))
        self.rate_limit_per_minute = cast(
            int, self.api_config.get("rate_limit_per_minute", 600)
        )

        # SEC requires a User-Agent with contact info for fair access
        contact_email = str(
            self.api_config.get(
                "contact_email_env_var", "SEC_EDGAR_CONTACT_EMAIL"
            )
        )
        self.contact_email = os.getenv(contact_email, "")
        if not self.contact_email:
            logger.warning(
                f"SEC EDGAR contact email not found in {contact_email}. "
                "Set this to comply with SEC fair-access policy."
            )

        self._client = http_client or httpx.AsyncClient(timeout=self.timeout)

        logger.info(
            f"Initialized EdgarAPIClient: efts={self.base_url}, "
            f"rate_limit={self.rate_limit_per_minute}/min"
        )

    def _build_headers(self) -> dict[str, str]:
        """Build headers with SEC-required User-Agent."""
        headers = super()._build_headers()
        if self.contact_email:
            headers["User-Agent"] = f"SBIR-Analytics/0.1.0 ({self.contact_email})"
        return headers

    async def search_companies(
        self,
        company_name: str,
        *,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Search EDGAR full-text search for companies by name.

        Uses the EFTS endpoint to find CIK matches.

        Args:
            company_name: Company name to search for.
            limit: Maximum results to return.

        Returns:
            List of company match dicts with keys: cik, entity_name, ticker, etc.
        """
        params = {
            "q": company_name,
            "dateRange": "custom",
            "startdt": "2000-01-01",
            "enddt": "2026-12-31",
            "forms": "10-K",
        }
        try:
            response = await self._make_request(
                "GET", "/search-index", params=params
            )
            hits = response.get("hits", {}).get("hits", [])
            results = []
            for hit in hits[:limit]:
                source = hit.get("_source", {})
                results.append({
                    "cik": str(source.get("entity_id", "")),
                    "entity_name": source.get("entity_name", ""),
                    "ticker": source.get("ticker", None),
                    "file_date": source.get("file_date", None),
                    "form_type": source.get("form_type", None),
                })
            return results
        except APIError as e:
            logger.warning(f"EDGAR company search failed for '{company_name}': {e}")
            return []

    async def search_filing_mentions(
        self,
        company_name: str,
        *,
        forms: str = "8-K",
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Search EFTS for mentions of a company name inside filing text.

        Unlike search_companies which finds the *filing entity*, this searches
        the full text of filings for any mention of the company name. This is
        the key method for finding private SBIR companies mentioned in public
        company filings (e.g., acquisition targets in 8-K filings).

        Args:
            company_name: Company name to search for in filing text.
            forms: Filing types to search (comma-separated, e.g., "8-K,10-K").
            limit: Maximum results to return.

        Returns:
            List of filing mention dicts with: filer_cik, filer_name,
            form_type, file_date, accession_number, file_description.
        """
        # Quote the company name for exact phrase matching
        params = {
            "q": f'"{company_name}"',
            "dateRange": "custom",
            "startdt": "2000-01-01",
            "enddt": "2026-12-31",
            "forms": forms,
        }
        try:
            response = await self._make_request(
                "GET", "/search-index", params=params
            )
            hits = response.get("hits", {}).get("hits", [])
            results = []
            for hit in hits[:limit]:
                source = hit.get("_source", {})
                results.append({
                    "filer_cik": str(source.get("entity_id", "")),
                    "filer_name": source.get("entity_name", ""),
                    "form_type": source.get("form_type", ""),
                    "file_date": source.get("file_date", None),
                    "accession_number": source.get("file_num", ""),
                    "file_description": source.get("file_description", ""),
                })
            return results
        except APIError as e:
            logger.warning(
                f"EDGAR filing mention search failed for '{company_name}': {e}"
            )
            return []

    async def search_form_d_filings(
        self,
        company_name: str,
        *,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Search for Form D (Regulation D) filings by a company.

        Private companies raising capital under Regulation D must file Form D
        with the SEC. This identifies SBIR companies that raised venture/angel
        capital — a strong signal for company health and growth trajectory.

        Args:
            company_name: Company name to search for.
            limit: Maximum results to return.

        Returns:
            List of Form D filing dicts with: cik, entity_name, file_date.
        """
        params = {
            "q": f'"{company_name}"',
            "forms": "D",
            "dateRange": "custom",
            "startdt": "2000-01-01",
            "enddt": "2026-12-31",
        }
        try:
            response = await self._make_request(
                "GET", "/search-index", params=params
            )
            hits = response.get("hits", {}).get("hits", [])
            results = []
            for hit in hits[:limit]:
                source = hit.get("_source", {})
                results.append({
                    "cik": str(source.get("entity_id", "")),
                    "entity_name": source.get("entity_name", ""),
                    "file_date": source.get("file_date", None),
                    "form_type": "D",
                })
            return results
        except APIError as e:
            logger.warning(
                f"EDGAR Form D search failed for '{company_name}': {e}"
            )
            return []

    async def get_company_tickers(self) -> dict[str, dict[str, Any]]:
        """Fetch the full CIK-to-ticker mapping from EDGAR.

        Returns a dict keyed by CIK with ticker and company name info.
        This is a single static file and should be cached.
        """
        url = "https://www.sec.gov/files/company_tickers.json"
        headers = self._build_headers()
        try:
            response = await self._client.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()
            # Rekey by CIK (zero-padded to 10 digits)
            result = {}
            for entry in data.values():
                cik = str(entry.get("cik_str", "")).zfill(10)
                result[cik] = {
                    "cik": cik,
                    "ticker": entry.get("ticker"),
                    "entity_name": entry.get("title"),
                }
            return result
        except (httpx.HTTPError, httpx.TimeoutException) as e:
            logger.warning(f"Failed to fetch company tickers: {e}")
            return {}

    async def get_company_facts(self, cik: str) -> dict[str, Any] | None:
        """Fetch XBRL company facts for a given CIK.

        Returns standardized financial data from SEC filings.

        Args:
            cik: Central Index Key (zero-padded to 10 digits).

        Returns:
            Company facts dict or None if not found.
        """
        cik_padded = cik.zfill(10)
        url = f"{self.facts_base_url}/companyfacts/CIK{cik_padded}.json"
        headers = self._build_headers()
        try:
            await self._wait_for_rate_limit()
            response = await self._client.get(url, headers=headers)
            if response.status_code == 404:
                logger.debug(f"No company facts for CIK {cik}")
                return None
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise APIError(
                f"EDGAR companyfacts failed: HTTP {e.response.status_code}",
                api_name=self.api_name,
                endpoint=f"companyfacts/CIK{cik_padded}",
                http_status=e.response.status_code,
            ) from e
        except (httpx.HTTPError, httpx.TimeoutException) as e:
            logger.warning(f"Failed to fetch company facts for CIK {cik}: {e}")
            return None

    async def get_recent_filings(
        self,
        cik: str,
        *,
        filing_types: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch recent filings for a CIK from the submissions endpoint.

        Args:
            cik: Central Index Key.
            filing_types: Optional filter for filing types (e.g., ['8-K', '10-K']).

        Returns:
            List of filing dicts with accession_number, filing_date, form, etc.
        """
        cik_padded = cik.zfill(10)
        url = f"{self.filings_base_url}/CIK{cik_padded}.json"
        headers = self._build_headers()
        try:
            await self._wait_for_rate_limit()
            response = await self._client.get(url, headers=headers)
            if response.status_code == 404:
                return []
            response.raise_for_status()
            data = response.json()

            recent = data.get("filings", {}).get("recent", {})
            forms = recent.get("form", [])
            dates = recent.get("filingDate", [])
            accessions = recent.get("accessionNumber", [])
            primary_docs = recent.get("primaryDocument", [])
            descriptions = recent.get("primaryDocDescription", [])

            filings = []
            for i in range(len(forms)):
                if filing_types and forms[i] not in filing_types:
                    continue
                filings.append({
                    "form_type": forms[i],
                    "filing_date": dates[i] if i < len(dates) else None,
                    "accession_number": accessions[i] if i < len(accessions) else None,
                    "primary_document": primary_docs[i] if i < len(primary_docs) else None,
                    "description": descriptions[i] if i < len(descriptions) else None,
                })
            return filings
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return []
            raise APIError(
                f"EDGAR filings failed: HTTP {e.response.status_code}",
                api_name=self.api_name,
                endpoint=f"submissions/CIK{cik_padded}",
                http_status=e.response.status_code,
            ) from e
        except (httpx.HTTPError, httpx.TimeoutException) as e:
            logger.warning(f"Failed to fetch filings for CIK {cik}: {e}")
            return []
