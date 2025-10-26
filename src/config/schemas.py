"""Configuration schemas using Pydantic for type-safe configuration.

This version relaxes several strict string-typed dict annotations to accept
non-string values (ints, floats, bools, etc.) and converts/coerces common
string-number inputs where appropriate. It also relaxes the root `PipelineConfig`
model to allow extra keys (previously `extra = "forbid"`), since environment
overrides and external config sources may supply heterogeneous types.
"""

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SbirValidationConfig(BaseModel):
    """SBIR-specific validation configuration."""

    pass_rate_threshold: float = Field(
        default=0.95, description="Minimum pass rate required (0.95 = 95%)"
    )
    completeness_threshold: float = Field(
        default=0.90, description="Completeness threshold for individual fields"
    )
    uniqueness_threshold: float = Field(
        default=0.99, description="Uniqueness threshold for Contract IDs"
    )

    @field_validator("pass_rate_threshold", "completeness_threshold", "uniqueness_threshold")
    @classmethod
    def validate_threshold(cls, v: float) -> float:
        """Validate that threshold is between 0.0 and 1.0."""
        if not (0.0 <= v <= 1.0):
            raise ValueError("Threshold must be between 0.0 and 1.0")
        return v


class SbirDuckDBConfig(BaseModel):
    """SBIR DuckDB extraction configuration."""

    csv_path: str = Field(
        default="data/raw/sbir/awards_data.csv", description="Path to SBIR CSV file"
    )
    database_path: str = Field(
        default=":memory:", description="DuckDB database path (:memory: for in-memory)"
    )
    table_name: str = Field(default="sbir_awards", description="DuckDB table name")
    batch_size: int = Field(default=10000, description="Batch size for chunked processing")
    encoding: str = Field(default="utf-8", description="CSV file encoding")


class DataQualityConfig(BaseModel):
    """Configuration for data quality checks."""

    sbir_awards: SbirValidationConfig = Field(
        default_factory=SbirValidationConfig, description="SBIR-specific validation thresholds"
    )
    # Allow numbers (int/float/bool) as well as strings for percentages and thresholds.
    completeness: dict[str, Any] = Field(
        default_factory=lambda: {
            "award_id": 1.00,
            "company_name": 0.95,
            "award_amount": 0.90,
            "award_date": 0.95,
            "program": 0.98,
        }
    )
    uniqueness: dict[str, Any] = Field(
        default_factory=lambda: {
            "award_id": 1.00,
        }
    )
    validity: dict[str, Any] = Field(
        default_factory=lambda: {
            "award_amount_min": 0.0,
            "award_amount_max": 5000000.0,
            "award_year_min": 1983,
            "award_year_max": 2030,
        }
    )
    enrichment: dict[str, Any] = Field(
        default_factory=lambda: {
            "sam_gov_success_rate": 0.85,
            "usaspending_match_rate": 0.70,
        }
    )

    @field_validator("completeness", "uniqueness", "enrichment")
    @classmethod
    def validate_percentage(cls, v: Mapping[str, Any]) -> dict[str, float]:
        """Validate and coerce percentage-like values to floats between 0 and 1.

        Accepts ints/floats/strings (e.g. "0.85" or 0.85) and converts strings to float.
        """
        if not isinstance(v, Mapping):
            raise TypeError("Expected a mapping for percentage configuration")
        out: dict[str, float] = {}
        for key, value in v.items():
            # Coerce strings like "0.85" or numeric types to float
            try:
                num = float(value)
            except (TypeError, ValueError):
                raise ValueError(f"{key} must be a number (0.0-1.0), got {value!r}")
            if not (0.0 <= num <= 1.0):
                raise ValueError(f"{key} must be between 0.0 and 1.0, got {num}")
            out[key] = num
        return out


class EnrichmentConfig(BaseModel):
    """Configuration for data enrichment services."""

    # Relaxed to accept numeric and boolean values if provided by environment vars.
    sam_gov: dict[str, Any] = Field(
        default_factory=lambda: {
            "base_url": "https://api.sam.gov/entity-information/v3",
            "api_key_env_var": "SAM_GOV_API_KEY",
            "rate_limit_per_minute": 60,
            "timeout_seconds": 30,
            "retry_attempts": 3,
            "retry_backoff_seconds": 1,
        }
    )
    usaspending_api: dict[str, Any] = Field(
        default_factory=lambda: {
            "base_url": "https://api.usaspending.gov/api/v2",
            "timeout_seconds": 30,
            "retry_attempts": 3,
            "retry_backoff_seconds": 2,
        }
    )


class Neo4jConfig(BaseModel):
    """Configuration for Neo4j database connection."""

    # Primary connection fields (application-level)
    uri: str = Field(default="bolt://localhost:7687", description="Neo4j Bolt URI")
    username: str = Field(default="neo4j", description="Neo4j username")
    password: str = Field(default="neo4j", description="Neo4j password")
    database: str = Field(default="neo4j", description="Neo4j database/catalog")

    # Backwards-compatible env-var key names retained for loader compatibility
    uri_env_var: str = "NEO4J_URI"
    user_env_var: str = "NEO4J_USER"
    password_env_var: str = "NEO4J_PASSWORD"

    # Performance / loading options
    batch_size: int = 1000
    parallel_threads: int = 4
    create_constraints: bool = True
    create_indexes: bool = True
    transaction_timeout_seconds: int = 300
    retry_on_deadlock: bool = True
    max_deadlock_retries: int = 3


class ExtractionConfig(BaseModel):
    """Configuration for data extraction."""

    sbir: SbirDuckDBConfig = Field(
        default_factory=SbirDuckDBConfig, description="SBIR extraction configuration"
    )
    # Allow import_chunk_size to be int if provided from numeric sources
    usaspending: dict[str, Any] = Field(
        default_factory=lambda: {
            "database_name": "usaspending",
            "table_name": "awards",
            "import_chunk_size": 50000,
        }
    )


class ValidationConfig(BaseModel):
    """Configuration for data validation."""

    strict_schema: bool = True
    fail_on_first_error: bool = False
    sample_size_for_checks: int = 1000
    max_error_percentage: float = 0.05

    @field_validator("max_error_percentage")
    @classmethod
    def validate_error_percentage(cls, v: Any) -> float:
        """Coerce and validate error percentage to be between 0 and 1."""
        try:
            num = float(v)
        except (TypeError, ValueError):
            raise ValueError(f"max_error_percentage must be numeric, got {v!r}")
        if not (0.0 <= num <= 1.0):
            raise ValueError(f"max_error_percentage must be between 0.0 and 1.0, got {num}")
        return num


class TransformationConfig(BaseModel):
    """Configuration for data transformation."""

    company_deduplication: dict[str, Any] = Field(
        default_factory=lambda: {
            "similarity_threshold": 0.85,
            "min_company_name_length": 3,
        }
    )
    award_normalization: dict[str, Any] = Field(
        default_factory=lambda: {
            "currency": "USD",
            "standardize_program_names": True,
        }
    )
    graph_preparation: dict[str, Any] = Field(
        default_factory=lambda: {
            "batch_size": 1000,
        }
    )


class LoggingConfig(BaseModel):
    """Configuration for logging."""

    level: str = "INFO"
    format: str = "json"
    file_path: str = "logs/sbir-etl.log"
    max_file_size_mb: int = 100
    backup_count: int = 5
    include_stage: bool = True
    include_run_id: bool = True
    include_timestamps: bool = True

    # Flags controlling output destinations; present so environment overrides work predictably
    console_enabled: bool = True
    file_enabled: bool = True

    @field_validator("format")
    @classmethod
    def _normalize_format(cls, v: str) -> str:
        """Normalize common format synonyms into the canonical values used by the app.

        Accepts 'pretty'/'text' -> 'text', 'json'/'structured' -> 'json'.
        """
        if not isinstance(v, str):
            return v
        vv = v.lower()
        if vv in ("pretty", "text", "plain"):
            return "text"
        if vv in ("json", "structured"):
            return "json"
        return v


class MetricsConfig(BaseModel):
    """Configuration for metrics collection."""

    enabled: bool = True
    collection_interval_seconds: int = 30
    persist_to_file: bool = True
    metrics_file_path: str = "logs/metrics.json"
    warning_thresholds: dict[str, Any] = Field(
        default_factory=lambda: {
            "stage_duration_seconds": 3600,
            "memory_usage_mb": 2048,
            "error_rate_percentage": 5.0,
        }
    )


class DuckDBConfig(BaseModel):
    """Configuration for DuckDB."""

    database_path: str = "data/processed/sbir.duckdb"
    memory_limit_gb: int = 4
    threads: int = 4
    enable_object_cache: bool = True
    enable_query_profiler: bool = False


class PipelineConfig(BaseModel):
    """Root configuration model for the SBIR ETL pipeline."""

    pipeline: dict[str, Any] = Field(
        default_factory=lambda: {
            "name": "sbir-etl",
            "version": "0.1.0",
            "environment": "development",
        }
    )

    data_quality: DataQualityConfig = Field(default_factory=DataQualityConfig)
    enrichment: EnrichmentConfig = Field(default_factory=EnrichmentConfig)
    neo4j: Neo4jConfig = Field(default_factory=Neo4jConfig)
    extraction: ExtractionConfig = Field(default_factory=ExtractionConfig)
    validation: ValidationConfig = Field(default_factory=ValidationConfig)
    transformation: TransformationConfig = Field(default_factory=TransformationConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    metrics: MetricsConfig = Field(default_factory=MetricsConfig)
    duckdb: DuckDBConfig = Field(default_factory=DuckDBConfig)

    model_config = ConfigDict(
        validate_assignment=True,
        extra="allow",
    )
