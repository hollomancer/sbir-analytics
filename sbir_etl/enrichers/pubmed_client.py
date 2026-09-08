"""PubMed (NCBI E-utilities) client for researcher authorship lookups.

Queries `NCBI E-utilities <https://eutils.ncbi.nlm.nih.gov/entrez/eutils/>`_
to find PubMed articles by author and extract the author's affiliation
strings as recorded on that article (PubMed carries free-text
affiliations per author, not a normalized institution ID).

No API key is required (rate limited to 3 requests/second). Set
``NCBI_API_KEY`` for a higher limit (10 requests/second).

This client inherits shared rate limiting, retry, and error
translation from :class:`BaseAsyncAPIClient`. ``esearch`` responses are
JSON; ``efetch`` responses are PubMed XML, so
:meth:`get_author_affiliations` uses the body-agnostic
:meth:`BaseAsyncAPIClient._request_raw` (see the FPDS Atom client for
the same pattern). Synchronous callers should use
:class:`sbir_etl.enrichers.sync_wrappers.SyncPubMedClient`.

Usage (sync)::

    from sbir_etl.enrichers.sync_wrappers import SyncPubMedClient

    with SyncPubMedClient() as client:
        record = client.lookup("Jane Smith")
        if record:
            print(record.pmid, record.affiliations)
"""

from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any

import httpx
from loguru import logger

from sbir_etl.enrichers.base_client import BaseAsyncAPIClient
from sbir_etl.enrichers.rate_limiting import RateLimiter
from sbir_etl.exceptions import APIError

PUBMED_API_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
DEFAULT_RATE_LIMIT_PER_MINUTE_NO_KEY = 180  # 3 req/sec, NCBI's unauthenticated limit
DEFAULT_RATE_LIMIT_PER_MINUTE_WITH_KEY = 600  # 10 req/sec, with NCBI_API_KEY


@dataclass
class PubMedRecord:
    """Author affiliation data extracted from a PubMed article."""

    pmid: str
    author_name: str
    affiliations: list[str] = field(default_factory=list)
    title: str | None = None


def _parse_efetch_xml(xml_text: str) -> dict[str, Any] | None:
    """Parse an ``efetch`` PubMed XML body into title + per-author affiliations.

    Returns ``None`` if the body doesn't parse or contains no article.
    """
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        logger.debug("PubMed XML parse error: {}", e)
        return None

    article = root.find(".//PubmedArticle")
    if article is None:
        return None

    title_el = article.find(".//ArticleTitle")
    title = title_el.text.strip() if title_el is not None and title_el.text else None

    authors: list[dict[str, Any]] = []
    for author_el in article.findall(".//AuthorList/Author"):
        last = author_el.findtext("LastName") or ""
        fore = author_el.findtext("ForeName") or ""
        name = f"{fore} {last}".strip() or (author_el.findtext("CollectiveName") or "")
        affiliations = [
            aff.text.strip() for aff in author_el.findall("AffiliationInfo/Affiliation") if aff.text
        ]
        authors.append({"name": name, "affiliations": affiliations})

    return {"title": title, "authors": authors}


def _best_matching_author(authors: list[dict[str, Any]], query_name: str) -> dict[str, Any] | None:
    """Pick the author entry whose name best matches *query_name*.

    Best-effort match on last name (case-insensitive substring); falls
    back to the first author if no name matches.
    """
    if not authors:
        return None
    parts = query_name.strip().split()
    if not parts:
        return authors[0]
    last_name = parts[-1].lower()
    for author in authors:
        if last_name in author["name"].lower():
            return author
    return authors[0]


class PubMedClient(BaseAsyncAPIClient):
    """Async client for NCBI E-utilities (PubMed search + fetch).

    Inherits retry, rate limiting, and typed error translation from
    :class:`BaseAsyncAPIClient`. For sync callers, use
    :class:`sbir_etl.enrichers.sync_wrappers.SyncPubMedClient`.

    Args:
        api_key: Optional NCBI API key. Defaults to the ``NCBI_API_KEY``
            environment variable. Sent as the ``api_key`` query parameter
            (E-utilities does not use header-based auth). When set, and
            *rate_limit_per_minute* is not explicitly overridden, the
            default rate limit rises from 3 req/sec to 10 req/sec.
        timeout: HTTP request timeout in seconds.
        rate_limit_per_minute: Requests per minute when no
            ``shared_limiter`` is provided. Defaults based on whether an
            API key is configured.
        shared_limiter: Optional shared synchronous :class:`RateLimiter` for
            sharing a global budget across worker threads. Dispatched via
            :func:`asyncio.to_thread`.
        http_client: Optional pre-constructed :class:`httpx.AsyncClient`
            (useful for testing).
    """

    api_name = "pubmed"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        timeout: int = 30,
        rate_limit_per_minute: int | None = None,
        shared_limiter: RateLimiter | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(shared_limiter=shared_limiter)
        self.base_url = PUBMED_API_URL
        self._api_key = api_key or os.environ.get("NCBI_API_KEY", "")
        if rate_limit_per_minute is None:
            rate_limit_per_minute = (
                DEFAULT_RATE_LIMIT_PER_MINUTE_WITH_KEY
                if self._api_key
                else DEFAULT_RATE_LIMIT_PER_MINUTE_NO_KEY
            )
        self.rate_limit_per_minute = rate_limit_per_minute
        self._client = http_client or httpx.AsyncClient(timeout=timeout)

    def _with_api_key(self, params: dict[str, Any]) -> dict[str, Any]:
        """Merge the ``api_key`` query parameter into a query dict."""
        merged = dict(params)
        if self._api_key:
            merged["api_key"] = self._api_key
        return merged

    async def search_pmids(self, author: str, limit: int = 5) -> list[str]:
        """Search PubMed for articles by author name.

        Returns the list of matching PMIDs (possibly empty). Returns an
        empty list on 4xx client errors; propagates :class:`APIError`
        on 5xx.
        """
        try:
            data = await self._make_request(
                "GET",
                "esearch.fcgi",
                params=self._with_api_key(
                    {
                        "db": "pubmed",
                        "term": f"{author}[Author]",
                        "retmode": "json",
                        "retmax": limit,
                    }
                ),
            )
        except APIError as e:
            status = e.details.get("http_status")
            if status and 400 <= status < 500:
                return []
            raise
        return data.get("esearchresult", {}).get("idlist", []) or []

    async def get_author_affiliations(self, pmid: str) -> dict[str, Any] | None:
        """Fetch an article's title and per-author affiliation strings.

        Uses ``efetch`` (PubMed XML), not ``esummary``, because
        ``esummary`` does not carry affiliation data. Returns ``None``
        if the article isn't found or the body doesn't parse;
        propagates :class:`APIError` on 5xx failures.
        """
        try:
            response = await self._request_raw(
                "GET",
                "efetch.fcgi",
                params=self._with_api_key(
                    {"db": "pubmed", "id": pmid, "rettype": "abstract", "retmode": "xml"}
                ),
            )
        except APIError as e:
            status = e.details.get("http_status")
            if status and 400 <= status < 500:
                return None
            raise
        return _parse_efetch_xml(response.text)

    async def lookup(self, name: str) -> PubMedRecord | None:
        """Look up a researcher's most recent PubMed affiliation by name.

        Two-step: author search → fetch affiliations for the top hit.
        Returns ``None`` when no match is found. Propagates
        :class:`APIError` on real API failures so callers can
        distinguish.
        """
        name = name.strip()
        if not name:
            return None

        pmids = await self.search_pmids(name)
        if not pmids:
            return None

        pmid = pmids[0]
        parsed = await self.get_author_affiliations(pmid)
        if parsed is None:
            return None

        author = _best_matching_author(parsed["authors"], name)
        return PubMedRecord(
            pmid=pmid,
            author_name=author["name"] if author else name,
            affiliations=author["affiliations"] if author else [],
            title=parsed.get("title"),
        )
