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
import re
import unicodedata
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from enum import StrEnum

import httpx
from loguru import logger

from sbir_etl.enrichers.base_client import BaseAsyncAPIClient
from sbir_etl.enrichers.rate_limiting import RateLimiter
from sbir_etl.exceptions import APIError
from sbir_etl.identity import CompanyNameProfile, normalize_company_name

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

# Below this length, even a bounded literal match is weak evidence: a normalized
# watchlist name of 1-3 characters (e.g. "bal", "app", "dri") is likely to
# collide with an unrelated short word used as a standalone token somewhere in
# a press release. Names shorter than this floor are held for human review
# rather than matched with lower confidence, since there is no curated
# allowlist of legitimate short company names (e.g. ticker-style names like
# "IBM") to exempt from the floor.
_MIN_NORMALIZED_NAME_LENGTH = 4
_WATCHLIST_PROFILE = CompanyNameProfile.PRESS_WIRE_WATCHLIST_V1

# This is a deliberately narrow, human-curated list of observed ordinary-word
# collisions. It is not a dictionary and does not claim to identify every
# ambiguous company name. Changing it changes automatic matching output and
# therefore requires a new watchlist/profile version.
_CURATED_COMMON_NAMES_V1 = frozenset({"connect"})


class WatchlistReviewReason(StrEnum):
    """Reasons an identity is held outside automatic press-wire matching."""

    EMPTY_NAME = "empty-name"
    SHORT_NAME = "short-name"
    CURATED_COMMON_NAME = "curated-common-name"


@dataclass(frozen=True)
class WatchlistReviewItem:
    """A company identity that requires human review instead of auto-matching."""

    company_name: str
    normalized_name: str
    reason: WatchlistReviewReason


@dataclass(frozen=True)
class WatchlistCoverage:
    """Structured coverage report for one configured watchlist.

    ``review_required`` identities need release-level human adjudication; the
    automatic matcher does not treat a watchlist-level approval as sufficient.
    """

    profile: CompanyNameProfile
    requested_count: int
    automatic_match_count: int
    review_required: tuple[WatchlistReviewItem, ...] = ()

    @property
    def automatic_coverage(self) -> float:
        """Share of requested identities eligible for automatic matching."""
        if not self.requested_count:
            return 0.0
        return self.automatic_match_count / self.requested_count


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
    matched_in: str = ""  # Where the match occurred: "title", "summary", or "title+summary"


@dataclass
class PollResult:
    """Summary of a polling run."""

    items_scanned: int = 0
    matches: list[PressRelease] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _content_hash(title: str, link: str) -> str:
    """Generate a dedup hash from title + link."""
    return hashlib.sha256(f"{title}|{link}".encode()).hexdigest()[:16]


def _normalize_release_text(text: str) -> str:
    """Normalize feed prose without applying company-identity rules."""
    normalized = unicodedata.normalize("NFKD", text.strip().lower())
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return " ".join(normalized.split())


def _boundary_pattern(normalized_name: str) -> re.Pattern[str]:
    """Compile a punctuation-safe literal boundary pattern for a company name.

    Word-character lookarounds prevent substring matches while allowing a
    literal name to begin or end in punctuation, as ``SKY+`` and ``.NET`` do.
    """
    return re.compile(rf"(?<!\w){re.escape(normalized_name)}(?!\w)")


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
        self._requested_company_names: list[str] = []
        self._watchlist: dict[str, str] = {}  # normalized -> original
        self._patterns: dict[str, re.Pattern[str]] = {}  # normalized -> compiled boundary pattern
        self._watchlist_report = WatchlistCoverage(
            profile=_WATCHLIST_PROFILE,
            requested_count=0,
            automatic_match_count=0,
        )
        self._seen_hashes: set[str] = set()

    # ------------------------------------------------------------------
    # Watchlist management
    # ------------------------------------------------------------------

    @property
    def watchlist_report(self) -> WatchlistCoverage:
        """Return coverage and human-review exclusions for the active watchlist."""
        return self._watchlist_report

    @staticmethod
    def _review_reason(normalized_name: str) -> WatchlistReviewReason | None:
        if not normalized_name:
            return WatchlistReviewReason.EMPTY_NAME
        if len(normalized_name) < _MIN_NORMALIZED_NAME_LENGTH:
            return WatchlistReviewReason.SHORT_NAME
        if normalized_name in _CURATED_COMMON_NAMES_V1:
            return WatchlistReviewReason.CURATED_COMMON_NAME
        return None

    def _configure_watchlist(self) -> WatchlistCoverage:
        self._watchlist = {}
        self._patterns = {}
        review_required: list[WatchlistReviewItem] = []
        automatic_match_count = 0

        for name in self._requested_company_names:
            normalized = normalize_company_name(name, profile=_WATCHLIST_PROFILE)
            reason = self._review_reason(normalized)
            if reason is not None:
                review_required.append(
                    WatchlistReviewItem(
                        company_name=name,
                        normalized_name=normalized,
                        reason=reason,
                    )
                )
                continue
            automatic_match_count += 1
            self._watchlist[normalized] = name
            self._patterns[normalized] = _boundary_pattern(normalized)

        self._watchlist_report = WatchlistCoverage(
            profile=_WATCHLIST_PROFILE,
            requested_count=len(self._requested_company_names),
            automatic_match_count=automatic_match_count,
            review_required=tuple(review_required),
        )
        if review_required:
            reason_counts = ", ".join(
                f"{reason.value}={sum(item.reason is reason for item in review_required)}"
                for reason in WatchlistReviewReason
                if any(item.reason is reason for item in review_required)
            )
            logger.warning(
                "Press wire watchlist: {}/{} identities require human review and are excluded "
                "from automatic matching ({})",
                len(review_required),
                len(self._requested_company_names),
                reason_counts,
            )
        logger.info(
            "Press wire watchlist set: {}/{} identities eligible as {} unique patterns",
            automatic_match_count,
            len(self._requested_company_names),
            len(self._watchlist),
        )
        return self._watchlist_report

    def set_watchlist(self, company_names: list[str]) -> WatchlistCoverage:
        """Set the list of company names to watch for in press releases.

        Identities use the explicit press-wire profile. Short, blank, and
        curated common-word identities are returned in a structured report for
        human review and are not automatically matched.
        """
        self._requested_company_names = list(company_names)
        return self._configure_watchlist()

    def add_to_watchlist(self, company_name: str) -> WatchlistCoverage:
        """Add a company and return the updated automatic-coverage report.

        A risky identity is recorded for human review but does not enter the
        automatic matcher.
        """
        self._requested_company_names.append(company_name)
        return self._configure_watchlist()

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

    def _parse_rss_items(self, root: ET.Element, source: str) -> list[PressRelease]:
        """Parse RSS 2.0 ``<item>`` elements."""
        items: list[PressRelease] = []
        for item in root.iter("item"):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            pub_date = item.findtext("pubDate") or item.findtext("dc:date", namespaces=NS)
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

    def _parse_atom_entries(self, root: ET.Element, source: str) -> list[PressRelease]:
        """Parse Atom ``<entry>`` elements."""
        items: list[PressRelease] = []
        for entry in root.iter(f"{{{NS['atom']}}}entry"):
            title_el = entry.find(f"{{{NS['atom']}}}title")
            title = (title_el.text or "").strip() if title_el is not None else ""

            link = ""
            link_el = entry.find(f"{{{NS['atom']}}}link")
            if link_el is not None:
                link = link_el.get("href", "")

            pub_el = entry.find(f"{{{NS['atom']}}}published") or entry.find(
                f"{{{NS['atom']}}}updated"
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

    def _match_company(self, item: PressRelease) -> tuple[str, str] | None:
        """Check if a press release mentions a watchlist company.

        Matches a normalized watchlist name as a bounded literal so it cannot
        match a substring inside an unrelated longer word. Title and summary
        are checked separately: a title hit is stronger evidence than a summary-only
        hit, so the match location is returned alongside the company name
        rather than collapsed into a single yes/no. This does not change
        whether a match counts — a summary-only hit still returns a match —
        it only records where the evidence came from for downstream
        consumers that want to weight headline mentions higher.

        Returns:
            ``(original_name, matched_in)`` for the first watchlist hit, or
            ``None``. ``matched_in`` is one of ``"title"``, ``"summary"``,
            or ``"title+summary"``.
        """
        title_text = _normalize_release_text(item.title)
        summary_text = _normalize_release_text(item.summary or "")
        for normalized_name, original_name in self._watchlist.items():
            pattern = self._patterns[normalized_name]
            title_hit = bool(pattern.search(title_text))
            summary_hit = bool(pattern.search(summary_text))
            if not (title_hit or summary_hit):
                continue
            if title_hit and summary_hit:
                matched_in = "title+summary"
            elif title_hit:
                matched_in = "title"
            else:
                matched_in = "summary"
            return original_name, matched_in
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
                    item.matched_company, item.matched_in = matched
                    self._seen_hashes.add(item.content_hash)
                    all_matches.append(item)

        logger.info(f"Press wire poll complete: {len(all_matches)} matches")
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
