"""Semantic Scholar API client for researcher publication lookups.

Queries the `Semantic Scholar Academic Graph API
<https://api.semanticscholar.org/>`_ to find author profiles and
retrieve publication statistics (h-index, citation count, paper titles,
affiliations).

No API key is required for basic access (rate limited to ~100 req/min).
Set ``SEMANTIC_SCHOLAR_API_KEY`` for higher limits.

Usage::

    from sbir_etl.enrichers.semantic_scholar import SemanticScholarClient

    client = SemanticScholarClient()
    record = client.lookup_author("Jane Smith")
    if record:
        print(record.h_index, record.total_papers)
    client.close()
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any

import httpx
from loguru import logger

SEMANTIC_SCHOLAR_API_URL = "https://api.semanticscholar.org/graph/v1"
MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 2


@dataclass
class PublicationRecord:
    """Summary of a researcher's publication history."""

    total_papers: int
    h_index: int | None
    citation_count: int
    sample_titles: list[str]
    affiliations: list[str]


class SemanticScholarClient:
    """Client for querying the Semantic Scholar Academic Graph API.

    Args:
        rate_limiter: Optional rate limiter instance with ``wait_if_needed()`` method.
        api_key: Optional API key. Defaults to ``SEMANTIC_SCHOLAR_API_KEY`` env var.
        timeout: HTTP request timeout in seconds.
    """

    def __init__(
        self,
        rate_limiter: Any | None = None,
        api_key: str | None = None,
        timeout: int = 30,
    ) -> None:
        self._limiter = rate_limiter
        self._timeout = timeout
        resolved_key = api_key or os.environ.get("SEMANTIC_SCHOLAR_API_KEY", "")
        self._headers: dict[str, str] = {}
        if resolved_key:
            self._headers["x-api-key"] = resolved_key
        self._client = httpx.Client(timeout=timeout, headers=self._headers)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "SemanticScholarClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _wait(self) -> None:
        if self._limiter is not None:
            self._limiter.wait_if_needed()

    def _get_with_retry(self, url: str, params: dict[str, Any] | None = None) -> dict | None:
        """GET with retry on 429/5xx."""
        for attempt in range(MAX_RETRIES):
            self._wait()
            try:
                resp = self._client.get(url, params=params)
                if resp.status_code == 429:
                    wait = RETRY_BACKOFF_BASE ** (attempt + 1)
                    logger.debug(f"Semantic Scholar 429, retrying in {wait}s")
                    time.sleep(wait)
                    continue
                if resp.status_code != 200:
                    logger.debug(f"Semantic Scholar returned {resp.status_code}")
                    return None
                return resp.json()
            except httpx.HTTPError as e:
                logger.debug(f"Semantic Scholar request error: {e}")
                time.sleep(RETRY_BACKOFF_BASE ** (attempt + 1))
        return None

    def search_author(self, name: str, limit: int = 5) -> list[dict[str, Any]]:
        """Search for authors by name.

        Returns list of author dicts with ``authorId``, ``name``, etc.
        """
        data = self._get_with_retry(
            f"{SEMANTIC_SCHOLAR_API_URL}/author/search",
            params={"query": name, "limit": limit},
        )
        if data is None:
            return []
        return data.get("data", [])

    def get_author_details(
        self, author_id: str
    ) -> dict[str, Any] | None:
        """Fetch author details including papers, h-index, and affiliations."""
        return self._get_with_retry(
            f"{SEMANTIC_SCHOLAR_API_URL}/author/{author_id}",
            params={
                "fields": "name,hIndex,citationCount,affiliations,papers.title,papers.year",
            },
        )

    def lookup_author(self, name: str) -> PublicationRecord | None:
        """Look up a researcher's publication profile by name.

        Two-step: author search → author details with papers.
        Returns ``None`` if no match found.
        """
        authors = self.search_author(name)
        if not authors:
            return None

        author_id = authors[0].get("authorId")
        if not author_id:
            return None

        details = self.get_author_details(author_id)
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
