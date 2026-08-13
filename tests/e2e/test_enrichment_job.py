"""Hermetic end-to-end test for the USAspending freshness Dagster job."""

from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd
import pytest

from sbir_analytics.assets import usaspending_iterative_enrichment as enrichment_assets
from sbir_etl.models.enrichment import EnrichmentFreshnessRecord, EnrichmentStatus
from sbir_etl.utils.enrichment.freshness import FreshnessStore


pytestmark = [pytest.mark.e2e, pytest.mark.smoke]


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

    def reject_api_client(*_args, **_kwargs):
        raise AssertionError("freshness-selection job attempted to construct an API client")

    monkeypatch.setattr(enrichment_assets, "USAspendingAPIClient", reject_api_client)

    job = defs.resolve_job_def("usaspending_iterative_enrichment_job")
    result = job.execute_in_process()

    assert result.success
    ledger = result.output_for_node("usaspending_freshness_ledger")
    stale = result.output_for_node("stale_usaspending_awards")
    assert set(ledger["award_id"]) == {"AWARD-STALE", "AWARD-FRESH"}
    assert stale["award_id"].tolist() == ["AWARD-STALE"]
    evaluations = result.get_asset_check_evaluations()
    assert len(evaluations) == 1
    assert evaluations[0].check_name == "stale_awards_threshold_check"
    assert evaluations[0].passed
