"""USAspending ZIP dump import against a real DuckDB database.

These tests build a small pg_dump directory-format ZIP (``toc.dat`` plus
``<oid>.dat.gz`` COPY files), run it through ``import_postgres_dump`` the way
the assets do, and check which DuckDB object the callers end up querying.
"""

from __future__ import annotations

import gzip
import shutil
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
from sbir_etl.extractors import contract_extractor
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


def _toc_listing(toc: dict[int, str]) -> str:
    """Render ``pg_restore --list`` TABLE DATA lines for ``{dump_id: "schema.table"}``."""
    lines = []
    for dump_id, relation in toc.items():
        schema, table = relation.split(".")
        lines.append(f"{dump_id}; 0 16385 TABLE DATA {schema} {table} postgres")
    return "\n".join(lines) + "\n"


def _write_dump(path: Path, files: dict[int, str], toc: dict[int, str] | None = None) -> Path:
    """Write a directory-format dump ZIP: ``toc.dat`` plus ``<id>.dat.gz`` members.

    ``toc`` maps dump IDs to ``schema.table``. By default ``RECIPIENT_OID`` is
    ``rpt.recipient_lookup`` and every other ID is an unrelated table. The
    ``toc.dat`` here holds the ``pg_restore --list`` text that the
    ``fake_pg_restore`` fixture returns for it.
    """
    if toc is None:
        toc = {
            oid: "rpt.recipient_lookup" if oid == RECIPIENT_OID else f"public.unrelated_{oid}"
            for oid in files
        }
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("toc.dat", _toc_listing(toc))
        for oid, data in files.items():
            zf.writestr(f"{oid}.dat.gz", gzip.compress(data.encode()))
    return path


_REAL_RUN_PG_RESTORE = contract_extractor.run_pg_restore


@pytest.fixture(autouse=True)
def fake_pg_restore(monkeypatch):
    """Stand in for ``pg_restore --list``, as the contract extractor tests do.

    A fixture ``toc.dat`` holds its own listing text, so the fake echoes it.
    A real pg_dump ``toc.dat`` (starts with ``PGDMP``) goes to the real binary.
    """

    def run(dump_dir: Path, *arguments: str) -> str:
        toc_bytes = (dump_dir / "toc.dat").read_bytes()
        if toc_bytes.startswith(b"PGDMP"):
            return _REAL_RUN_PG_RESTORE(dump_dir, *arguments)
        assert arguments == ("--list",)
        return toc_bytes.decode()

    monkeypatch.setattr(contract_extractor, "run_pg_restore", run)


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


# --- table selection from the archive table of contents (#798) ---------------

TRANSACTION_COPY_DATA = "100\tTX-A\n101\tTX-B\n"
UNRELATED_COPY_DATA = "9\tnot-a-recipient\n"


def test_renumbered_dump_ids_still_resolve_tables_by_name(tmp_path) -> None:
    # A later dump renumbers its members. IDs 5419 and 5420 now belong to
    # unrelated tables; the TOC says where recipient_lookup and
    # transaction_normalized went.
    dump = _write_dump(
        tmp_path / "usaspending-db.zip",
        {
            5419: UNRELATED_COPY_DATA,
            5420: UNRELATED_COPY_DATA,
            7001: RECIPIENT_COPY_DATA,
            7002: TRANSACTION_COPY_DATA,
        },
        toc={
            5419: "public.unrelated_a",
            5420: "public.unrelated_b",
            7001: "rpt.recipient_lookup",
            7002: "int.transaction_normalized",
        },
    )
    extractor = DuckDBUSAspendingExtractor(str(tmp_path / "usa.duckdb"))

    assert extractor.import_postgres_dump(dump, "recipient_lookup") is True
    recipients = extractor.query_awards("recipient_lookup")
    assert sorted(recipients["legal_business_name"]) == ["Acme", "Beta", "Other"]

    assert extractor.import_postgres_dump(dump, "usaspending_awards") is True
    transactions = extractor.query_awards("usaspending_awards")
    assert sorted(transactions["column1"]) == ["TX-A", "TX-B"]


def test_must_not_build_view_from_unrelated_table_at_ids_5419_5420(tmp_path) -> None:
    # The old code took 5419 as recipient_lookup and 5420 as
    # transaction_normalized without reading the TOC.
    dump = _write_dump(
        tmp_path / "usaspending-db.zip",
        {5419: RECIPIENT_COPY_DATA, 5420: TRANSACTION_COPY_DATA},
        toc={5419: "public.award_search", 5420: "public.subaward_search"},
    )
    db_path = tmp_path / "usa.duckdb"
    extractor = DuckDBUSAspendingExtractor(str(db_path))

    with pytest.raises(ExtractionError, match="does not list table 'recipient_lookup'") as exc:
        extractor.import_postgres_dump(dump, "recipient_lookup")
    assert exc.value.details["toc_tables"] == ["public.award_search", "public.subaward_search"]
    assert "public.award_search" in str(exc.value)

    with pytest.raises(ExtractionError, match="does not list table 'transaction_normalized'"):
        extractor.import_postgres_dump(dump, "usaspending_awards")
    extractor.close()

    with duckdb.connect(str(db_path)) as conn:
        views = conn.execute("SELECT count(*) FROM duckdb_views() WHERE NOT internal").fetchone()
        assert views == (0,)


def test_must_not_fall_back_to_transaction_table_for_recipient_request(tmp_path) -> None:
    # The old code fell back to 5420 (or the first COPY file) when a recipient
    # view could not find 5419.
    dump = _write_dump(
        tmp_path / "usaspending-db.zip",
        {7002: TRANSACTION_COPY_DATA},
        toc={7002: "int.transaction_normalized"},
    )
    extractor = DuckDBUSAspendingExtractor(str(tmp_path / "usa.duckdb"))

    with pytest.raises(ExtractionError, match="does not list table 'recipient_lookup'"):
        extractor.import_postgres_dump(dump, "raw_usaspending_recipients")


def test_table_listed_twice_in_toc_raises(tmp_path) -> None:
    dump = _write_dump(
        tmp_path / "usaspending-db.zip",
        {7001: RECIPIENT_COPY_DATA, 7003: RECIPIENT_COPY_DATA},
        toc={7001: "rpt.recipient_lookup", 7003: "temp.recipient_lookup"},
    )
    extractor = DuckDBUSAspendingExtractor(str(tmp_path / "usa.duckdb"))

    with pytest.raises(ExtractionError, match="lists 2 copies of table 'recipient_lookup'"):
        extractor.import_postgres_dump(dump, "recipient_lookup")


def test_toc_entry_without_zip_member_raises(tmp_path) -> None:
    dump = _write_dump(
        tmp_path / "usaspending-db.zip",
        {5500: UNRELATED_COPY_DATA},
        toc={5500: "public.other", 7001: "rpt.recipient_lookup"},
    )
    extractor = DuckDBUSAspendingExtractor(str(tmp_path / "usa.duckdb"))

    with pytest.raises(ExtractionError, match=r"7001\.dat\.gz, but the ZIP has no such member"):
        extractor.import_postgres_dump(dump, "recipient_lookup")


def test_dump_without_toc_raises(tmp_path) -> None:
    dump = tmp_path / "usaspending-db.zip"
    with zipfile.ZipFile(dump, "w") as zf:
        zf.writestr(f"{RECIPIENT_OID}.dat.gz", gzip.compress(RECIPIENT_COPY_DATA.encode()))
    extractor = DuckDBUSAspendingExtractor(str(tmp_path / "usa.duckdb"))

    with pytest.raises(ExtractionError, match="exactly one toc.dat; found 0") as exc:
        extractor.import_postgres_dump(dump, "recipient_lookup")
    assert exc.value.operation == "read_toc"


def test_unreadable_toc_raises_and_does_not_fall_back_to_ids(tmp_path, monkeypatch) -> None:
    dump = _write_dump(tmp_path / "usaspending-db.zip", {RECIPIENT_OID: RECIPIENT_COPY_DATA})
    # Use the real reader with no pg_restore on PATH: the TOC cannot be read.
    monkeypatch.setattr(contract_extractor, "run_pg_restore", _REAL_RUN_PG_RESTORE)
    monkeypatch.setattr(contract_extractor.shutil, "which", lambda _name: None)
    extractor = DuckDBUSAspendingExtractor(str(tmp_path / "usa.duckdb"))

    with pytest.raises(ExtractionError, match="pg_restore is required") as exc:
        extractor.import_postgres_dump(dump, "recipient_lookup")
    assert isinstance(exc.value.__cause__, contract_extractor.ArchiveSchemaError)


def test_recipient_column_mapping_failure_raises(tmp_path) -> None:
    # Before the fix a column-count mismatch logged a warning and exposed the
    # raw column00, column01 names under the recipient_lookup view.
    dump = _write_dump(tmp_path / "usaspending-db.zip", {RECIPIENT_OID: "1\tAcme\n2\tBeta\n"})
    extractor = DuckDBUSAspendingExtractor(str(tmp_path / "usa.duckdb"))

    with pytest.raises(ExtractionError, match="recipient_lookup column names") as exc:
        extractor.import_postgres_dump(dump, "recipient_lookup")
    assert isinstance(exc.value.__cause__, duckdb.Error)


REAL_DUMP_DIR = Path(__file__).parents[2] / "fixtures" / "extractors" / "usaspending_pg_dump"


@pytest.mark.skipif(shutil.which("pg_restore") is None, reason="pg_restore is not installed")
def test_real_pg_dump_toc_resolves_renumbered_member(tmp_path) -> None:
    # The fixture is a real `pg_dump -Fd` archive (PostgreSQL 16) of three small
    # tables: public.other (3398), rpt.recipient_lookup (3399) and
    # public.transaction_normalized (3400).
    dump = tmp_path / "usaspending-db_20990101.zip"
    with zipfile.ZipFile(dump, "w") as zf:
        for member in sorted(REAL_DUMP_DIR.iterdir()):
            zf.write(member, f"usaspending-db/{member.name}")
    extractor = DuckDBUSAspendingExtractor(str(tmp_path / "usa.duckdb"))

    entries = extractor._read_toc_entries(dump)
    assert {(e.dump_id, e.schema, e.table) for e in entries} == {
        ("3398", "public", "other"),
        ("3399", "rpt", "recipient_lookup"),
        ("3400", "public", "transaction_normalized"),
    }
    assert extractor._view_source_entry("usaspending_awards", entries).dump_id == "3400"
    assert extractor._view_source_entry("recipient_lookup", entries).dump_id == "3399"
    # The full import is not run here: real data members end with the COPY
    # terminator line, which read_csv_auto cannot sniff in a file this small.
