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

import pandas as pd
import pytest
from dagster import build_asset_context

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

# DuckDB's CSV sniffer cannot find a dialect for this, so the table load fails.
BAD_COPY_DATA = 'a\tb\n1\n1\t2\t3\t4\t5\n"x\ty\n'


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


def test_copy_file_that_fails_to_load_fails_the_import(tmp_path) -> None:
    dump = _write_dump(
        tmp_path / "usaspending-db.zip",
        {RECIPIENT_OID: RECIPIENT_COPY_DATA, 5500: BAD_COPY_DATA},
    )
    extractor = DuckDBUSAspendingExtractor(str(tmp_path / "usa.duckdb"))

    # Before the fix the bad table was only logged and the import returned True.
    with pytest.raises(ExtractionError, match="1 of 2 COPY files failed to load") as exc_info:
        extractor.import_postgres_dump(dump, "recipient_lookup")

    assert list(exc_info.value.details["failed_tables"]) == ["recipient_lookup_5500"]
