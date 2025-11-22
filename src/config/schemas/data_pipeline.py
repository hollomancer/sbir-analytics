"""Schemas for core data pipeline components (extraction, validation, transformation)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, Field, field_validator

from .common import FloatRangeValidatorMixin, PercentageMappingMixin


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
    def validate_threshold(cls, value: float) -> float:
        """Validate that threshold is between 0.0 and 1.0."""
        if not (0.0 <= value <= 1.0):
            raise ValueError("Threshold must be between 0.0 and 1.0")
        return value


class SbirDuckDBConfig(BaseModel):
    """SBIR DuckDB extraction configuration."""

    csv_path: str = Field(
        default="data/raw/sbir/awards_data.csv",
        description="Path to SBIR CSV file (local fallback path)",
    )
    csv_path_s3: str | None = Field(
        default=None,
        description="S3 URL for SBIR CSV (auto-built from csv_path if bucket configured)",
    )
    use_s3_first: bool = Field(
        default=True, description="If True, try S3 first, fallback to local csv_path"
    )
    database_path: str = Field(
        default=":memory:", description="DuckDB database path (:memory: for in-memory)"
    )
    table_name: str = Field(default="sbir_awards", description="DuckDB table name")
    batch_size: int = Field(default=10000, description="Batch size for chunked processing")
    encoding: str = Field(default="utf-8", description="CSV file encoding")


class SamGovConfig(BaseModel):
    """SAM.gov parquet extraction configuration."""

    parquet_path: str = Field(
        default="data/raw/sam_gov/sam_entity_records.parquet",
        description="Path to SAM.gov parquet file (local fallback path)",
    )
    parquet_path_s3: str | None = Field(
        default=None,
        description="S3 URL for SAM.gov parquet (auto-built from parquet_path if bucket configured)",
    )
    use_s3_first: bool = Field(
        default=True, description="If True, try S3 first, fallback to local parquet_path"
    )
    batch_size: int = Field(default=10000, description="Batch size for chunked processing")


class DataQualityConfig(PercentageMappingMixin, BaseModel):
    """Configuration for data quality checks."""

    sbir_awards: SbirValidationConfig = Field(
        default_factory=SbirValidationConfig, description="SBIR-specific validation thresholds"
    )
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
    def validate_percentage(cls, value: Mapping[str, Any]) -> dict[str, float]:
        """Validate and coerce percentage-like values to floats between 0 and 1."""

        return cls._coerce_percentage_mapping(value, field_name="data_quality")


class Neo4jConfig(BaseModel):
    """Configuration for Neo4j connectivity."""

    uri: str = Field(default="bolt://localhost:7687")
    database: str = Field(default="neo4j")
    username: str = Field(default="neo4j")
    password_env_var: str = Field(default="NEO4J_PASSWORD")
    password: str | None = Field(default=None, description="Password (can be set from env var)")
    max_connection_lifetime: int = Field(default=3600)
    encrypted: bool = Field(default=False)
    verify_certificate: bool = Field(default=True)
    retries: int = Field(default=3)
    retry_delay_seconds: int = Field(default=5)
    enable_tls: bool = Field(default=False)
    use_aura: bool = Field(default=False)

    # Performance / loading options
    batch_size: int = 1000
    parallel_threads: int = 4
    create_constraints: bool = True
    create_indexes: bool = True
    transaction_timeout_seconds: int = 300
    retry_on_deadlock: bool = True
    max_deadlock_retries: int = 3
    auto_migrate: bool = True


class ExtractionConfig(BaseModel):
    """Configuration for data extraction."""

    sbir: SbirDuckDBConfig = Field(
        default_factory=SbirDuckDBConfig, description="SBIR extraction configuration"
    )
    usaspending: dict[str, Any] = Field(
        default_factory=lambda: {
            "database_name": "usaspending",
            "table_name": "awards",
            "import_chunk_size": 50000,
        }
    )
    sam_gov: SamGovConfig = Field(
        default_factory=SamGovConfig, description="SAM.gov extraction configuration"
    )


class ValidationConfig(FloatRangeValidatorMixin, BaseModel):
    """Configuration for data validation."""

    strict_schema: bool = True
    fail_on_first_error: bool = False
    sample_size_for_checks: int = 1000
    max_error_percentage: float = 0.05

    @field_validator("max_error_percentage")
    @classmethod
    def validate_error_percentage(cls, value: Any) -> float:
        """Coerce and validate error percentage to be between 0 and 1."""

        return cls._coerce_float(
            value,
            field_name="max_error_percentage",
            lower_bound=0.0,
            upper_bound=1.0,
        )


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


class DuckDBConfig(BaseModel):
    """Configuration for DuckDB."""

    database_path: str = "data/processed/sbir.duckdb"
    memory_limit_gb: int = 4
    threads: int = 4
    enable_object_cache: bool = True
    enable_query_profiler: bool = False


__all__ = [
    "DataQualityConfig",
    "DuckDBConfig",
    "ExtractionConfig",
    "Neo4jConfig",
    "SamGovConfig",
    "SbirDuckDBConfig",
    "SbirValidationConfig",
    "TransformationConfig",
    "ValidationConfig",
]
