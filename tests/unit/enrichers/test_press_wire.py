"""Tests for press wire RSS/Atom feed client."""

from unittest.mock import Mock

import pytest

from sbir_etl.enrichers.press_wire import (
    PressRelease,
    PressWireClient,
    _content_hash,
    _normalize,
)

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


class TestPressWireClient:
    def _mock_client(self, feeds: dict[str, str] | None = None) -> PressWireClient:
        client = PressWireClient(feeds=feeds or {"TestRSS": "http://test/rss"})
        client._client = Mock()
        return client

    def test_parse_rss(self):
        client = self._mock_client()
        items = client._parse_feed(SAMPLE_RSS, "PRNewswire")
        assert len(items) == 2
        assert items[0].title == "Acme Defense Awarded $5M DoD Contract for Next-Gen Sensors"
        assert items[0].source == "PRNewswire"
        assert "prnewswire.com" in items[0].link

    def test_parse_atom(self):
        client = self._mock_client()
        items = client._parse_feed(SAMPLE_ATOM, "BusinessWire")
        assert len(items) == 1
        assert "Nova Quantum" in items[0].title
        assert items[0].source == "BusinessWire"
        assert "businesswire.com" in items[0].link

    def test_poll_with_matches(self):
        client = self._mock_client()
        client.set_watchlist(["Acme Defense Systems", "Nova Quantum Inc"])

        resp = Mock(status_code=200, text=SAMPLE_RSS)
        client._client.get.return_value = resp

        matches = client.poll()
        assert len(matches) == 1
        assert matches[0].matched_company == "Acme Defense Systems"
        assert "DoD Contract" in matches[0].title

    def test_poll_no_watchlist_warns(self):
        client = self._mock_client()
        matches = client.poll()
        assert matches == []

    def test_dedup_across_polls(self):
        client = self._mock_client()
        client.set_watchlist(["Acme Defense Systems"])

        resp = Mock(status_code=200, text=SAMPLE_RSS)
        client._client.get.return_value = resp

        matches1 = client.poll()
        matches2 = client.poll()
        assert len(matches1) == 1
        assert len(matches2) == 0  # Already seen

    def test_reset_seen(self):
        client = self._mock_client()
        client.set_watchlist(["Acme Defense Systems"])

        resp = Mock(status_code=200, text=SAMPLE_RSS)
        client._client.get.return_value = resp

        client.poll()
        client.reset_seen()
        matches = client.poll()
        assert len(matches) == 1

    def test_poll_all_unfiltered(self):
        client = self._mock_client()
        resp = Mock(status_code=200, text=SAMPLE_RSS)
        client._client.get.return_value = resp

        items = client.poll_all_unfiltered()
        assert len(items) == 2  # Both items, no watchlist filter

    def test_feed_fetch_failure(self):
        client = self._mock_client()
        client.set_watchlist(["Acme Defense Systems"])

        resp = Mock(status_code=500)
        client._client.get.return_value = resp

        matches = client.poll()
        assert matches == []

    def test_malformed_xml(self):
        client = self._mock_client()
        items = client._parse_feed("not xml at all", "BadFeed")
        assert items == []

    def test_context_manager(self):
        with PressWireClient() as client:
            assert hasattr(client, "poll")

    def test_add_to_watchlist(self):
        client = self._mock_client()
        client.set_watchlist(["Company A"])
        client.add_to_watchlist("Company B")
        assert len(client._watchlist) == 2
