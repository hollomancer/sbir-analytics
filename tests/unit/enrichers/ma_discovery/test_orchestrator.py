"""Tests for the M&A discovery orchestrator."""

from __future__ import annotations

import pytest

from sbir_etl.enrichers.ma_discovery.orchestrator import process_batch
from sbir_etl.enrichers.ma_discovery.search import MockSearchTool


pytestmark = pytest.mark.fast


@pytest.mark.asyncio
async def test_process_batch_confirms_physical_optics_mercury_systems() -> None:
    queries = [
        {
            "company_name": "Physical Optics Corporation",
            "acquirer": "Mercury Systems",
            "query": '"Physical Optics" acquired by "Mercury Systems" press release',
        }
    ]
    verified = await process_batch(queries, MockSearchTool())
    assert len(verified) == 1
    assert verified[0]["company_name"] == "Physical Optics Corporation"
    assert verified[0]["acquirer"] == "Mercury Systems"
    assert verified[0]["date"] == "Unknown"
    assert verified[0]["source"] == "http://example.com"


@pytest.mark.asyncio
async def test_process_batch_rejects_unrelated_query() -> None:
    queries = [
        {
            "company_name": "Unrelated Labs",
            "acquirer": "Other Holdings",
            "query": "unrelated labs other holdings",
        }
    ]
    verified = await process_batch(queries, MockSearchTool())
    assert verified == []
