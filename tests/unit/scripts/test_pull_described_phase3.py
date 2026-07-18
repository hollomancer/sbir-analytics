"""Fixture test for the manifested described-Phase III puller (canned fetcher, no network)."""

from __future__ import annotations

import json

from scripts.phase3_benchmark.pull_described_phase3 import pull_described


def _canned_page() -> bytes:
    return json.dumps({
        "results": [
            {"generated_internal_id": "CONT_AWD_P1_9700_-NONE-_-NONE-", "Award ID": "P1",
             "Description": "SBIR PHASE III widget"},
            {"generated_internal_id": "CONT_AWD_P2_9700_-NONE-_-NONE-", "Award ID": "P2",
             "Description": "SBIR PHASE III gadget"},
        ],
        "page_metadata": {"hasNext": False},
    }).encode()


def test_pull_described_dedupes_and_emits_provenance_manifest() -> None:
    frame, manifest = pull_described("Department of Defense", fetcher=lambda _body: _canned_page(),
                                     source_vintage="test")
    # Two signals x two award-type groups are independently manifested.
    assert len(frame) == 8
    assert manifest["row_count"] == 8
    assert manifest["queries"]["SBIR"] == "SBIR PHASE III"
    assert manifest["queries"]["STTR"] == "STTR PHASE III"
    assert manifest["grain"].startswith("award")
    assert manifest["retrieval_complete"] is True
    assert set(manifest["query_termination"].values()) == {"feed_exhausted"}
    assert len(manifest["raw_pages_sha256"]) == 64  # sha256 hex digest of the raw payloads
    assert manifest["field_completeness"]["generated_internal_id"] == 1.0
    assert manifest["pages_retrieved"] == 4


def test_pull_completion_requires_every_query_to_exhaust() -> None:
    calls = 0

    def fetch(_body: bytes) -> bytes:
        nonlocal calls
        calls += 1
        body = json.loads(_canned_page())
        if calls == 1:
            body["page_metadata"]["hasNext"] = True
        return json.dumps(body).encode()

    _, manifest = pull_described(
        "Department of Defense", fetcher=fetch, max_pages=1, source_vintage="test"
    )
    assert manifest["retrieval_complete"] is False
    assert "page_limit_reached" in manifest["query_termination"].values()
