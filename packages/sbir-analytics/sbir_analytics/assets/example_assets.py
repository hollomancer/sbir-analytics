"""Example Dagster assets demonstrating the ETL pipeline structure.

This module contains example/demo assets used for:
- Testing the lazy import mechanism in src/assets/__init__.py
- Documentation and examples of asset patterns
- Development and learning purposes

NOTE: These assets use hardcoded example data and are NOT used in production pipelines.
They are kept for testing and documentation purposes only.
"""

import pandas as pd
from dagster import AssetCheckResult, AssetCheckSeverity, AssetExecutionContext, asset, asset_check
from loguru import logger

from ..models.quality import QualitySeverity
from ..quality.checks import validate_sbir_awards


@asset(
    description="Raw SBIR award data extracted from CSV files",
    group_name="extraction",
)
def raw_sbir_data(context: AssetExecutionContext) -> pd.DataFrame:
    """Extract raw SBIR award data from CSV files.

    This is an example asset that demonstrates data extraction.
    In production, this would read from actual SBIR CSV files.

    Args:
        context: Dagster asset execution context

    Returns:
        DataFrame containing raw SBIR award data
    """
    logger.info("Extracting raw SBIR data")

    # Example data - in production this would read from actual CSV
    data = pd.DataFrame(
        {
            "award_id": ["AWARD001", "AWARD002", "AWARD003"],
            "agency": ["DOD", "NIH", "NSF"],
            "award_amount": [150000.0, 200000.0, 175000.0],
            "award_date": ["2023-01-15", "2023-02-20", "2023-03-10"],
            "company_name": ["Tech Innovations Inc", "BioMed Solutions", "AI Research Corp"],
            "project_title": [
                "Advanced Sensor Technology",
                "Novel Drug Delivery System",
                "Machine Learning Framework",
            ],
        }
    )

    context.log.info(f"Extracted {len(data)} raw SBIR award records")
    logger.info(f"Raw data shape: {data.shape}")

    return data


@asset(
    description="SBIR award data validated against quality rules",
    group_name="validation",
)
def validated_sbir_data(
    context: AssetExecutionContext,
    raw_sbir_data: pd.DataFrame,
) -> pd.DataFrame:
    """Validate SBIR award data against quality rules.

    Args:
        context: Dagster asset execution context
        raw_sbir_data: Raw SBIR data from extraction

    Returns:
        Validated DataFrame with quality report logged
    """
    logger.info("Validating SBIR data")

    # Run quality checks
    quality_report = validate_sbir_awards(
        raw_sbir_data.to_dict("records"),  # type: ignore[arg-type]
        config={
            "completeness": {"min_completeness": 0.95},
            "required_columns": ["award_id", "agency", "award_amount"],
        },
    )

    # Log quality issues
    critical_issues = [
        issue for issue in quality_report.issues if issue.severity == QualitySeverity.CRITICAL
    ]

    warning_issues = [
        issue for issue in quality_report.issues if issue.severity == QualitySeverity.WARNING
    ]

    context.log.info(
        f"Validation complete: {len(critical_issues)} critical issues, "
        f"{len(warning_issues)} warnings"
    )

    logger.info(f"Quality report: {quality_report.summary}")

    for issue in critical_issues[:5]:  # Log first 5 critical issues
        logger.warning(f"Critical issue: {issue.message}")

    # In production, you might filter out invalid records here
    # For this example, we return all data
    return raw_sbir_data


@asset_check(
    asset=validated_sbir_data,
    description="Check that data quality meets minimum thresholds",
)
def validated_data_quality_check(
    context: AssetExecutionContext,
    validated_sbir_data: pd.DataFrame,
) -> AssetCheckResult:
    """Asset check to verify data quality meets minimum standards.

    Args:
        context: Dagster asset execution context
        validated_sbir_data: Validated SBIR data

    Returns:
        Asset check result indicating pass/fail status
    """
    # Run quality validation
    quality_report = validate_sbir_awards(
        validated_sbir_data.to_dict("records"),  # type: ignore[arg-type]
        config={"completeness": {"min_completeness": 0.95}},
    )

    critical_issues = [
        issue for issue in quality_report.issues if issue.severity == QualitySeverity.CRITICAL
    ]

    passed = len(critical_issues) == 0

    severity = AssetCheckSeverity.WARN if not passed else AssetCheckSeverity.ERROR

    metadata = {
        "total_records": len(validated_sbir_data),
        "critical_issues": len(critical_issues),
        "total_issues": len(quality_report.issues),
        "completeness_score": quality_report.summary.get("completeness_score", 0.0),
    }

    return AssetCheckResult(
        passed=passed,
        severity=severity,
        metadata=metadata,
        description=(
            f"Quality check {'passed' if passed else 'failed'}: "
            f"{len(critical_issues)} critical issues found"
        ),
    )
