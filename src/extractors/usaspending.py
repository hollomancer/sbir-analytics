"""USAspending data extractor using DuckDB.

This module provides functionality to extract USAspending data from compressed PostgreSQL dumps using DuckDB.
Supports both direct DuckDB postgres_scanner access and pg_restore streaming for removable media workflows.
"""

import subprocess
import tempfile
from pathlib import Path

import duckdb
import pandas as pd

from ..config.loader import get_config
from ..utils import log_with_context


class DuckDBUSAspendingExtractor:
    """Extractor for USAspending data using DuckDB."""

    def __init__(self, db_path: str | None = None):
        """Initialize the extractor.

        Args:
            db_path: Path to DuckDB database file
        """
        self.db_path = db_path or ":memory:"
        self.connection = None

    @staticmethod
    def _escape_identifier(identifier: str) -> str:
        try:
            return duckdb.escape_identifier(identifier)  # type: ignore[attr-defined]
        except AttributeError:
            double_quoted = identifier.replace('"', '""')
            return f'"{double_quoted}"'

    @staticmethod
    def _escape_literal(value: str) -> str:
        try:
            return duckdb.escape_string_literal(value)  # type: ignore[attr-defined]
        except AttributeError:
            escaped = value.replace("\\", "\\\\").replace("'", "''")
            return "'" + escaped + "'"

    def connect(self) -> duckdb.DuckDBPyConnection:
        """Get or create database connection."""
        if self.connection is None:
            self.connection = duckdb.connect(self.db_path)
            # Enable object cache for better performance
            self.connection.execute("SET enable_object_cache=true")
        return self.connection

    def close(self) -> None:
        """Close database connection."""
        if self.connection:
            self.connection.close()
            self.connection = None

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type: Any, exc_val, exc_tb: Any) -> None:
        """Context manager exit."""
        self.close()

    def import_postgres_dump(self, dump_file: Path, table_name: str = "usaspending_awards") -> bool:
        """Import PostgreSQL dump file into DuckDB.

        Args:
            dump_file: Path to the PostgreSQL dump file (supports .zip, .gz, .sql)
            table_name: Name for the imported table

        Returns:
            True if import successful, False otherwise
        """
        with log_with_context(stage="extract", run_id="usaspending_import") as logger:
            dump_file = Path(dump_file)
            logger.info(f"Importing PostgreSQL dump from {dump_file}")

            if not dump_file.exists():
                raise FileNotFoundError(f"PostgreSQL dump file not found: {dump_file}")

            self.connect()
            self._escape_identifier(table_name)

            try:
                # Handle different dump formats
                if dump_file.suffix == ".zip":
                    return self._import_zipped_dump(dump_file, table_name)
                elif dump_file.suffix == ".gz":
                    return self._import_gzipped_dump(dump_file, table_name)
                else:
                    # Assume plain SQL dump
                    return self._import_sql_dump(dump_file, table_name)

            except Exception as e:
                logger.error(f"Failed to import PostgreSQL dump: {e}")
                return False

    def _import_zipped_dump(self, dump_file: Path, table_name: str) -> bool:
        """Import zipped PostgreSQL dump using postgres_scanner, COPY files, or pg_restore."""
        with log_with_context(stage="extract", run_id="usaspending_import") as logger:
            conn = self.connect()
            table_identifier = self._escape_identifier(table_name)
            dump_literal = self._escape_literal(str(dump_file))

            try:
                # Try direct postgres_scanner access first
                logger.info("Attempting direct postgres_scanner access to zipped dump")
                test_query = (
                    f"SELECT 1 FROM postgres_scan({dump_literal}, 'transaction_normalized') LIMIT 1"
                )
                conn.execute(test_query)
                logger.info("Direct postgres_scanner access successful")

                # Create view for the main table
                create_view_query = f"""
                CREATE OR REPLACE VIEW {table_identifier} AS
                SELECT * FROM postgres_scan({dump_literal}, 'transaction_normalized')
                """  # nosec B608
                conn.execute(create_view_query)

                # Get approximate row count (this may be slow on removable media)
                try:
                    count_query = f"SELECT COUNT(*) FROM {table_identifier}"  # nosec B608
                    result = conn.execute(count_query).fetchone()
                    row_count = result[0] if result else 0
                    logger.info(f"Created view with approximately {row_count} rows")
                except Exception:
                    logger.warning("Could not determine row count from zipped dump")

                return True

            except Exception as e:
                logger.warning(f"Direct postgres_scanner access failed: {e}")
                logger.info("Attempting COPY file extraction")

                # Try extracting COPY files
                if self._import_copy_files(dump_file, table_name):
                    return True

                logger.info("Falling back to pg_restore extraction")

                # Fallback: extract dump temporarily and import
                return self._extract_and_import_dump(dump_file, table_name)

    def _import_copy_files(self, dump_file: Path, table_name: str) -> bool:
        """Import PostgreSQL COPY files from ZIP archive."""
        with log_with_context(stage="extract", run_id="usaspending_import") as logger:
            conn = self.connect()

            try:
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
                            filename = parts[-1]
                            oid = int(filename.split("/")[-1].split(".")[0])
                            copy_files.append({"oid": oid, "filename": filename})

                if not copy_files:
                    logger.warning("No .dat.gz files found in ZIP")
                    return False

                logger.info(f"Found {len(copy_files)} COPY files in ZIP")

                # Create tables for each COPY file
                for file_info in copy_files:
                    oid = file_info["oid"]
                    filename = file_info["filename"]
                    table_name_for_file = f"{table_name}_{oid}"
                    table_identifier = self._escape_identifier(table_name_for_file)

                    logger.info(f"Importing {filename} as {table_name_for_file}")

                    # Extract and decompress the file
                    with tempfile.TemporaryDirectory() as temp_dir:
                        temp_file = Path(temp_dir) / f"{oid}.dat"

                        # Extract specific file
                        extract_cmd = ["unzip", "-p", str(dump_file), filename]
                        with open(temp_file, "wb") as f:
                            result = subprocess.run(extract_cmd, stdout=f, stderr=subprocess.PIPE)

                        if result.returncode != 0:
                            logger.error(f"Failed to extract {filename}: {result.stderr.decode()}")
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
                            file_literal = self._escape_literal(str(decompressed_file))
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

                # Create a union view for transaction_normalized if multiple tables
                base_table_identifier = self._escape_identifier(table_name)
                txn_tables = [f"{table_name}_{f['oid']}" for f in copy_files if f["oid"] == 5420]
                if txn_tables:
                    first_table_identifier = self._escape_identifier(txn_tables[0])
                    union_query = f"CREATE OR REPLACE VIEW {base_table_identifier} AS SELECT * FROM {first_table_identifier}"  # nosec B608
                    conn.execute(union_query)
                    logger.info(f"Created view {table_name} from {txn_tables[0]}")

                return True

            except Exception as e:
                logger.error(f"Failed to import COPY files: {e}")
                return False

    def _extract_and_import_dump(self, dump_file: Path, table_name: str) -> bool:
        """Extract dump to temporary location and import."""
        with log_with_context(stage="extract", run_id="usaspending_import") as logger:
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_dump = Path(temp_dir) / "dump.sql"

                logger.info(f"Extracting dump to temporary file: {temp_dump}")

                # Extract dump using pg_restore
                cmd = ["pg_restore", "-f", str(temp_dump), str(dump_file)]
                result = subprocess.run(cmd, capture_output=True, text=True)

                if result.returncode != 0:
                    logger.error(f"pg_restore extraction failed: {result.stderr}")
                    return False

                # Import the extracted SQL
                return self._import_sql_dump(temp_dump, table_name)

    def _import_gzipped_dump(self, dump_file: Path, table_name: str) -> bool:
        """Import gzipped PostgreSQL dump."""
        with log_with_context(stage="extract", run_id="usaspending_import") as logger:
            logger.warning("Gzipped dump support is limited - consider using .zip format")
            # For now, fall back to extraction
            return self._extract_and_import_dump(dump_file, table_name)

    def _import_sql_dump(self, dump_file: Path, table_name: str) -> bool:
        """Import plain SQL dump file."""
        with log_with_context(stage="extract", run_id="usaspending_import") as logger:
            conn = self.connect()

            # This is a simplified approach - real implementation would parse SQL properly
            logger.warning("Plain SQL dump import is not fully implemented")
            logger.info("Use postgres_scanner for production dump access")

            # Placeholder: try to read as CSV if it's actually CSV data
            try:
                import_query = f"""
                CREATE TABLE IF NOT EXISTS {table_name} AS
                SELECT * FROM read_csv_auto('{dump_file}')
                """
                conn.execute(import_query)
                return True
            except Exception:
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
    data_dir: Path | None = None, dump_filename: str = "usaspending-db_20251006.zip"
) -> DuckDBUSAspendingExtractor:
    """Create USAspending extractor using configuration settings.

    Args:
        data_dir: Directory containing data files (uses config if None)
        dump_filename: Name of the USAspending dump file

    Returns:
        Configured DuckDBUSAspendingExtractor instance
    """
    config = get_config()

    if data_dir is None:
        data_dir = Path("data/raw")

    db_path = config.duckdb.database_path
    extractor = DuckDBUSAspendingExtractor(db_path)

    # Import dump if it exists - check multiple locations:
    # 1. Specified data_dir
    dump_file = data_dir / dump_filename
    if dump_file.exists():
        table_name = config.extraction.usaspending.get("table_name", "usaspending_awards")
        extractor.import_postgres_dump(dump_file, table_name)
    else:
        # 2. Try configured path (supports environment variable overrides)
        try:
            configured_dump = config.paths.resolve_path("usaspending_dump_file")
            if configured_dump.exists():
                with log_with_context(stage="extract", run_id="usaspending_config") as logger:
                    logger.info(f"Using dump from configured path: {configured_dump}")
                    table_name = config.extraction.usaspending.get("table_name", "usaspending_awards")
                    extractor.import_postgres_dump(configured_dump, table_name)
        except Exception as e:
            with log_with_context(stage="extract", run_id="usaspending_config") as logger:
                logger.debug(f"Configured dump path not available: {e}")

    return extractor
