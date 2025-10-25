"""USAspending data extractor using DuckDB.

This module provides functionality to extract USAspending data from compressed PostgreSQL dumps using DuckDB.
"""

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

    def connect(self) -> duckdb.DuckDBPyConnection:
        """Get or create database connection."""
        if self.connection is None:
            self.connection = duckdb.connect(self.db_path)
            # Enable object cache for better performance
            self.connection.execute("SET enable_object_cache=true")
        return self.connection

    def close(self):
        """Close database connection."""
        if self.connection:
            self.connection.close()
            self.connection = None

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()

    def import_postgres_dump(self, dump_file: Path, table_name: str = "usaspending_awards") -> bool:
        """Import PostgreSQL dump file into DuckDB.

        Args:
            dump_file: Path to the PostgreSQL dump file
            table_name: Name for the imported table

        Returns:
            True if import successful, False otherwise
        """
        with log_with_context(stage="extract", run_id="usaspending_import") as logger:
            logger.info(f"Importing PostgreSQL dump from {dump_file}")

            if not dump_file.exists():
                raise FileNotFoundError(f"PostgreSQL dump file not found: {dump_file}")

            conn = self.connect()

            try:
                # Check if file is compressed
                if dump_file.suffix == ".gz":
                    # For compressed files, we'll need to decompress first
                    # This is a simplified version - real implementation would handle compression
                    logger.warning("Compressed dump files not yet fully supported")
                    return False

                # Import PostgreSQL dump
                # Note: This is a simplified version. Real implementation would need
                # to handle PostgreSQL dump format properly
                import_query = f"""
                CREATE TABLE IF NOT EXISTS {table_name} AS
                SELECT * FROM read_csv_auto('{dump_file}')
                """

                conn.execute(import_query)

                # Get row count
                result = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()
                row_count = result[0] if result else 0

                logger.info(f"Imported {row_count} rows into table '{table_name}'")
                return True

            except Exception as e:
                logger.error(f"Failed to import PostgreSQL dump: {e}")
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

            # Get row count
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


def extract_usaspending_from_config(
    data_dir: Path | None = None, dump_filename: str = "usaspending_dump.sql"
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

    # Import dump if it exists
    dump_file = data_dir / dump_filename
    if dump_file.exists():
        table_name = config.extraction.usaspending.get("table_name", "usaspending_awards")
        extractor.import_postgres_dump(dump_file, table_name)

    return extractor
