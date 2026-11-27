"""Modular configuration schemas for SBIR ETL.

Epistemic tier: primitives. The parent ``sbir_etl.config`` package routes all
configuration access through its loader and these schemas, and CLAUDE.md lists
``sbir_etl/config/`` as primitives.
"""

from .data import (
    CLIConfig,
    CompanyCategorizationConfig,
    DataQualityConfig,
    DuckDBConfig,
    ExtractionConfig,
    LoggingConfig,
    MetricsConfig,
    PathsConfig,
    SbirDuckDBConfig,
    SbirValidationConfig,
    TransformationConfig,
    ValidationConfig,
)
from .domain import (
    EnrichmentConfig,
    EnrichmentRefreshConfig,
    EnrichmentSourceConfig,
    FiscalAnalysisConfig,
    MADiscoveryConfig,
    MLConfig,
    ModernBertConfig,
    OTConsortiumConfig,
    SensitivityConfig,
    TaxParameterConfig,
)
from .pipeline import PipelineConfig, PipelineMetadata

EPISTEMIC_TIER = "primitives"


__all__ = [
    "CLIConfig",
    "CompanyCategorizationConfig",
    "DataQualityConfig",
    "DuckDBConfig",
    "EnrichmentConfig",
    "EnrichmentRefreshConfig",
    "EnrichmentSourceConfig",
    "ExtractionConfig",
    "FiscalAnalysisConfig",
    "LoggingConfig",
    "MADiscoveryConfig",
    "MetricsConfig",
    "MLConfig",
    "ModernBertConfig",
    "OTConsortiumConfig",
    "PathsConfig",
    "PipelineConfig",
    "PipelineMetadata",
    "SbirDuckDBConfig",
    "SbirValidationConfig",
    "SensitivityConfig",
    "TaxParameterConfig",
    "TransformationConfig",
    "ValidationConfig",
]
