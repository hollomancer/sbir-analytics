"""USAspending ZIP dump import against a real DuckDB database.

These tests build a small pg_dump-style ZIP (``<oid>.dat.gz`` COPY files), run it
through ``import_postgres_dump`` the way the assets do, and check which DuckDB
object the callers end up querying.
"""

from __future__ import annotations

import gzip
import zipfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import duckdb
import pandas as pd
import pytest
from dagster import build_asset_context
from loguru import logger

from sbir_etl.exceptions import ExtractionError
from sbir_etl.extractors.usaspending import RECIPIENT_LOOKUP_COLUMNS, DuckDBUSAspendingExtractor


pytestmark = pytest.mark.fast

RECIPIENT_OID = 5419


def _recipient_row(**values: str) -> str:
    return "\t".join(values.get(col, "\\N") for col in RECIPIENT_LOOKUP_COLUMNS)


RECIPIENT_COPY_DATA = (
    "\n".join(
        [
            _recipient_row(
                id="1", recipient_hash="h1", legal_business_name="Acme", uei="UEIACME00001"
            ),
            _recipient_row(
                id="2", recipient_hash="h2", legal_business_name="Beta", duns="123456789"
            ),
            _recipient_row(
                id="3", recipient_hash="h3", legal_business_name="Other", uei="UEIOTHER0001"
            ),
        ]
    )
    + "\n"
)


def _write_dump(path: Path, files: dict[int, str]) -> Path:
    with zipfile.ZipFile(path, "w") as zf:
        for oid, data in files.items():
            zf.writestr(f"{oid}.dat.gz", gzip.compress(data.encode()))
    return path


@pytest.fixture
def recipient_dump(tmp_path: Path) -> Path:
    return _write_dump(tmp_path / "usaspending-db.zip", {RECIPIENT_OID: RECIPIENT_COPY_DATA})


def _columns(extractor: DuckDBUSAspendingExtractor, name: str) -> list[str]:
    return extractor.connect().execute(f"DESCRIBE {name}").fetchdf()["column_name"].tolist()


# --- resolve_physical_table_name ---------------------------------------------


def test_resolve_returns_named_view_over_raw_oid_table(recipient_dump, tmp_path) -> None:
    extractor = DuckDBUSAspendingExtractor(str(tmp_path / "usa.duckdb"))
    assert extractor.import_postgres_dump(recipient_dump, "recipient_lookup") is True

    # The import leaves both the raw OID table and the named view.
    assert _columns(extractor, f"recipient_lookup_{RECIPIENT_OID}")[0] == "column00"

    resolved = extractor.resolve_physical_table_name("recipient_lookup")

    assert resolved == "recipient_lookup"
    assert _columns(extractor, resolved) == RECIPIENT_LOOKUP_COLUMNS


def test_resolve_must_not_return_raw_placeholder_column_table(recipient_dump, tmp_path) -> None:
    extractor = DuckDBUSAspendingExtractor(str(tmp_path / "usa.duckdb"))
    extractor.import_postgres_dump(recipient_dump, "recipient_lookup")

    resolved = extractor.resolve_physical_table_name("recipient_lookup")

    # A prefix lookup over duckdb_tables() finds only the raw table, not the view.
    assert resolved != f"recipient_lookup_{RECIPIENT_OID}"
    assert not any(col.startswith("column") for col in _columns(extractor, resolved))


def test_resolve_raises_when_no_named_object_exists(tmp_path) -> None:
    extractor = DuckDBUSAspendingExtractor(str(tmp_path / "usa.duckdb"))
    # Only a raw OID table, as if the view step never ran.
    extractor.connect().execute(f"CREATE TABLE recipient_lookup_{RECIPIENT_OID} (column00 VARCHAR)")

    with pytest.raises(ExtractionError, match="No table or view named 'recipient_lookup'"):
        extractor.resolve_physical_table_name("recipient_lookup")


# --- callers, end to end on the real extractor -------------------------------


def test_recipient_asset_queries_work_on_imported_dump(
    monkeypatch, recipient_dump, tmp_path
) -> None:
    from sbir_analytics.assets import usaspending_database_enrichment as db_enrichment

    config = SimpleNamespace(duckdb=SimpleNamespace(database_path=str(tmp_path / "usa.duckdb")))
    monkeypatch.setattr(db_enrichment, "get_config", lambda: config)
    monkeypatch.setattr(db_enrichment, "find_latest_usaspending_dump", lambda **_kw: recipient_dump)
    awards = pd.DataFrame({"UEI": ["UEIACME00001"], "Duns": ["123456789"]})

    output: Any = db_enrichment.sbir_company_usaspending_recipients(build_asset_context(), awards)
    df = output.value.sort_values("recipient_hash").reset_index(drop=True)

    assert df["recipient_hash"].tolist() == ["h1", "h2"]
    assert df["recipient_name"].tolist() == ["Acme", "Beta"]


def test_ingestion_asset_reads_named_columns_from_imported_dump(
    monkeypatch, recipient_dump, tmp_path
) -> None:
    from sbir_analytics.assets import usaspending_ingestion

    config = SimpleNamespace(duckdb=SimpleNamespace(database_path=str(tmp_path / "usa.duckdb")))
    monkeypatch.setattr(usaspending_ingestion, "get_config", lambda: config)
    monkeypatch.setattr(
        usaspending_ingestion,
        "_resolve_tiered_path",
        lambda *_a, **_kw: (recipient_dump, str(recipient_dump)),
    )

    output: Any = usaspending_ingestion._import_usaspending_table(
        build_asset_context(),
        log_label="recipient_lookup",
        table_name="raw_usaspending_recipients",
    )

    assert {"legal_business_name", "uei", "duns"} <= set(output.value.columns)
    assert len(output.value) == 3


# --- partial COPY import -----------------------------------------------------

UNUSED_OID = 5500


def _late_type_change(row: str, bad_row: str, good_rows: int = 30_000) -> str:
    # DuckDB sniffs the column types from the first rows, so a bad value this
    # far down fails the load with a Conversion Error, not a sniffing error.
    return row * good_rows + bad_row


BAD_RECIPIENT_COPY_DATA = _late_type_change(
    _recipient_row(id="1", recipient_hash="h1") + "\n",
    _recipient_row(id="x", recipient_hash="h2") + "\n",
)
BAD_UNUSED_COPY_DATA = _late_type_change("1\ta\n", "x\ta\n")


def test_needed_table_that_fails_to_load_fails_the_import(tmp_path) -> None:
    dump = _write_dump(
        tmp_path / "usaspending-db.zip",
        {RECIPIENT_OID: BAD_RECIPIENT_COPY_DATA, UNUSED_OID: RECIPIENT_COPY_DATA},
    )
    extractor = DuckDBUSAspendingExtractor(str(tmp_path / "usa.duckdb"))

    # Before the fix this returned False with only a log line.
    with pytest.raises(ExtractionError, match="recipient_lookup_5419") as exc_info:
        extractor.import_postgres_dump(dump, "recipient_lookup")

    assert exc_info.value.details["source_table"] == f"recipient_lookup_{RECIPIENT_OID}"
    assert isinstance(exc_info.value.__cause__, duckdb.ConversionException)


def test_unused_table_that_fails_to_load_is_recorded_not_fatal(tmp_path) -> None:
    dump = _write_dump(
        tmp_path / "usaspending-db.zip",
        {RECIPIENT_OID: RECIPIENT_COPY_DATA, UNUSED_OID: BAD_UNUSED_COPY_DATA},
    )
    extractor = DuckDBUSAspendingExtractor(str(tmp_path / "usa.duckdb"))
    warnings: list[str] = []
    sink_id = logger.add(warnings.append, level="WARNING", format="{message}")
    try:
        assert extractor.import_postgres_dump(dump, "recipient_lookup") is True
    finally:
        logger.remove(sink_id)

    assert list(extractor.import_failed_tables) == [f"recipient_lookup_{UNUSED_OID}"]
    assert "Conversion Error" in extractor.import_failed_tables[f"recipient_lookup_{UNUSED_OID}"]
    assert any("recipient_lookup_5500" in w for w in warnings)
    assert _columns(extractor, "recipient_lookup") == RECIPIENT_LOOKUP_COLUMNS


def test_unused_table_failure_shows_in_asset_metadata(monkeypatch, tmp_path) -> None:
    from sbir_analytics.assets import usaspending_database_enrichment as db_enrichment

    dump = _write_dump(
        tmp_path / "usaspending-db.zip",
        {RECIPIENT_OID: RECIPIENT_COPY_DATA, UNUSED_OID: BAD_UNUSED_COPY_DATA},
    )
    config = SimpleNamespace(duckdb=SimpleNamespace(database_path=str(tmp_path / "usa.duckdb")))
    monkeypatch.setattr(db_enrichment, "get_config", lambda: config)
    monkeypatch.setattr(db_enrichment, "find_latest_usaspending_dump", lambda **_kw: dump)
    awards = pd.DataFrame({"UEI": ["UEIACME00001"], "Duns": ["123456789"]})

    output: Any = db_enrichment.sbir_company_usaspending_recipients(build_asset_context(), awards)

    failed = output.metadata["dump_import_failed_tables"].value
    assert list(failed) == [f"recipient_lookup_{UNUSED_OID}"]


def test_ingestion_keeps_the_import_error_and_its_cause(monkeypatch, tmp_path) -> None:
    from sbir_analytics.assets import usaspending_ingestion

    dump = _write_dump(tmp_path / "usaspending-db.zip", {RECIPIENT_OID: BAD_RECIPIENT_COPY_DATA})
    config = SimpleNamespace(duckdb=SimpleNamespace(database_path=str(tmp_path / "usa.duckdb")))
    monkeypatch.setattr(usaspending_ingestion, "get_config", lambda: config)
    monkeypatch.setattr(
        usaspending_ingestion, "_resolve_tiered_path", lambda *_a, **_kw: (dump, str(dump))
    )

    # Before the fix the asset raised a new, unchained "API fallback not
    # implemented" error and the failed tables were only in a log line.
    with pytest.raises(ExtractionError) as exc_info:
        usaspending_ingestion._import_usaspending_table(
            build_asset_context(),
            log_label="recipient_lookup",
            table_name="raw_usaspending_recipients",
        )

    assert exc_info.value.operation == "import_copy_files"
    assert list(exc_info.value.details["failed_tables"]) == [
        f"raw_usaspending_recipients_{RECIPIENT_OID}"
    ]
    assert isinstance(exc_info.value.__cause__, duckdb.ConversionException)


PLAIN_SQL_DUMP = (
    "--\n-- PostgreSQL database dump\n--\n"
    "CREATE TABLE public.recipient_lookup (id integer, legal_business_name text);\n"
    "COPY public.recipient_lookup (id, legal_business_name) FROM stdin;\n"
    "1\tAcme\n\\.\n"
)


@pytest.mark.parametrize(
    ("filename", "content"),
    [
        ("usaspending-db.sql", PLAIN_SQL_DUMP.encode()),
        # A gzip file that is not a ZIP archive.
        ("usaspending-db.sql.gz", gzip.compress(PLAIN_SQL_DUMP.encode())),
        # No suffix also used to fall through to the plain-SQL path.
        ("usaspending-db", PLAIN_SQL_DUMP.encode()),
    ],
)
def test_non_zip_dump_raises_and_creates_no_table(tmp_path, filename, content) -> None:
    dump = tmp_path / filename
    dump.write_bytes(content)
    db_path = tmp_path / "usa.duckdb"
    extractor = DuckDBUSAspendingExtractor(str(db_path))

    # Before the fix, a plain-SQL file "imported" its own text lines as a
    # one-column table and returned True, and a .gz file returned False.
    with pytest.raises(ExtractionError, match=r"Supported formats: \.zip") as exc_info:
        extractor.import_postgres_dump(dump, "recipient_lookup")
    extractor.close()

    assert exc_info.value.operation == "import_postgres_dump"
    assert exc_info.value.details["supported_formats"] == [".zip"]
    with duckdb.connect(str(db_path)) as conn:
        assert conn.execute("SELECT count(*) FROM duckdb_tables()").fetchone() == (0,)
