"""Root PipelineConfig composed from modular schema components."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .data_pipeline import (
    DataQualityConfig,
    DuckDBConfig,
    ExtractionConfig,
    Neo4jConfig,
    SbirDuckDBConfig,
    SbirValidationConfig,
    TransformationConfig,
    ValidationConfig,
)
from .enrichment import EnrichmentConfig, EnrichmentRefreshConfig
from .fiscal import FiscalAnalysisConfig
from .reporting import StatisticalReportingConfig
from .runtime import CLIConfig, CompanyCategorizationConfig, LoggingConfig, MetricsConfig, PathsConfig


class PipelineConfig(BaseModel):
    """Root configuration model for the SBIR ETL pipeline."""

    pipeline: dict[str, Any] = Field(
        default_factory=lambda: {
            "name": "sbir-analytics",
            "version": "0.1.0",
            "environment": "development",
        }
    )

    paths: PathsConfig = Field(default_factory=PathsConfig, description="File system paths")
    data_quality: DataQualityConfig = Field(default_factory=DataQualityConfig)
    enrichment: EnrichmentConfig = Field(default_factory=EnrichmentConfig)
    enrichment_refresh: EnrichmentRefreshConfig = Field(
        default_factory=EnrichmentRefreshConfig,
        description="Iterative enrichment refresh configuration",
    )
    neo4j: Neo4jConfig = Field(default_factory=Neo4jConfig)
    extraction: ExtractionConfig = Field(default_factory=ExtractionConfig)
    validation: ValidationConfig = Field(default_factory=ValidationConfig)
    transformation: TransformationConfig = Field(default_factory=TransformationConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    metrics: MetricsConfig = Field(default_factory=MetricsConfig)
    duckdb: DuckDBConfig = Field(default_factory=DuckDBConfig)
    statistical_reporting: StatisticalReportingConfig = Field(
        default_factory=StatisticalReportingConfig
    )
    fiscal_analysis: FiscalAnalysisConfig = Field(default_factory=FiscalAnalysisConfig)
    cli: CLIConfig = Field(default_factory=CLIConfig, description="CLI interface configuration")
    company_categorization: CompanyCategorizationConfig = Field(
        default_factory=CompanyCategorizationConfig,
        description="Company categorization configuration",
    )

    model_config = ConfigDict(
        validate_assignment=True,
        extra="allow",
    )


__all__ = [
    "CLIConfig",
    "CompanyCategorizationConfig",
    "DataQualityConfig",
    "DuckDBConfig",
    "EnrichmentConfig",
    "EnrichmentRefreshConfig",
    "ExtractionConfig",
    "FiscalAnalysisConfig",
    "LoggingConfig",
    "MetricsConfig",
    "Neo4jConfig",
    "PathsConfig",
    "PipelineConfig",
    "SbirDuckDBConfig",
    "SbirValidationConfig",
    "StatisticalReportingConfig",
    "TransformationConfig",
    "ValidationConfig",
]
