"""Tests for the exploratory M&A discovery sample-run CLI helpers."""

from __future__ import annotations

import pytest

from scripts.data.run_ma_discovery_sample import build_review_queue


pytestmark = pytest.mark.fast


def test_review_queue_keeps_medium_discovery_rows_only() -> None:
    queue = build_review_queue(
        [
            {
                "company_name": "A",
                "acquirer": "B",
                "confidence": "medium",
                "signals": {"discovery_confirmed": True},
                "source": "https://example.com/a",
                "evidence": "B acquired A.",
            },
            {
                "company_name": "C",
                "acquirer": "D",
                "confidence": "high",
                "signals": {"discovery_confirmed": True},
            },
            {
                "company_name": "E",
                "acquirer": "F",
                "confidence": "medium",
                "signals": {},
            },
        ],
        limit=20,
    )
    assert len(queue) == 1
    assert queue[0]["review_outcome"] == "unreviewed"
    assert queue[0]["company_name"] == "A"
