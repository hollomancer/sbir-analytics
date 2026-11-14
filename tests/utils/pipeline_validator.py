"""Test-support pipeline validator.

This module validates extraction and enrichment stages in the SBIR ETL pipeline.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

import pandas as pd
from sbir_etl.models.quality import QualitySeverity


class ValidationStage(StrEnum):
    """Pipeline stages that can be validated."""

    EXTRACTION = "extraction"
    VALIDATION = "validation"
    ENRICHMENT = "enrichment"
    TRANSFORMATION = "transformation"
    LOADING = "loading"


class ValidationStatus(StrEnum):
    """Validation result status."""

    PASSED = "passed"
    FAILED = "failed"
    WARNING = "warning"
    SKIPPED = "skipped"


@dataclass
class ValidationCheck:
    """Individual validation check result."""

    name: str
    status: ValidationStatus
    message: str
    expected: Any | None = None
    actual: Any | None = None
    threshold: float | None = None
    severity: QualitySeverity = QualitySeverity.MEDIUM
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class StageValidationResult:
    """Validation result for a single pipeline stage."""

    stage: ValidationStage
    status: ValidationStatus
    duration_seconds: float
    checks: list[ValidationCheck] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def passed_checks(self) -> list[ValidationCheck]:
        """Get all checks that passed."""
        return [c for c in self.checks if c.status == ValidationStatus.PASSED]

    @property
    def failed_checks(self) -> list[ValidationCheck]:
        """Get all checks that failed."""
        return [c for c in self.checks if c.status == ValidationStatus.FAILED]

    @property
    def warning_checks(self) -> list[ValidationCheck]:
        """Get all checks with warnings."""
        return [c for c in self.checks if c.status == ValidationStatus.WARNING]


class PipelineValidator:
    """Comprehensive pipeline validator for E2E testing."""

    def validate_extraction_stage(
        self,
        raw_data: pd.DataFrame,
        expected_columns: list[str] | None = None,
        min_records: int = 1,
        max_records: int | None = None,
    ) -> StageValidationResult:
        """Validate data extraction stage.

        Args:
            raw_data: Raw extracted DataFrame
            expected_columns: List of expected column names
            min_records: Minimum expected record count
            max_records: Maximum expected record count

        Returns:
            StageValidationResult with extraction validation results
        """
        start_time = datetime.now()
        checks = []

        # Record count validation
        record_count = len(raw_data)
        if record_count < min_records:
            checks.append(
                ValidationCheck(
                    name="minimum_record_count",
                    status=ValidationStatus.FAILED,
                    message=f"Record count {record_count} below minimum {min_records}",
                    expected=min_records,
                    actual=record_count,
                    severity=QualitySeverity.CRITICAL,
                )
            )
        else:
            checks.append(
                ValidationCheck(
                    name="minimum_record_count",
                    status=ValidationStatus.PASSED,
                    message=f"Record count {record_count} meets minimum requirement",
                    expected=min_records,
                    actual=record_count,
                )
            )

        if max_records and record_count > max_records:
            checks.append(
                ValidationCheck(
                    name="maximum_record_count",
                    status=ValidationStatus.WARNING,
                    message=f"Record count {record_count} exceeds expected maximum {max_records}",
                    expected=max_records,
                    actual=record_count,
                    severity=QualitySeverity.LOW,
                )
            )

        # Column validation
        if expected_columns:
            missing_columns = set(expected_columns) - set(raw_data.columns)
            if missing_columns:
                checks.append(
                    ValidationCheck(
                        name="required_columns",
                        status=ValidationStatus.FAILED,
                        message=f"Missing required columns: {list(missing_columns)}",
                        expected=expected_columns,
                        actual=list(raw_data.columns),
                        severity=QualitySeverity.CRITICAL,
                    )
                )
            else:
                checks.append(
                    ValidationCheck(
                        name="required_columns",
                        status=ValidationStatus.PASSED,
                        message="All required columns present",
                        expected=expected_columns,
                        actual=list(raw_data.columns),
                    )
                )

        # Data type validation
        null_columns = raw_data.columns[raw_data.isnull().all()].tolist()
        if null_columns:
            checks.append(
                ValidationCheck(
                    name="null_columns",
                    status=ValidationStatus.WARNING,
                    message=f"Columns with all null values: {null_columns}",
                    actual=null_columns,
                    severity=QualitySeverity.MEDIUM,
                )
            )

        # Schema compliance check
        duplicate_columns = raw_data.columns[raw_data.columns.duplicated()].tolist()
        if duplicate_columns:
            checks.append(
                ValidationCheck(
                    name="duplicate_columns",
                    status=ValidationStatus.FAILED,
                    message=f"Duplicate column names found: {duplicate_columns}",
                    actual=duplicate_columns,
                    severity=QualitySeverity.HIGH,
                )
            )

        duration = (datetime.now() - start_time).total_seconds()

        # Determine overall status
        failed_checks = [c for c in checks if c.status == ValidationStatus.FAILED]
        overall_status = ValidationStatus.FAILED if failed_checks else ValidationStatus.PASSED

        return StageValidationResult(
            stage=ValidationStage.EXTRACTION,
            status=overall_status,
            duration_seconds=duration,
            checks=checks,
            metadata={
                "record_count": record_count,
                "column_count": len(raw_data.columns),
                "columns": list(raw_data.columns),
                "memory_usage_mb": raw_data.memory_usage(deep=True).sum() / 1024 / 1024,
            },
        )

    def validate_enrichment_stage(
        self,
        enriched_data: pd.DataFrame,
        original_data: pd.DataFrame,
        min_match_rate: float = 0.7,
        expected_enrichment_columns: list[str] | None = None,
    ) -> StageValidationResult:
        """Validate data enrichment stage.

        Args:
            enriched_data: Enriched DataFrame
            original_data: Original DataFrame before enrichment
            min_match_rate: Minimum acceptable match rate
            expected_enrichment_columns: Expected enrichment columns

        Returns:
            StageValidationResult with enrichment validation results
        """
        start_time = datetime.now()
        checks = []

        # Record count preservation
        original_count = len(original_data)
        enriched_count = len(enriched_data)

        if enriched_count != original_count:
            checks.append(
                ValidationCheck(
                    name="record_count_preservation",
                    status=ValidationStatus.FAILED,
                    message=f"Record count changed during enrichment: {original_count} -> {enriched_count}",
                    expected=original_count,
                    actual=enriched_count,
                    severity=QualitySeverity.HIGH,
                )
            )
        else:
            checks.append(
                ValidationCheck(
                    name="record_count_preservation",
                    status=ValidationStatus.PASSED,
                    message="Record count preserved during enrichment",
                    expected=original_count,
                    actual=enriched_count,
                )
            )

        # Enrichment columns validation
        if expected_enrichment_columns:
            missing_enrichment_cols = set(expected_enrichment_columns) - set(enriched_data.columns)
            if missing_enrichment_cols:
                checks.append(
                    ValidationCheck(
                        name="enrichment_columns",
                        status=ValidationStatus.FAILED,
                        message=f"Missing enrichment columns: {list(missing_enrichment_cols)}",
                        expected=expected_enrichment_columns,
                        actual=[
                            col for col in enriched_data.columns if col not in original_data.columns
                        ],
                        severity=QualitySeverity.HIGH,
                    )
                )
            else:
                checks.append(
                    ValidationCheck(
                        name="enrichment_columns",
                        status=ValidationStatus.PASSED,
                        message="All expected enrichment columns present",
                        expected=expected_enrichment_columns,
                        actual=[
                            col for col in enriched_data.columns if col not in original_data.columns
                        ],
                    )
                )

        # Match rate validation
        match_rate = self._calculate_match_rate(enriched_data)
        if match_rate < min_match_rate:
            checks.append(
                ValidationCheck(
                    name="match_rate",
                    status=ValidationStatus.FAILED,
                    message=f"Match rate {match_rate:.1%} below threshold {min_match_rate:.1%}",
                    expected=min_match_rate,
                    actual=match_rate,
                    threshold=min_match_rate,
                    severity=QualitySeverity.HIGH,
                )
            )
        else:
            checks.append(
                ValidationCheck(
                    name="match_rate",
                    status=ValidationStatus.PASSED,
                    message=f"Match rate {match_rate:.1%} meets threshold",
                    expected=min_match_rate,
                    actual=match_rate,
                    threshold=min_match_rate,
                )
            )

        # Quality metrics validation
        quality_metrics = self._calculate_enrichment_quality_metrics(enriched_data)

        duration = (datetime.now() - start_time).total_seconds()

        # Determine overall status
        failed_checks = [c for c in checks if c.status == ValidationStatus.FAILED]
        overall_status = ValidationStatus.FAILED if failed_checks else ValidationStatus.PASSED

        return StageValidationResult(
            stage=ValidationStage.ENRICHMENT,
            status=overall_status,
            duration_seconds=duration,
            checks=checks,
            metadata={
                "match_rate": match_rate,
                "quality_metrics": quality_metrics,
                "enrichment_columns": [
                    col for col in enriched_data.columns if col not in original_data.columns
                ],
            },
        )

    def _calculate_match_rate(self, enriched_data: pd.DataFrame) -> float:
        """Calculate enrichment match rate from enriched data."""
        if len(enriched_data) == 0:
            return 0.0

        # Look for common enrichment match columns
        match_columns = [col for col in enriched_data.columns if "match" in col.lower()]
        if not match_columns:
            return 0.0

        # Use the first match column to determine match rate
        match_col = match_columns[0]
        matched_count = enriched_data[match_col].notna().sum()
        return matched_count / len(enriched_data)

    def _calculate_enrichment_quality_metrics(self, enriched_data: pd.DataFrame) -> dict[str, Any]:
        """Calculate quality metrics for enriched data."""
        metrics = {}

        # Match method distribution
        match_method_col = None
        for col in enriched_data.columns:
            if "match_method" in col.lower():
                match_method_col = col
                break

        if match_method_col:
            method_counts = enriched_data[match_method_col].value_counts()
            metrics["match_methods"] = method_counts.to_dict()

        # Match score statistics
        match_score_col = None
        for col in enriched_data.columns:
            if "match_score" in col.lower():
                match_score_col = col
                break

        if match_score_col:
            scores = enriched_data[match_score_col].dropna()
            if len(scores) > 0:
                metrics["match_score_stats"] = {
                    "mean": float(scores.mean()),
                    "median": float(scores.median()),
                    "min": float(scores.min()),
                    "max": float(scores.max()),
                    "std": float(scores.std()) if len(scores) > 1 else 0.0,
                }

        return metrics
