"""Root PipelineConfig composed from modular schema components."""

from __future__ import annotations

from collections.abc import Mapping
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
from .runtime import (
    CLIConfig,
    CompanyCategorizationConfig,
    LoggingConfig,
    MetricsConfig,
    PathsConfig,
)


class PipelineMetadata(BaseModel, Mapping[str, Any]):
    """Metadata for the configured pipeline with dual dict/attribute access."""

    name: str = Field(default="sbir-analytics", description="Pipeline identifier")
    version: str = Field(default="0.1.0", description="Semantic version of the pipeline")
    environment: str = Field(default="development", description="Active environment name")

    model_config = ConfigDict(extra="allow")

    def _as_mapping(self) -> dict[str, Any]:
        """Return the metadata as a plain dict (including extras)."""

        return self.model_dump(mode="python")

    def __getitem__(self, key: str) -> Any:
        data = self._as_mapping()
        if key in data:
            return data[key]
        raise KeyError(key)

    def __iter__(self):
        return iter(self._as_mapping())

    def __len__(self) -> int:
        return len(self._as_mapping())

    def __contains__(self, key: object) -> bool:
        return isinstance(key, str) and key in self._as_mapping()

    def get(self, key: str, default: Any = None) -> Any:
        return self._as_mapping().get(key, default)

    def items(self):  # type: ignore[override]
        return self._as_mapping().items()

    def keys(self):  # type: ignore[override]
        return self._as_mapping().keys()

    def values(self):  # type: ignore[override]
        return self._as_mapping().values()


class PipelineConfig(BaseModel):
    """Root configuration model for the SBIR ETL pipeline."""

    pipeline: PipelineMetadata = Field(default_factory=PipelineMetadata)

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
    "PipelineMetadata",
    "SbirDuckDBConfig",
    "SbirValidationConfig",
    "StatisticalReportingConfig",
    "TransformationConfig",
    "ValidationConfig",
]
