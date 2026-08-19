"""Tests for the M&A discovery orchestrator."""

from __future__ import annotations

import pytest

from sbir_etl.enrichers.ma_discovery.orchestrator import main, process_batch
from sbir_etl.enrichers.ma_discovery.queries import generate_queries
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
async def test_process_batch_confirms_recipient_v1_generated_query() -> None:
    query = generate_queries("Physical Optics Corporation", "Mercury Systems, Inc.")[0]
    queries = [
        {
            "company_name": "Physical Optics Corporation",
            "acquirer": "Mercury Systems",
            "query": query,
        }
    ]
    verified = await process_batch(queries, MockSearchTool())
    assert len(verified) == 1
    assert verified[0]["company_name"] == "Physical Optics Corporation"


def test_main_uses_mock_backend(tmp_path) -> None:
    input_path = tmp_path / "queries.csv"
    input_path.write_text(
        "company_name,acquirer,query\n"
        'Physical Optics Corporation,Mercury Systems,"physical optics" "mercury systems"\n'
    )
    output_path = tmp_path / "out.jsonl"
    rc = main(
        [
            "--input",
            str(input_path),
            "--output",
            str(output_path),
            "--search-backend",
            "mock",
        ]
    )
    assert rc == 0
    lines = [line for line in output_path.read_text().splitlines() if line]
    assert len(lines) == 1


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
