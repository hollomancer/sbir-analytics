"""SBIR data extraction using DuckDB."""

from pathlib import Path
from typing import Optional, List
import pandas as pd
from loguru import logger

from ..utils.duckdb_client import DuckDBClient
from ..models.sbir_award import (
    SbirAward,
    parse_bool_from_csv,
    parse_date_from_csv,
    parse_int_from_csv,
    parse_float_from_csv,
)


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
        self, csv_path: Path | str, duckdb_path: str = ":memory:", table_name: str = "sbir_awards"
    ):
        """
        Initialize SBIR DuckDB extractor.

        Args:
            csv_path: Path to SBIR CSV file
            duckdb_path: Path to DuckDB database (":memory:" for in-memory)
            table_name: Name for DuckDB table
        """
        self.csv_path = Path(csv_path)
        self.table_name = table_name
        self.duckdb_client = DuckDBClient(database_path=duckdb_path)
        self._imported = False

        logger.info(
            f"Initialized SbirDuckDBExtractor",
            csv_path=str(self.csv_path),
            duckdb_path=duckdb_path,
            table_name=table_name,
        )

    def import_csv(self) -> dict:
        """
        Import SBIR CSV into DuckDB table.

        Returns:
            Dictionary with import metadata (record count, duration, etc.)
        """
        import time

        logger.info(f"Importing CSV to DuckDB table '{self.table_name}'")

        if not self.csv_path.exists():
            raise FileNotFoundError(f"CSV file not found: {self.csv_path}")

        # Get file size
        file_size_mb = self.csv_path.stat().st_size / (1024 * 1024)

        start_time = time.time()

        # Import CSV to DuckDB
        success = self.duckdb_client.import_csv(
            csv_path=self.csv_path,
            table_name=self.table_name,
            delimiter=",",
            header=True,
            encoding="utf-8",
        )

        if not success:
            raise RuntimeError(f"Failed to import CSV to DuckDB")

        import_duration = time.time() - start_time

        # Get table info
        table_info = self.duckdb_client.get_table_info(self.table_name)
        row_count = table_info.get("row_count", 0)
        columns = table_info.get("columns", [])
        column_count = len(columns)

        self._imported = True

        metadata = {
            "csv_path": str(self.csv_path),
            "file_size_mb": round(file_size_mb, 2),
            "table_name": self.table_name,
            "row_count": row_count,
            "column_count": column_count,
            "import_duration_seconds": round(import_duration, 2),
            "records_per_second": round(row_count / import_duration) if import_duration > 0 else 0,
        }

        logger.info(f"CSV import complete", **metadata)

        return metadata

    def _ensure_imported(self):
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

        query = f"SELECT * FROM {self.table_name}"
        df = self.duckdb_client.execute_query_df(query)

        logger.info(f"Extracted {len(df)} records")

        return df

    def extract_by_year(self, start_year: int, end_year: Optional[int] = None) -> pd.DataFrame:
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

        query = f"""
        SELECT * FROM {self.table_name}
        WHERE "Award Year" BETWEEN {start_year} AND {end_year}
        """

        df = self.duckdb_client.execute_query_df(query)

        logger.info(f"Extracted {len(df)} records for years {start_year}-{end_year}")

        return df

    def extract_by_agency(self, agencies: List[str]) -> pd.DataFrame:
        """
        Extract SBIR awards filtered by Agency.

        Args:
            agencies: List of agency names

        Returns:
            pandas DataFrame with filtered records
        """
        self._ensure_imported()

        logger.info(f"Extracting records for agencies: {agencies}")

        # Build SQL IN clause
        agency_list = ", ".join(f"'{agency}'" for agency in agencies)

        query = f"""
        SELECT * FROM {self.table_name}
        WHERE Agency IN ({agency_list})
        """

        df = self.duckdb_client.execute_query_df(query)

        logger.info(f"Extracted {len(df)} records for {len(agencies)} agencies")

        return df

    def extract_by_phase(self, phases: List[str]) -> pd.DataFrame:
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
        phase_list = ", ".join(f"'{phase}'" for phase in phases)

        query = f"""
        SELECT * FROM {self.table_name}
        WHERE Phase IN ({phase_list})
        """

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

        query = f"""
        SELECT
            {', '.join(null_counts)}
        FROM {self.table_name}
        """

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
            f"Missing value analysis complete",
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

        query = f"""
        SELECT
            Contract,
            Company,
            COUNT(*) as record_count,
            STRING_AGG(DISTINCT Phase, ', ') as phases,
            STRING_AGG(DISTINCT CAST("Award Year" AS VARCHAR), ', ') as years
        FROM {self.table_name}
        WHERE Contract IS NOT NULL AND Contract != ''
        GROUP BY Contract, Company
        HAVING COUNT(*) > 1
        ORDER BY record_count DESC, Contract
        """

        df = self.duckdb_client.execute_query_df(query)

        logger.info(
            f"Duplicate analysis complete",
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
        FROM {self.table_name}
        WHERE "Award Amount" IS NOT NULL
        GROUP BY Phase, Agency
        ORDER BY total_funding DESC
        """

        df = self.duckdb_client.execute_query_df(query)

        # Round amounts
        for col in ["min_amount", "max_amount", "avg_amount", "median_amount", "total_funding"]:
            if col in df.columns:
                df[col] = df[col].round(2)

        logger.info(f"Award amount analysis complete", phase_agency_combinations=len(df))

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
        year_query = f"""
        SELECT
            MIN("Award Year") as min_year,
            MAX("Award Year") as max_year,
            COUNT(DISTINCT "Award Year") as year_count
        FROM {self.table_name}
        WHERE "Award Year" IS NOT NULL
        """
        year_stats = self.duckdb_client.execute_query(year_query)[0]

        # Get agency count
        agency_query = f"""
        SELECT COUNT(DISTINCT Agency) as agency_count
        FROM {self.table_name}
        WHERE Agency IS NOT NULL
        """
        agency_stats = self.duckdb_client.execute_query(agency_query)[0]

        # Get phase distribution
        phase_query = f"""
        SELECT Phase, COUNT(*) as count
        FROM {self.table_name}
        GROUP BY Phase
        ORDER BY count DESC
        """
        phase_dist = self.duckdb_client.execute_query_df(phase_query)

        stats = {
            "table_name": self.table_name,
            "total_records": table_info.get("row_count", 0),
            "total_columns": len(table_info.get("columns", [])),
            "year_range": f"{year_stats['min_year']}-{year_stats['max_year']}"
            if year_stats["min_year"]
            else None,
            "unique_years": year_stats.get("year_count", 0),
            "unique_agencies": agency_stats.get("agency_count", 0),
            "phase_distribution": phase_dist.to_dict("records") if len(phase_dist) > 0 else [],
        }

        return stats
