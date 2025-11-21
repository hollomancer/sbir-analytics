"""Pydantic models for statistical reporting.

This module defines data models for comprehensive statistical reporting
across pipeline runs, including pipeline metrics, module metrics, and
report collections for multi-format outputs.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from src.models.quality import ChangesSummary, DataHygieneMetrics


class ReportFormat(str, Enum):
    """Supported report output formats."""

    HTML = "html"
    JSON = "json"
    MARKDOWN = "markdown"
    EXECUTIVE = "executive"


class PerformanceMetrics(BaseModel):
    """Performance metrics for pipeline execution."""

    # Execution timing
    start_time: datetime = Field(..., description="Pipeline start timestamp")
    end_time: datetime = Field(..., description="Pipeline end timestamp")
    duration: timedelta = Field(..., description="Total execution duration")

    # Throughput metrics
    records_per_second: float = Field(..., description="Overall processing throughput")
    peak_memory_mb: float = Field(..., description="Peak memory usage in MB")
    average_memory_mb: float = Field(..., description="Average memory usage in MB")

    # Resource utilization
    cpu_usage_percent: float | None = Field(None, description="Average CPU usage percentage")
    disk_io_mb: float | None = Field(None, description="Total disk I/O in MB")

    # Error and retry metrics
    total_retries: int = Field(
        default=0, description="Total number of retries across all operations"
    )
    failed_operations: int = Field(default=0, description="Number of failed operations")

    model_config = ConfigDict(validate_assignment=True)


class ModuleMetrics(BaseModel):
    """Metrics for individual pipeline modules."""

    # Module identification
    module_name: str = Field(..., description="Name of the pipeline module")
    run_id: str = Field(..., description="Pipeline run identifier")
    stage: str = Field(
        ..., description="Pipeline stage (extract, validate, enrich, transform, load)"
    )

    # Execution metrics
    execution_time: timedelta = Field(..., description="Module execution duration")
    start_time: datetime = Field(..., description="Module start timestamp")
    end_time: datetime = Field(..., description="Module end timestamp")

    # Record processing
    records_in: int = Field(..., description="Number of input records")
    records_out: int = Field(..., description="Number of output records")
    records_processed: int = Field(..., description="Number of successfully processed records")
    records_failed: int = Field(default=0, description="Number of failed records")

    # Success metrics
    success_rate: float = Field(
        ..., ge=0.0, le=1.0, description="Processing success rate (0.0-1.0)"
    )
    throughput_records_per_second: float = Field(..., description="Processing throughput")

    # Quality metrics
    quality_metrics: dict[str, float] = Field(
        default_factory=dict, description="Module-specific quality scores"
    )
    data_hygiene: DataHygieneMetrics | None = Field(
        None, description="Data hygiene metrics if applicable"
    )
    changes_summary: ChangesSummary | None = Field(
        None, description="Summary of changes made if applicable"
    )

    # Enrichment-specific metrics (optional)
    enrichment_coverage: float | None = Field(
        None, ge=0.0, le=1.0, description="Percentage of records successfully enriched"
    )
    match_rates: dict[str, float] | None = Field(
        None, description="Match rates by enrichment source"
    )

    # Memory and performance
    peak_memory_mb: float | None = Field(
        None, description="Peak memory usage during module execution"
    )
    average_cpu_percent: float | None = Field(None, description="Average CPU usage percentage")

    # Module-specific metrics
    module_specific_metrics: dict[str, Any] = Field(
        default_factory=dict, description="Additional module-specific metrics"
    )

    model_config = ConfigDict(validate_assignment=True)


class PipelineMetrics(BaseModel):
    """Overall pipeline statistics and metrics."""

    # Pipeline identification
    run_id: str = Field(..., description="Unique pipeline run identifier")
    pipeline_name: str = Field(default="sbir-analytics", description="Name of the pipeline")
    environment: str = Field(default="development", description="Execution environment")

    # Timing information
    timestamp: datetime = Field(..., description="Pipeline execution timestamp")
    duration: timedelta = Field(..., description="Total pipeline execution duration")

    # Overall processing metrics
    total_records_processed: int = Field(
        ..., description="Total records processed across all modules"
    )
    overall_success_rate: float = Field(
        ..., ge=0.0, le=1.0, description="Overall pipeline success rate"
    )

    # Quality scores
    quality_scores: dict[str, float] = Field(
        default_factory=dict, description="Aggregate quality scores by category"
    )

    # Module metrics
    module_metrics: dict[str, ModuleMetrics] = Field(
        default_factory=dict, description="Metrics for each pipeline module"
    )

    # Performance metrics
    performance_metrics: PerformanceMetrics = Field(..., description="Pipeline performance metrics")

    # Data coverage and completeness
    data_coverage_metrics: dict[str, float] = Field(
        default_factory=dict, description="Data coverage metrics by source/type"
    )

    # Technology transition metrics (if applicable)
    transition_metrics: dict[str, Any] | None = Field(
        None, description="Technology transition analysis metrics"
    )

    # Ecosystem insights (if applicable)
    ecosystem_metrics: dict[str, Any] | None = Field(
        None, description="SBIR ecosystem analysis metrics"
    )

    model_config = ConfigDict(validate_assignment=True)


class ReportArtifact(BaseModel):
    """Individual report artifact (file) information."""

    # File information
    format: ReportFormat = Field(..., description="Report format type")
    file_path: Path = Field(..., description="Path to the generated report file")
    file_size_bytes: int = Field(..., description="File size in bytes")

    # Generation metadata
    generated_at: datetime = Field(..., description="When the artifact was generated")
    generation_duration_seconds: float = Field(
        ..., description="Time taken to generate the artifact"
    )

    # Content metadata
    contains_interactive_elements: bool = Field(
        default=False, description="Whether the report contains interactive elements"
    )
    contains_visualizations: bool = Field(
        default=False, description="Whether the report contains charts/graphs"
    )

    # Accessibility and sharing
    is_public_safe: bool = Field(
        default=True, description="Whether the report is safe for public sharing"
    )
    requires_authentication: bool = Field(
        default=False, description="Whether the report requires authentication to view"
    )

    model_config = ConfigDict(validate_assignment=True)


class ReportCollection(BaseModel):
    """Collection of multi-format report outputs."""

    # Collection metadata
    collection_id: str = Field(..., description="Unique identifier for this report collection")
    run_id: str = Field(..., description="Pipeline run identifier")
    generated_at: datetime = Field(..., description="When the collection was generated")

    # Report artifacts
    artifacts: list[ReportArtifact] = Field(
        default_factory=list, description="List of generated report artifacts"
    )

    # Format availability
    available_formats: list[ReportFormat] = Field(
        default_factory=list, description="List of available report formats"
    )

    # Collection statistics
    total_artifacts: int = Field(default=0, description="Total number of artifacts in collection")
    total_size_bytes: int = Field(default=0, description="Total size of all artifacts")

    # Generation performance
    total_generation_time_seconds: float = Field(
        default=0.0, description="Total time to generate all artifacts"
    )

    # Output configuration
    output_directory: Path = Field(..., description="Base directory for report outputs")
    retention_policy_days: int | None = Field(
        None, description="Number of days to retain reports (None = indefinite)"
    )

    # CI/CD integration metadata
    ci_context: dict[str, Any] | None = Field(
        None, description="CI/CD context information if applicable"
    )
    pr_comment_generated: bool = Field(
        default=False, description="Whether a PR comment was generated"
    )
    artifacts_uploaded: bool = Field(
        default=False, description="Whether artifacts were uploaded to CI system"
    )

    def get_artifact_by_format(self, format: ReportFormat) -> ReportArtifact | None:
        """Get artifact by format type.

        Args:
            format: The report format to find

        Returns:
            ReportArtifact if found, None otherwise
        """
        for artifact in self.artifacts:
            if artifact.format == format:
                return artifact
        return None

    def get_primary_artifact_paths(self) -> dict[str, Path]:
        """Get paths to primary artifacts by format.

        Returns:
            Dictionary mapping format names to file paths
        """
        return {artifact.format.value: artifact.file_path for artifact in self.artifacts}

    def calculate_totals(self) -> None:
        """Calculate and update total statistics from artifacts."""
        self.total_artifacts = len(self.artifacts)
        self.total_size_bytes = sum(artifact.file_size_bytes for artifact in self.artifacts)
        self.total_generation_time_seconds = sum(
            artifact.generation_duration_seconds for artifact in self.artifacts
        )
        self.available_formats = [artifact.format for artifact in self.artifacts]

    model_config = ConfigDict(validate_assignment=True)


class ExecutiveSummary(BaseModel):
    """Executive-level summary for program managers and stakeholders."""

    # Summary metadata
    summary_id: str = Field(..., description="Unique identifier for this executive summary")
    run_id: str = Field(..., description="Pipeline run identifier")
    generated_at: datetime = Field(..., description="When the summary was generated")

    # High-level impact metrics
    total_funding_analyzed: float = Field(..., description="Total SBIR funding analyzed (USD)")
    companies_tracked: int = Field(..., description="Number of companies tracked")
    patents_linked: int = Field(..., description="Number of patents linked to SBIR awards")
    technology_areas_covered: int = Field(..., description="Number of CET technology areas covered")

    # Program effectiveness metrics
    funding_roi_indicators: dict[str, float] = Field(
        default_factory=dict, description="Return on investment indicators"
    )
    commercialization_rates: dict[str, float] = Field(
        default_factory=dict, description="Commercialization success rates by sector"
    )

    # Success stories
    success_story_count: int = Field(default=0, description="Number of identified success stories")
    high_impact_transitions: list[dict[str, Any]] = Field(
        default_factory=list, description="High-impact technology transition examples"
    )

    # Comparative analysis
    program_goals_comparison: dict[str, Any] = Field(
        default_factory=dict, description="Comparison against program goals and benchmarks"
    )
    historical_trends: dict[str, Any] = Field(
        default_factory=dict, description="Historical trend analysis"
    )

    # Geographic and temporal insights
    geographic_distribution: dict[str, Any] = Field(
        default_factory=dict, description="Geographic distribution of innovation activities"
    )
    temporal_patterns: dict[str, Any] = Field(
        default_factory=dict, description="Temporal patterns in funding and outcomes"
    )

    # Key performance indicators
    kpis: dict[str, float] = Field(
        default_factory=dict, description="Key performance indicators for executive reporting"
    )

    model_config = ConfigDict(validate_assignment=True)
ModuleMetrics.model_rebuild()
PipelineMetrics.model_rebuild()
