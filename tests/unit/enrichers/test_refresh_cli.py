"""CLI wiring for refresh-enrichment."""

from __future__ import annotations

from datetime import datetime

from sbir_etl.enrichers.refresh_cli import build_parser, run_refresh
from sbir_etl.enrichers.source_adapter import (
    QualityResult,
    RawPage,
    SourceProvenance,
    SourceRefreshRunner,
)
from sbir_etl.models.enrichment import EnrichmentFreshnessRecord, EnrichmentStatus
from sbir_etl.utils.enrichment.checkpoints import CheckpointStore
from sbir_etl.utils.enrichment.freshness import FreshnessStore

import pytest

pytestmark = pytest.mark.fast


class _Adapter:
    source_id = "usaspending"

    def fetch_page(self, request, cursor):
        del cursor
        return RawPage(
            payload={"success": True, "payload_hash": "x"}, record_id=request["award_id"]
        )

    def normalize(self, raw):
        return [
            {"award_id": raw.record_id, "success": True, "delta_detected": True, "metadata": {}}
        ]

    def validate(self, records):
        del records
        return QualityResult(ok=True)

    def provenance(self, raw):
        return SourceProvenance(
            source_id=self.source_id,
            retrieved_at=datetime.now(),
            content_hash="x",
            citation_url="https://example.test",
        )


def test_parser_help_lists_source() -> None:
    parser = build_parser()
    help_text = parser.format_help()
    assert "--source" in help_text
    assert "--window" in help_text


def test_run_refresh_mocked(tmp_path, monkeypatch) -> None:
    store = FreshnessStore(tmp_path / "freshness.parquet")
    store.save_record(
        EnrichmentFreshnessRecord(
            award_id="AW-CLI",
            source="usaspending",
            last_attempt_at=datetime(2020, 1, 1),
            last_success_at=datetime(2020, 1, 1),
            status=EnrichmentStatus.SUCCESS,
        )
    )
    monkeypatch.setattr("sbir_etl.enrichers.refresh_cli.FreshnessStore", lambda: store)
    runner = SourceRefreshRunner(
        freshness=store,
        checkpoints=CheckpointStore(tmp_path / "ck.parquet"),
        partition_id="cli",
    )
    stats = run_refresh(source="usaspending", adapter=_Adapter(), runner=runner)
    assert stats["success"] == 1
    assert stats["failed"] == 0
