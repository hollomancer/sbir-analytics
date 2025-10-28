"""Pydantic models for data quality reporting."""

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


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
    row_index: int | None = Field(None, description="Row index in the dataset")

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


class InsightRecommendation(BaseModel):
    """Automated insight or recommendation based on data quality analysis."""

    # Metadata
    category: str = Field(..., description="Category of insight (quality, performance, coverage)")
    priority: QualitySeverity = Field(..., description="Priority level of the recommendation")

    # Insight details
    title: str = Field(..., description="Brief title of the insight")
    message: str = Field(..., description="Detailed explanation of the insight")
    affected_metrics: list[str] = Field(
        default_factory=list, description="Metrics that triggered this insight"
    )

    # Context
    current_value: float | None = Field(None, description="Current metric value")
    expected_value: float | None = Field(None, description="Expected or baseline value")
    deviation: float | None = Field(None, description="Deviation from expected (%)")

    # Action items
    recommendations: list[str] = Field(
        default_factory=list, description="List of actionable recommendations"
    )

    model_config = ConfigDict(validate_assignment=True, use_enum_values=True)


class DataHygieneMetrics(BaseModel):
    """Metrics describing data cleanliness and quality distribution."""

    # Clean vs dirty split
    total_records: int = Field(..., description="Total number of records analyzed")
    clean_records: int = Field(..., description="Records passing all quality checks")
    dirty_records: int = Field(..., description="Records with quality issues")
    clean_percentage: float = Field(
        ..., ge=0.0, le=100.0, description="Percentage of clean records"
    )

    # Quality score distribution
    quality_score_mean: float = Field(..., ge=0.0, le=1.0, description="Mean quality score")
    quality_score_median: float = Field(..., ge=0.0, le=1.0, description="Median quality score")
    quality_score_std: float = Field(
        ..., ge=0.0, description="Standard deviation of quality scores"
    )
    quality_score_min: float = Field(..., ge=0.0, le=1.0, description="Minimum quality score")
    quality_score_max: float = Field(..., ge=0.0, le=1.0, description="Maximum quality score")

    # Validation results
    validation_pass_rate: float = Field(
        ..., ge=0.0, le=1.0, description="Proportion of records passing validation"
    )
    validation_errors: int = Field(..., description="Number of validation errors")
    validation_warnings: int = Field(..., description="Number of validation warnings")

    # Field-level quality
    field_quality_scores: dict[str, float] = Field(
        default_factory=dict, description="Quality score per field"
    )
    field_completeness: dict[str, float] = Field(
        default_factory=dict, description="Completeness percentage per field"
    )

    # Threshold compliance
    thresholds_met: dict[str, bool] = Field(
        default_factory=dict, description="Whether each threshold was met"
    )

    model_config = ConfigDict(validate_assignment=True)


class ChangesSummary(BaseModel):
    """Summary of changes made to data during processing."""

    # Record-level changes
    total_records: int = Field(..., description="Total number of records processed")
    records_modified: int = Field(..., description="Number of records that were modified")
    records_unchanged: int = Field(..., description="Number of records that remained unchanged")
    modification_rate: float = Field(
        ..., ge=0.0, le=1.0, description="Proportion of records modified"
    )

    # Field-level changes
    fields_added: list[str] = Field(default_factory=list, description="Fields added to records")
    fields_modified: list[str] = Field(
        default_factory=list, description="Existing fields that were modified"
    )
    fields_removed: list[str] = Field(
        default_factory=list, description="Fields removed from records"
    )

    # Change counts
    field_modification_counts: dict[str, int] = Field(
        default_factory=dict, description="Number of modifications per field"
    )

    # Enrichment coverage
    enrichment_coverage: dict[str, float] = Field(
        default_factory=dict, description="Enrichment coverage percentage per field"
    )
    enrichment_sources: dict[str, int] = Field(
        default_factory=dict, description="Count of records enriched from each source"
    )

    # Examples
    sample_changes: list[dict[str, Any]] = Field(
        default_factory=list, description="Sample before/after comparisons for manual review"
    )

    model_config = ConfigDict(validate_assignment=True)


class ModuleReport(BaseModel):
    """Base class for module-specific statistical reports."""

    # Metadata
    module_name: str = Field(..., description="Name of the module (sbir, patent, transition, cet)")
    run_id: str = Field(..., description="Pipeline run identifier")
    timestamp: str = Field(..., description="When the report was generated")
    stage: str = Field(..., description="Pipeline stage")

    # Processing statistics
    total_records: int = Field(..., description="Total number of records processed")
    records_processed: int = Field(..., description="Records successfully processed")
    records_failed: int = Field(..., description="Records that failed processing")
    success_rate: float = Field(..., ge=0.0, le=1.0, description="Processing success rate")

    # Duration and performance
    duration_seconds: float = Field(..., description="Processing duration in seconds")
    throughput_records_per_second: float = Field(..., description="Processing throughput")

    # Quality metrics
    data_hygiene: DataHygieneMetrics | None = Field(
        None, description="Data hygiene metrics if applicable"
    )
    changes_summary: ChangesSummary | None = Field(
        None, description="Summary of changes made if applicable"
    )

    # Module-specific metrics (to be extended by subclasses)
    module_metrics: dict[str, Any] = Field(
        default_factory=dict, description="Module-specific metrics"
    )

    model_config = ConfigDict(validate_assignment=True)


class StatisticalReport(BaseModel):
    """Comprehensive statistical report aggregating multiple modules."""

    # Metadata
    report_id: str = Field(..., description="Unique identifier for this report")
    run_id: str = Field(..., description="Pipeline run identifier")
    timestamp: str = Field(..., description="When the report was generated")
    report_type: str = Field(..., description="Type of report (unified, module-specific)")

    # Overall pipeline statistics
    total_records_processed: int = Field(..., description="Total records across all modules")
    total_duration_seconds: float = Field(..., description="Total pipeline duration")
    overall_success_rate: float = Field(..., ge=0.0, le=1.0, description="Overall success rate")

    # Module reports
    module_reports: list[ModuleReport] = Field(
        default_factory=list, description="Individual module reports"
    )

    # Aggregate quality metrics
    aggregate_data_hygiene: DataHygieneMetrics | None = Field(
        None, description="Aggregated data hygiene metrics"
    )
    aggregate_changes: ChangesSummary | None = Field(None, description="Aggregated changes summary")

    # Insights and recommendations
    insights: list[InsightRecommendation] = Field(
        default_factory=list, description="Automated insights and recommendations"
    )

    # Quality trends (if historical data available)
    quality_trends: dict[str, Any] = Field(
        default_factory=dict, description="Quality trends over time"
    )

    # Report metadata
    report_formats: list[str] = Field(
        default_factory=list, description="Available report formats (html, json, markdown)"
    )
    report_paths: dict[str, str] = Field(
        default_factory=dict, description="File paths to generated report artifacts"
    )

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
