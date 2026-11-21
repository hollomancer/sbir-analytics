"""Failures in top-level Dagster assets must fail the run or show in asset metadata.

Each test drives one exception handler that used to log and continue (or return
an empty value) so that the asset output looked complete when it was not.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pandas as pd
import pytest
from dagster import Output, build_asset_context

from sbir_analytics.assets import nih_reporter_iterative_enrichment as nih_assets
from sbir_analytics.assets import sbir_ingestion
from sbir_analytics.assets import usaspending_database_enrichment as db_enrichment
from sbir_analytics.assets import usaspending_ingestion
from sbir_analytics.assets import usaspending_iterative_enrichment as usa_iterative
from sbir_etl.exceptions import ExtractionError, ValidationError


pytestmark = pytest.mark.fast


def _md(output: Any, key: str) -> Any:
    value = output.metadata[key]
    return getattr(value, "value", value)


class _Conn:
    def __init__(self, *, describe: pd.DataFrame | None = None, error: Exception | None = None):
        self._describe = describe
        self._error = error

    def execute(self, _query: str):
        if self._error is not None:
            raise self._error
        return SimpleNamespace(fetchdf=lambda: self._describe)


class _Extractor:
    def __init__(self, conn: _Conn):
        self._conn = conn

    def connect(self) -> _Conn:
        return self._conn


# --- usaspending_database_enrichment._table_has_column ---------------------------


def test_table_has_column_raises_when_schema_read_fails() -> None:
    extractor: Any = _Extractor(_Conn(error=RuntimeError("Catalog Error: table does not exist")))

    with pytest.raises(ExtractionError, match="schema of transaction_normalized"):
        db_enrichment._table_has_column(extractor, "transaction_normalized", "research")


def test_table_has_column_still_reports_a_missing_column() -> None:
    describe = pd.DataFrame({"column_name": ["award_id", "federal_action_obligation"]})
    extractor: Any = _Extractor(_Conn(describe=describe))

    assert db_enrichment._table_has_column(extractor, "t", "research") is False
    assert db_enrichment._table_has_column(extractor, "t", "AWARD_ID") is True


# --- usaspending_database_enrichment._build_sbir_gov_index -----------------------


def _fake_sbir_gov_client(failing_agency: str, bulk_awards: list[dict] | None = None):
    class _Client:
        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

        def query_all_awards(self, *, agency, year, max_results):
            del year, max_results
            if agency == failing_agency:
                raise RuntimeError("HTTP 503")
            return [{"agency": agency}]

        def load_bulk_awards(self, _path):
            return bulk_awards or []

        @staticmethod
        def build_lookup_index(awards):
            return {"agencies": sorted({a["agency"] for a in awards})}

    return _Client


def test_sbir_gov_index_is_not_built_from_a_partial_api_pull(monkeypatch) -> None:
    monkeypatch.setattr(db_enrichment, "SbirGovClient", _fake_sbir_gov_client("DOE"))
    monkeypatch.setattr(db_enrichment, "_find_sbir_gov_bulk_file", lambda: None)

    index = db_enrichment._build_sbir_gov_index(
        build_asset_context(), agencies=["HHS", "DOE", "ED"]
    )

    # Before the fix this returned an index with HHS and ED only.
    assert index is None


def test_sbir_gov_partial_api_pull_falls_back_to_bulk_file(monkeypatch, tmp_path) -> None:
    bulk = [{"agency": "HHS"}, {"agency": "DOE"}, {"agency": "ED"}, {"agency": "BULK"}]
    monkeypatch.setattr(db_enrichment, "SbirGovClient", _fake_sbir_gov_client("DOE", bulk))
    monkeypatch.setattr(db_enrichment, "_find_sbir_gov_bulk_file", lambda: tmp_path / "a.json")

    index = db_enrichment._build_sbir_gov_index(
        build_asset_context(), agencies=["HHS", "DOE", "ED"]
    )

    assert index == {"agencies": ["BULK", "DOE", "ED", "HHS"]}


# --- usaspending_database_enrichment.sbir_company_usaspending_recipients ---------


def test_recipient_query_failure_fails_the_asset(monkeypatch) -> None:
    class _DumpExtractor:
        def __init__(self, db_path):
            del db_path
            self.import_failed_tables = {}

        def import_postgres_dump(self, _dump, _table):
            return True

        def resolve_physical_table_name(self, table):
            return table

        def connect(self):
            return _Conn(error=RuntimeError("Binder Error: column recipient_uei not found"))

    config = SimpleNamespace(duckdb=SimpleNamespace(database_path=":memory:"))
    monkeypatch.setattr(db_enrichment, "get_config", lambda: config)
    monkeypatch.setattr(
        db_enrichment, "find_latest_usaspending_dump", lambda **_kw: Path("dump.zip")
    )
    monkeypatch.setattr(db_enrichment, "DuckDBUSAspendingExtractor", _DumpExtractor)
    awards = pd.DataFrame({"UEI": ["ABCDEFGHJKLM"], "Duns": ["123456789"]})

    # Before the fix the asset returned an empty frame with row_count 0.
    with pytest.raises(ExtractionError, match="Recipient query failed"):
        db_enrichment.sbir_company_usaspending_recipients(build_asset_context(), awards)


def test_recipient_query_matches_the_real_recipient_lookup_columns(monkeypatch) -> None:
    import duckdb

    from sbir_etl.extractors.usaspending import RECIPIENT_LOOKUP_COLUMNS

    conn = duckdb.connect(":memory:")
    columns_sql = ", ".join(f"{col} VARCHAR" for col in RECIPIENT_LOOKUP_COLUMNS)
    conn.execute(f"CREATE TABLE recipient_lookup ({columns_sql})")
    rows = [
        {"recipient_hash": "h1", "legal_business_name": "Acme", "uei": "ABCDEFGHJKLM"},
        {"recipient_hash": "h2", "legal_business_name": "Beta", "duns": "123456789"},
        {"recipient_hash": "h3", "legal_business_name": "Other", "uei": "ZZZZZZZZZZZZ"},
    ]
    placeholders = ", ".join("?" for _ in RECIPIENT_LOOKUP_COLUMNS)
    for row in rows:
        values = [row.get(col) for col in RECIPIENT_LOOKUP_COLUMNS]
        conn.execute(f"INSERT INTO recipient_lookup VALUES ({placeholders})", values)

    class _RealSchemaExtractor:
        def __init__(self, db_path):
            del db_path
            self.import_failed_tables = {}

        def import_postgres_dump(self, _dump, _table):
            return True

        def resolve_physical_table_name(self, table):
            return table

        def connect(self):
            return conn

    config = SimpleNamespace(duckdb=SimpleNamespace(database_path=":memory:"))
    monkeypatch.setattr(db_enrichment, "get_config", lambda: config)
    monkeypatch.setattr(
        db_enrichment, "find_latest_usaspending_dump", lambda **_kw: Path("dump.zip")
    )
    monkeypatch.setattr(db_enrichment, "DuckDBUSAspendingExtractor", _RealSchemaExtractor)
    awards = pd.DataFrame({"UEI": ["ABCDEFGHJKLM"], "Duns": ["123456789"]})

    output: Any = db_enrichment.sbir_company_usaspending_recipients(build_asset_context(), awards)
    df = output.value.sort_values("recipient_hash").reset_index(drop=True)

    assert df["recipient_hash"].tolist() == ["h1", "h2"]
    assert df["recipient_name"].tolist() == ["Acme", "Beta"]
    assert df.loc[0, "recipient_uei"] == "ABCDEFGHJKLM"
    assert df.loc[1, "recipient_duns"] == "123456789"
    assert df["parent_recipient_hash"].isna().all()
    assert df["business_types_description"].isna().all()


# --- usaspending_iterative_enrichment ---------------------------------------------


def test_unreadable_enriched_awards_file_is_not_treated_as_absent(monkeypatch, tmp_path) -> None:
    corrupt = tmp_path / "sbir_awards.parquet"
    corrupt.write_bytes(b"not a parquet file")
    monkeypatch.setattr(
        "sbir_etl.enrichers.usaspending.requests.enriched_awards_path", lambda: corrupt
    )

    # Before the fix this returned None and the asset reported "no_enriched_data".
    with pytest.raises(ValidationError, match="could not be read"):
        usa_iterative._load_enriched_awards(build_asset_context())


class _FailingMetrics:
    def emit_metrics(self, _source):
        raise OSError("disk full")


class _FakeRunner:
    def __init__(self, **_kwargs):
        pass

    def refresh_records(self, _adapter, requests):
        stats = {
            "total": len(requests),
            "success": len(requests),
            "failed": 0,
            "unchanged": 0,
            "skipped": 0,
            "errors": [],
        }
        return SimpleNamespace(as_dict=lambda: stats)


def test_usaspending_refresh_records_metrics_emit_failure(monkeypatch) -> None:
    monkeypatch.setattr(usa_iterative, "FreshnessStore", lambda: object())
    monkeypatch.setattr(usa_iterative, "CheckpointStore", lambda: object())
    monkeypatch.setattr(usa_iterative, "EnrichmentMetricsCollector", _FailingMetrics)
    monkeypatch.setattr(usa_iterative, "SourceRefreshRunner", _FakeRunner)
    monkeypatch.setattr(usa_iterative, "build_usaspending_adapter", lambda **_kw: object())
    monkeypatch.setattr(usa_iterative, "stale_awards_to_requests", lambda _df: [{"award_id": "A1"}])
    monkeypatch.setattr(usa_iterative, "has_identifier", lambda _request: True)

    output = usa_iterative.usaspending_refresh_batch(
        build_asset_context(),
        pd.DataFrame({"award_id": ["A1"]}),
        config=usa_iterative.EnrichmentRefreshConfig(),
    )

    assert _md(output, "success") == 1
    assert _md(output, "metrics_emit_error") == "disk full"


def test_nih_refresh_records_metrics_emit_failure(monkeypatch) -> None:
    refresh = SimpleNamespace(enabled=True, batch_size=10, checkpoint_interval=10)
    config = SimpleNamespace(enrichment_refresh=SimpleNamespace(nih_reporter=refresh))
    monkeypatch.setattr(nih_assets, "get_config", lambda: config)
    monkeypatch.setattr(nih_assets, "FreshnessStore", lambda: object())
    monkeypatch.setattr(nih_assets, "CheckpointStore", lambda: object())
    monkeypatch.setattr(nih_assets, "EnrichmentMetricsCollector", _FailingMetrics)
    monkeypatch.setattr(nih_assets, "SourceRefreshRunner", _FakeRunner)
    monkeypatch.setattr(nih_assets, "build_nih_reporter_adapter", lambda **_kw: object())
    monkeypatch.setattr(nih_assets, "frame_to_nih_requests", lambda _df: [{"award_id": "A1"}])

    output = nih_assets.nih_reporter_refresh_batch(
        build_asset_context(),
        pd.DataFrame({"award_id": ["A1"]}),
        config=nih_assets.NIHReporterRefreshConfig(),
    )

    assert _md(output, "success") == 1
    assert _md(output, "metrics_emit_error") == "disk full"


# --- usaspending_ingestion.raw_usaspending_recipients -----------------------------


def test_recipients_metadata_names_the_dump_when_parquet_load_fails(monkeypatch, tmp_path) -> None:
    corrupt = tmp_path / "recipient_lookup.parquet"
    corrupt.write_bytes(b"not a parquet file")
    monkeypatch.setattr(
        "sbir_etl.utils.cloud_storage.find_latest_recipient_lookup_parquet",
        lambda: str(corrupt),
    )
    monkeypatch.setattr(usaspending_ingestion, "resolve_data_path", lambda url: Path(url))
    dump_df = pd.DataFrame(
        {
            "legal_business_name": ["Acme"],
            "uei": ["ABCDEFGHJKLM"],
            "duns": ["123456789"],
            "data_source": ["usaspending"],
        }
    )
    monkeypatch.setattr(
        usaspending_ingestion,
        "_import_usaspending_table",
        lambda _ctx, **_kw: Output(value=dump_df, metadata={"dump_import_failed_tables": {}}),
    )

    output = usaspending_ingestion.raw_usaspending_recipients(build_asset_context())

    # Before the fix the metadata said "parquet" because a parquet URL was found.
    assert _md(output, "source") == "dump"
    assert _md(output, "parquet_load_error")


# --- sbir_ingestion.validated_sbir_awards -----------------------------------------


def test_validated_sbir_awards_records_processed_parquet_write_failure(monkeypatch) -> None:
    def _no_data_root():
        raise OSError("data root is not mounted")

    report = SimpleNamespace(
        failing_row_indices=set(),
        issues=[],
        total_records=1,
        passed_records=1,
        failed_records=0,
        pass_rate=1.0,
        passed=True,
    )
    audit = {
        "steps": [],
        "original_count": 1,
        "final_count": 1,
        "total_dropped": 0,
        "total_coerced_fields": 0,
        "retention_rate": 1.0,
    }
    config = SimpleNamespace(
        data_quality=SimpleNamespace(sbir_awards=SimpleNamespace(pass_rate_threshold=0.0))
    )
    monkeypatch.setattr(sbir_ingestion, "get_config", lambda: config)
    monkeypatch.setattr(sbir_ingestion, "_apply_quality_filters", lambda df, _ctx: (df, audit))
    monkeypatch.setattr(sbir_ingestion, "validate_sbir_awards", lambda **_kw: report)
    monkeypatch.setattr("sbir_etl.utils.cloud_storage.get_data_root", _no_data_root)

    output = sbir_ingestion.validated_sbir_awards(
        build_asset_context(), pd.DataFrame({"Award Number": ["A1"]})
    )

    assert "s3_uri" not in output.metadata  # type: ignore[attr-defined]
    assert _md(output, "processed_parquet_status") == "write_failed"
