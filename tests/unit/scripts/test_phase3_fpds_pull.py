"""Tests for the research-only FPDS Element 10Q puller."""

import json
from pathlib import Path

from scripts.phase3_benchmark.pull_fpds_10q import (
    build_query_url,
    parse_feed,
    pull_research_code,
    write_outputs,
)


FIXTURE = Path("tests/fixtures/phase3_benchmark/fpds_atom_page.xml")


def test_parse_feed_extracts_nested_parent_idv_without_replacing_order_piid():
    frame, total = parse_feed(FIXTURE.read_bytes(), "sr3")

    assert total == 1
    assert frame.iloc[0]["PIID"] == "0001"
    assert frame.iloc[0]["referenced_idv_piid"] == "N00019-20-D-0001"
    assert frame.iloc[0]["referenced_idv_agency_id"] == "1700"
    assert frame.iloc[0]["agencyID"] == "2100"
    assert frame.iloc[0]["agencyID_name"] == "Department of Defense"


def test_pull_records_manifest_and_writes_outputs(tmp_path):
    payload = FIXTURE.read_bytes()
    requested: list[str] = []

    def fetcher(url: str) -> bytes:
        requested.append(url)
        return payload

    frame, manifest = pull_research_code(
        "sr3",
        pages=3,
        fetcher=fetcher,
        source_vintage="fixture-2024",
        retrieved_at="2026-07-16T00:00:00+00:00",
    )
    output = tmp_path / "records.parquet"
    manifest_path = tmp_path / "manifest.json"
    write_outputs(frame, manifest, output_path=output, manifest_path=manifest_path)

    saved = json.loads(manifest_path.read_text())
    assert requested == [build_query_url("SR3", 0)]
    assert output.exists()
    assert saved["query"] == "RESEARCH:SR3"
    assert saved["row_count"] == 1
    assert saved["retrieval_complete"] is True
    assert saved["field_completeness"]["referenced_idv_piid"] == 1.0
    assert len(saved["raw_pages_sha256"]) == 64
