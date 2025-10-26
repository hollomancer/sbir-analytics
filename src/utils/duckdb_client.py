"""DuckDB client utilities for data processing."""

import csv
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any

import duckdb
import pandas as pd

from ..config.loader import get_config
from .logging_config import log_with_context

if TYPE_CHECKING:
    # For type checkers we still reference pandas types
    import pandas as pd


class DuckDBClient:
    """Client for DuckDB database operations."""

    def __init__(self, database_path: str | None = None, read_only: bool = False):
        """Initialize DuckDB client.

        Args:
            database_path: Path to database file, or None for in-memory
            read_only: Whether to open database in read-only mode
        """
        self.database_path = database_path or ":memory:"
        self.read_only = read_only
        self._connection = None
        # For in-memory databases, maintain a persistent connection
        self._persistent_conn = None if self.database_path != ":memory:" else None

    @contextmanager
    def connection(self):
        """Context manager for database connection."""
        if self.database_path == ":memory:":
            # For in-memory databases, use persistent connection
            if self._persistent_conn is None:
                self._persistent_conn = duckdb.connect(self.database_path, read_only=self.read_only)
                # Configure connection
                self._persistent_conn.execute("SET enable_object_cache=true")
                self._persistent_conn.execute("SET memory_limit='4GB'")
                self._persistent_conn.execute("SET threads=4")
            yield self._persistent_conn
        else:
            # For file-based databases, use temporary connections
            conn = None
            try:
                conn = duckdb.connect(self.database_path, read_only=self.read_only)
                # Configure connection
                conn.execute("SET enable_object_cache=true")
                conn.execute("SET memory_limit='4GB'")
                conn.execute("SET threads=4")
                yield conn
            finally:
                if conn:
                    conn.close()

    def execute_query(
        self, query: str, parameters: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Execute a query and return results as list of dictionaries.

        Args:
            query: SQL query to execute
            parameters: Query parameters

        Returns:
            List of result rows as dictionaries
        """
        with self.connection() as conn:
            if parameters:
                result = conn.execute(query, parameters)
            else:
                result = conn.execute(query)

            # Convert to list of dicts
            columns = [desc[0] for desc in result.description]
            rows = result.fetchall()
            return [dict(zip(columns, row, strict=False)) for row in rows]

    def close(self):
        """Close persistent connection if it exists."""
        if self._persistent_conn:
            self._persistent_conn.close()
            self._persistent_conn = None

    def execute_query_df(
        self, query: str, parameters: dict[str, Any] | None = None
    ) -> "pd.DataFrame":
        """Execute a query and return results as pandas DataFrame.

        Args:
            query: SQL query to execute
            parameters: Query parameters

        Returns:
            pandas DataFrame with results
        """

        with self.connection() as conn:
            if parameters:
                return conn.execute(query, parameters).fetchdf()
            else:
                return conn.execute(query).fetchdf()

    def import_csv(
        self,
        csv_path: Path,
        table_name: str,
        delimiter: str = ",",
        header: bool = True,
        encoding: str = "utf-8",
        quote: str = '"',
    ) -> bool:
        """Import CSV file into DuckDB table.

        Args:
            csv_path: Path to CSV file
            table_name: Name for the table
            delimiter: CSV delimiter
            header: Whether CSV has header row
            encoding: File encoding

        Returns:
            True if import successful
        """
        with log_with_context(stage="extract", run_id="csv_import") as logger:
            logger.info(f"Importing CSV {csv_path} into table {table_name}")

            if not csv_path.exists():
                raise FileNotFoundError(f"CSV file not found: {csv_path}")

            query = f"""
            CREATE TABLE IF NOT EXISTS {table_name} AS
            SELECT * FROM read_csv_auto('{csv_path}',
                delim='{delimiter}',
                header={header},
                encoding='{encoding}',
                quote='{quote}',
                sample_size=100000,
                max_line_size=1000000,
                ignore_errors=true)
            """

            try:
                with self.connection() as conn:
                    conn.execute(query)

                    # Get row count using the same connection
                    count_query = f"SELECT COUNT(*) as count FROM {table_name}"
                    result = conn.execute(count_query).fetchall()
                    row_count = result[0][0] if result else 0

                logger.info(f"Imported {row_count} rows into table '{table_name}'")
                return True

            except Exception as e:
                logger.error(f"Failed to import CSV: {e}")
                return False

    def import_postgres_dump(
        self, dump_path: Path, table_name: str, schema_only: bool = False
    ) -> bool:
        """Import PostgreSQL dump file into DuckDB.

        Note: This is a simplified implementation. Real PostgreSQL dumps
        are complex and may require preprocessing.

        Args:
            dump_path: Path to PostgreSQL dump file
            table_name: Name for the imported table
            schema_only: Whether to import only schema

        Returns:
            True if import successful
        """
        with log_with_context(stage="extract", run_id="postgres_import") as logger:
            logger.info(f"Importing PostgreSQL dump {dump_path} into table {table_name}")

            if not dump_path.exists():
                raise FileNotFoundError(f"Dump file not found: {dump_path}")

            try:
                # For now, assume the dump is a CSV-like format
                # Real implementation would need to parse PostgreSQL dump format
                if dump_path.suffix == ".sql":
                    logger.warning("SQL dump files require preprocessing - not yet implemented")
                    return False

                # Try to read as CSV
                return self.import_csv(dump_path, table_name)

            except Exception as e:
                logger.error(f"Failed to import PostgreSQL dump: {e}")
                return False

    def create_table_from_df(self, df: "pd.DataFrame", table_name: str) -> bool:
        """Create table from pandas DataFrame.

        Args:
            df: DataFrame to import
            table_name: Name for the table

        Returns:
            True if creation successful
        """
        with log_with_context(stage="transform", run_id="df_import") as logger:
            logger.info(f"Creating table {table_name} from DataFrame with {len(df)} rows")

            try:
                with self.connection() as conn:
                    # Register DataFrame
                    conn.register("temp_df", df)
                    conn.execute(f"CREATE TABLE {table_name} AS SELECT * FROM temp_df")

                    # Get row count using the same connection
                    count_query = f"SELECT COUNT(*) as count FROM {table_name}"
                    result = conn.execute(count_query).fetchall()
                    row_count = result[0][0] if result else 0

                logger.info(f"Created table '{table_name}' with {row_count} rows")
                return True

            except Exception as e:
                logger.error(f"Failed to create table from DataFrame: {e}")
                return False

    def get_table_info(self, table_name: str) -> dict[str, Any]:
        """Get information about a table.

        Args:
            table_name: Name of the table

        Returns:
            Dictionary with table information
        """
        try:
            with self.connection() as conn:
                # Get column information
                describe_query = f"DESCRIBE {table_name}"
                columns_result = conn.execute(describe_query)
                columns = columns_result.fetchall()

                # Get row count
                count_query = f"SELECT COUNT(*) as row_count FROM {table_name}"
                count_result = conn.execute(count_query).fetchall()
                row_count = count_result[0][0] if count_result else 0

            return {"table_name": table_name, "row_count": row_count, "columns": columns}

        except Exception as e:
            return {"table_name": table_name, "error": str(e)}

    def table_exists(self, table_name: str) -> bool:
        """Check if table exists.

        Args:
            table_name: Name of the table

        Returns:
            True if table exists
        """
        try:
            with self.connection() as conn:
                # Use information_schema for DuckDB table existence check
                query = f"SELECT table_name FROM information_schema.tables WHERE table_name='{table_name}'"
                result = conn.execute(query).fetchall()
                return len(result) > 0
        except Exception:
            return False

    def fetch_df_chunks(self, query: str, batch_size: int = 10000):
        """
        Generator that yields pandas DataFrames for a SQL query in chunked pages.

        This implementation paginates using LIMIT/OFFSET and wraps the original
        query in a subselect to avoid modifying user SQL. It is intentionally
        conservative (uses offset-based pagination) which is suitable for
        read-only analytical queries against DuckDB tables.

        Args:
            query: SQL query that selects the desired rows (no terminating semicolon)
            batch_size: Number of rows per yielded DataFrame

        Yields:
            pandas.DataFrame objects with up to `batch_size` rows
        """
        # Normalize query (remove trailing semicolon if present)
        base_query = query.strip().rstrip(";")
        offset = 0

        with log_with_context(stage="extract", run_id="fetch_df_chunks") as logger:
            logger.info("Starting chunked fetch", batch_size=batch_size)

            while True:
                paged_query = (
                    f"SELECT * FROM ({base_query}) AS sub LIMIT {batch_size} OFFSET {offset}"
                )
                df = self.execute_query_df(paged_query)

                if df is None or len(df) == 0:
                    logger.info("No more rows to fetch, ending chunked fetch", offset=offset)
                    break

                logger.debug("Yielding chunk", rows=len(df), offset=offset)
                yield df

                # Advance offset by number of rows actually returned to handle last partial page
                offset += len(df)

                # Stop early if last page was shorter than batch_size
                if len(df) < batch_size:
                    logger.info("Final chunk retrieved", rows=len(df), offset=offset)
                    break

    def import_csv_incremental(
        self,
        csv_path: Path,
        table_name: str,
        batch_size: int = 10000,
        delimiter: str = ",",
        header: bool = True,
        encoding: str = "utf-8",
        create_table_if_missing: bool = True,
    ) -> bool:
        """
        Import a CSV into DuckDB incrementally using pandas chunking.

        This method is intended for very large CSVs where importing the entire
        file in one shot may be memory-heavy. It reads the CSV in pandas
        chunks and writes each chunk into DuckDB. The first chunk creates the
        table (or overwrites if it already exists and `create_table_if_missing` is False).
        Subsequent chunks are appended.

        Args:
            csv_path: Path to CSV file
            table_name: Destination DuckDB table name
            batch_size: pandas chunk size
            delimiter: CSV delimiter
            header: Whether CSV has header row (True uses header=0)
            encoding: File encoding
            create_table_if_missing: If True and table does not exist, create it from first chunk

        Returns:
            True if import completed successfully, False on error
        """
        with log_with_context(stage="extract", run_id="csv_import_incremental") as logger:
            logger.info(
                f"Starting incremental CSV import into {table_name}", csv_path=str(csv_path)
            )

            if not csv_path.exists():
                raise FileNotFoundError(f"CSV file not found: {csv_path}")

            try:
                with self.connection() as conn:
                    first_chunk = True
                    total_rows = 0
                    # pandas.read_csv will raise if CSV can't be parsed; let that bubble
                    for chunk in pd.read_csv(
                        csv_path,
                        delimiter=delimiter,
                        header=0 if header else None,
                        encoding=encoding,
                        chunksize=batch_size,
                        dtype=str,  # read as strings to avoid type surprises; downstream logic can cast
                        low_memory=False,
                        quoting=csv.QUOTE_MINIMAL,
                        quotechar='"',
                    ):
                        # Normalize column names (strip whitespace) to reduce surprises
                        chunk.columns = [str(col).strip() for col in chunk.columns]

                        if first_chunk:
                            if create_table_if_missing or not self.table_exists(table_name):
                                # Create table from first chunk
                                conn.register("temp_df", chunk)
                                conn.execute(f"CREATE TABLE {table_name} AS SELECT * FROM temp_df")
                            else:
                                # Table exists: append first chunk
                                conn.register("temp_chunk", chunk)
                                conn.execute(f"INSERT INTO {table_name} SELECT * FROM temp_chunk")
                            first_chunk = False
                        else:
                            # Append subsequent chunks
                            conn.register("temp_chunk", chunk)
                            conn.execute(f"INSERT INTO {table_name} SELECT * FROM temp_chunk")

                        total_rows += len(chunk)
                        logger.info("Imported chunk", rows=len(chunk), total_rows=total_rows)

                    # Get final row count
                    count_result = conn.execute(
                        f"SELECT COUNT(*) as count FROM {table_name}"
                    ).fetchall()
                    final_count = count_result[0][0] if count_result else 0

                logger.info(
                    "Incremental CSV import complete", table_name=table_name, total_rows=final_count
                )
                return True

            except Exception as e:
                logger.error(f"Incremental CSV import failed: {e}")
                return False


def get_duckdb_client() -> DuckDBClient:
    """Get configured DuckDB client instance."""
    config = get_config()
    return DuckDBClient(database_path=config.duckdb.database_path)
