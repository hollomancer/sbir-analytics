"""Configuration schemas using Pydantic for type-safe configuration."""

from typing import Dict, List, Optional

from pydantic import BaseModel, Field, validator


class DataQualityConfig(BaseModel):
    """Configuration for data quality checks."""

    completeness: Dict[str, float] = Field(
        default_factory=lambda: {
            "award_id": 1.00,
            "company_name": 0.95,
            "award_amount": 0.90,
            "award_date": 0.95,
            "program": 0.98,
        }
    )
    uniqueness: Dict[str, float] = Field(
        default_factory=lambda: {
            "award_id": 1.00,
        }
    )
    validity: Dict[str, float] = Field(
        default_factory=lambda: {
            "award_amount_min": 0.0,
            "award_amount_max": 5000000.0,
            "award_year_min": 1983,
            "award_year_max": 2030,
        }
    )
    enrichment: Dict[str, float] = Field(
        default_factory=lambda: {
            "sam_gov_success_rate": 0.85,
            "usaspending_match_rate": 0.70,
        }
    )

    @validator("completeness", "uniqueness", "enrichment")
    def validate_percentage(cls, v):
        """Validate that percentage values are between 0 and 1."""
        for key, value in v.items():
            if not (0.0 <= value <= 1.0):
                raise ValueError(f"{key} must be between 0.0 and 1.0, got {value}")
        return v


class EnrichmentConfig(BaseModel):
    """Configuration for data enrichment services."""

    sam_gov: Dict[str, str] = Field(
        default_factory=lambda: {
            "base_url": "https://api.sam.gov/entity-information/v3",
            "api_key_env_var": "SAM_GOV_API_KEY",
            "rate_limit_per_minute": "60",
            "timeout_seconds": "30",
            "retry_attempts": "3",
            "retry_backoff_seconds": "1",
        }
    )
    usaspending_api: Dict[str, str] = Field(
        default_factory=lambda: {
            "base_url": "https://api.usaspending.gov/api/v2",
            "timeout_seconds": "30",
            "retry_attempts": "3",
            "retry_backoff_seconds": "2",
        }
    )


class Neo4jConfig(BaseModel):
    """Configuration for Neo4j database connection."""

    uri_env_var: str = "NEO4J_URI"
    user_env_var: str = "NEO4J_USER"
    password_env_var: str = "NEO4J_PASSWORD"
    batch_size: int = 1000
    parallel_threads: int = 4
    create_constraints: bool = True
    create_indexes: bool = True
    transaction_timeout_seconds: int = 300
    retry_on_deadlock: bool = True
    max_deadlock_retries: int = 3


class ExtractionConfig(BaseModel):
    """Configuration for data extraction."""

    sbir: Dict[str, str] = Field(
        default_factory=lambda: {
            "date_format": "%m/%d/%Y",
            "encoding": "utf-8",
            "chunk_size": "10000",
        }
    )
    usaspending: Dict[str, str] = Field(
        default_factory=lambda: {
            "database_name": "usaspending",
            "table_name": "awards",
            "import_chunk_size": "50000",
        }
    )


class ValidationConfig(BaseModel):
    """Configuration for data validation."""

    strict_schema: bool = True
    fail_on_first_error: bool = False
    sample_size_for_checks: int = 1000
    max_error_percentage: float = 0.05

    @validator("max_error_percentage")
    def validate_error_percentage(cls, v):
        """Validate that error percentage is between 0 and 1."""
        if not (0.0 <= v <= 1.0):
            raise ValueError(f"max_error_percentage must be between 0.0 and 1.0, got {v}")
        return v


class TransformationConfig(BaseModel):
    """Configuration for data transformation."""

    company_deduplication: Dict[str, str] = Field(
        default_factory=lambda: {
            "similarity_threshold": "0.85",
            "min_company_name_length": "3",
        }
    )
    award_normalization: Dict[str, str] = Field(
        default_factory=lambda: {
            "currency": "USD",
            "standardize_program_names": "true",
        }
    )
    graph_preparation: Dict[str, str] = Field(
        default_factory=lambda: {
            "batch_size": "1000",
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


class MetricsConfig(BaseModel):
    """Configuration for metrics collection."""

    enabled: bool = True
    collection_interval_seconds: int = 30
    persist_to_file: bool = True
    metrics_file_path: str = "logs/metrics.json"
    warning_thresholds: Dict[str, str] = Field(
        default_factory=lambda: {
            "stage_duration_seconds": "3600",
            "memory_usage_mb": "2048",
            "error_rate_percentage": "5.0",
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

    pipeline: Dict[str, str] = Field(
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

    class Config:
        """Pydantic configuration."""
        validate_assignment = True
        extra = "forbid"