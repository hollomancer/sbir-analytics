"""Tests for the exploratory M&A discovery sample-run CLI helpers."""

from __future__ import annotations

import hashlib
import json

import pytest

from scripts.data.run_ma_discovery_sample import (
    RecordingSearchTool,
    bound_queries,
    build_review_queue,
    check_run_manifest,
    drop_recorded_queries,
    load_recorded_queries,
    strict_medium_high_n,
)


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


def test_bound_queries_caps_pairs_and_templates() -> None:
    rows = [
        {"company_name": "A", "acquirer": "B", "query": "q1"},
        {"company_name": "A", "acquirer": "B", "query": "q2"},
        {"company_name": "A", "acquirer": "B", "query": "q3"},
        {"company_name": "C", "acquirer": "D", "query": "q4"},
        {"company_name": "E", "acquirer": "F", "query": "q5"},
    ]
    kept = bound_queries(rows, max_candidates=2, queries_per_pair=1)
    assert [(r["company_name"], r["query"]) for r in kept] == [("A", "q1"), ("C", "q4")]


def test_bound_queries_skips_leading_pairs() -> None:
    rows = [
        {"company_name": "A", "acquirer": "B", "query": "q1"},
        {"company_name": "C", "acquirer": "D", "query": "q2"},
        {"company_name": "E", "acquirer": "F", "query": "q3"},
    ]
    kept = bound_queries(rows, max_candidates=1, queries_per_pair=1, skip_pairs=1)
    assert [(r["company_name"], r["query"]) for r in kept] == [("C", "q2")]


def test_drop_recorded_queries_skips_frozen_strings() -> None:
    rows = [
        {"company_name": "A", "acquirer": "B", "query": "q1"},
        {"company_name": "C", "acquirer": "D", "query": "q2"},
    ]
    kept = drop_recorded_queries(rows, {"q1"})
    assert [r["query"] for r in kept] == ["q2"]


@pytest.mark.asyncio
async def test_recording_search_tool_checkpoints_each_query(tmp_path) -> None:
    path = tmp_path / "snippets.jsonl"

    class _Inner:
        async def search(self, query: str) -> list[dict[str, str]]:
            return [{"snippet": "hit", "link": f"http://example.com/{query}"}]

    sink: list[dict[str, object]] = []
    tool = RecordingSearchTool(_Inner(), sink, path=path)
    await tool.search("q1")
    await tool.search("q2")
    lines = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert [row["query"] for row in lines] == ["q1", "q2"]
    assert sink == lines


def test_load_recorded_queries_reads_jsonl(tmp_path) -> None:
    path = tmp_path / "snippets.jsonl"
    path.write_text(
        '{"query": "q1", "snippet": "s", "link": "http://a"}\n'
        '{"query": "q1", "snippet": "t", "link": "http://b"}\n'
        '{"query": "q2", "snippet": "", "link": null}\n',
        encoding="utf-8",
    )
    assert load_recorded_queries(path) == {"q1", "q2"}
    assert load_recorded_queries(tmp_path / "missing.jsonl") == set()


def test_strict_medium_high_excludes_already_medium_pairs() -> None:
    events = [
        {"company_name": "GINER INC", "acquirer": "ENER1 INC", "confidence": "medium"},
        {"company_name": "SDL Inc", "acquirer": "JDS UNIPHASE CORP /CA/", "confidence": "low"},
    ]
    mutated = [
        {"company_name": "GINER INC", "acquirer": "ENER1 INC", "confidence": "medium"},
        {"company_name": "SDL Inc", "acquirer": "JDS UNIPHASE CORP /CA/", "confidence": "medium"},
    ]
    assert strict_medium_high_n(events, mutated) == 1


def test_check_run_manifest_detects_mismatch(tmp_path) -> None:
    events = tmp_path / "events.jsonl"
    events.write_text("{}\n", encoding="utf-8")
    snippets = tmp_path / "sn.jsonl"
    snippets.write_text("{}\n", encoding="utf-8")
    manifest = tmp_path / "run-manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "inputs": {
                    "events": {"sha256": "0" * 64},
                    "snippets": {"sha256": hashlib.sha256(snippets.read_bytes()).hexdigest()},
                }
            }
        ),
        encoding="utf-8",
    )
    errors = check_run_manifest(manifest, events=events, snippets=snippets, llm=None)
    assert any("events SHA mismatch" in e for e in errors)
    assert not any("snippets SHA mismatch" in e for e in errors)
