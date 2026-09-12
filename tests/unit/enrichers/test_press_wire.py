"""Tests for PressWireClient (async) and SyncPressWireClient.

Pure parsing/normalization helpers (``_content_hash``, ``_normalize``)
are unchanged after the migration. The client tests use the
``AsyncMock``-based pattern established in the earlier migrations.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import httpx
import pytest

from sbir_etl.enrichers.press_wire import (
    PressRelease,
    PressWireClient,
    _content_hash,
    _normalize,
)
from sbir_etl.enrichers.sync_wrappers import SyncPressWireClient

pytestmark = pytest.mark.fast

# Sample RSS 2.0 feed
SAMPLE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
    <title>PR Newswire</title>
    <item>
        <title>Acme Defense Awarded $5M DoD Contract for Next-Gen Sensors</title>
        <link>https://prnewswire.com/news/acme-defense-dod-contract</link>
        <pubDate>Mon, 07 Apr 2026 12:00:00 GMT</pubDate>
        <description>Acme Defense Systems today announced a $5 million production contract from the Department of Defense.</description>
    </item>
    <item>
        <title>Unrelated Corp Reports Q1 Earnings</title>
        <link>https://prnewswire.com/news/unrelated-earnings</link>
        <pubDate>Mon, 07 Apr 2026 10:00:00 GMT</pubDate>
        <description>Unrelated Corp reported strong Q1 results.</description>
    </item>
</channel>
</rss>"""

# Sample Atom feed
SAMPLE_ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
    <title>BusinessWire</title>
    <entry>
        <title>Nova Quantum Completes Series B Funding Round</title>
        <link href="https://businesswire.com/news/nova-quantum-series-b"/>
        <published>2026-04-06T14:00:00Z</published>
        <summary>Nova Quantum Inc announced the completion of a $20M Series B.</summary>
    </entry>
</feed>"""


# ==================== Pure helpers (unchanged) ====================


class TestNormalize:
    def test_strips_common_suffixes(self):
        assert _normalize("Acme Defense Inc.") == "acme defense"
        assert _normalize("Nova Quantum LLC") == "nova quantum"
        assert _normalize("Big Corp Corporation") == "big corp"

    def test_lowercases(self):
        assert _normalize("ACME DEFENSE") == "acme defense"

    def test_no_suffix(self):
        assert _normalize("Acme Defense") == "acme defense"


class TestContentHash:
    def test_deterministic(self):
        h1 = _content_hash("Title", "https://example.com")
        h2 = _content_hash("Title", "https://example.com")
        assert h1 == h2

    def test_different_inputs(self):
        h1 = _content_hash("Title A", "https://a.com")
        h2 = _content_hash("Title B", "https://b.com")
        assert h1 != h2


# ==================== Fixtures ====================


def _mock_response(status: int = 200, text: str = "") -> Mock:
    resp = Mock()
    resp.status_code = status
    resp.text = text
    resp.raise_for_status = Mock()
    return resp


@pytest.fixture
def mock_http_client() -> AsyncMock:
    mock = AsyncMock(spec=httpx.AsyncClient)
    mock.aclose = AsyncMock()
    return mock


@pytest.fixture
def client(mock_http_client: AsyncMock) -> PressWireClient:
    return PressWireClient(
        feeds={"TestRSS": "https://test.example.com/rss"},
        http_client=mock_http_client,
    )


# ==================== Client lifecycle / initialization ====================


class TestInitialization:
    def test_defaults(self, client: PressWireClient) -> None:
        assert client.api_name == "press_wire"
        # base_url is empty — feed URLs are absolute and passed per-call
        assert client.base_url == ""

    def test_inherits_from_base(self, client: PressWireClient) -> None:
        from sbir_etl.enrichers.base_client import BaseAsyncAPIClient

        assert isinstance(client, BaseAsyncAPIClient)

    def test_default_feeds_used_when_not_specified(self, mock_http_client: AsyncMock) -> None:
        c = PressWireClient(http_client=mock_http_client)
        assert "PRNewswire" in c._feeds
        assert "BusinessWire" in c._feeds
        assert "GlobeNewsWire" in c._feeds


# ==================== Watchlist ====================


class TestWatchlist:
    def test_set_watchlist(self, client: PressWireClient) -> None:
        client.set_watchlist(["Acme Defense Systems"])
        assert len(client._watchlist) == 1

    def test_add_to_watchlist(self, client: PressWireClient) -> None:
        client.set_watchlist(["Company A"])
        client.add_to_watchlist("Company B")
        assert len(client._watchlist) == 2

    def test_set_watchlist_normalizes(self, client: PressWireClient) -> None:
        """Watchlist keys are normalized forms; values are originals."""
        client.set_watchlist(["Acme Defense Inc."])
        assert "acme defense" in client._watchlist
        assert client._watchlist["acme defense"] == "Acme Defense Inc."


# ==================== Matching: word boundary, length floor, evidence ====================
#
# Issue #708: unanchored substring matching gave 0/18 precision on the
# shipped `enriched_sbir_ma_events.jsonl` artifact. Real false positives:
# BAL matched inside "global", APP inside "approximately", ATI inside
# "nationwide", DRI inside "alexandria", Ert inside "hardwareintegrierte".
# All five of those watchlist names normalize to 3 characters or fewer, so
# the length floor alone would block them. The tests below isolate each
# defense: the floor (short names excluded from the watchlist entirely) and
# the word-boundary pattern (a 4+ char name still must not match as a
# substring of a longer word).


class TestLengthFloor:
    def test_short_names_excluded_from_watchlist(self, client: PressWireClient) -> None:
        client.set_watchlist(["BAL", "APP, Inc", "ATI, INC.", "DRI", "Ert"])
        assert client._watchlist == {}

    def test_names_at_floor_are_kept(self, client: PressWireClient) -> None:
        # "Bali" normalizes to 4 characters — right at the floor.
        client.set_watchlist(["Bali"])
        assert "bali" in client._watchlist

    def test_add_to_watchlist_skips_short_name(self, client: PressWireClient) -> None:
        client.set_watchlist(["Acme Defense Systems"])
        client.add_to_watchlist("Ert")
        assert len(client._watchlist) == 1
        assert "ert" not in client._watchlist


class TestWordBoundaryMatching:
    """Adversarial cases: a watchlist name must not match as a substring of
    an unrelated longer word, even when it clears the length floor."""

    def test_bal_does_not_match_inside_global(self, client: PressWireClient) -> None:
        client.set_watchlist(["Bali"])  # normalizes to "bali", a substring of "globalization"
        item = PressRelease(
            title="Firm expands globalization strategy", link="https://x", summary=None
        )
        assert client._match_company(item) is None

    def test_cast_does_not_match_inside_broadcast(self, client: PressWireClient) -> None:
        client.set_watchlist(["Cast"])  # "cast" is a substring of "broadcast"
        item = PressRelease(
            title="Network to broadcast the event live", link="https://x", summary=None
        )
        assert client._match_company(item) is None

    def test_nova_does_not_match_inside_renovation(self, client: PressWireClient) -> None:
        client.set_watchlist(["Nova"])
        item = PressRelease(title="Downtown renovation project completed", link="https://x")
        assert client._match_company(item) is None

    def test_rice_does_not_match_inside_prices(self, client: PressWireClient) -> None:
        client.set_watchlist(["Rice"])  # "rice" is a substring of "prices"
        item = PressRelease(
            title="Report cites rising commodity prices", link="https://x", summary=None
        )
        assert client._match_company(item) is None

    def test_real_company_name_matches_real_headline(self, client: PressWireClient) -> None:
        client.set_watchlist(["Acme Defense"])
        item = PressRelease(
            title="Acme Defense Awarded $5M DoD Contract for Next-Gen Sensors",
            link="https://x",
            summary=None,
        )
        result = client._match_company(item)
        assert result is not None
        assert result[0] == "Acme Defense"

    def test_multiword_name_matches_with_trailing_punctuation(
        self, client: PressWireClient
    ) -> None:
        client.set_watchlist(["Nova Quantum"])
        item = PressRelease(
            title="Nova Quantum, a leading firm, announced a merger",
            link="https://x",
            summary=None,
        )
        result = client._match_company(item)
        assert result is not None
        assert result[0] == "Nova Quantum"


class TestMatchEvidence:
    """Title vs. summary are recorded as separate evidence (issue #708,
    item 3). Either location still counts as a match; the location is
    recorded, not used to accept/reject."""

    def test_title_only_match(self, client: PressWireClient) -> None:
        client.set_watchlist(["Acme Defense"])
        item = PressRelease(
            title="Acme Defense wins new contract", link="https://x", summary="No mention here."
        )
        result = client._match_company(item)
        assert result == ("Acme Defense", "title")

    def test_summary_only_match(self, client: PressWireClient) -> None:
        client.set_watchlist(["Acme Defense"])
        item = PressRelease(
            title="Local firm wins new contract",
            link="https://x",
            summary="Acme Defense will deliver sensors under the award.",
        )
        result = client._match_company(item)
        assert result == ("Acme Defense", "summary")

    def test_title_and_summary_match(self, client: PressWireClient) -> None:
        client.set_watchlist(["Acme Defense"])
        item = PressRelease(
            title="Acme Defense wins new contract",
            link="https://x",
            summary="Acme Defense will deliver sensors under the award.",
        )
        result = client._match_company(item)
        assert result == ("Acme Defense", "title+summary")

    async def test_poll_records_matched_in(
        self, client: PressWireClient, mock_http_client: AsyncMock
    ) -> None:
        client.set_watchlist(["Acme Defense Systems"])
        mock_http_client.get.return_value = _mock_response(200, SAMPLE_RSS)

        matches = await client.poll()

        assert len(matches) == 1
        assert matches[0].matched_in in {"title", "summary", "title+summary"}


# ==================== Parsing ====================


class TestParsing:
    def test_parse_rss(self, client: PressWireClient) -> None:
        items = client._parse_feed(SAMPLE_RSS, "PRNewswire")
        assert len(items) == 2
        assert items[0].title == "Acme Defense Awarded $5M DoD Contract for Next-Gen Sensors"
        assert items[0].source == "PRNewswire"
        assert items[0].link == "https://prnewswire.com/news/acme-defense-dod-contract"

    def test_parse_atom(self, client: PressWireClient) -> None:
        items = client._parse_feed(SAMPLE_ATOM, "BusinessWire")
        assert len(items) == 1
        assert "Nova Quantum" in items[0].title
        assert items[0].source == "BusinessWire"
        assert items[0].link == "https://businesswire.com/news/nova-quantum-series-b"

    def test_malformed_xml_returns_empty(self, client: PressWireClient) -> None:
        items = client._parse_feed("not xml at all", "BadFeed")
        assert items == []


# ==================== Polling ====================


class TestPoll:
    async def test_poll_with_matches(
        self, client: PressWireClient, mock_http_client: AsyncMock
    ) -> None:
        client.set_watchlist(["Acme Defense Systems", "Nova Quantum Inc"])
        mock_http_client.get.return_value = _mock_response(200, SAMPLE_RSS)

        matches = await client.poll()

        assert len(matches) == 1
        assert matches[0].matched_company == "Acme Defense Systems"
        assert "DoD Contract" in matches[0].title

    async def test_poll_no_watchlist_returns_empty(
        self, client: PressWireClient, mock_http_client: AsyncMock
    ) -> None:
        matches = await client.poll()
        assert matches == []
        mock_http_client.get.assert_not_called()

    async def test_dedup_across_polls(
        self, client: PressWireClient, mock_http_client: AsyncMock
    ) -> None:
        client.set_watchlist(["Acme Defense Systems"])
        mock_http_client.get.return_value = _mock_response(200, SAMPLE_RSS)

        matches1 = await client.poll()
        matches2 = await client.poll()

        assert len(matches1) == 1
        assert len(matches2) == 0  # Already seen

    async def test_reset_seen(self, client: PressWireClient, mock_http_client: AsyncMock) -> None:
        client.set_watchlist(["Acme Defense Systems"])
        mock_http_client.get.return_value = _mock_response(200, SAMPLE_RSS)

        await client.poll()
        client.reset_seen()
        matches = await client.poll()

        assert len(matches) == 1

    async def test_poll_all_unfiltered(
        self, client: PressWireClient, mock_http_client: AsyncMock
    ) -> None:
        mock_http_client.get.return_value = _mock_response(200, SAMPLE_RSS)

        items = await client.poll_all_unfiltered()

        assert len(items) == 2  # Both items, no watchlist filter

    async def test_feed_fetch_500_logged_as_empty(
        self, client: PressWireClient, mock_http_client: AsyncMock
    ) -> None:
        """When a feed returns 5xx, poll continues with other feeds.

        In this test there's only one feed, so matches should be empty.
        """
        client.set_watchlist(["Acme Defense Systems"])
        resp = Mock()
        resp.status_code = 500
        resp.text = "server error"
        mock_http_client.get.side_effect = httpx.HTTPStatusError(
            "500", request=Mock(), response=resp
        )

        matches = await client.poll()

        assert matches == []

    async def test_absolute_url_passed_through(
        self, client: PressWireClient, mock_http_client: AsyncMock
    ) -> None:
        """Feed URL is passed absolute — base client should use as-is."""
        client.set_watchlist(["something"])
        mock_http_client.get.return_value = _mock_response(200, SAMPLE_RSS)

        await client.poll()

        called_url = mock_http_client.get.call_args[0][0]
        assert called_url == "https://test.example.com/rss"


# ==================== Sync facade ====================


class TestSyncFacade:
    def test_context_manager(self) -> None:
        with SyncPressWireClient(feeds={"Test": "https://test/rss"}) as client:
            assert hasattr(client, "poll")
            assert hasattr(client, "set_watchlist")

    def test_watchlist_on_sync_facade(self) -> None:
        with SyncPressWireClient(feeds={"Test": "https://test/rss"}) as client:
            client.set_watchlist(["Acme"])
            client.add_to_watchlist("Nova")
            assert len(client._client._watchlist) == 2

    def test_poll_delegates_to_async(self) -> None:
        with SyncPressWireClient(feeds={"Test": "https://test/rss"}) as client:
            client._client.poll = AsyncMock(return_value=[])  # type: ignore[method-assign]

            result = client.poll()

            assert result == []
            client._client.poll.assert_awaited_once()

    def test_reset_seen_on_sync_facade(self) -> None:
        with SyncPressWireClient(feeds={"Test": "https://test/rss"}) as client:
            client._client._seen_hashes.add("abc")
            client.reset_seen()
            assert client._client._seen_hashes == set()
