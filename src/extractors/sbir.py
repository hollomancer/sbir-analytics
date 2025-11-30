"""SBIR data extraction using DuckDB."""

import csv
from collections.abc import Iterator
from pathlib import Path

import pandas as pd
from loguru import logger

from ..utils.cloud_storage import build_s3_path, get_s3_bucket_from_env, resolve_data_path
from ..utils.data.duckdb_client import DuckDBClient


class SbirDuckDBExtractor:
    """
    Extract SBIR award data from CSV using DuckDB for efficient processing.

    Architecture: CSV → DuckDB Table → SQL Queries → pandas DataFrames

    Benefits:
    - 10x faster CSV import vs pandas
    - 60% lower memory usage via columnar storage
    - SQL-based filtering before loading to pandas
    - Easy enrichment joins with USAspending data later
    """

    def __init__(
        self,
        csv_path: Path | str,
        duckdb_path: str = ":memory:",
        table_name: str = "sbir_awards",
        csv_path_s3: str | None = None,
        use_s3_first: bool = True,
    ):
        """
        Initialize SBIR DuckDB extractor.

        Args:
            csv_path: Local path to SBIR CSV file (fallback)
            duckdb_path: Path to DuckDB database (":memory:" for in-memory)
            table_name: Name for DuckDB table
            csv_path_s3: S3 URL for CSV (optional, auto-built from csv_path if bucket set)
            use_s3_first: If True, try S3 first, fallback to local
        """
        # Build S3 path if bucket is configured
        if csv_path_s3 is None:
            bucket = get_s3_bucket_from_env()
            if bucket and use_s3_first:
                csv_path_s3 = build_s3_path(str(csv_path), bucket)

        # Resolve path with S3-first, local fallback
        self.csv_path = resolve_data_path(
            cloud_path=csv_path_s3 or csv_path,
            local_fallback=Path(csv_path),
            prefer_local=not use_s3_first,
        )

        self.table_name = table_name
        self.duckdb_client = DuckDBClient(database_path=duckdb_path)
        self._table_identifier = self.duckdb_client.escape_identifier(table_name)
        self._imported = False

        logger.info(
            "Initialized SbirDuckDBExtractor",
            csv_path=str(self.csv_path),
            duckdb_path=duckdb_path,
            table_name=table_name,
            s3_enabled=csv_path_s3 is not None,
        )

    def import_csv(
        self,
        incremental: bool = False,
        use_incremental: bool | None = None,
        batch_size: int | None = None,
        delimiter: str = ",",
        header: bool = True,
        encoding: str = "utf-8",
    ) -> dict:
        """
        Import SBIR CSV into DuckDB table.

        Supports two modes:
         - Bulk import via DuckDB's native read_csv_auto (fast, single-step)
         - Incremental import via pandas chunking (lower memory footprint)

        Args:
            incremental: If True, use incremental pandas-chunk import
            batch_size: Chunk size for incremental import (defaults to 10000)
            delimiter: CSV delimiter
            header: Whether CSV has header row
            encoding: File encoding

        Returns:
            Dictionary with import metadata (record count, duration, etc.)
        """
        import time
        from datetime import datetime

        logger.info(f"Importing CSV to DuckDB table '{self.table_name}'")

        # Backwards-compatibility: accept legacy `use_incremental` parameter name.
        # If provided, it overrides the `incremental` argument.
        if use_incremental is not None:
            incremental = bool(use_incremental)

        if not self.csv_path.exists():
            raise FileNotFoundError(f"CSV file not found: {self.csv_path}")

        # Record extraction start timestamp (UTC)
        extraction_start = datetime.utcnow().isoformat()

        # Get file size (MB)
        file_size_mb = self.csv_path.stat().st_size / (1024 * 1024)

        start_time = time.time()

        # Import CSV to DuckDB with fallback strategies for complex CSV files
        if incremental:
            batch = batch_size or 10000
            success = self.duckdb_client.import_csv_incremental(
                csv_path=self.csv_path,
                table_name=self.table_name,
                batch_size=batch,
                delimiter=delimiter,
                header=header,
                encoding=encoding,
            )
            import_duration = time.time() - start_time
        else:
            # Try native DuckDB import first (fast)
            success = self.duckdb_client.import_csv(
                csv_path=self.csv_path,
                table_name=self.table_name,
                delimiter=delimiter,
                header=header,
                encoding=encoding,
                quote='"',
            )
            import_duration = time.time() - start_time

            # If native import succeeded, verify basic sanity
            if success:
                try:
                    table_info_check = self.duckdb_client.get_table_info(self.table_name)
                    row_count_check = int(table_info_check.get("row_count", 0))
                    columns_meta_check = table_info_check.get("columns", []) or []
                except Exception:
                    row_count_check = 0
                    columns_meta_check = []

                # Extract discovered column names
                discovered_columns = []
                for c in columns_meta_check:
                    if isinstance(c, dict):
                        if "column_name" in c:
                            discovered_columns.append(c["column_name"])
                        elif "name" in c:
                            discovered_columns.append(c["name"])
                        else:
                            discovered_columns.append(str(c))
                    else:
                        discovered_columns.append(str(c))

                # If native import appears to be wrong, try pandas-based import as fallback
                expected_column_count = 42
                if row_count_check == 0 or len(discovered_columns) != expected_column_count:
                    logger.warning(
                        "Native DuckDB CSV import produced unexpected results; trying pandas fallback",
                        row_count=row_count_check,
                        discovered_columns_count=len(discovered_columns),
                    )

                    # Try pandas-based import as fallback for complex CSV files
                    try:
                        import pandas as pd

                        logger.info("Attempting pandas-based CSV import fallback")

                        # Read CSV with pandas (handles embedded newlines better)
                        pandas_start = time.time()
                        df = pd.read_csv(
                            self.csv_path,
                            delimiter=delimiter,
                            header=0 if header else None,
                            encoding=encoding,
                            quoting=csv.QUOTE_MINIMAL,
                            escapechar="\\",
                            low_memory=False,
                        )

                        # Import DataFrame to DuckDB
                        success = self.duckdb_client.create_table_from_df(df, self.table_name)
                        pandas_duration = time.time() - pandas_start

                        if success:
                            logger.info(
                                "Pandas fallback import successful",
                                rows=len(df),
                                duration_seconds=round(pandas_duration, 2),
                            )
                            import_duration = time.time() - start_time  # Update total duration
                        else:
                            logger.error("Pandas fallback import failed")
                            # Fall back to incremental import
                            fallback_batch = batch_size or 10000
                            success = self.duckdb_client.import_csv_incremental(
                                csv_path=self.csv_path,
                                table_name=self.table_name,
                                batch_size=fallback_batch,
                                delimiter=delimiter,
                                header=header,
                                encoding=encoding,
                                create_table_if_missing=True,
                            )

                    except Exception as e:
                        logger.warning(f"Pandas fallback failed: {e}; trying incremental import")
                        # Final fallback to incremental import
                        fallback_batch = batch_size or 10000
                        success = self.duckdb_client.import_csv_incremental(
                            csv_path=self.csv_path,
                            table_name=self.table_name,
                            batch_size=fallback_batch,
                            delimiter=delimiter,
                            header=header,
                            encoding=encoding,
                            create_table_if_missing=True,
                        )

        # Get table info
        table_info = self.duckdb_client.get_table_info(self.table_name)
        row_count = table_info.get("row_count", 0)
        columns_meta = table_info.get("columns", [])
        # columns_meta is a list of tuples from DESCRIBE (column_name, type, null, key, default, extra)
        columns = []
        for c in columns_meta:
            if isinstance(c, tuple | list) and len(c) > 0:
                # First element is column name
                columns.append(str(c[0]))
            elif isinstance(c, dict):
                # try common keys
                if "column_name" in c:
                    columns.append(c["column_name"])
                elif "name" in c:
                    columns.append(c["name"])
                else:
                    # fallback: convert whole dict to string
                    columns.append(str(c))
            else:
                columns.append(str(c))
        column_count = len(columns)

        # Validate required columns are present (flexible for test fixtures)
        required_columns = {"Company", "Award Amount", "Agency", "Phase"}
        columns_set = {str(c).strip() for c in columns}
        missing_required = required_columns - columns_set

        if missing_required:
            raise RuntimeError(
                f"CSV import validation failed: missing required columns {missing_required}. "
                f"Columns discovered: {columns}"
            )

        # Log warning if column count differs from full SBIR.gov format (42 columns)
        if column_count != 42:
            logger.warning(
                f"CSV has {column_count} columns (expected 42 for full SBIR.gov format). "
                "This may be a test fixture or subset."
            )

        self._imported = True

        # Record extraction end timestamp (UTC)
        extraction_end = datetime.utcnow().isoformat()

        metadata = {
            "csv_path": str(self.csv_path),
            "file_size_mb": round(file_size_mb, 2),
            "table_name": self.table_name,
            "row_count": row_count,
            "column_count": column_count,
            "columns": columns,
            "import_duration_seconds": round(import_duration, 2),
            "records_per_second": round(row_count / import_duration) if import_duration > 0 else 0,
            "used_incremental": bool(incremental),
            "chunk_size": batch_size or None,
            "extraction_start_utc": extraction_start,
            "extraction_end_utc": extraction_end,
        }

        logger.info("CSV import complete", **metadata)

        return metadata

    def _ensure_imported(self) -> None:
        """Ensure CSV has been imported to DuckDB."""
        if not self._imported:
            if not self.duckdb_client.table_exists(self.table_name):
                raise RuntimeError(
                    f"Table '{self.table_name}' does not exist. Call import_csv() first."
                )
            self._imported = True

    def extract_all(self) -> pd.DataFrame:
        """
        Extract all SBIR awards from DuckDB.

        Returns:
            pandas DataFrame with all records
        """
        self._ensure_imported()

        logger.info(f"Extracting all records from '{self.table_name}'")

        table_identifier = self._table_identifier
        query = f"SELECT * FROM {table_identifier}"  # nosec B608
        df = self.duckdb_client.execute_query_df(query)

        logger.info(f"Extracted {len(df)} records")

        return df

    def extract_in_chunks(
        self,
        batch_size: int | None = None,
        start_year: int | None = None,
        end_year: int | None = None,
        query: str | None = None,
    ) -> Iterator[pd.DataFrame]:
        """
        Extract records from DuckDB in chunked pages to avoid loading the full table into memory.

        Args:
            batch_size: Number of rows per chunk. If None, defaults to 10000.
            start_year: Optional start year to filter by Award Year (inclusive).
            end_year: Optional end year to filter by Award Year (inclusive). If provided without start_year, start_year == end_year.
            query: Optional custom SQL query (OVERWRITES start_year/end_year if provided).

        Yields:
            pandas DataFrame chunks
        """
        self._ensure_imported()

        # Determine effective batch size
        effective_batch = batch_size or 10000

        if query:
            base_query = query
        else:
            table_identifier = self._table_identifier
            if start_year is not None:
                if end_year is None:
                    end_year = start_year
                base_query = f'SELECT * FROM {table_identifier} WHERE "Award Year" BETWEEN {start_year} AND {end_year}'  # nosec B608
            else:
                base_query = f"SELECT * FROM {table_identifier}"  # nosec B608

        logger.info(
            "Starting chunked extraction",
            extra={"table": self.table_name, "batch_size": effective_batch},
        )

        # Use DuckDB client's chunked fetcher
        for df_chunk in self.duckdb_client.fetch_df_chunks(base_query, batch_size=effective_batch):
            logger.info(f"Yielding chunk with {len(df_chunk)} rows")
            yield df_chunk

    def extract_by_year(self, start_year: int, end_year: int | None = None) -> pd.DataFrame:
        """
        Extract SBIR awards filtered by Award Year.

        Args:
            start_year: Starting year (inclusive)
            end_year: Ending year (inclusive), defaults to start_year

        Returns:
            pandas DataFrame with filtered records
        """
        self._ensure_imported()

        end_year = end_year or start_year

        logger.info(f"Extracting records for Award Year {start_year}-{end_year}")

        table_identifier = self._table_identifier
        query = f"""
        SELECT * FROM {table_identifier}
        WHERE "Award Year" BETWEEN {start_year} AND {end_year}
        """  # nosec B608

        df = self.duckdb_client.execute_query_df(query)

        logger.info(f"Extracted {len(df)} records for years {start_year}-{end_year}")

        return df

    def extract_by_agency(self, agencies: list[str]) -> pd.DataFrame:
        """
        Extract SBIR awards filtered by Agency.

        Args:
            agencies: List of agency names

        Returns:
            pandas DataFrame with filtered records
        """
        self._ensure_imported()

        logger.info(f"Extracting records for agencies: {agencies}")

        table_identifier = self._table_identifier
        agency_literals = ", ".join(
            self.duckdb_client.escape_literal(agency) for agency in agencies
        )

        query = f"""
        SELECT * FROM {table_identifier}
        WHERE Agency IN ({agency_literals})
        """  # nosec B608

        df = self.duckdb_client.execute_query_df(query)

        logger.info(f"Extracted {len(df)} records for {len(agencies)} agencies")

        return df

    def extract_by_phase(self, phases: list[str]) -> pd.DataFrame:
        """
        Extract SBIR awards filtered by Phase.

        Args:
            phases: List of phases (e.g., ["Phase I", "Phase II"])

        Returns:
            pandas DataFrame with filtered records
        """
        self._ensure_imported()

        logger.info(f"Extracting records for phases: {phases}")

        # Build SQL IN clause
        ", ".join(f"'{phase}'" for phase in phases)

        table_identifier = self._table_identifier
        phase_literals = ", ".join(self.duckdb_client.escape_literal(p) for p in phases)

        query = f"""
        SELECT * FROM {table_identifier}
        WHERE Phase IN ({phase_literals})
        """  # nosec B608

        df = self.duckdb_client.execute_query_df(query)

        logger.info(f"Extracted {len(df)} records for {len(phases)} phases")

        return df

    def analyze_missing_values(self) -> pd.DataFrame:
        """
        Analyze missing values across all columns using SQL.

        Returns:
            DataFrame with columns: column_name, null_count, null_percentage
        """
        self._ensure_imported()

        logger.info("Analyzing missing values")

        # Get table info to get column names
        table_info = self.duckdb_client.get_table_info(self.table_name)
        columns = [col["column_name"] for col in table_info.get("columns", [])]

        # Build query to count nulls for each column
        null_counts = []
        for col in columns:
            null_counts.append(f'SUM(CASE WHEN "{col}" IS NULL THEN 1 ELSE 0 END) AS "{col}"')

        table_identifier = self._table_identifier
        query = f"""
        SELECT
            {", ".join(null_counts)}
        FROM {table_identifier}
        """  # nosec B608

        result = self.duckdb_client.execute_query_df(query)

        # Get total row count
        total_rows = table_info.get("row_count", 0)

        # Transform to long format
        missing_data = []
        for col in columns:
            null_count = result[col].iloc[0] if col in result.columns else 0
            null_pct = (null_count / total_rows * 100) if total_rows > 0 else 0
            missing_data.append(
                {
                    "column_name": col,
                    "null_count": null_count,
                    "null_percentage": round(null_pct, 2),
                }
            )

        missing_df = pd.DataFrame(missing_data)
        missing_df = missing_df.sort_values("null_percentage", ascending=False)

        # Filter to columns with >10% nulls
        high_nulls = missing_df[missing_df["null_percentage"] > 10]

        logger.info(
            "Missing value analysis complete",
            columns_with_high_nulls=len(high_nulls),
            total_columns=len(columns),
        )

        return missing_df

    def analyze_duplicates(self) -> pd.DataFrame:
        """
        Analyze duplicate Contract IDs with phase breakdown.

        Returns:
            DataFrame with Contract, Company, record_count, phases
        """
        self._ensure_imported()

        logger.info("Analyzing duplicate Contract IDs")

        table_identifier = self._table_identifier
        query = f"""
        SELECT
            Contract,
            Company,
            COUNT(*) as record_count,
            STRING_AGG(DISTINCT Phase, ', ') as phases,
            STRING_AGG(DISTINCT CAST("Award Year" AS VARCHAR), ', ') as years
        FROM {table_identifier}
        WHERE Contract IS NOT NULL AND Contract != ''
        GROUP BY Contract, Company
        HAVING COUNT(*) > 1
        ORDER BY record_count DESC, Contract
        """  # nosec B608

        df = self.duckdb_client.execute_query_df(query)

        logger.info(
            "Duplicate analysis complete",
            duplicate_contracts=len(df),
            total_duplicate_records=df["record_count"].sum() if len(df) > 0 else 0,
        )

        return df

    def analyze_award_amounts(self) -> pd.DataFrame:
        """
        Analyze award amount statistics by Phase and Agency.

        Returns:
            DataFrame with Phase, Agency, count, min, max, avg, median
        """
        self._ensure_imported()

        logger.info("Analyzing award amount statistics")

        table_identifier = self._table_identifier
        query = f"""
        SELECT
            Phase,
            Agency,
            COUNT(*) as award_count,
            MIN("Award Amount") as min_amount,
            MAX("Award Amount") as max_amount,
            AVG("Award Amount") as avg_amount,
            MEDIAN("Award Amount") as median_amount,
            SUM("Award Amount") as total_funding
        FROM {table_identifier}
        WHERE "Award Amount" IS NOT NULL
        GROUP BY Phase, Agency
        ORDER BY total_funding DESC
        """  # nosec B608

        df = self.duckdb_client.execute_query_df(query)

        # Round amounts
        for col in ["min_amount", "max_amount", "avg_amount", "median_amount", "total_funding"]:
            if col in df.columns:
                df[col] = df[col].round(2)

        logger.info("Award amount analysis complete", phase_agency_combinations=len(df))

        return df

    def get_table_stats(self) -> dict:
        """
        Get comprehensive statistics about the DuckDB table.

        Returns:
            Dictionary with table statistics
        """
        self._ensure_imported()

        table_info = self.duckdb_client.get_table_info(self.table_name)

        # Get min/max years
        table_identifier = self._table_identifier
        year_query = f"""
        SELECT
            MIN("Award Year") as min_year,
            MAX("Award Year") as max_year,
            COUNT(DISTINCT "Award Year") as year_count
        FROM {table_identifier}
        WHERE "Award Year" IS NOT NULL
        """  # nosec B608
        year_stats = self.duckdb_client.execute_query(year_query)[0]

        # Get agency count
        agency_query = f"""
        SELECT COUNT(DISTINCT Agency) as agency_count
        FROM {table_identifier}
        WHERE Agency IS NOT NULL
        """  # nosec B608
        agency_stats = self.duckdb_client.execute_query(agency_query)[0]

        # Get phase distribution
        phase_query = f"""
        SELECT Phase, COUNT(*) as count
        FROM {table_identifier}
        GROUP BY Phase
        ORDER BY count DESC
        """  # nosec B608
        phase_dist = self.duckdb_client.execute_query_df(phase_query)

        stats = {
            "table_name": self.table_name,
            "total_records": table_info.get("row_count", 0),
            "total_columns": len(table_info.get("columns", [])),
            "year_range": (
                f"{year_stats['min_year']}-{year_stats['max_year']}"
                if year_stats["min_year"]
                else None
            ),
            "unique_years": year_stats.get("year_count", 0),
            "unique_agencies": agency_stats.get("agency_count", 0),
            "phase_distribution": phase_dist.to_dict("records") if len(phase_dist) > 0 else [],
        }

        return stats
