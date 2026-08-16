"""Hermetic tests for the NIH RePORTER iterative enrichment job."""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import pytest
from dagster import Definitions

from sbir_analytics.assets import nih_reporter_iterative_enrichment as nih_assets
from sbir_analytics.assets.jobs.nih_reporter_iterative_job import (
    nih_reporter_iterative_enrichment_job,
)
from sbir_etl.config.loader import get_config
from sbir_etl.enrichers.source_adapter import QualityResult, RawPage, SourceProvenance
from sbir_etl.utils.enrichment.checkpoints import CheckpointStore
from sbir_etl.utils.enrichment.freshness import FreshnessStore


pytestmark = pytest.mark.fast


class _HermeticAdapter:
    source_id = "nih_reporter"

    def __init__(self) -> None:
        self.requests: list[dict] = []

    def fetch_page(self, request, cursor):
        del cursor
        self.requests.append(dict(request))
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
            citation_url="https://api.reporter.nih.gov/",
        )


def _defs() -> Definitions:
    return Definitions(
        assets=[
            nih_assets.nih_reporter_freshness_ledger,
            nih_assets.stale_nih_reporter_awards,
            nih_assets.nih_reporter_refresh_batch,
        ],
        jobs=[nih_reporter_iterative_enrichment_job],
    )


def _nih_awards() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "award_id": "AW-NIH-1",
                "agency": "HHS",
                "branch": "NIAID",
                "contract_number": "1R43AI123456-01",
                "agency_tracking_number": None,
                "award_year": 2024,
            }
        ]
    )


def test_job_selection_includes_refresh_asset() -> None:
    job = _defs().resolve_job_def("nih_reporter_iterative_enrichment_job")
    node_names = {node.name for node in job.nodes}
    assert "nih_reporter_freshness_ledger" in node_names
    assert "stale_nih_reporter_awards" in node_names
    assert "nih_reporter_refresh_batch" in node_names


def test_no_nih_reporter_sensor_is_registered() -> None:
    from sbir_analytics import assets as assets_pkg

    sensor_names = {sensor.name for sensor in assets_pkg.iter_public_sensors()}
    assert not any("nih_reporter" in name for name in sensor_names)


def _patch_stores(monkeypatch, tmp_path, store: FreshnessStore, adapter: _HermeticAdapter) -> None:
    monkeypatch.setattr(nih_assets, "FreshnessStore", lambda: store)
    monkeypatch.setattr(
        nih_assets,
        "CheckpointStore",
        lambda: CheckpointStore(tmp_path / "checkpoints.parquet"),
    )
    monkeypatch.setattr(nih_assets, "load_sbir_award_frame", lambda: _nih_awards())
    monkeypatch.setattr(nih_assets, "build_nih_reporter_adapter", lambda **_kwargs: adapter)


def test_hermetic_job_refreshes_first_run_when_enabled(tmp_path, monkeypatch) -> None:
    store = FreshnessStore(tmp_path / "freshness.parquet")
    adapter = _HermeticAdapter()
    _patch_stores(monkeypatch, tmp_path, store, adapter)
    config = get_config()
    monkeypatch.setattr(config.enrichment_refresh.nih_reporter, "enabled", True)
    monkeypatch.setattr(nih_assets, "get_config", lambda: config)

    result = _defs().resolve_job_def("nih_reporter_iterative_enrichment_job").execute_in_process()

    assert result.success
    stale = result.output_for_node("stale_nih_reporter_awards")
    refresh = result.output_for_node("nih_reporter_refresh_batch")
    assert stale["award_id"].tolist() == ["AW-NIH-1"]
    assert refresh["success"] == 1
    assert adapter.requests[0]["project_num"] == "1R43AI123456-01"
    assert adapter.requests[0]["award_year"] == 2024


def test_disabled_source_skips_adapter(tmp_path, monkeypatch) -> None:
    store = FreshnessStore(tmp_path / "freshness.parquet")
    adapter = _HermeticAdapter()
    _patch_stores(monkeypatch, tmp_path, store, adapter)
    config = get_config()
    monkeypatch.setattr(config.enrichment_refresh.nih_reporter, "enabled", False)
    monkeypatch.setattr(nih_assets, "get_config", lambda: config)

    result = _defs().resolve_job_def("nih_reporter_iterative_enrichment_job").execute_in_process()

    assert result.success
    refresh = result.output_for_node("nih_reporter_refresh_batch")
    assert refresh["success"] == 0
    assert adapter.requests == []


def test_missing_sbir_frame_fails_closed(tmp_path, monkeypatch) -> None:
    store = FreshnessStore(tmp_path / "freshness.parquet")
    adapter = _HermeticAdapter()
    monkeypatch.setattr(nih_assets, "FreshnessStore", lambda: store)
    monkeypatch.setattr(
        nih_assets,
        "load_sbir_award_frame",
        lambda: (_ for _ in ()).throw(FileNotFoundError("SBIR.gov award CSV is unavailable")),
    )
    monkeypatch.setattr(nih_assets, "build_nih_reporter_adapter", lambda **_kwargs: adapter)

    result = (
        _defs()
        .resolve_job_def("nih_reporter_iterative_enrichment_job")
        .execute_in_process(raise_on_error=False)
    )

    assert result.success is False
    assert adapter.requests == []
