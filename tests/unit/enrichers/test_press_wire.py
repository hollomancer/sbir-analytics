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

    def test_default_feeds_used_when_not_specified(
        self, mock_http_client: AsyncMock
    ) -> None:
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

    async def test_reset_seen(
        self, client: PressWireClient, mock_http_client: AsyncMock
    ) -> None:
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
