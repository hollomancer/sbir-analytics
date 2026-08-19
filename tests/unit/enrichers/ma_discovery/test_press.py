"""Tests for press-wire merge onto M&A events."""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from sbir_etl.enrichers.ma_discovery.press import enrich_ma_events
from sbir_etl.enrichers.press_wire import PressRelease


pytestmark = pytest.mark.fast


def test_enrich_ma_events_merges_mocked_poll_hit() -> None:
    events = [
        {"company_name": "Physical Optics Corporation", "signal_count": 1},
        {"company_name": "Unrelated Labs"},
    ]
    hit = PressRelease(
        title="Mercury Systems Completes Acquisition of Physical Optics",
        link="http://example.com/poc",
        published="2018-01-01",
        summary="Mercury Systems announced the acquisition.",
        source="PRNewswire",
        matched_company="Physical Optics Corporation",
    )
    client = Mock()
    client.poll.return_value = [hit]

    enriched = enrich_ma_events(events, client)

    client.set_watchlist.assert_called_once_with(["Physical Optics Corporation", "Unrelated Labs"])
    client.poll.assert_called_once_with()

    matched, other = enriched
    assert matched["enriched"] is True
    assert matched["signal_count"] == 2
    assert matched["press_wire_signals"] == [
        {
            "title": hit.title,
            "link": hit.link,
            "published": hit.published,
            "summary": hit.summary,
            "source": hit.source,
        }
    ]
    assert other["enriched"] is False
    assert other["press_wire_signals"] == []
    assert "signal_count" not in other
