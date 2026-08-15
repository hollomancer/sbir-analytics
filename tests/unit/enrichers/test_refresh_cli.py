"""CLI wiring for refresh-enrichment."""

from __future__ import annotations

from datetime import datetime

import pandas as pd

from sbir_etl.config.loader import get_config
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

    def __init__(self) -> None:
        self.requests: list[dict] = []

    def fetch_page(self, request, cursor):
        del cursor
        self.requests.append(dict(request))
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


def _stale_store(tmp_path, award_id: str = "AW-CLI") -> FreshnessStore:
    store = FreshnessStore(tmp_path / "freshness.parquet")
    store.save_record(
        EnrichmentFreshnessRecord(
            award_id=award_id,
            source="usaspending",
            last_attempt_at=datetime(2020, 1, 1),
            last_success_at=datetime(2020, 1, 1),
            status=EnrichmentStatus.SUCCESS,
        )
    )
    return store


def _patch_cli(monkeypatch, store: FreshnessStore, enriched: pd.DataFrame | None) -> None:
    monkeypatch.setattr("sbir_etl.enrichers.refresh_cli.FreshnessStore", lambda: store)
    monkeypatch.setattr(
        "sbir_etl.enrichers.refresh_cli.load_enriched_awards", lambda *a, **k: enriched
    )


def _runner(tmp_path, store: FreshnessStore) -> SourceRefreshRunner:
    return SourceRefreshRunner(
        freshness=store,
        checkpoints=CheckpointStore(tmp_path / "ck.parquet"),
        partition_id="cli",
    )


def test_run_refresh_mocked(tmp_path, monkeypatch) -> None:
    store = _stale_store(tmp_path)
    enriched = pd.DataFrame([{"award_id": "AW-CLI", "UEI": "ABC123456789"}])
    _patch_cli(monkeypatch, store, enriched)

    stats = run_refresh(source="usaspending", adapter=_Adapter(), runner=_runner(tmp_path, store))

    assert stats["success"] == 1
    assert stats["failed"] == 0


def test_requests_carry_identifiers_not_just_award_ids(tmp_path, monkeypatch) -> None:
    """enrich_award cannot match on award_id alone, so the CLI must join them (regression)."""

    store = _stale_store(tmp_path)
    enriched = pd.DataFrame(
        [{"award_id": "AW-CLI", "UEI": "ABC123456789", "Contract": "W911-24-C-1"}]
    )
    _patch_cli(monkeypatch, store, enriched)
    adapter = _Adapter()

    run_refresh(source="usaspending", adapter=adapter, runner=_runner(tmp_path, store))

    assert adapter.requests == [
        {
            "award_id": "AW-CLI",
            "uei": "ABC123456789",
            "duns": None,
            "cage": None,
            "piid": "W911-24-C-1",
        }
    ]


def test_awards_without_identifiers_are_skipped(tmp_path, monkeypatch) -> None:
    store = _stale_store(tmp_path)
    _patch_cli(monkeypatch, store, pd.DataFrame([{"award_id": "AW-CLI", "UEI": None}]))
    adapter = _Adapter()

    stats = run_refresh(source="usaspending", adapter=adapter, runner=_runner(tmp_path, store))

    assert adapter.requests == []
    assert stats["total"] == 0
    assert stats["failed"] == 0


def test_missing_enriched_awards_fails_fast(tmp_path, monkeypatch) -> None:
    store = _stale_store(tmp_path)
    _patch_cli(monkeypatch, store, None)

    with pytest.raises(SystemExit, match="enriched awards"):
        run_refresh(source="usaspending", adapter=_Adapter(), runner=_runner(tmp_path, store))


def test_window_is_applied_rather_than_discarded(tmp_path, monkeypatch) -> None:
    store = _stale_store(tmp_path)
    store.save_record(
        EnrichmentFreshnessRecord(
            award_id="AW-OLD",
            source="usaspending",
            last_attempt_at=datetime(2020, 1, 1),
            last_success_at=datetime(2020, 1, 1),
            status=EnrichmentStatus.SUCCESS,
        )
    )
    enriched = pd.DataFrame(
        [
            {"award_id": "AW-CLI", "UEI": "ABC123456789", "award_date": "2024-06-01"},
            {"award_id": "AW-OLD", "UEI": "DEF123456789", "award_date": "2019-06-01"},
        ]
    )
    _patch_cli(monkeypatch, store, enriched)
    adapter = _Adapter()

    run_refresh(
        source="usaspending",
        window="2024-01-01:2024-12-31",
        adapter=adapter,
        runner=_runner(tmp_path, store),
    )

    assert [request["award_id"] for request in adapter.requests] == ["AW-CLI"]


def test_disabled_source_is_refused(tmp_path, monkeypatch) -> None:
    """The enabled=false kill switch must apply to usaspending too (regression)."""

    store = _stale_store(tmp_path)
    _patch_cli(monkeypatch, store, pd.DataFrame([{"award_id": "AW-CLI", "UEI": "ABC123456789"}]))
    config = get_config()
    monkeypatch.setattr(config.enrichment_refresh.usaspending, "enabled", False)
    monkeypatch.setattr("sbir_etl.enrichers.refresh_cli.get_config", lambda: config)

    with pytest.raises(SystemExit, match="disabled"):
        run_refresh(source="usaspending", adapter=_Adapter(), runner=_runner(tmp_path, store))


def test_stale_ids_absent_from_enriched_are_reported(tmp_path, monkeypatch, capsys) -> None:
    store = _stale_store(tmp_path, award_id="AW-MISSING")
    _patch_cli(monkeypatch, store, pd.DataFrame([{"award_id": "AW-OTHER", "UEI": "ABC123456789"}]))
    adapter = _Adapter()

    stats = run_refresh(source="usaspending", adapter=adapter, runner=_runner(tmp_path, store))

    assert adapter.requests == []
    assert stats["total"] == 0
    assert "absent from enriched awards" in capsys.readouterr().err
