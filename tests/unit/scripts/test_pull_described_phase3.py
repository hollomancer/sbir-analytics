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
    # two award-type groups each return the same page -> deduped to 2 distinct awards
    assert len(frame) == 2
    assert manifest["row_count"] == 2
    assert manifest["query"] == 'description="SBIR PHASE III"'
    assert manifest["grain"].startswith("award")
    assert manifest["retrieval_complete"] is True
    assert manifest["termination_reason"] == "feed_exhausted"
    assert len(manifest["raw_pages_sha256"]) == 64  # sha256 hex digest of the raw payloads
    assert manifest["field_completeness"]["generated_internal_id"] == 1.0
    assert manifest["pages_retrieved"] == 2  # one page per award-type group before exhaustion
