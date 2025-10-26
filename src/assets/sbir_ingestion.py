"""Dagster assets for SBIR data ingestion pipeline."""

import json
from pathlib import Path
from typing import Any

import pandas as pd
from dagster import (
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

from ..config.loader import get_config
from ..extractors.sbir import SbirDuckDBExtractor
from ..validators.sbir_awards import validate_sbir_awards


@asset(
    description="Raw SBIR awards extracted from CSV via DuckDB",
    group_name="sbir_ingestion",
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

    # Initialize extractor
    extractor = SbirDuckDBExtractor(
        csv_path=sbir_config.csv_path,
        duckdb_path=sbir_config.database_path,
        table_name=sbir_config.table_name,
    )

    # Import CSV to DuckDB
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

    # Extract all records
    df = extractor.extract_all()

    # Get table statistics
    table_stats = extractor.get_table_stats()

    context.log.info(f"Extraction complete: {len(df)} records", extra=table_stats)

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
    }

    return Output(value=df, metadata=metadata)


@asset(
    description="Validated SBIR awards (passed quality checks)",
    group_name="sbir_ingestion",
    compute_kind="pandas",
)
def validated_sbir_awards(
    context: AssetExecutionContext, raw_sbir_awards: pd.DataFrame
) -> Output[pd.DataFrame]:
    """
    Validate SBIR awards and filter to passing records.

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

    # Run validation
    quality_report = validate_sbir_awards(
        df=raw_sbir_awards, pass_rate_threshold=pass_rate_threshold
    )

    # Filter to passing records (no ERROR issues)
    error_rows = set(
        issue.row_index for issue in quality_report.issues if issue.severity.value == "ERROR"
    )

    validated_df = raw_sbir_awards[~raw_sbir_awards.index.isin(error_rows)].copy()

    context.log.info(
        "Validation complete",
        extra={
            "total_records": quality_report.total_records,
            "passed_records": quality_report.passed_records,
            "failed_records": quality_report.failed_records,
            "pass_rate": f"{quality_report.pass_rate:.1%}",
            "total_issues": len(quality_report.issues),
            "validation_passed": quality_report.passed,
        },
    )

    # Create metadata
    metadata = {
        "num_records": len(validated_df),
        "pass_rate": f"{quality_report.pass_rate:.1%}",
        "passed_records": quality_report.passed_records,
        "failed_records": quality_report.failed_records,
        "total_issues": len(quality_report.issues),
        "validation_status": "PASSED" if quality_report.passed else "FAILED",
        "threshold": f"{pass_rate_threshold:.1%}",
    }

    return Output(value=validated_df, metadata=metadata)


@asset(
    description="SBIR data quality validation report",
    group_name="sbir_ingestion",
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

    # Convert to dictionary
    report_dict = {
        "total_records": quality_report.total_records,
        "passed_records": quality_report.passed_records,
        "failed_records": quality_report.failed_records,
        "pass_rate": quality_report.pass_rate,
        "threshold": quality_report.threshold,
        "passed": quality_report.passed,
        "issues": [
            {
                "severity": issue.severity.value,
                "field": issue.field,
                "message": issue.message,
                "row_index": issue.row_index,
            }
            for issue in quality_report.issues
        ],
    }

    # Group issues by severity and field
    issues_by_severity = {}
    issues_by_field = {}

    for issue in quality_report.issues:
        severity = issue.severity.value
        field = issue.field

        issues_by_severity[severity] = issues_by_severity.get(severity, 0) + 1
        issues_by_field[field] = issues_by_field.get(field, 0) + 1

    report_dict["issues_by_severity"] = issues_by_severity
    report_dict["issues_by_field"] = issues_by_field

    # Write report to file
    report_path = Path("data/validated/sbir_validation_report.json")
    report_path.parent.mkdir(parents=True, exist_ok=True)

    with open(report_path, "w") as f:
        json.dump(report_dict, f, indent=2)

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

    return Output(value=report_dict, metadata=metadata)


@asset_check(
    asset=validated_sbir_awards,
    additional_ins={"raw_sbir_awards": AssetIn()},
    description="Verify SBIR data quality meets threshold",
)
def sbir_data_quality_check(
    context: AssetExecutionContext,
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
        passed=passed, severity=severity, description=description, metadata=metadata
    )
