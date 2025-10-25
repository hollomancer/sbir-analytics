"""Data quality validation functions."""

from typing import Any

import pandas as pd

from ..config.loader import get_config
from ..models import QualityIssue, QualityReport, QualitySeverity


def check_completeness(
    df: pd.DataFrame, required_fields: list[str], threshold: float = 0.95
) -> list[QualityIssue]:
    """Check completeness of required fields.

    Args:
        df: DataFrame to check
        required_fields: List of fields that must be non-null
        threshold: Minimum completeness ratio required

    Returns:
        List of quality issues found
    """
    issues = []

    for field in required_fields:
        if field not in df.columns:
            issues.append(
                QualityIssue(
                    field=field,
                    value=None,
                    expected="column exists",
                    message=f"Required field '{field}' is missing from dataset",
                    severity=QualitySeverity.CRITICAL,
                    rule="completeness_check",
                )
            )
            continue

        non_null_count = df[field].notna().sum()
        total_count = len(df)
        completeness_ratio = non_null_count / total_count if total_count > 0 else 0

        if completeness_ratio < threshold:
            issues.append(
                QualityIssue(
                    field=field,
                    value=f"{non_null_count}/{total_count}",
                    expected=f">={threshold:.1%}",
                    message=f"Field '{field}' completeness ({completeness_ratio:.1%}) below threshold ({threshold:.1%})",
                    severity=(
                        QualitySeverity.HIGH if completeness_ratio < 0.8 else QualitySeverity.MEDIUM
                    ),
                    rule="completeness_check",
                )
            )

    return issues


def check_uniqueness(
    df: pd.DataFrame, fields: list[str], case_sensitive: bool = True
) -> list[QualityIssue]:
    """Check uniqueness of field combinations.

    Args:
        df: DataFrame to check
        fields: List of fields to check for uniqueness
        case_sensitive: Whether uniqueness check is case sensitive

    Returns:
        List of quality issues found
    """
    issues = []

    # Check if all fields exist
    missing_fields = [field for field in fields if field not in df.columns]
    if missing_fields:
        issues.append(
            QualityIssue(
                field=str(missing_fields),
                value=None,
                expected="columns exist",
                message=f"Fields required for uniqueness check are missing: {missing_fields}",
                severity=QualitySeverity.CRITICAL,
                rule="uniqueness_check",
            )
        )
        return issues

    # Create combined key for uniqueness check
    subset_df = df[fields].copy()

    if not case_sensitive:
        # Convert string columns to lowercase for case-insensitive comparison
        for col in subset_df.select_dtypes(include=["object"]).columns:
            subset_df[col] = subset_df[col].astype(str).str.lower()

    # Find duplicates
    duplicates = subset_df[subset_df.duplicated(keep=False)]

    if not duplicates.empty:
        duplicate_count = len(duplicates)
        total_count = len(df)
        duplicate_ratio = duplicate_count / total_count

        issues.append(
            QualityIssue(
                field=str(fields),
                value=f"{duplicate_count} duplicates",
                expected="0 duplicates",
                message=f"Found {duplicate_count} duplicate records ({duplicate_ratio:.1%}) for fields: {fields}",
                severity=QualitySeverity.HIGH if duplicate_ratio > 0.1 else QualitySeverity.MEDIUM,
                rule="uniqueness_check",
            )
        )

    return issues


def check_value_ranges(
    df: pd.DataFrame,
    field: str,
    min_value: float | None = None,
    max_value: float | None = None,
    allowed_values: list[Any] | None = None,
) -> list[QualityIssue]:
    """Check if field values are within acceptable ranges.

    Args:
        df: DataFrame to check
        field: Field name to validate
        min_value: Minimum allowed value
        max_value: Maximum allowed value
        allowed_values: List of allowed values

    Returns:
        List of quality issues found
    """
    issues = []

    if field not in df.columns:
        issues.append(
            QualityIssue(
                field=field,
                value=None,
                expected="column exists",
                message=f"Field '{field}' does not exist for range validation",
                severity=QualitySeverity.CRITICAL,
                rule="value_range_check",
            )
        )
        return issues

    series = df[field]

    # Check allowed values
    if allowed_values is not None:
        invalid_values = series[~series.isin(allowed_values)].dropna()
        if not invalid_values.empty:
            unique_invalid = invalid_values.unique()[:5]  # Show first 5 examples
            issues.append(
                QualityIssue(
                    field=field,
                    value=list(unique_invalid),
                    expected=allowed_values,
                    message=f"Found {len(invalid_values)} values not in allowed list: {list(unique_invalid)}",
                    severity=QualitySeverity.HIGH,
                    rule="value_range_check",
                )
            )

    # Check numeric ranges
    if min_value is not None or max_value is not None:
        # Try to convert to numeric
        try:
            numeric_series = pd.to_numeric(series, errors="coerce")

            if min_value is not None:
                below_min = numeric_series < min_value
                if below_min.any():
                    min_violations = below_min.sum()
                    issues.append(
                        QualityIssue(
                            field=field,
                            value=f"min: {numeric_series.min()}",
                            expected=f">= {min_value}",
                            message=f"Found {min_violations} values below minimum {min_value}",
                            severity=QualitySeverity.MEDIUM,
                            rule="value_range_check",
                        )
                    )

            if max_value is not None:
                above_max = numeric_series > max_value
                if above_max.any():
                    max_violations = above_max.sum()
                    issues.append(
                        QualityIssue(
                            field=field,
                            value=f"max: {numeric_series.max()}",
                            expected=f"<= {max_value}",
                            message=f"Found {max_violations} values above maximum {max_value}",
                            severity=QualitySeverity.MEDIUM,
                            rule="value_range_check",
                        )
                    )

        except (ValueError, TypeError):
            issues.append(
                QualityIssue(
                    field=field,
                    value="non-numeric",
                    expected="numeric",
                    message=f"Cannot perform range check on non-numeric field '{field}'",
                    severity=QualitySeverity.LOW,
                    rule="value_range_check",
                )
            )

    return issues


def validate_sbir_awards(df: pd.DataFrame, config: dict[str, Any] | None = None) -> QualityReport:
    """Comprehensive validation of SBIR awards data.

    Args:
        df: DataFrame containing SBIR awards data
        config: Validation configuration (uses default config if None)

    Returns:
        QualityReport with validation results
    """
    if config is None:
        app_config = get_config()
        config = {
            "completeness": app_config.data_quality.completeness,
            "uniqueness": app_config.data_quality.uniqueness,
            "validity": app_config.data_quality.validity,
        }

    all_issues = []
    total_fields = 0
    valid_fields = 0

    # Completeness checks
    completeness_config = config.get("completeness", {})
    for field, threshold in completeness_config.items():
        issues = check_completeness(df, [field], threshold)
        all_issues.extend(issues)
        total_fields += 1
        if not issues:
            valid_fields += 1

    # Uniqueness checks
    uniqueness_config = config.get("uniqueness", {})
    for field in uniqueness_config:
        issues = check_uniqueness(df, [field])
        all_issues.extend(issues)
        total_fields += 1
        if not issues:
            valid_fields += 1

    # Value range checks
    validity_config = config.get("validity", {})
    award_amount_min = validity_config.get("award_amount_min")
    award_amount_max = validity_config.get("award_amount_max")

    if "award_amount" in df.columns:
        issues = check_value_ranges(
            df, "award_amount", min_value=award_amount_min, max_value=award_amount_max
        )
        all_issues.extend(issues)
        total_fields += 1
        if not issues:
            valid_fields += 1

    # Calculate scores
    completeness_score = valid_fields / total_fields if total_fields > 0 else 1.0
    validity_score = 1.0 - (len(all_issues) / max(total_fields, 1))
    overall_score = (completeness_score + validity_score) / 2

    # Determine if passed
    critical_issues = [issue for issue in all_issues if issue.severity == QualitySeverity.CRITICAL]
    passed = len(critical_issues) == 0

    return QualityReport(
        record_id="sbir_awards_dataset",
        stage="validation",
        timestamp=pd.Timestamp.now().isoformat(),
        total_fields=total_fields,
        valid_fields=valid_fields,
        invalid_fields=total_fields - valid_fields,
        completeness_score=completeness_score,
        validity_score=validity_score,
        overall_score=overall_score,
        issues=all_issues,
        passed=passed,
    )
