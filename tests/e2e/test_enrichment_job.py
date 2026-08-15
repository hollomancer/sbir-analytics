"""Hermetic end-to-end test for the USAspending freshness Dagster job."""

from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd
import pytest

from sbir_analytics.assets import usaspending_iterative_enrichment as enrichment_assets
from sbir_etl.enrichers.source_adapter import QualityResult, RawPage, SourceProvenance
from sbir_etl.models.enrichment import EnrichmentFreshnessRecord, EnrichmentStatus
from sbir_etl.utils.enrichment.checkpoints import CheckpointStore
from sbir_etl.utils.enrichment.freshness import FreshnessStore


pytestmark = [pytest.mark.e2e, pytest.mark.smoke]


class HermeticAdapter:
    source_id = "usaspending"

    def fetch_page(self, request, cursor):
        del cursor
        return RawPage(
            payload={"success": True, "payload_hash": "hermetic", "delta_detected": True},
            record_id=str(request["award_id"]),
        )

    def normalize(self, raw):
        return [
            {
                "award_id": raw.record_id,
                "success": True,
                "payload_hash": "hermetic",
                "delta_detected": True,
                "metadata": {},
            }
        ]

    def validate(self, records):
        del records
        return QualityResult(ok=True)

    def provenance(self, raw):
        return SourceProvenance(
            source_id=self.source_id,
            retrieved_at=datetime.now(),
            content_hash="hermetic",
            citation_url="https://example.test",
        )


def test_usaspending_enrichment_job_smoke(tmp_path, monkeypatch):
    """Materialize persisted freshness inputs through stale-award selection."""
    defs = pytest.importorskip("sbir_analytics.definitions").defs
    data_root = tmp_path / "data"
    enriched_path = data_root / "processed" / "enriched" / "sbir_awards.parquet"
    enriched_path.parent.mkdir(parents=True)
    pd.DataFrame(
        [
            {"award_id": "AWARD-STALE", "UEI": "ABCDEFGHIJKL"},
            {"award_id": "AWARD-FRESH", "UEI": "MNOPQRSTUVWX"},
        ]
    ).to_parquet(enriched_path, index=False)

    store = FreshnessStore(tmp_path / "freshness.parquet")
    now = datetime.now()
    store.save_records(
        [
            EnrichmentFreshnessRecord(
                award_id="AWARD-STALE",
                source="usaspending",
                last_attempt_at=now - timedelta(days=3),
                last_success_at=now - timedelta(days=3),
                status=EnrichmentStatus.SUCCESS,
            ),
            EnrichmentFreshnessRecord(
                award_id="AWARD-FRESH",
                source="usaspending",
                last_attempt_at=now,
                last_success_at=now,
                status=EnrichmentStatus.SUCCESS,
            ),
        ]
    )

    monkeypatch.setenv("SBIR_ETL__PATHS__DATA_ROOT", str(data_root))
    monkeypatch.setattr(enrichment_assets, "FreshnessStore", lambda: store)
    monkeypatch.setattr(
        enrichment_assets,
        "CheckpointStore",
        lambda: CheckpointStore(tmp_path / "checkpoints.parquet"),
    )
    monkeypatch.setattr(
        enrichment_assets,
        "build_usaspending_adapter",
        lambda **_kwargs: HermeticAdapter(),
    )

    job = defs.resolve_job_def("usaspending_iterative_enrichment_job")
    result = job.execute_in_process()

    assert result.success
    ledger = result.output_for_node("usaspending_freshness_ledger")
    stale = result.output_for_node("stale_usaspending_awards")
    refresh = result.output_for_node("usaspending_refresh_batch")
    assert set(ledger["award_id"]) == {"AWARD-STALE", "AWARD-FRESH"}
    assert stale["award_id"].tolist() == ["AWARD-STALE"]
    assert refresh["success"] == 1
    evaluations = result.get_asset_check_evaluations()
    assert len(evaluations) == 1
    assert evaluations[0].check_name == "stale_awards_threshold_check"
    assert evaluations[0].passed
