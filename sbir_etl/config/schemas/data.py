"""Schemas for data pipeline infrastructure and runtime settings.

Consolidated from data_pipeline.py and runtime.py.
Covers: extraction, validation, transformation, Neo4j, DuckDB,
paths, logging, metrics, CLI, and company categorization.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Helpers (inlined from former common.py mixins)
# ---------------------------------------------------------------------------

def _coerce_percentage_mapping(
    values: Mapping[str, Any],
    *,
    field_name: str,
    lower_bound: float = 0.0,
    upper_bound: float = 1.0,
) -> dict[str, float]:
    """Normalize mapping values into bounded percentages."""
    if not isinstance(values, Mapping):
        raise TypeError(f"Expected a mapping for {field_name}")
    normalized: dict[str, float] = {}
    for key, value in values.items():
        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{key} must be numeric, got {value!r}") from exc
        if not (lower_bound <= number <= upper_bound):
            raise ValueError(
                f"{key} must be between {lower_bound} and {upper_bound}, got {number}"
            )
        normalized[key] = number
    return normalized


# ---------------------------------------------------------------------------
# Extraction schemas
# ---------------------------------------------------------------------------


class SbirValidationConfig(BaseModel):
    """SBIR-specific validation configuration."""

    pass_rate_threshold: float = Field(
        default=0.95, ge=0.0, le=1.0, description="Minimum pass rate required (0.95 = 95%)"
    )
    completeness_threshold: float = Field(
        default=0.90, ge=0.0, le=1.0, description="Completeness threshold for individual fields"
    )
    uniqueness_threshold: float = Field(
        default=0.99, ge=0.0, le=1.0, description="Uniqueness threshold for Contract IDs"
    )


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


class DataQualityConfig(BaseModel):
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
        return _coerce_percentage_mapping(value, field_name="data_quality")


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


class ValidationConfig(BaseModel):
    """Configuration for data validation."""

    strict_schema: bool = True
    fail_on_first_error: bool = False
    sample_size_for_checks: int = 1000
    max_error_percentage: float = Field(default=0.05, ge=0.0, le=1.0)


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


# ---------------------------------------------------------------------------
# Runtime schemas (logging, CLI, paths, metrics, company categorization)
# ---------------------------------------------------------------------------


class LoggingConfig(BaseModel):
    """Configuration for logging."""

    level: str = "INFO"
    format: str = "json"
    file_path: str = "logs/sbir-analytics.log"
    max_file_size_mb: int = 100
    backup_count: int = 5
    include_stage: bool = True
    include_run_id: bool = True
    include_timestamps: bool = True
    console_enabled: bool = True
    file_enabled: bool = True

    @field_validator("format")
    @classmethod
    def _normalize_format(cls, value: str) -> str:
        if not isinstance(value, str):
            return value  # type: ignore[return-value]
        lowered = value.lower()
        if lowered in {"pretty", "text", "plain"}:
            return "text"
        if lowered in {"json", "structured"}:
            return "json"
        return value


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


class CLIConfig(BaseModel):
    """Configuration for CLI interface settings."""

    theme: str = Field(default="default", description="CLI theme (default, dark, light)")
    progress_refresh_rate: float = Field(
        default=0.1, ge=0.0, description="Progress bar refresh rate in seconds"
    )
    dashboard_refresh_rate: int = Field(
        default=10, ge=1, description="Dashboard auto-refresh interval in seconds"
    )
    max_table_rows: int = Field(default=50, description="Maximum rows to display in tables")
    truncate_long_text: bool = Field(default=True, description="Truncate long text in displays")
    show_timestamps: bool = Field(default=True, description="Show timestamps in output")
    api_timeout_seconds: int = Field(default=30, description="API request timeout")
    max_concurrent_operations: int = Field(default=4, description="Maximum concurrent operations")
    cache_metrics_seconds: int = Field(default=60, description="Metrics cache TTL in seconds")

    @field_validator("theme")
    @classmethod
    def validate_theme(cls, value: str) -> str:
        if value not in ["default", "dark", "light"]:
            raise ValueError("Theme must be 'default', 'dark', or 'light'")
        return value


class CompanyCategorizationConfig(BaseModel):
    """Configuration for company categorization system."""

    product_leaning_pct: float = Field(
        default=51.0, ge=0.0, le=100.0,
        description="Product percentage threshold for Product-leaning classification",
    )
    service_leaning_pct: float = Field(
        default=51.0, ge=0.0, le=100.0,
        description="Service percentage threshold for Service-leaning classification",
    )
    psc_family_diversity_threshold: int = Field(
        default=6, ge=1, description="PSC family count threshold for Mixed override"
    )
    low_max_awards: int = Field(default=2, ge=1, description="Maximum awards for Low confidence")
    medium_max_awards: int = Field(default=5, ge=1, description="Maximum awards for Medium")
    batch_size: int = Field(default=100, ge=1, description="Batch size for processing companies")
    parallel_workers: int = Field(
        default=4, ge=1, description="Number of parallel workers for processing"
    )
    usaspending_table_name: str = Field(
        default="usaspending_awards", description="USAspending table name in DuckDB"
    )
    usaspending_timeout_seconds: int = Field(
        default=30, ge=1, description="Query timeout in seconds"
    )
    usaspending_retry_attempts: int = Field(
        default=3, ge=0, description="Number of retry attempts for failed queries"
    )
    include_contract_details: bool = Field(
        default=True, description="Include individual contract details in output"
    )
    include_metadata: bool = Field(default=True, description="Include classification metadata")


class PathsConfig(BaseModel):
    """File system paths configuration with environment variable expansion."""

    data_root: str = Field(
        default="data", description="Root data directory (relative to project root)"
    )
    raw_data: str = Field(default="data/raw", description="Raw data directory")
    usaspending_dump_dir: str = Field(
        default="data/usaspending", description="USAspending database dumps directory"
    )
    usaspending_dump_file: str = Field(
        default="data/usaspending/usaspending-db_20251006.zip",
        description="USAspending database dump file",
    )
    transition_contracts_output: str = Field(
        default="data/transition/contracts_ingestion.parquet",
        description="Transition contracts output file",
    )
    transition_dump_dir: str = Field(
        default="data/transition/pruned_data_store_api_dump",
        description="Transition API dump directory",
    )
    transition_vendor_filters: str = Field(
        default="data/transition/sbir_vendor_filters.json",
        description="SBIR vendor filters file",
    )
    scripts_output: str = Field(
        default="data/scripts_output", description="Scripts output directory"
    )

    def _expand_variables(self, value: str, context: dict[str, Any]) -> str:
        pattern = re.compile(r"\$\{([^}]+)\}")

        def replacer(match: re.Match[str]) -> str:
            var_path = match.group(1)
            parts = var_path.split(".")
            current: Any = context
            for part in parts:
                if isinstance(current, dict) and part in current:
                    current = current[part]
                else:
                    return match.group(0)
            return str(current)

        return pattern.sub(replacer, value)

    def resolve_path(
        self, path_key: str, create_parent: bool = False, project_root: Path | None = None
    ) -> Path:
        if not hasattr(self, path_key):
            raise ValueError(f"Unknown path key: {path_key}")

        path_str = getattr(self, path_key)
        path_str = os.path.expandvars(path_str)
        path_str = os.path.expanduser(path_str)
        path = Path(path_str)

        if not path.is_absolute():
            project_root = project_root or Path.cwd()
            path = project_root / path

        if create_parent and not path.parent.exists():
            path.parent.mkdir(parents=True, exist_ok=True)

        return path.resolve()


__all__ = [
    "CLIConfig",
    "CompanyCategorizationConfig",
    "DataQualityConfig",
    "DuckDBConfig",
    "ExtractionConfig",
    "LoggingConfig",
    "MetricsConfig",
    "Neo4jConfig",
    "PathsConfig",
    "SamGovConfig",
    "SbirDuckDBConfig",
    "SbirValidationConfig",
    "TransformationConfig",
    "ValidationConfig",
]
