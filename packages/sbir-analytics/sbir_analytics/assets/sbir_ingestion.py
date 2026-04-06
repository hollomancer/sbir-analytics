"""Dagster assets for SBIR data ingestion pipeline."""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from dagster import (
    AssetCheckExecutionContext,
    AssetCheckResult,
    AssetCheckSeverity,
    AssetExecutionContext,
    AssetIn,
    MetadataValue,
    Output,
    asset,
    asset_check,
)
from loguru import logger

from sbir_etl.config.loader import get_config
from sbir_etl.extractors.sbir import SbirDuckDBExtractor
from sbir_etl.utils.monitoring import performance_monitor
from sbir_etl.validators.sbir_awards import validate_sbir_awards


def _apply_quality_filters(
    df: pd.DataFrame, context: AssetExecutionContext
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Apply structural quality filters and return an audit trail.

    Returns:
        Tuple of (filtered DataFrame, audit dict). The audit dict records every
        transformation step with counts and a small sample of affected indices
        so that downstream consumers can trace what was modified or dropped
        without excessive memory overhead.
    """
    original_count = len(df)
    context.log.info(f"Starting quality filtering with {original_count} records")

    # Max indices to store per step (keeps memory bounded for large datasets)
    _SAMPLE_LIMIT = 50

    audit: dict[str, Any] = {
        "original_count": original_count,
        "steps": [],
    }

    # 1. Filter empty / placeholder award_id values
    if "award_id" in df.columns:
        before = len(df)
        empty_mask = df["award_id"].isna() | (df["award_id"] == "") | (df["award_id"] == "-")
        dropped_count = int(empty_mask.sum())
        sample_indices = df.index[empty_mask].tolist()[:_SAMPLE_LIMIT]
        df = df[~empty_mask].copy()
        after = len(df)
        audit["steps"].append({
            "name": "empty_award_id",
            "dropped_count": dropped_count,
            "sample_indices": sample_indices,
        })
        if before != after:
            context.log.info(f"Empty award_id filter: {before} -> {after} ({after / before:.1%})")

    # 2. Coerce award_amount to numeric (records modified, not dropped)
    amount_coerced_count = 0
    if "award_amount" in df.columns:
        before_numeric = pd.to_numeric(df["award_amount"], errors="coerce")
        # Count values that were non-numeric and got coerced to NaN
        was_non_null = df["award_amount"].notna()
        became_null = before_numeric.isna()
        amount_coerced_count = int((was_non_null & became_null).sum())
        df["award_amount"] = before_numeric
        audit["steps"].append({
            "name": "award_amount_coercion",
            "coerced_to_nan_count": amount_coerced_count,
        })

    # 3. Coerce award_date to datetime (records modified, not dropped)
    date_coerced_count = 0
    if "award_date" in df.columns:
        before_dates = pd.to_datetime(df["award_date"], errors="coerce")
        was_non_null = df["award_date"].notna()
        became_null = before_dates.isna()
        date_coerced_count = int((was_non_null & became_null).sum())
        df["award_date"] = before_dates
        audit["steps"].append({
            "name": "award_date_coercion",
            "coerced_to_nat_count": date_coerced_count,
        })

    # 4. Remove exact duplicates (award_id + phase or award_id only)
    if "award_id" in df.columns and "phase" in df.columns:
        before = len(df)
        dup_mask = df.duplicated(subset=["award_id", "phase"], keep="first")
        dropped_count = int(dup_mask.sum())
        sample_indices = df.index[dup_mask].tolist()[:_SAMPLE_LIMIT]
        df = df[~dup_mask].copy()
        after = len(df)
        audit["steps"].append({
            "name": "dedup_award_id_phase",
            "dropped_count": dropped_count,
            "sample_indices": sample_indices,
        })
        if before != after:
            context.log.info(
                f"Duplicate filter (award_id + phase): {before} -> {after} ({after / before:.1%})"
            )
    elif "award_id" in df.columns:
        before = len(df)
        dup_mask = df.duplicated(subset=["award_id"], keep="first")
        dropped_count = int(dup_mask.sum())
        sample_indices = df.index[dup_mask].tolist()[:_SAMPLE_LIMIT]
        df = df[~dup_mask].copy()
        after = len(df)
        audit["steps"].append({
            "name": "dedup_award_id",
            "dropped_count": dropped_count,
            "sample_indices": sample_indices,
        })
        if before != after:
            context.log.info(
                f"Duplicate filter (award_id only): {before} -> {after} ({after / before:.1%})"
            )

    final_count = len(df)
    total_dropped = original_count - final_count
    retention_rate = final_count / original_count if original_count else 1.0

    audit["final_count"] = final_count
    audit["total_dropped"] = total_dropped
    audit["retention_rate"] = retention_rate
    audit["total_coerced_fields"] = amount_coerced_count + date_coerced_count

    context.log.info(
        f"Quality filtering complete: {final_count} records ({retention_rate:.1%} retention), "
        f"{total_dropped} dropped, {audit['total_coerced_fields']} fields coerced"
    )

    return df, audit


def _save_to_s3(df: pd.DataFrame, s3_key: str, context: AssetExecutionContext) -> str | None:
    """Save DataFrame to S3 as parquet. Returns S3 URI or None if not configured."""
    bucket = os.getenv("S3_BUCKET")
    if not bucket:
        context.log.info("S3_BUCKET not set, skipping S3 persistence")
        return None

    try:
        import boto3
        import io

        # Convert to parquet in memory
        buffer = io.BytesIO()
        df.to_parquet(buffer, index=False)
        buffer.seek(0)

        # Upload to S3
        s3 = boto3.client("s3", region_name=os.getenv("AWS_REGION", "us-east-2"))
        s3.put_object(Bucket=bucket, Key=s3_key, Body=buffer.getvalue())

        s3_uri = f"s3://{bucket}/{s3_key}"
        context.log.info(f"Saved to S3: {s3_uri}")
        return s3_uri
    except Exception as e:
        context.log.warning(f"Failed to save to S3: {e}")
        return None


@asset(
    description="Raw SBIR awards extracted from CSV via DuckDB",
    group_name="extraction",
    compute_kind="duckdb",
)
def raw_sbir_awards(context: AssetExecutionContext) -> Output[pd.DataFrame]:
    """
    Extract raw SBIR award data from CSV using DuckDB.

    Returns:
        pandas DataFrame with all raw SBIR records
    """
    # Get configuration
    config = get_config()
    sbir_config = config.extraction.sbir

    context.log.info(
        "Starting SBIR extraction",
        extra={
            "csv_path": sbir_config.csv_path,
            "duckdb_path": sbir_config.database_path,
            "table_name": sbir_config.table_name,
        },
    )

    # Initialize extractor with S3-first support
    extractor = SbirDuckDBExtractor(
        csv_path=sbir_config.csv_path,
        duckdb_path=sbir_config.database_path,
        table_name=sbir_config.table_name,
        csv_path_s3=sbir_config.csv_path_s3,
        use_s3_first=sbir_config.use_s3_first,
    )

    # Import CSV to DuckDB with performance monitoring
    with performance_monitor.monitor_block("sbir_import_csv"):
        import_metadata = extractor.import_csv()

    context.log.info("CSV import complete", extra=import_metadata)

    # Log column mapping (CSV column -> normalized field) for observability on first extraction
    actual_columns = import_metadata.get("columns", []) or []
    # Best-effort normalized field names (lowercase snake_case) for easier consumption in UI
    column_mapping = {
        col: col.strip().lower().replace(" ", "_").replace("-", "_") for col in actual_columns
    }
    try:
        context.log.info("Column mapping discovered", extra={"column_mapping": column_mapping})
    except Exception:
        # In non-Dagster contexts context.log may not accept 'extra' the same way; swallow safely
        logger.info("Column mapping discovered", column_mapping)

    # Extract all records with performance monitoring
    with performance_monitor.monitor_block("sbir_extract_all"):
        df = extractor.extract_all()

    # Get table statistics
    table_stats = extractor.get_table_stats()

    context.log.info(f"Extraction complete: {len(df)} records", extra=table_stats)

    # Get performance metrics
    perf_summary = performance_monitor.get_metrics_summary()
    import_perf = perf_summary.get("sbir_import_csv", {})
    extract_perf = perf_summary.get("sbir_extract_all", {})

    # Calculate combined extraction metrics
    total_import_duration = import_perf.get("total_duration", 0.0)
    total_extract_duration = extract_perf.get("total_duration", 0.0)
    total_extraction_duration = total_import_duration + total_extract_duration
    import_peak_memory = import_perf.get("max_peak_memory_mb", 0.0)
    extract_peak_memory = extract_perf.get("max_peak_memory_mb", 0.0)
    total_peak_memory = max(import_peak_memory, extract_peak_memory)

    # Create metadata for Dagster UI
    metadata = {
        "num_records": len(df),
        "num_columns": len(df.columns),
        "file_size_mb": import_metadata.get("file_size_mb"),
        "import_duration_seconds": import_metadata.get("import_duration_seconds"),
        "records_per_second": import_metadata.get("records_per_second"),
        "year_range": table_stats.get("year_range"),
        "unique_agencies": table_stats.get("unique_agencies"),
        "phase_distribution": MetadataValue.json(table_stats.get("phase_distribution", [])),
        # Include extraction timestamps and discovered columns/mapping for traceability
        "extraction_start_utc": import_metadata.get("extraction_start_utc")
        or import_metadata.get("import_start"),
        "extraction_end_utc": import_metadata.get("extraction_end_utc")
        or import_metadata.get("import_end"),
        "column_mapping": MetadataValue.json(column_mapping),
        "columns": MetadataValue.json(import_metadata.get("columns", [])),
        "preview": MetadataValue.md(df.head(10).to_markdown()),
        # Performance metrics
        "performance_import_duration_seconds": round(total_import_duration, 2),
        "performance_extract_duration_seconds": round(total_extract_duration, 2),
        "performance_total_duration_seconds": round(total_extraction_duration, 2),
        "performance_peak_memory_mb": round(total_peak_memory, 2),
    }

    # Normalize column names for downstream processing
    # This ensures validation and other steps can use consistent column names
    column_normalization_map = {
        "Agency Tracking Number": "award_id",
        "Company": "company_name",
        "Award Amount": "award_amount",
        "Proposal Award Date": "award_date",
        "Program": "program",
        "Award Title": "award_title",
        "Agency": "agency",
        "Branch": "branch",
        "Phase": "phase",
        "Contract": "contract",
        "UEI": "uei",
        "Duns": "duns",
        "Address1": "address1",
        "Address2": "address2",
        "City": "city",
        "State": "state",
        "Zip": "zip",
        "Abstract": "abstract",
        "HUBZone Owned": "hubzone_owned",
        "Woman Owned": "woman_owned",
        "Socially and Economically Disadvantaged": "socially_and_economically_disadvantaged",
        "Number Employees": "number_employees",
        "PI Name": "pi_name",
        "PI Email": "pi_email",
        "RI Name": "ri_name",
    }

    # Apply column normalization
    df = df.rename(columns=column_normalization_map)

    # Stamp data source provenance on every record
    # Prefer the original S3 URL over the resolved temp/cache path
    ingested_at = datetime.now(timezone.utc)
    source_url = sbir_config.csv_path_s3 or str(extractor.csv_path)
    df["data_source"] = "sbir.gov"
    df["data_source_url"] = str(source_url)
    df["ingested_at"] = ingested_at

    # Update metadata to reflect normalized columns
    metadata["normalized_columns"] = MetadataValue.json(list(df.columns))
    metadata["column_normalization_applied"] = True

    return Output(value=df, metadata=metadata)  # type: ignore[arg-type]


@asset(
    description="Validated SBIR awards (passed quality checks)",
    group_name="extraction",
    compute_kind="pandas",
)
def validated_sbir_awards(
    context: AssetExecutionContext, raw_sbir_awards: pd.DataFrame
) -> Output[pd.DataFrame]:
    """
    Validate SBIR awards and filter to passing records.

    Quality filtering (empty IDs, duplicates, type coercion) is applied here
    rather than in raw_sbir_awards so that upstream validation reports reflect
    true source data quality.

    Args:
        raw_sbir_awards: Raw SBIR awards DataFrame

    Returns:
        DataFrame with only validated records
    """
    # Get configuration
    config = get_config()
    pass_rate_threshold = config.data_quality.sbir_awards.pass_rate_threshold

    context.log.info(
        f"Starting validation of {len(raw_sbir_awards)} records",
        extra={"pass_rate_threshold": pass_rate_threshold},
    )

    # Apply structural quality filters (empty IDs, duplicates, type coercion)
    # Returns audit trail with per-step drop counts and affected indices
    filtered_df, filter_audit = _apply_quality_filters(raw_sbir_awards, context)

    # Run validation on the filtered data
    quality_report = validate_sbir_awards(
        df=filtered_df, pass_rate_threshold=pass_rate_threshold
    )

    # Filter to passing records using failing_row_indices (fast path) or
    # fall back to issue-based filtering for backward compatibility
    failing_indices = getattr(quality_report, "failing_row_indices", None)
    if failing_indices is None:
        # Fallback: extract from issues. QualityIssue uses use_enum_values=True,
        # so severity is stored as a string value (e.g. "error"), not the enum.
        failing_indices = {
            issue.row_index
            for issue in quality_report.issues
            if issue.severity == "error" and issue.row_index is not None
        }

    validated_df = filtered_df[~filtered_df.index.isin(failing_indices)].copy()

    context.log.info(
        "Validation complete",
        extra={
            "total_records": quality_report.total_records,  # type: ignore[attr-defined]
            "passed_records": quality_report.passed_records,  # type: ignore[attr-defined]
            "failed_records": quality_report.failed_records,  # type: ignore[attr-defined]
            "pass_rate": f"{quality_report.pass_rate:.1%}",  # type: ignore[attr-defined]
            "total_issues": len(quality_report.issues),
            "validation_passed": quality_report.passed,
        },
    )

    # Save to S3 for downstream processing (e.g., Neo4j loading in GitHub Actions)
    s3_uri = _save_to_s3(validated_df, "validated/sbir_awards.parquet", context)

    # Build audit summary for metadata (strip sample indices for serialization —
    # keep counts and step names so Dagster UI shows a concise trail)
    audit_summary = {
        step["name"]: {
            k: v for k, v in step.items() if k != "sample_indices"
        }
        for step in filter_audit.get("steps", [])
    }
    audit_summary["totals"] = {
        "original_count": filter_audit["original_count"],
        "final_count": filter_audit["final_count"],
        "total_dropped": filter_audit["total_dropped"],
        "total_coerced_fields": filter_audit["total_coerced_fields"],
        "retention_rate": f"{filter_audit['retention_rate']:.1%}",
        "validation_failed_rows": len(failing_indices),
    }

    # Create metadata - convert numpy types to Python types for JSON serialization
    metadata = {
        "num_records": len(validated_df),
        "pass_rate": f"{quality_report.pass_rate:.1%}",  # type: ignore[attr-defined]
        "passed_records": int(quality_report.passed_records),  # type: ignore[attr-defined]
        "failed_records": int(quality_report.failed_records),  # type: ignore[attr-defined]
        "total_issues": len(quality_report.issues),
        "validation_status": "PASSED" if quality_report.passed else "FAILED",
        "threshold": f"{pass_rate_threshold:.1%}",
        "preprocessing_audit": MetadataValue.json(audit_summary),
    }
    if s3_uri:
        metadata["s3_uri"] = s3_uri

    return Output(value=validated_df, metadata=metadata)


@asset(
    description="SBIR data quality validation report",
    group_name="extraction",
    compute_kind="validation",
)
def sbir_validation_report(
    context: AssetExecutionContext, raw_sbir_awards: pd.DataFrame
) -> Output[dict[str, Any]]:
    """
    Generate comprehensive quality report for SBIR data.

    Args:
        raw_sbir_awards: Raw SBIR awards DataFrame

    Returns:
        QualityReport as dictionary
    """
    # Get configuration
    config = get_config()
    pass_rate_threshold = config.data_quality.sbir_awards.pass_rate_threshold

    # Run validation
    quality_report = validate_sbir_awards(
        df=raw_sbir_awards, pass_rate_threshold=pass_rate_threshold
    )

    # Convert to dictionary.
    # QualityIssue uses use_enum_values=True, so severity is stored as a string
    # (e.g. "error") rather than the enum member — access it directly.
    report_dict = {
        "total_records": quality_report.total_records,  # type: ignore[attr-defined]
        "passed_records": quality_report.passed_records,  # type: ignore[attr-defined]
        "failed_records": quality_report.failed_records,  # type: ignore[attr-defined]
        "pass_rate": quality_report.pass_rate,  # type: ignore[attr-defined]
        "passed": quality_report.passed,
        "issues": [
            {
                "severity": issue.severity,
                "field": issue.field,
                "message": issue.message,
                "row_index": issue.row_index,
            }
            for issue in quality_report.issues
        ],
    }

    # Group issues by severity and field
    issues_by_severity: dict[Any, Any] = {}
    issues_by_field: dict[Any, Any] = {}

    for issue in quality_report.issues:
        severity = issue.severity
        field = issue.field

        issues_by_severity[severity] = issues_by_severity.get(severity, 0) + 1
        issues_by_field[field] = issues_by_field.get(field, 0) + 1

    report_dict["issues_by_severity"] = issues_by_severity
    report_dict["issues_by_field"] = issues_by_field

    # Write report to file
    report_path = Path("data/validated/sbir_validation_report.json")
    report_path.parent.mkdir(parents=True, exist_ok=True)

    with open(report_path, "w") as f:
        json.dump(report_dict, f, indent=2, default=int)

    context.log.info(
        f"Validation report written to {report_path}",
        extra={
            "total_issues": len(quality_report.issues),
            "issues_by_severity": issues_by_severity,
            "top_5_fields_with_issues": dict(
                sorted(issues_by_field.items(), key=lambda x: x[1], reverse=True)[:5]
            ),
        },
    )

    # Create metadata
    metadata = {
        "report_path": str(report_path),
        "total_issues": len(quality_report.issues),
        "pass_rate": f"{quality_report.pass_rate:.1%}",
        "issues_by_severity": MetadataValue.json(issues_by_severity),
        "issues_by_field": MetadataValue.json(issues_by_field),
    }

    return Output(value=report_dict, metadata=metadata)  # type: ignore[arg-type]


@asset_check(
    asset=validated_sbir_awards,
    additional_ins={"raw_sbir_awards": AssetIn()},
    description="Verify SBIR data quality meets threshold",
)
def sbir_data_quality_check(
    context: AssetCheckExecutionContext,
    validated_sbir_awards: pd.DataFrame,
    raw_sbir_awards: pd.DataFrame,
) -> AssetCheckResult:
    """
    Asset check to ensure SBIR data quality meets configured threshold.

    This check will FAIL the asset if pass rate is below threshold,
    preventing downstream assets from running.
    """
    # Get configuration
    config = get_config()
    pass_rate_threshold = config.data_quality.sbir_awards.pass_rate_threshold

    # Calculate actual pass rate
    total_records = len(raw_sbir_awards)
    passed_records = len(validated_sbir_awards)
    actual_pass_rate = passed_records / total_records if total_records > 0 else 0.0

    # Determine if check passes
    passed = actual_pass_rate >= pass_rate_threshold

    # Create check result
    if passed:
        severity = AssetCheckSeverity.WARN
        description = f"✓ Data quality check passed: {actual_pass_rate:.1%} pass rate (threshold: {pass_rate_threshold:.1%})"
    else:
        severity = AssetCheckSeverity.ERROR
        description = f"✗ Data quality check FAILED: {actual_pass_rate:.1%} pass rate is below threshold of {pass_rate_threshold:.1%}"

    metadata = {
        "actual_pass_rate": f"{actual_pass_rate:.1%}",
        "threshold": f"{pass_rate_threshold:.1%}",
        "total_records": total_records,
        "passed_records": passed_records,
        "failed_records": total_records - passed_records,
    }

    context.log.info(f"Quality check result: {'PASSED' if passed else 'FAILED'}", extra=metadata)

    return AssetCheckResult(
        passed=passed,
        severity=severity,
        description=description,
        metadata=metadata,  # type: ignore[arg-type]
    )
