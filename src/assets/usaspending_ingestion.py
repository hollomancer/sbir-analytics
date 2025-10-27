"""Dagster assets for USAspending data ingestion pipeline."""

import json
from pathlib import Path
from typing import Any

import pandas as pd
from dagster import (
    AssetExecutionContext,
    MetadataValue,
    Output,
    asset,
)

from ..config.loader import get_config
from ..extractors.usaspending import DuckDBUSAspendingExtractor


@asset(
    description="USAspending recipient lookup table loaded into DuckDB",
    group_name="usaspending_ingestion",
    compute_kind="duckdb",
)
def usaspending_recipient_lookup(context: AssetExecutionContext) -> Output[pd.DataFrame]:
    """
    Load USAspending recipient_lookup table from COPY dump.

    Returns:
        pandas DataFrame with recipient data
    """
    # Get configuration
    config = get_config()

    # Use removable media path
    dump_path = Path("/Volumes/X10 Pro/projects/usaspending-db-subset_20251006.zip")

    context.log.info(
        "Starting USAspending recipient_lookup extraction",
        extra={
            "dump_path": str(dump_path),
            "duckdb_path": config.duckdb.database_path,
        },
    )

    # Initialize extractor
    extractor = DuckDBUSAspendingExtractor(db_path=config.duckdb.database_path)

    # Import dump
    table_name = "usaspending_recipient_lookup"
    success = extractor.import_postgres_dump(dump_path, table_name)

    if not success:
        raise RuntimeError("Failed to import USAspending dump")

    # Get table info
    table_info = extractor.get_table_info(f"{table_name}_5412")  # recipient_lookup OID

    # Sample data for metadata
    sample_df = extractor.query_awards(table_name=f"{table_name}_5412", limit=100)

    context.log.info(
        "Recipient lookup extraction complete",
        extra={
            "table_name": table_info.get("table_name"),
            "row_count": table_info.get("row_count"),
            "columns": len(table_info.get("columns", [])),
        },
    )

    # Create metadata
    metadata = {
        "table_name": table_info.get("table_name"),
        "row_count": table_info.get("row_count"),
        "num_columns": len(table_info.get("columns", [])),
        "columns": MetadataValue.json(
            [col["column_name"] for col in table_info.get("columns", [])]
        ),
        "preview": MetadataValue.md(sample_df.head(10).to_markdown()),
    }

    return Output(value=sample_df, metadata=metadata)


@asset(
    description="USAspending transaction normalized table loaded into DuckDB",
    group_name="usaspending_ingestion",
    compute_kind="duckdb",
)
def usaspending_transaction_normalized(context: AssetExecutionContext) -> Output[pd.DataFrame]:
    """
    Load USAspending transaction_normalized table from COPY dump.

    Returns:
        pandas DataFrame with transaction data
    """
    # Get configuration
    config = get_config()

    # Use removable media path
    dump_path = Path("/Volumes/X10 Pro/projects/usaspending-db-subset_20251006.zip")

    context.log.info(
        "Starting USAspending transaction_normalized extraction",
        extra={
            "dump_path": str(dump_path),
            "duckdb_path": config.duckdb.database_path,
        },
    )

    # Initialize extractor
    extractor = DuckDBUSAspendingExtractor(db_path=config.duckdb.database_path)

    # Import dump
    table_name = "usaspending_transaction_normalized"
    success = extractor.import_postgres_dump(dump_path, table_name)

    if not success:
        raise RuntimeError("Failed to import USAspending dump")

    # Get table info
    table_info = extractor.get_table_info(f"{table_name}_5420")  # transaction_normalized OID

    # Sample data for metadata
    sample_df = extractor.query_awards(table_name=f"{table_name}_5420", limit=100)

    context.log.info(
        "Transaction normalized extraction complete",
        extra={
            "table_name": table_info.get("table_name"),
            "row_count": table_info.get("row_count"),
            "columns": len(table_info.get("columns", [])),
        },
    )

    # Create metadata
    metadata = {
        "table_name": table_info.get("table_name"),
        "row_count": table_info.get("row_count"),
        "num_columns": len(table_info.get("columns", [])),
        "columns": MetadataValue.json(
            [col["column_name"] for col in table_info.get("columns", [])]
        ),
        "preview": MetadataValue.md(sample_df.head(10).to_markdown()),
    }

    return Output(value=sample_df, metadata=metadata)


@asset(
    description="USAspending dump profiling report",
    group_name="usaspending_ingestion",
    compute_kind="profiling",
)
def usaspending_profile_report(context: AssetExecutionContext) -> Output[dict[str, Any]]:
    """
    Load and return USAspending dump profiling report.

    Returns:
        Profiling report as dictionary
    """
    profile_path = Path("reports/usaspending_subset_profile.json")

    if not profile_path.exists():
        raise FileNotFoundError(f"Profile report not found: {profile_path}")

    with open(profile_path) as f:
        report = json.load(f)

    context.log.info(
        "Loaded profiling report",
        extra={
            "dump_size_gb": report.get("dump_size_gb"),
            "total_files": report.get("metadata", {}).get("total_files"),
            "tables_identified": report.get("metadata", {}).get("tables_identified"),
        },
    )

    # Create metadata
    metadata = {
        "dump_size_gb": report.get("dump_size_gb"),
        "total_files": report.get("metadata", {}).get("total_files"),
        "tables_identified": report.get("metadata", {}).get("tables_identified"),
        "profiling_timestamp": report.get("profiling_timestamp"),
    }

    return Output(value=report, metadata=metadata)
