"""Dagster assets for USAspending data ingestion pipeline.

Data Source Priority:
1. PRIMARY: S3 database dump (from EC2 automation workflow)
2. FALLBACK: USAspending API (if S3 unavailable)
3. FAIL: If both sources fail
"""

import json
from pathlib import Path
from typing import Any

import pandas as pd
from dagster import AssetExecutionContext, MetadataValue, Output, asset

from ..config.loader import get_config
from ..exceptions import ExtractionError, FileSystemError
from ..extractors.usaspending import DuckDBUSAspendingExtractor
from ..utils.cloud_storage import (
    find_latest_usaspending_dump,
    get_s3_bucket_from_env,
    resolve_data_path,
)


def _import_usaspending_table(
    context: AssetExecutionContext,
    *,
    log_label: str,
    table_name: str,
) -> Output[pd.DataFrame]:
    """
    Helper to import a USAspending table with S3-first, API-fallback strategy.

    Priority:
    1. Try S3 database dump (primary)
    2. Fall back to API if S3 fails
    3. Fail if both fail
    """
    config = get_config()

    # PRIMARY: Try S3 database dump first
    dump_path = None
    s3_bucket = get_s3_bucket_from_env()

    if s3_bucket:
        context.log.info("Attempting to load USAspending data from S3 (PRIMARY)")
        # Find latest dump in S3 (prefer test, fallback to full)
        s3_dump_url = find_latest_usaspending_dump(
            bucket=s3_bucket, database_type="test"
        ) or find_latest_usaspending_dump(bucket=s3_bucket, database_type="full")

        if s3_dump_url:
            try:
                # Resolve S3 path (downloads to temp if needed)
                dump_path = resolve_data_path(s3_dump_url)
                context.log.info(f"Using S3 dump: {s3_dump_url} -> {dump_path}")
            except Exception as e:
                context.log.warning(f"S3 dump resolution failed: {e}")
                dump_path = None

    # If S3 failed, try configured path (local fallback)
    if not dump_path:
        try:
            dump_path = config.paths.resolve_path("usaspending_dump_file")
            if dump_path.exists():
                context.log.info(f"Using configured dump path: {dump_path}")
            else:
                dump_path = None
        except Exception as e:
            context.log.warning(f"Configured dump path not available: {e}")
            dump_path = None

    # Try to import from dump if available
    extractor = DuckDBUSAspendingExtractor(db_path=config.duckdb.database_path)
    dump_success = False

    if dump_path:
        context.log.info(
            f"Starting USAspending {log_label} extraction from dump",
            extra={
                "dump_path": str(dump_path),
                "duckdb_path": config.duckdb.database_path,
                "source": "S3_dump",
            },
        )

        try:
            dump_success = extractor.import_postgres_dump(dump_path, table_name)
            if dump_success:
                context.log.info(f"Successfully imported {log_label} from S3 dump")
        except Exception as e:
            context.log.warning(f"Dump import failed: {e}")
            dump_success = False

    # FALLBACK: If dump failed, try API (for recipient_lookup only)
    if not dump_success and table_name == "raw_usaspending_recipients":
        context.log.warning("S3 dump unavailable, falling back to USAspending API (FALLBACK)")
        try:
            # Note: API fallback would need to be implemented to fetch recipients
            # from ..enrichers.usaspending import USAspendingAPIClient
            # Note: API fallback would need to be implemented to fetch recipients
            # For now, we'll raise an error to indicate API fallback is needed
            context.log.error(
                "API fallback not yet implemented for bulk recipient data. S3 dump is required."
            )
            raise ExtractionError(
                "USAspending data unavailable: S3 dump failed and API fallback not implemented for bulk data",
                component="assets.usaspending_ingestion",
                operation="import_table",
                details={
                    "table_name": table_name,
                    "s3_attempted": s3_bucket is not None,
                    "dump_path_attempted": str(dump_path) if dump_path else None,
                },
            )
        except ImportError:
            context.log.error("USAspending API client not available")
            raise ExtractionError(
                "USAspending data unavailable: S3 dump failed and API client not available",
                component="assets.usaspending_ingestion",
                operation="import_table",
                details={"table_name": table_name},
            )

    # FAIL: If dump failed and no API fallback available
    if not dump_success:
        raise ExtractionError(
            f"Failed to import USAspending {log_label}: S3 dump unavailable and no fallback",
            component="assets.usaspending_ingestion",
            operation="import_dump",
            details={
                "dump_path": str(dump_path) if dump_path else None,
                "table_name": table_name,
                "s3_bucket": s3_bucket,
            },
        )

    physical_table = extractor.resolve_physical_table_name(table_name)
    table_info = extractor.get_table_info(physical_table)
    sample_df = extractor.query_awards(table_name=physical_table, limit=100)

    context.log.info(
        f"{log_label.replace('_', ' ').title()} extraction complete",
        extra={
            "logical_table": table_name,
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
    Load USAspending recipient_lookup table.

    Priority:
    1. Parquet extract (~500MB) - preferred, fast
    2. Full database dump (217GB) - fallback, slow

    Returns:
        pandas DataFrame with recipient data
    """
    from ..utils.cloud_storage import find_latest_recipient_lookup_parquet

    s3_bucket = get_s3_bucket_from_env()
    df = None

    # PRIORITY 1: Try parquet extract (fast, ~500MB)
    if s3_bucket:
        parquet_url = find_latest_recipient_lookup_parquet(bucket=s3_bucket)
        if parquet_url:
            try:
                context.log.info(f"Loading recipient_lookup from parquet: {parquet_url}")
                parquet_path = resolve_data_path(parquet_url)
                df = pd.read_parquet(parquet_path)
                context.log.info(f"Loaded {len(df)} recipients from parquet")
            except Exception as e:
                context.log.warning(f"Parquet load failed: {e}, falling back to dump")
                df = None

    # PRIORITY 2: Fall back to full dump extraction
    if df is None:
        context.log.info("Falling back to full USAspending dump extraction")
        result = _import_usaspending_table(
            context,
            log_label="recipient_lookup",
            table_name="raw_usaspending_recipients",
        )
        df = result.value

    # Verify expected columns exist
    required_cols = ["legal_business_name", "uei", "duns"]
    missing_cols = [col for col in required_cols if col not in df.columns]

    if missing_cols:
        context.log.warning(
            f"Missing expected columns: {missing_cols}. "
            "This may indicate old test data or schema mismatch."
        )
        for col in missing_cols:
            df[col] = None

    context.log.info(f"Loaded {len(df)} recipient records with columns: {list(df.columns)}")

    metadata = {
        "num_records": len(df),
        "columns": list(df.columns),
        "source": "parquet" if parquet_url else "dump",
        "preview": MetadataValue.md(df.head(10).to_markdown()),
    }

    return Output(value=df, metadata=metadata)


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
