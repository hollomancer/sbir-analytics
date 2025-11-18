"""Dagster assets for USAspending data ingestion pipeline."""

import json
from pathlib import Path
from typing import Any

import pandas as pd
from dagster import AssetExecutionContext, MetadataValue, Output, asset

from ..config.loader import get_config
from ..exceptions import ExtractionError, FileSystemError
from ..extractors.usaspending import DuckDBUSAspendingExtractor


def _import_usaspending_table(
    context: AssetExecutionContext,
    *,
    log_label: str,
    table_name: str,
    table_oid: str,
) -> Output[pd.DataFrame]:
    """Helper to import a USAspending table and emit consistent Dagster metadata."""
    config = get_config()
    dump_path = config.paths.resolve_path("usaspending_dump_file")

    context.log.info(
        f"Starting USAspending {log_label} extraction",
        extra={
            "dump_path": str(dump_path),
            "duckdb_path": config.duckdb.database_path,
        },
    )

    extractor = DuckDBUSAspendingExtractor(db_path=config.duckdb.database_path)
    success = extractor.import_postgres_dump(dump_path, table_name)
    if not success:
        raise ExtractionError(
            "Failed to import USAspending dump",
            component="assets.usaspending_ingestion",
            operation="import_dump",
            details={"dump_path": str(dump_path), "table_name": table_name},
        )

    full_table_name = f"{table_name}_{table_oid}"
    table_info = extractor.get_table_info(full_table_name)
    sample_df = extractor.query_awards(table_name=full_table_name, limit=100)

    context.log.info(
        f"{log_label.replace('_', ' ').title()} extraction complete",
        extra={
            "table_name": table_info.get("table_name"),
            "row_count": table_info.get("row_count"),
            "columns": len(table_info.get("columns", [])),
        },
    )

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
    description="USAspending recipient lookup table loaded into DuckDB",
    group_name="extraction",
    compute_kind="duckdb",
)
def raw_usaspending_recipients(context: AssetExecutionContext) -> Output[pd.DataFrame]:
    """
    Load USAspending recipient_lookup table from COPY dump.

    Returns:
        pandas DataFrame with recipient data
    """
    return _import_usaspending_table(
        context,
        log_label="recipient_lookup",
        table_name="raw_usaspending_recipients",
        table_oid="5412",
    )


@asset(
    description="USAspending transaction normalized table loaded into DuckDB",
    group_name="extraction",
    compute_kind="duckdb",
)
def raw_usaspending_transactions(context: AssetExecutionContext) -> Output[pd.DataFrame]:
    """
    Load USAspending transaction_normalized table from COPY dump.

    Returns:
        pandas DataFrame with transaction data
    """
    return _import_usaspending_table(
        context,
        log_label="transaction_normalized",
        table_name="raw_usaspending_transactions",
        table_oid="5420",
    )


@asset(
    description="USAspending dump profiling report",
    group_name="extraction",
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
        raise FileSystemError(
            f"Profile report not found: {profile_path}",
            file_path=str(profile_path),
            operation="load_profile_report",
            component="assets.usaspending_ingestion",
        )

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
