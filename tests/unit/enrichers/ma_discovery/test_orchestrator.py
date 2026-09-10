"""Tests for the M&A discovery orchestrator."""

from __future__ import annotations

import pytest

from sbir_etl.enrichers.ma_discovery.extractor import ExtractionInput, ExtractionVerdict
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
    assert verified[0]["date"] is None
    assert verified[0]["event_date"] is None
    assert verified[0]["confidence"] == "low"
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


@pytest.mark.asyncio
async def test_process_batch_dedupes_four_query_rows_for_one_pair() -> None:
    base = {
        "company_name": "Physical Optics Corporation",
        "acquirer": "Mercury Systems",
    }
    queries = [
        {**base, "query": generate_queries(base["company_name"], base["acquirer"])[i]}
        for i in range(4)
    ]
    verified = await process_batch(queries, MockSearchTool())
    assert len(verified) == 1


class _TwoHitSearch:
    async def search(self, query: str) -> list[dict[str, str]]:
        return [
            {"snippet": "acquired with no calendar date", "link": "http://example.com/a"},
            {"snippet": "acquired on 2015-12-16", "link": "http://example.com/b"},
        ]


class _UndatedThenDated:
    def __init__(self) -> None:
        self.n = 0

    def extract(self, item: ExtractionInput) -> ExtractionVerdict:
        self.n += 1
        if "2015-12-16" in item.snippet:
            return ExtractionVerdict(
                confirmed=True,
                reason="dated",
                acquisition_date="2015-12-16",
                matched_company=item.company,
                matched_acquirer=item.acquirer,
            )
        return ExtractionVerdict(
            confirmed=True,
            reason="undated",
            matched_company=item.company,
            matched_acquirer=item.acquirer,
        )


class _UndatedThenDatedValueHits:
    async def search(self, query: str) -> list[dict[str, str]]:
        return [
            {"snippet": "acquired with no calendar date", "link": "http://example.com/a"},
            {
                "snippet": "acquired on 2015-12-16 for value",
                "link": "http://example.com/b",
            },
        ]


class _NoiseThenDatedValueHits:
    async def search(self, query: str) -> list[dict[str, str]]:
        return [
            {"snippet": "unrelated industry news", "link": "http://example.com/noise"},
            {
                "snippet": "acquired on 2015-12-16 for value",
                "link": "http://example.com/deal",
            },
        ]


class _RejectThenDatedValue:
    def extract(self, item: ExtractionInput) -> ExtractionVerdict:
        if "unrelated" in item.snippet:
            return ExtractionVerdict(confirmed=False, reason="no")
        if "2015-12-16" in item.snippet:
            return ExtractionVerdict(
                confirmed=True,
                reason="dated",
                acquisition_date="2015-12-16",
                value_usd=1.0,
                matched_company=item.company,
                matched_acquirer=item.acquirer,
            )
        return ExtractionVerdict(
            confirmed=True,
            reason="undated",
            matched_company=item.company,
            matched_acquirer=item.acquirer,
        )


class _UndatedThenDatedQueries:
    async def search(self, query: str) -> list[dict[str, str]]:
        if query == "q1":
            return [{"snippet": "acquired with no calendar date", "link": "http://example.com/a"}]
        return [{"snippet": "acquired on 2015-12-16", "link": "http://example.com/b"}]


@pytest.mark.asyncio
async def test_high_confidence_counts_distinct_confirming_sources_only() -> None:
    queries = [
        {
            "company_name": "Lewis Innovative Technologies, Inc.",
            "acquirer": "MERCURY SYSTEMS INC",
            "query": "q",
        }
    ]
    noise = await process_batch(
        queries,
        _NoiseThenDatedValueHits(),
        extractor=_RejectThenDatedValue(),
        stop_when="dated_confirm",
    )
    assert noise[0]["confidence"] == "medium"
    two = await process_batch(
        queries,
        _UndatedThenDatedValueHits(),
        extractor=_RejectThenDatedValue(),
        stop_when="dated_confirm",
    )
    assert two[0]["confidence"] == "high"


@pytest.mark.asyncio
async def test_dated_confirm_keeps_scanning_after_undated_query() -> None:
    base = {
        "company_name": "Lewis Innovative Technologies, Inc.",
        "acquirer": "MERCURY SYSTEMS INC",
    }
    queries = [{**base, "query": "q1"}, {**base, "query": "q2"}]
    first = await process_batch(
        queries,
        _UndatedThenDatedQueries(),
        extractor=_UndatedThenDated(),
        stop_when="first_confirm",
    )
    assert first[0]["confidence"] == "low"
    assert first[0]["date"] is None
    dated = await process_batch(
        queries,
        _UndatedThenDatedQueries(),
        extractor=_UndatedThenDated(),
        stop_when="dated_confirm",
    )
    assert dated[0]["confidence"] == "medium"
    assert dated[0]["date"] == "2015-12-16"
    assert dated[0]["source"] == "http://example.com/b"


@pytest.mark.asyncio
async def test_dated_confirm_skips_undated_first_hit() -> None:
    queries = [
        {
            "company_name": "Lewis Innovative Technologies, Inc.",
            "acquirer": "MERCURY SYSTEMS INC",
            "query": "q",
        }
    ]
    first = await process_batch(
        queries, _TwoHitSearch(), extractor=_UndatedThenDated(), stop_when="first_confirm"
    )
    assert first[0]["confidence"] == "low"
    assert first[0]["date"] is None
    dated = await process_batch(
        queries, _TwoHitSearch(), extractor=_UndatedThenDated(), stop_when="dated_confirm"
    )
    assert dated[0]["confidence"] == "medium"
    assert dated[0]["date"] == "2015-12-16"
    assert dated[0]["source"] == "http://example.com/b"


def test_main_without_backend_is_fail_closed(tmp_path) -> None:
    from sbir_etl.exceptions import ConfigurationError

    input_path = tmp_path / "queries.csv"
    input_path.write_text(
        "company_name,acquirer,query\n"
        'Physical Optics Corporation,Mercury Systems,"physical optics" "mercury systems"\n'
    )
    output_path = tmp_path / "out.jsonl"
    with pytest.raises(ConfigurationError, match="fail-closed"):
        main(["--input", str(input_path), "--output", str(output_path)])
    assert not output_path.exists()
