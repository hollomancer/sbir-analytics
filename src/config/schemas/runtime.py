"""Runtime-supporting configuration schemas (logging, CLI, paths, etc.)."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator


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
        default=0.1, description="Progress bar refresh rate in seconds"
    )
    dashboard_refresh_rate: int = Field(
        default=10, description="Dashboard auto-refresh interval in seconds"
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

    @field_validator("progress_refresh_rate", "dashboard_refresh_rate")
    @classmethod
    def validate_refresh_rate(cls, value: float | int) -> float | int:
        if value <= 0:
            raise ValueError("Refresh rate must be positive")
        return value


class CompanyCategorizationConfig(BaseModel):
    """Configuration for company categorization system."""

    product_leaning_pct: float = Field(
        default=60.0,
        ge=0.0,
        le=100.0,
        description="Product percentage threshold for Product-leaning classification",
    )
    service_leaning_pct: float = Field(
        default=60.0,
        ge=0.0,
        le=100.0,
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

    @field_validator("product_leaning_pct", "service_leaning_pct")
    @classmethod
    def validate_threshold_percentage(cls, value: float) -> float:
        if not (0.0 <= value <= 100.0):
            raise ValueError(f"Threshold percentage must be between 0.0 and 100.0, got {value}")
        return value


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
    "LoggingConfig",
    "MetricsConfig",
    "PathsConfig",
]
