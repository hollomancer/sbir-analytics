"""DuckDB client utilities for data processing."""

import duckdb
from pathlib import Path
from typing import Optional, Dict, Any, List
from contextlib import contextmanager

from ..config.loader import get_config
from . import log_with_context


class DuckDBClient:
    """Client for DuckDB database operations."""

    def __init__(self, database_path: Optional[str] = None, read_only: bool = False):
        """Initialize DuckDB client.

        Args:
            database_path: Path to database file, or None for in-memory
            read_only: Whether to open database in read-only mode
        """
        self.database_path = database_path or ":memory:"
        self.read_only = read_only
        self._connection = None

    @contextmanager
    def connection(self):
        """Context manager for database connection."""
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

    def execute_query(self, query: str, parameters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
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
            return [dict(zip(columns, row)) for row in rows]

    def execute_query_df(self, query: str, parameters: Optional[Dict[str, Any]] = None) -> 'pd.DataFrame':
        """Execute a query and return results as pandas DataFrame.

        Args:
            query: SQL query to execute
            parameters: Query parameters

        Returns:
            pandas DataFrame with results
        """
        import pandas as pd

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
        encoding: str = "utf-8"
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
                encoding='{encoding}')
            """

            try:
                with self.connection() as conn:
                    conn.execute(query)

                # Get row count
                count_query = f"SELECT COUNT(*) FROM {table_name}"
                result = self.execute_query(count_query)
                row_count = result[0]['count_star()'] if result else 0

                logger.info(f"Imported {row_count} rows into table '{table_name}'")
                return True

            except Exception as e:
                logger.error(f"Failed to import CSV: {e}")
                return False

    def import_postgres_dump(
        self,
        dump_path: Path,
        table_name: str,
        schema_only: bool = False
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
                if dump_path.suffix == '.sql':
                    logger.warning("SQL dump files require preprocessing - not yet implemented")
                    return False

                # Try to read as CSV
                return self.import_csv(dump_path, table_name)

            except Exception as e:
                logger.error(f"Failed to import PostgreSQL dump: {e}")
                return False

    def create_table_from_df(self, df: 'pd.DataFrame', table_name: str) -> bool:
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
                    conn.register('temp_df', df)
                    conn.execute(f"CREATE TABLE {table_name} AS SELECT * FROM temp_df")

                logger.info(f"Created table '{table_name}' with {len(df)} rows")
                return True

            except Exception as e:
                logger.error(f"Failed to create table from DataFrame: {e}")
                return False

    def get_table_info(self, table_name: str) -> Dict[str, Any]:
        """Get information about a table.

        Args:
            table_name: Name of the table

        Returns:
            Dictionary with table information
        """
        try:
            # Get column information
            describe_query = f"DESCRIBE {table_name}"
            columns = self.execute_query(describe_query)

            # Get row count
            count_query = f"SELECT COUNT(*) as row_count FROM {table_name}"
            count_result = self.execute_query(count_query)
            row_count = count_result[0]['row_count'] if count_result else 0

            return {
                "table_name": table_name,
                "row_count": row_count,
                "columns": columns
            }

        except Exception as e:
            return {
                "table_name": table_name,
                "error": str(e)
            }

    def table_exists(self, table_name: str) -> bool:
        """Check if table exists.

        Args:
            table_name: Name of the table

        Returns:
            True if table exists
        """
        try:
            query = "SELECT name FROM sqlite_master WHERE type='table' AND name=?"
            # DuckDB uses different system catalog
            query = f"SELECT table_name FROM information_schema.tables WHERE table_name='{table_name}'"
            result = self.execute_query(query)
            return len(result) > 0
        except Exception:
            return False


def get_duckdb_client() -> DuckDBClient:
    """Get configured DuckDB client instance."""
    config = get_config()
    return DuckDBClient(database_path=config.duckdb.database_path)