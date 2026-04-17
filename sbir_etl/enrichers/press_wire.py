"""Press wire RSS/Atom feed client for SBIR awardee news monitoring.

Polls RSS/Atom feeds from PR Newswire, BusinessWire, and GlobeNewsWire
for press releases mentioning known SBIR awardee companies. Designed
as a leading-indicator source for commercialization events (contract
wins, acquisitions, product launches, partnerships) that appear in
press releases weeks/months before they surface in USAspending or FPDS.

**Unique value over OpenAI web_search():**

- Proactive monitoring (event-driven, not reactive lookup)
- Structured, timestamped, reproducible records
- Survivorship-biased toward companies that matter (companies that
  issue press releases are disproportionately the ones commercializing)

No API keys required — all feeds are public RSS/Atom.

This client inherits shared rate limiting, retry, and error
translation from :class:`BaseAsyncAPIClient`. Feeds live on multiple
hostnames so the client passes absolute URLs as the endpoint
argument, which the base client's URL-join recognizes and uses
as-is. Synchronous callers should use
:class:`sbir_etl.enrichers.sync_wrappers.SyncPressWireClient`.

Usage (sync)::

    from sbir_etl.enrichers.sync_wrappers import SyncPressWireClient

    with SyncPressWireClient() as client:
        client.set_watchlist(["Acme Defense Systems", "Nova Quantum Inc"])
        hits = client.poll()
        for hit in hits:
            print(f"{hit.published} | {hit.source} | {hit.title}")
"""

from __future__ import annotations

import hashlib
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

import httpx
from loguru import logger

from sbir_etl.enrichers.base_client import BaseAsyncAPIClient
from sbir_etl.enrichers.rate_limiting import RateLimiter
from sbir_etl.exceptions import APIError

# Feed URLs — public RSS/Atom endpoints
FEEDS: dict[str, str] = {
    "PRNewswire": "https://www.prnewswire.com/rss/news-releases-list.rss",
    "BusinessWire": "https://feed.businesswire.com/rss/home/?rss=G1QFDERJXkJeEFpRWA==",
    "GlobeNewsWire": "https://www.globenewswire.com/RSSFeed/subjectcode/01-Business%20Operations/feedTitle/GlobeNewswire%20-%20Business%20Operations",
}

# Common XML namespaces
NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "dc": "http://purl.org/dc/elements/1.1/",
    "content": "http://purl.org/rss/1.0/modules/content/",
}

DEFAULT_RATE_LIMIT_PER_MINUTE = 30


@dataclass
class PressRelease:
    """A press release item from an RSS/Atom feed."""

    title: str
    link: str
    published: str | None = None
    summary: str | None = None
    source: str = ""  # Which wire service
    matched_company: str = ""  # Which watchlist company matched
    content_hash: str = ""  # For dedup across feeds


@dataclass
class PollResult:
    """Summary of a polling run."""

    items_scanned: int = 0
    matches: list[PressRelease] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _content_hash(title: str, link: str) -> str:
    """Generate a dedup hash from title + link."""
    return hashlib.sha256(f"{title}|{link}".encode()).hexdigest()[:16]


def _normalize(name: str) -> str:
    """Normalize company name for matching.

    Strips common suffixes and lowercases for substring matching.
    """
    lower = name.lower().strip()
    for suffix in (
        " inc", " inc.", " llc", " corp", " corp.",
        " corporation", " company", " co.", " ltd", " ltd.",
        " lp", " l.p.", " plc",
    ):
        if lower.endswith(suffix):
            lower = lower[: -len(suffix)].rstrip(" ,")
    return lower


class PressWireClient(BaseAsyncAPIClient):
    """Async client for polling press wire RSS/Atom feeds.

    Inherits retry, rate limiting, and typed error translation from
    :class:`BaseAsyncAPIClient`. Passes absolute feed URLs as the
    endpoint argument so the base client's URL-join logic uses them
    as-is (no per-host base_url needed). For sync callers, use
    :class:`sbir_etl.enrichers.sync_wrappers.SyncPressWireClient`.

    Args:
        feeds: Override the default feed URLs. Keys are source names,
            values are absolute feed URLs.
        timeout: HTTP request timeout in seconds.
        rate_limit_per_minute: Requests per minute when no
            ``shared_limiter`` is provided. Defaults to 30 — RSS feeds
            are cheap but we stay polite.
        shared_limiter: Optional shared synchronous :class:`RateLimiter`.
            Dispatched via :func:`asyncio.to_thread`.
        http_client: Optional pre-constructed :class:`httpx.AsyncClient`
            (useful for testing).
    """

    api_name = "press_wire"

    def __init__(
        self,
        feeds: dict[str, str] | None = None,
        *,
        timeout: int = 30,
        rate_limit_per_minute: int = DEFAULT_RATE_LIMIT_PER_MINUTE,
        shared_limiter: RateLimiter | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(shared_limiter=shared_limiter)
        # base_url unused — feed URLs are absolute and passed as endpoint
        self.base_url = ""
        self.rate_limit_per_minute = rate_limit_per_minute
        self._client = http_client or httpx.AsyncClient(timeout=timeout)
        self._feeds = feeds or dict(FEEDS)
        self._watchlist: dict[str, str] = {}  # normalized -> original
        self._seen_hashes: set[str] = set()

    # ------------------------------------------------------------------
    # Watchlist management
    # ------------------------------------------------------------------

    def set_watchlist(self, company_names: list[str]) -> None:
        """Set the list of company names to watch for in press releases.

        Names are normalized (lowercased, common suffixes stripped) for
        substring matching against feed items.
        """
        self._watchlist = {_normalize(name): name for name in company_names}
        logger.info(f"Press wire watchlist set: {len(self._watchlist)} companies")

    def add_to_watchlist(self, company_name: str) -> None:
        """Add a single company to the watchlist."""
        self._watchlist[_normalize(company_name)] = company_name

    # ------------------------------------------------------------------
    # Feed fetching
    # ------------------------------------------------------------------

    async def _fetch_feed(self, source: str, url: str) -> str | None:
        """Fetch raw XML from a feed URL.

        Returns ``None`` on failure so ``poll`` can continue with the
        other feeds. Errors are logged, not raised.
        """
        try:
            response = await self._request_raw("GET", url)
        except APIError as e:
            logger.debug("{} fetch error: {}", source, e)
            return None
        return response.text

    # ------------------------------------------------------------------
    # Parsing — handles both RSS 2.0 and Atom formats
    # ------------------------------------------------------------------

    def _parse_rss_items(
        self, root: ET.Element, source: str
    ) -> list[PressRelease]:
        """Parse RSS 2.0 ``<item>`` elements."""
        items: list[PressRelease] = []
        for item in root.iter("item"):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            pub_date = item.findtext("pubDate") or item.findtext(
                "dc:date", namespaces=NS
            )
            summary = (item.findtext("description") or "").strip()

            if not title:
                continue

            items.append(
                PressRelease(
                    title=title,
                    link=link,
                    published=pub_date,
                    summary=summary[:500] if summary else None,
                    source=source,
                    content_hash=_content_hash(title, link),
                )
            )
        return items

    def _parse_atom_entries(
        self, root: ET.Element, source: str
    ) -> list[PressRelease]:
        """Parse Atom ``<entry>`` elements."""
        items: list[PressRelease] = []
        for entry in root.iter(f"{{{NS['atom']}}}entry"):
            title_el = entry.find(f"{{{NS['atom']}}}title")
            title = (title_el.text or "").strip() if title_el is not None else ""

            link = ""
            link_el = entry.find(f"{{{NS['atom']}}}link")
            if link_el is not None:
                link = link_el.get("href", "")

            pub_el = (
                entry.find(f"{{{NS['atom']}}}published")
                or entry.find(f"{{{NS['atom']}}}updated")
            )
            pub_date = pub_el.text if pub_el is not None else None

            summary_el = entry.find(f"{{{NS['atom']}}}summary")
            summary = (summary_el.text or "").strip() if summary_el is not None else ""

            if not title:
                continue

            items.append(
                PressRelease(
                    title=title,
                    link=link,
                    published=pub_date,
                    summary=summary[:500] if summary else None,
                    source=source,
                    content_hash=_content_hash(title, link),
                )
            )
        return items

    def _parse_feed(self, xml_text: str, source: str) -> list[PressRelease]:
        """Parse a feed, auto-detecting RSS vs Atom format."""
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as e:
            logger.warning(f"Failed to parse {source} feed XML: {e}")
            return []

        # Detect format: RSS has <rss> or <channel>, Atom has <feed>
        tag = root.tag.split("}")[-1] if "}" in root.tag else root.tag
        if tag == "feed":
            return self._parse_atom_entries(root, source)
        else:
            return self._parse_rss_items(root, source)

    # ------------------------------------------------------------------
    # Matching
    # ------------------------------------------------------------------

    def _match_company(self, item: PressRelease) -> str | None:
        """Check if a press release mentions a watchlist company.

        Uses normalized substring matching against title and summary.
        """
        searchable = _normalize(
            f"{item.title} {item.summary or ''}"
        )
        for normalized_name, original_name in self._watchlist.items():
            if normalized_name in searchable:
                return original_name
        return None

    # ------------------------------------------------------------------
    # Polling
    # ------------------------------------------------------------------

    async def poll(self) -> list[PressRelease]:
        """Poll all configured feeds and return matching press releases.

        Deduplicates across feeds using content hashing.
        Returns only items matching the watchlist.
        """
        if not self._watchlist:
            logger.warning("Press wire watchlist is empty — no companies to match")
            return []

        all_matches: list[PressRelease] = []

        for source, url in self._feeds.items():
            xml_text = await self._fetch_feed(source, url)
            if xml_text is None:
                logger.warning(f"Failed to fetch {source} feed")
                continue

            items = self._parse_feed(xml_text, source)
            logger.debug(f"{source}: parsed {len(items)} items")

            for item in items:
                # Dedup
                if item.content_hash in self._seen_hashes:
                    continue

                matched = self._match_company(item)
                if matched:
                    item.matched_company = matched
                    self._seen_hashes.add(item.content_hash)
                    all_matches.append(item)

        logger.info(
            f"Press wire poll complete: {len(all_matches)} matches"
        )
        return all_matches

    async def poll_all_unfiltered(self) -> list[PressRelease]:
        """Poll all feeds and return ALL items (no watchlist filtering).

        Useful for exploring feed content or building a full archive.
        Deduplicates across feeds using content hashing.
        """
        all_items: list[PressRelease] = []

        for source, url in self._feeds.items():
            xml_text = await self._fetch_feed(source, url)
            if xml_text is None:
                continue

            items = self._parse_feed(xml_text, source)
            for item in items:
                if item.content_hash not in self._seen_hashes:
                    self._seen_hashes.add(item.content_hash)
                    all_items.append(item)

        return all_items

    def reset_seen(self) -> None:
        """Clear the deduplication cache."""
        self._seen_hashes.clear()
