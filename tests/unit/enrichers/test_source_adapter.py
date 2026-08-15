"""Contract tests for SourceRefreshRunner and the USAspending adapter wrap."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

import pytest

from sbir_etl.enrichers.source_adapter import (
    QualityResult,
    RawPage,
    SourceProvenance,
    SourceRefreshRunner,
)
from sbir_etl.enrichers.usaspending.adapter import USAspendingSourceAdapter
from sbir_etl.utils.enrichment.checkpoints import CheckpointStore
from sbir_etl.utils.enrichment.freshness import FreshnessStore


pytestmark = pytest.mark.fast


class FakeAdapter:
    source_id = "usaspending"

    def __init__(self) -> None:
        self.fetched: list[str] = []

    def fetch_page(self, request: Mapping[str, Any], cursor: str | None) -> RawPage:
        del cursor
        award_id = str(request["award_id"])
        self.fetched.append(award_id)
        return RawPage(
            payload={
                "success": True,
                "payload_hash": f"hash-{award_id}",
                "delta_detected": True,
                "metadata": {},
            },
            record_id=award_id,
        )

    def normalize(self, raw: RawPage) -> list[Mapping[str, Any]]:
        payload = raw.payload if isinstance(raw.payload, Mapping) else {}
        return [
            {
                "award_id": raw.record_id,
                "success": payload.get("success"),
                "payload_hash": payload.get("payload_hash"),
                "delta_detected": payload.get("delta_detected"),
                "metadata": payload.get("metadata") or {},
            }
        ]

    def validate(self, records: Sequence[Mapping[str, Any]]) -> QualityResult:
        return QualityResult(ok=True)

    def provenance(self, raw: RawPage) -> SourceProvenance:
        payload = raw.payload if isinstance(raw.payload, Mapping) else {}
        return SourceProvenance(
            source_id=self.source_id,
            retrieved_at=datetime.now(UTC),
            content_hash=str(payload.get("payload_hash")),
            citation_url="https://example.test",
        )


def test_runner_fetch_normalize_validate_freshness_checkpoint(tmp_path) -> None:
    freshness = FreshnessStore(tmp_path / "freshness.parquet")
    checkpoints = CheckpointStore(tmp_path / "checkpoints.parquet")
    adapter = FakeAdapter()
    runner = SourceRefreshRunner(
        freshness=freshness,
        checkpoints=checkpoints,
        partition_id="part-1",
    )

    stats = runner.refresh_records(adapter, [{"award_id": "A1"}, {"award_id": "A2"}])

    assert stats.as_dict()["success"] == 2
    assert adapter.fetched == ["A1", "A2"]
    assert freshness.get_record("A1", "usaspending") is not None
    checkpoint = checkpoints.load_checkpoint("part-1", "usaspending")
    assert checkpoint is not None
    assert set(checkpoint.metadata["processed_ids"]) == {"A1", "A2"}

    second = runner.refresh_records(adapter, [{"award_id": "A1"}, {"award_id": "A2"}])
    assert second.skipped == 2
    assert adapter.fetched == ["A1", "A2"]


class _FakeClient:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def enrich_award(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(str(kwargs["award_id"]))
        return {
            "success": True,
            "payload": {"uei": "ABC"},
            "payload_hash": "deadbeef",
            "delta_detected": True,
            "metadata": {"modification_number": "0"},
            "error": None,
        }


def test_usaspending_adapter_uses_client_without_network() -> None:
    client = _FakeClient()
    adapter = USAspendingSourceAdapter(client=client)
    raw = adapter.fetch_page({"award_id": "AW-1", "uei": "ABC123456789"}, None)
    records = adapter.normalize(raw)
    quality = adapter.validate(records)
    proven = adapter.provenance(raw)
    assert quality.ok
    assert records[0]["success"] is True
    assert proven.content_hash == "deadbeef"
    assert client.calls == ["AW-1"]
