"""USAspending data extractor using DuckDB.

This module provides functionality to extract USAspending data from compressed PostgreSQL dumps using DuckDB.
Supports both direct DuckDB postgres_scanner access and pg_restore streaming for removable media workflows.
Reads dumps from local disk.

The dump import reads the archive table of contents (``toc.dat``) with
``pg_restore --list`` to find each table's data member, so ``pg_restore``
must be installed.
"""

import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

import duckdb
import pandas as pd

from ..config.loader import get_config
from ..exceptions import ExtractionError
from ..utils.data.duckdb_client import DuckDBClient
from ..utils.logging_config import log_with_context
from .contract_extractor import ArchiveSchemaError, TocTableEntry, read_toc_table_data

# USAspending recipient_lookup table schema (from Django model)
# https://github.com/fedspendingtransparency/usaspending-api/blob/master/usaspending_api/recipient/models.py
RECIPIENT_LOOKUP_COLUMNS = [
    "id",
    "recipient_hash",
    "legal_business_name",
    "duns",
    "uei",
    "parent_uei",
    "parent_duns",
    "parent_legal_business_name",
    "address_line_1",
    "address_line_2",
    "city",
    "state",
    "zip5",
    "zip4",
    "country_code",
    "congressional_district",
    "business_types_codes",
    "update_date",
    "source",
    "alternate_names",
]

# Dump tables that the named import views are built from. The import finds
# each table's data member through the archive table of contents (toc.dat),
# because pg_dump renumbers the members between dumps.
RECIPIENT_LOOKUP_TABLE = "recipient_lookup"
TRANSACTION_NORMALIZED_TABLE = "transaction_normalized"


class DuckDBUSAspendingExtractor:
    """Extractor for USAspending data using DuckDB."""

    def __init__(self, db_path: str | None = None):
        """Initialize the extractor.

        Args:
            db_path: Path to DuckDB database file
        """
        self.db_path = db_path or ":memory:"
        self.connection: duckdb.DuckDBPyConnection | None = None
        # COPY tables of the last ZIP import that failed to load but that the
        # named view does not read. Maps raw table name to the error text.
        self.import_failed_tables: dict[str, str] = {}

    def connect(self) -> duckdb.DuckDBPyConnection:
        """Get or create database connection."""
        if self.connection is None:
            self.connection = duckdb.connect(self.db_path)
            # Enable object cache for better performance
            if self.connection is not None:  # type: ignore[redundant-expr]
                self.connection.execute("SET enable_object_cache=true")  # type: ignore[union-attr]
        assert self.connection is not None  # type: ignore[assert]
        return self.connection

    def close(self) -> None:
        """Close database connection."""
        if self.connection:
            self.connection.close()  # type: ignore[unreachable]
            self.connection = None

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type: Any, exc_val, exc_tb: Any) -> None:
        """Context manager exit."""
        self.close()

    def import_postgres_dump(
        self, dump_file: Path | str, table_name: str = "usaspending_awards"
    ) -> bool:
        """Import PostgreSQL dump file into DuckDB.

        Args:
            dump_file: Path to the USAspending pg_dump ZIP archive (.zip)
            table_name: Name for the imported table

        Returns:
            True if import successful, False otherwise

        Raises:
            ExtractionError: If ``dump_file`` is not a ``.zip`` archive. Only
                the ZIP archive of COPY files is supported.
            ExtractionError: If the archive has no readable ``toc.dat``, or
                the table of contents does not list the table that the
                ``table_name`` view is built from.
            ExtractionError: If the COPY file that the ``table_name`` view is
                built from fails to load, or its columns cannot be named.
                Other COPY files that fail are listed in
                ``self.import_failed_tables`` and logged at WARNING.
        """
        with log_with_context(stage="extract", run_id="usaspending_import") as logger:
            dump_file = Path(dump_file)

            logger.info(f"Importing PostgreSQL dump from {dump_file}")

            if not dump_file.exists():
                raise FileNotFoundError(f"PostgreSQL dump file not found: {dump_file}")

            if dump_file.suffix.lower() != ".zip":
                raise ExtractionError(
                    f"Unsupported USAspending dump format {dump_file.suffix!r} for "
                    f"{dump_file}. Supported formats: .zip (pg_dump archive of COPY files).",
                    component="extractors.usaspending",
                    operation="import_postgres_dump",
                    details={"dump_file": str(dump_file), "supported_formats": [".zip"]},
                )

            self.connect()
            DuckDBClient.escape_identifier(table_name)
            self.import_failed_tables = {}

            try:
                return self._import_zipped_dump(dump_file, table_name)

            except ExtractionError:
                raise
            except Exception as e:
                logger.error(f"Failed to import PostgreSQL dump: {e}")
                return False

    def _import_zipped_dump(self, dump_file: Path, table_name: str) -> bool:
        """Import zipped PostgreSQL dump using COPY file extraction."""
        with log_with_context(stage="extract", run_id="usaspending_import") as logger:
            logger.info("Extracting COPY files from ZIP archive")

            return self._import_copy_files(dump_file, table_name)

    @staticmethod
    def _read_toc_entries(dump_file: Path) -> list[TocTableEntry]:
        """Return the ``TABLE DATA`` entries of the ``toc.dat`` inside ``dump_file``."""
        try:
            with zipfile.ZipFile(dump_file) as archive:
                toc_members = [
                    name for name in archive.namelist() if PurePosixPath(name).name == "toc.dat"
                ]
                if len(toc_members) != 1:
                    raise ExtractionError(
                        f"USAspending dump {dump_file} must contain exactly one toc.dat; "
                        f"found {len(toc_members)}. Tables cannot be identified without it.",
                        component="extractors.usaspending",
                        operation="read_toc",
                        details={"dump_file": str(dump_file), "toc_members": toc_members},
                    )
                with tempfile.TemporaryDirectory(prefix="usaspending-toc-") as temp_name:
                    archive_dir = Path(temp_name)
                    with (
                        archive.open(toc_members[0]) as source,
                        open(archive_dir / "toc.dat", "wb") as target,
                    ):
                        shutil.copyfileobj(source, target)
                    return read_toc_table_data(archive_dir)
        except (zipfile.BadZipFile, ArchiveSchemaError) as e:
            raise ExtractionError(
                f"Could not read the table of contents of USAspending dump {dump_file}: {e}",
                component="extractors.usaspending",
                operation="read_toc",
                details={"dump_file": str(dump_file)},
                cause=e,
            ) from e

    @staticmethod
    def _view_source_entry(table_name: str, entries: list[TocTableEntry]) -> TocTableEntry:
        """Return the TOC entry of the dump table that the ``table_name`` view reads.

        A ``table_name`` that contains "recipient" reads ``recipient_lookup``;
        any other name reads ``transaction_normalized``.
        """
        wanted = (
            RECIPIENT_LOOKUP_TABLE
            if "recipient" in table_name.lower()
            else TRANSACTION_NORMALIZED_TABLE
        )
        matches = [entry for entry in entries if entry.table == wanted]
        if len(matches) == 1:
            return matches[0]
        available = sorted(f"{entry.schema}.{entry.table}" for entry in entries)
        problem = "does not list" if not matches else f"lists {len(matches)} copies of"
        raise ExtractionError(
            f"The dump table of contents {problem} table {wanted!r}, which the "
            f"{table_name} view reads. Tables in the TOC: {available}",
            component="extractors.usaspending",
            operation="import_copy_files",
            details={
                "view": table_name,
                "required_table": wanted,
                "matching_entries": [f"{e.schema}.{e.table} ({e.dump_id})" for e in matches],
                "toc_tables": available,
            },
        )

    def _import_copy_files(self, dump_file: Path, table_name: str) -> bool:
        """Import PostgreSQL COPY files from ZIP archive."""
        with log_with_context(stage="extract", run_id="usaspending_import") as logger:
            conn = self.connect()

            try:
                source_entry = self._view_source_entry(
                    table_name, self._read_toc_entries(dump_file)
                )
                source_oid = int(source_entry.dump_id)

                # List files in ZIP to find .dat.gz files
                cmd = ["unzip", "-l", str(dump_file)]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

                if result.returncode != 0:
                    logger.error(f"unzip -l failed: {result.stderr}")
                    return False

                # Parse for .dat.gz files
                copy_files = []
                for line in result.stdout.split("\n"):
                    if ".dat.gz" in line:
                        parts = line.split()
                        if len(parts) >= 4:
                            file_name = parts[-1]
                            file_oid = int(file_name.split("/")[-1].split(".")[0])
                            copy_files.append({"oid": file_oid, "filename": file_name})

                if not copy_files:
                    logger.warning("No .dat.gz files found in ZIP")
                    return False

                logger.info(f"Found {len(copy_files)} COPY files in ZIP")
                if source_oid not in {int(str(f["oid"])) for f in copy_files}:
                    raise ExtractionError(
                        f"The dump table of contents maps {source_entry.schema}."
                        f"{source_entry.table} to {source_oid}.dat.gz, but the ZIP has no "
                        "such member",
                        component="extractors.usaspending",
                        operation="import_copy_files",
                        details={
                            "dump_file": str(dump_file),
                            "required_table": source_entry.table,
                            "dump_id": source_entry.dump_id,
                        },
                    )
                logger.info(
                    f"TOC maps {source_entry.schema}.{source_entry.table} to "
                    f"{source_oid}.dat.gz; the {table_name} view reads it"
                )
                source_table_name = f"{table_name}_{source_oid}"
                failed_tables: dict[str, str] = {}
                source_error: Exception | None = None

                # Create tables for each COPY file
                for file_info in copy_files:
                    oid: int = int(file_info["oid"])  # type: ignore[assignment, call-overload]
                    filename: str = str(file_info["filename"])  # type: ignore[assignment]
                    table_name_for_file = f"{table_name}_{oid}"
                    table_identifier = DuckDBClient.escape_identifier(table_name_for_file)

                    logger.info(f"Importing {filename} as {table_name_for_file}")

                    # Extract and decompress the file
                    with tempfile.TemporaryDirectory() as temp_dir:
                        temp_file = Path(temp_dir) / f"{oid}.dat"

                        # Extract specific file
                        extract_cmd = ["unzip", "-p", str(dump_file), filename]
                        with open(temp_file, "wb") as f:
                            extract_result: subprocess.CompletedProcess[bytes] = subprocess.run(
                                extract_cmd, stdout=f, stderr=subprocess.PIPE
                            )

                        if extract_result.returncode != 0:
                            stderr_bytes = extract_result.stderr  # type: ignore[assignment]
                            stderr_str = stderr_bytes.decode() if stderr_bytes else "Unknown error"
                            logger.error(f"Failed to extract {filename}: {stderr_str}")
                            failed_tables[table_name_for_file] = f"extract failed: {stderr_str}"
                            continue

                        # Decompress if gzipped
                        decompressed_file = temp_file
                        try:
                            import gzip

                            with (
                                open(temp_file, "rb") as f_in,
                                open(decompressed_file.with_suffix(".decompressed"), "wb") as f_out,
                            ):
                                f_out.write(gzip.decompress(f_in.read()))
                            decompressed_file = decompressed_file.with_suffix(".decompressed")
                        except gzip.BadGzipFile:
                            pass  # Not gzipped

                        # Load into DuckDB
                        try:
                            file_literal = DuckDBClient.escape_literal(str(decompressed_file))
                            create_query = f"""
                            CREATE TABLE IF NOT EXISTS {table_identifier} AS
                            SELECT * FROM read_csv_auto({file_literal},
                                delim='\t',
                                nullstr='\\N',
                                header=false
                            )
                            """  # nosec B608
                            conn.execute(create_query)
                            logger.info(f"Created table {table_name_for_file}")
                        except Exception as e:
                            logger.error(f"Failed to create table {table_name_for_file}: {e}")
                            failed_tables[table_name_for_file] = str(e)
                            if table_name_for_file == source_table_name:
                                source_error = e

                if source_table_name in failed_tables:
                    raise ExtractionError(
                        f"COPY file for {source_table_name}, which the {table_name} view "
                        f"reads, failed to load: {failed_tables[source_table_name]}",
                        component="extractors.usaspending",
                        operation="import_copy_files",
                        details={
                            "dump_file": str(dump_file),
                            "source_table": source_table_name,
                            "failed_tables": failed_tables,
                        },
                        cause=source_error,
                    ) from source_error
                if failed_tables:
                    logger.warning(
                        f"{len(failed_tables)} of {len(copy_files)} COPY files failed to load; "
                        f"the {table_name} view does not read them: {sorted(failed_tables)}"
                    )
                self.import_failed_tables = failed_tables

                # Create the named view over the source table
                base_table_identifier = DuckDBClient.escape_identifier(table_name)
                source_table = DuckDBClient.escape_identifier(source_table_name)

                # recipient_lookup: apply column names from the schema
                if source_entry.table == RECIPIENT_LOOKUP_TABLE:
                    # Apply column names from schema (DuckDB uses column00, column01, etc.)
                    col_aliases = ", ".join(
                        f"column{i:02d} AS {col}" for i, col in enumerate(RECIPIENT_LOOKUP_COLUMNS)
                    )
                    view_query = f"CREATE OR REPLACE VIEW {base_table_identifier} AS SELECT {col_aliases} FROM {source_table}"  # nosec B608
                    try:
                        conn.execute(view_query)
                    except duckdb.Error as e:
                        raise ExtractionError(
                            f"Could not apply the {len(RECIPIENT_LOOKUP_COLUMNS)} "
                            f"recipient_lookup column names to {source_table_name}: {e}",
                            component="extractors.usaspending",
                            operation="import_copy_files",
                            details={
                                "dump_file": str(dump_file),
                                "source_table": source_table_name,
                                "expected_columns": RECIPIENT_LOOKUP_COLUMNS,
                            },
                            cause=e,
                        ) from e
                    logger.info(f"Created view {table_name} with schema from {source_table_name}")

                # transaction_normalized
                else:
                    view_query = f"CREATE OR REPLACE VIEW {base_table_identifier} AS SELECT * FROM {source_table}"  # nosec B608
                    conn.execute(view_query)
                    logger.info(f"Created view {table_name} from {source_table_name}")

                return True

            except ExtractionError:
                raise
            except Exception as e:
                logger.error(f"Failed to import COPY files: {e}")
                return False

    def query_awards(
        self,
        table_name: str = "usaspending_awards",
        limit: int | None = None,
        filters: dict | None = None,
    ) -> pd.DataFrame:
        """Query awards data from imported table.

        Args:
            table_name: Name of the imported table
            limit: Maximum number of rows to return
            filters: Dictionary of column filters

        Returns:
            DataFrame containing query results
        """
        with log_with_context(stage="extract", run_id="usaspending_query") as logger:
            conn = self.connect()

            # Build query
            query = f"SELECT * FROM {table_name}"

            # Add filters
            where_clauses = []
            if filters:
                for column, value in filters.items():
                    if isinstance(value, str):
                        where_clauses.append(f"{column} = '{value}'")
                    else:
                        where_clauses.append(f"{column} = {value}")

            if where_clauses:
                query += " WHERE " + " AND ".join(where_clauses)

            # Add limit
            if limit:
                query += f" LIMIT {limit}"

            logger.info(f"Executing query: {query}")

            try:
                result = conn.execute(query).fetchdf()
                logger.info(f"Query returned {len(result)} rows")
                return result

            except Exception as e:
                logger.error(f"Query failed: {e}")
                raise

    def extract_ot_awards(
        self,
        table_name: str = "usaspending_awards",
        limit: int | None = None,
        ot_only: bool = True,
    ) -> tuple[pd.DataFrame, dict[str, Any]]:
        """Query OT-relevant award fields for consortium verification tiering.

        Surfaces the fields the tiering module needs — OT indicator, PIID (for
        the 9th-position rule), recipient UEI, the DoD ``Consortia`` flag and
        ``Primary Consortia Member UEI`` where present, base→order parent
        linkage, and obligation — and tags each record with whether it looks like
        an Other Transaction instrument.

        Returns:
            ``(dataframe, metadata)`` where metadata records the DoD FPDS
            reporting-lag caveat for downstream provenance.
        """
        from ..ot_consortium.usaspending_ot import (
            FPDS_REPORTING_LAG_DAYS,
            build_ot_awards,
            is_ot_record,
        )

        df = self.query_awards(table_name=table_name, limit=limit)
        if not df.empty:
            records: list[dict[str, Any]] = df.to_dict("records")  # type: ignore[assignment]
            df["is_ot"] = [is_ot_record(r) for r in records]
            if ot_only:
                df = df[df["is_ot"]].reset_index(drop=True)

        metadata = {
            "table_name": table_name,
            "ot_record_count": int(len(df)),
            "fpds_reporting_lag_days": FPDS_REPORTING_LAG_DAYS,
            "fpds_lag_note": (
                "DoD OT actions post to FPDS/USAspending with an ~90-day lag; recent fiscal years "
                "undercount and the Consortia / Primary Consortia Member UEI fields are sparser."
            ),
        }
        # ot_awards is the parsed, tier-ready projection; callers may ignore the
        # raw frame and use these directly.
        metadata["ot_awards"] = build_ot_awards(df, ot_only=ot_only) if not df.empty else []
        return df, metadata

    def get_table_info(self, table_name: str = "usaspending_awards") -> dict:
        """Get information about the imported table.

        Args:
            table_name: Name of the table

        Returns:
            Dictionary with table information
        """
        conn = self.connect()

        try:
            # Get column information
            columns_query = f"DESCRIBE {table_name}"
            columns_df = conn.execute(columns_query).fetchdf()

            # Get row count (may be slow for large tables on removable media)
            count_query = f"SELECT COUNT(*) FROM {table_name}"
            count_result = conn.execute(count_query).fetchone()
            row_count = count_result[0] if count_result else 0

            return {
                "table_name": table_name,
                "row_count": row_count,
                "columns": columns_df.to_dict("records") if not columns_df.empty else [],
            }

        except Exception as e:
            return {"table_name": table_name, "error": str(e)}

    def resolve_physical_table_name(self, base_name: str) -> str:
        """Return the queryable DuckDB object for ``base_name`` after an import.

        A ZIP import loads each COPY file into a raw ``<base_name>_<oid>`` table
        with placeholder columns (``column00``...), then creates a view named
        ``base_name`` over it (with ``RECIPIENT_LOOKUP_COLUMNS`` names for
        recipient tables). Other import paths create a table named ``base_name``.
        Callers must query that named object, never the raw OID table, so this
        returns ``base_name`` once it exists as a table or view.

        Raises:
            ExtractionError: If no table or view named ``base_name`` exists.
        """
        conn = self.connect()
        row = conn.execute(
            "SELECT table_type FROM information_schema.tables WHERE table_name = ?",
            [base_name],
        ).fetchone()
        if row is None:
            raise ExtractionError(
                f"No table or view named {base_name!r} after USAspending import",
                component="extractors.usaspending",
                operation="resolve_physical_table_name",
                details={"table_name": base_name, "db_path": self.db_path},
            )
        return base_name

    def list_dump_tables(self, dump_file: Path) -> list:
        """List all tables in a PostgreSQL dump without importing.

        Args:
            dump_file: Path to the dump file

        Returns:
            List of table names
        """
        with log_with_context(stage="extract", run_id="usaspending_list_tables") as logger:
            logger.info(f"Listing tables in dump: {dump_file}")

            try:
                # Use pg_restore --list to get table information
                cmd = ["pg_restore", "--list", str(dump_file)]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

                if result.returncode != 0:
                    logger.error(f"pg_restore --list failed: {result.stderr}")
                    return []

                # Parse output to extract table names
                tables = []
                for line in result.stdout.split("\n"):
                    line = line.strip()
                    if line and not line.startswith(";"):
                        parts = line.split()
                        if len(parts) >= 2 and parts[0] in ["TABLE", "TABLE DATA"]:
                            table_name = parts[-1]
                            if table_name not in tables:
                                tables.append(table_name)

                logger.info(f"Found {len(tables)} tables in dump")
                return tables

            except subprocess.TimeoutExpired:
                logger.error("pg_restore --list timed out")
                return []
            except FileNotFoundError:
                logger.error("pg_restore command not found")
                return []

    def sample_table_from_dump(
        self, dump_file: Path, table_name: str, limit: int = 10
    ) -> pd.DataFrame:
        """Sample rows from a specific table in the dump.

        Args:
            dump_file: Path to the dump file
            table_name: Name of the table to sample
            limit: Number of rows to sample

        Returns:
            DataFrame with sample data
        """
        with log_with_context(stage="extract", run_id="usaspending_sample") as logger:
            logger.info(f"Sampling {limit} rows from {table_name} in {dump_file}")

            conn = self.connect()

            try:
                # Try postgres_scanner first
                query = f"SELECT * FROM postgres_scan('{dump_file}', '{table_name}') LIMIT {limit}"
                df = conn.execute(query).fetchdf()
                logger.info(f"Sampled {len(df)} rows using postgres_scanner")
                return df

            except Exception as e:
                logger.warning(f"postgres_scanner failed: {e}")
                logger.info("Falling back to pg_restore extraction for sampling")

                # Fallback: extract and sample
                with tempfile.TemporaryDirectory() as temp_dir:
                    temp_dump = Path(temp_dir) / "dump.sql"

                    # Extract dump
                    cmd = ["pg_restore", "-f", str(temp_dump), str(dump_file)]
                    result = subprocess.run(cmd, capture_output=True, text=True)

                    if result.returncode == 0:
                        # Try to sample from extracted dump
                        try:
                            # This is simplified - real implementation would need proper SQL parsing
                            logger.warning("Extracted dump sampling not fully implemented")
                            return pd.DataFrame()
                        except Exception:
                            pass

                return pd.DataFrame()


def extract_usaspending_from_config(
    data_dir: Path | None = None,
    dump_filename: str = "usaspending-db_20251006.zip",
    config=None,
) -> DuckDBUSAspendingExtractor:
    """Create USAspending extractor using configuration settings.

    Args:
        data_dir: Directory containing data files (uses config if None)
        dump_filename: Name of the USAspending dump file

    Returns:
        Configured DuckDBUSAspendingExtractor instance

    Raises:
        ExtractionError: If a dump file is found and its import fails or
            returns False. When no dump file is found, nothing is imported.
    """
    config = config or get_config()

    if data_dir is None:
        data_dir = Path("data/raw")

    db_path = config.duckdb.database_path
    extractor = DuckDBUSAspendingExtractor(db_path)

    # Import dump if it exists - check multiple locations:
    # 1. Specified data_dir
    dump_file = data_dir / dump_filename
    if not dump_file.exists():
        # 2. Try configured path (supports environment variable overrides).
        # Only the path lookup is optional; import errors propagate.
        try:
            configured_dump = config.paths.resolve_path("usaspending_dump_file")
        except (AttributeError, TypeError, ValueError) as e:
            with log_with_context(stage="extract", run_id="usaspending_config") as logger:
                logger.debug(f"Configured dump path not available: {e}")
        else:
            if configured_dump.exists():
                with log_with_context(stage="extract", run_id="usaspending_config") as logger:
                    logger.info(f"Using dump from configured path: {configured_dump}")
                dump_file = configured_dump

    if dump_file.exists():
        table_name = config.extraction.usaspending.get("table_name", "usaspending_awards")
        if not extractor.import_postgres_dump(dump_file, table_name):
            raise ExtractionError(
                f"USAspending dump import from {dump_file} failed",
                component="extractors.usaspending",
                operation="extract_usaspending_from_config",
                details={"dump_file": str(dump_file), "table_name": table_name},
            )

    return extractor
