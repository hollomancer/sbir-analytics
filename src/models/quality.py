"""Pydantic models for data quality reporting."""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, ConfigDict


class QualitySeverity(str, Enum):
    """Severity levels for quality issues."""

    ERROR = "error"
    WARNING = "warning"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class QualityIssue(BaseModel):
    """Individual data quality issue."""

    field: str = Field(..., description="Field name with the issue")
    # Make these optional to match validators which may omit value/expected/rule
    value: Any | None = Field(None, description="Actual value that caused the issue")
    expected: Any | None = Field(None, description="Expected value or format")
    message: str = Field(..., description="Human-readable error message")
    severity: QualitySeverity = Field(..., description="Issue severity level")
    rule: str | None = Field(None, description="Validation rule that failed")

    model_config = ConfigDict(validate_assignment=True, use_enum_values=True)


class QualityReport(BaseModel):
    """Comprehensive data quality report."""

    # Metadata
    record_id: str = Field(..., description="Identifier for the record checked")
    stage: str = Field(..., description="Pipeline stage where check was performed")
    timestamp: str = Field(..., description="When the check was performed")

    # Quality metrics
    total_fields: int = Field(..., description="Total number of fields checked")
    valid_fields: int = Field(..., description="Number of valid fields")
    invalid_fields: int = Field(..., description="Number of invalid fields")

    # Issues by severity
    issues: list[QualityIssue] = Field(default_factory=list, description="List of quality issues")

    # Summary statistics
    completeness_score: float = Field(..., ge=0.0, le=1.0, description="Completeness percentage")
    validity_score: float = Field(..., ge=0.0, le=1.0, description="Validity percentage")
    overall_score: float = Field(..., ge=0.0, le=1.0, description="Overall quality score")

    # Pass/fail status
    passed: bool = Field(..., description="Whether record passed quality checks")

    model_config = ConfigDict(validate_assignment=True)


class EnrichmentResult(BaseModel):
    """Result of data enrichment operation."""

    # Metadata
    record_id: str = Field(..., description="Identifier for the enriched record")
    source: str = Field(..., description="Data source used for enrichment")
    timestamp: str = Field(..., description="When enrichment was performed")

    # Enrichment details
    fields_enriched: list[str] = Field(
        default_factory=list, description="Fields that were enriched"
    )
    enrichment_success: bool = Field(..., description="Whether enrichment was successful")

    # Data added
    enriched_data: dict[str, Any] = Field(
        default_factory=dict, description="New data added during enrichment"
    )

    # Quality metrics
    confidence_score: float | None = Field(
        None, ge=0.0, le=1.0, description="Confidence in enrichment accuracy"
    )

    # Error information
    error_message: str | None = Field(None, description="Error message if enrichment failed")

    model_config = ConfigDict(validate_assignment=True)


class DataQualitySummary(BaseModel):
    """Summary of data quality across multiple records."""

    # Metadata
    stage: str = Field(..., description="Pipeline stage")
    run_id: str = Field(..., description="Pipeline run identifier")
    timestamp: str = Field(..., description="When summary was generated")

    # Aggregate statistics
    total_records: int = Field(..., description="Total number of records processed")
    valid_records: int = Field(..., description="Number of records that passed quality checks")
    invalid_records: int = Field(..., description="Number of records that failed quality checks")

    # Quality scores
    average_completeness: float = Field(
        ..., ge=0.0, le=1.0, description="Average completeness score"
    )
    average_validity: float = Field(..., ge=0.0, le=1.0, description="Average validity score")
    average_overall_score: float = Field(
        ..., ge=0.0, le=1.0, description="Average overall quality score"
    )

    # Issue breakdown
    issues_by_severity: dict[str, int] = Field(
        default_factory=dict, description="Count of issues by severity"
    )
    issues_by_field: dict[str, int] = Field(
        default_factory=dict, description="Count of issues by field"
    )
    issues_by_rule: dict[str, int] = Field(
        default_factory=dict, description="Count of issues by validation rule"
    )

    # Threshold compliance
    completeness_threshold_met: bool = Field(
        ..., description="Whether completeness threshold was met"
    )
    validity_threshold_met: bool = Field(..., description="Whether validity threshold was met")

    model_config = ConfigDict(validate_assignment=True)
