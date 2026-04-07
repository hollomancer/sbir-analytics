"""Lens.org Scholarly & Patent API client for patent fallback lookups.

The Lens.org API (https://www.lens.org/lens/api) provides free access to
patent and scholarly data. It serves as a fallback when the USPTO ODP
(PatentsView) API is unavailable or the API key is missing.

Free tier: 50 requests/minute, 1000/day with a free account.
Set ``LENS_API_TOKEN`` environment variable for authentication.

Usage::

    from sbir_etl.enrichers.lens_patents import LensPatentClient

    client = LensPatentClient()
    patents = client.search_patents_by_assignee("Acme Defense Systems")
    for p in patents:
        print(p.title, p.assignee)
    client.close()
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any

import httpx
from loguru import logger

LENS_API_URL = "https://api.lens.org/patent/search"
MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 2


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


class LensPatentClient:
    """Client for querying the Lens.org Patent API.

    Args:
        rate_limiter: Optional rate limiter with ``wait_if_needed()`` method.
        api_token: Optional API token. Defaults to ``LENS_API_TOKEN`` env var.
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
        self._token = api_token or os.environ.get("LENS_API_TOKEN", "")
        if not self._token:
            logger.debug("LENS_API_TOKEN not set — Lens.org patent lookups will fail")
        self._client = httpx.Client(timeout=timeout)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> LensPatentClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _wait(self) -> None:
        if self._limiter is not None:
            self._limiter.wait_if_needed()

    def _post_with_retry(self, payload: dict[str, Any]) -> dict | None:
        """POST to Lens.org API with retry on 429/5xx."""
        if not self._token:
            return None

        headers = {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }

        for attempt in range(MAX_RETRIES):
            self._wait()
            try:
                resp = self._client.post(
                    LENS_API_URL, json=payload, headers=headers,
                )
                if resp.status_code == 429 or resp.status_code >= 500:
                    wait = RETRY_BACKOFF_BASE ** (attempt + 1)
                    logger.debug(f"Lens.org {resp.status_code}, retrying in {wait}s")
                    time.sleep(wait)
                    continue
                if resp.status_code != 200:
                    logger.debug(f"Lens.org returned {resp.status_code}")
                    return None
                try:
                    return resp.json()
                except (ValueError, Exception) as je:
                    logger.debug(f"Lens.org JSON decode error: {je}")
                    return None
            except httpx.HTTPError as e:
                logger.debug(f"Lens.org request error: {e}")
                time.sleep(RETRY_BACKOFF_BASE ** (attempt + 1))
        return None

    def _parse_records(self, data: dict) -> list[LensPatentRecord]:
        """Parse Lens.org API response into LensPatentRecord list."""
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
                assignee = first.get("name") if isinstance(first, dict) else str(first)

            # Extract inventors
            inventor_names: list[str] = []
            for inv in hit.get("inventor", []):
                if isinstance(inv, dict):
                    name = inv.get("name", "")
                    if name:
                        inventor_names.append(name)

            records.append(LensPatentRecord(
                patent_number=hit.get("lens_id", ""),
                title=title,
                assignee=assignee,
                inventor_names=inventor_names,
                filing_date=hit.get("filing_date"),
                grant_date=None,  # Lens doesn't distinguish grant vs publication
                publication_date=hit.get("date_published"),
            ))

        return records

    def search_patents_by_assignee(
        self,
        company_name: str,
        max_results: int = 100,
    ) -> list[LensPatentRecord]:
        """Search for patents by assignee name.

        Args:
            company_name: Company/assignee name to search for.
            max_results: Maximum number of results to return.

        Returns:
            List of LensPatentRecord objects.
        """
        payload = {
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

        data = self._post_with_retry(payload)
        if data is None:
            return []

        return self._parse_records(data)

    def search_patents_by_inventor(
        self,
        inventor_name: str,
        max_results: int = 50,
    ) -> list[LensPatentRecord]:
        """Search for patents by inventor name.

        Args:
            inventor_name: Inventor name to search for.
            max_results: Maximum number of results to return.

        Returns:
            List of LensPatentRecord objects.
        """
        payload = {
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

        data = self._post_with_retry(payload)
        if data is None:
            return []

        return self._parse_records(data)
