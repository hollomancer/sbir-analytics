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
            except (TypeError, ValueError) as e:
                raise ValueError(f"{key} must be a number (0.0-1.0), got {value!r}") from e
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


class EnrichmentSourceConfig(BaseModel):
    """Configuration for a single enrichment source's iterative refresh settings."""

    cadence_days: int = Field(default=1, ge=1, description="Number of days between refresh cycles")
    sla_staleness_days: int = Field(
        default=1, ge=1, description="Maximum age in days before considered stale"
    )
    batch_size: int = Field(default=100, ge=1, le=1000, description="Number of records per batch")
    max_concurrent_requests: int = Field(
        default=5, ge=1, le=20, description="Maximum concurrent API requests"
    )
    rate_limit_per_minute: int = Field(
        default=120, ge=1, description="API rate limit (requests per minute)"
    )
    enable_delta_detection: bool = Field(
        default=True, description="Enable payload hash-based delta detection"
    )
    hash_algorithm: str = Field(default="sha256", description="Hash algorithm for payload hashing")
    retry_attempts: int = Field(default=3, ge=0, description="Number of retry attempts")
    retry_backoff_seconds: float = Field(
        default=2.0, ge=0.0, description="Initial retry backoff delay in seconds"
    )
    retry_backoff_multiplier: float = Field(
        default=2.0, ge=1.0, description="Exponential backoff multiplier"
    )
    timeout_seconds: int = Field(default=30, ge=1, description="Request timeout in seconds")
    connection_timeout_seconds: int = Field(
        default=10, ge=1, description="Connection timeout in seconds"
    )
    checkpoint_interval: int = Field(
        default=50, ge=1, description="Save checkpoint every N records"
    )
    state_file: str = Field(
        default="data/state/enrichment_refresh_state.json",
        description="Path to state file",
    )
    enable_metrics: bool = Field(default=True, description="Enable metrics collection")
    metrics_file: str = Field(
        default="reports/metrics/enrichment_freshness.json",
        description="Path to metrics output file",
    )


class EnrichmentRefreshConfig(BaseModel):
    """Configuration for iterative enrichment refresh across all sources.

    Phase 1: USAspending API only. Other APIs (SAM.gov, NIH RePORTER, PatentsView, etc.)
    will be evaluated in Phase 2+.
    """

    usaspending: EnrichmentSourceConfig = Field(
        default_factory=EnrichmentSourceConfig,
        description="USAspending API refresh configuration",
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
        except (TypeError, ValueError) as e:
            raise ValueError(f"max_error_percentage must be numeric, got {v!r}") from e
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


class StatisticalReportingConfig(BaseModel):
    """Configuration for statistical reporting system."""

    # Report generation settings
    generation: dict[str, Any] = Field(
        default_factory=lambda: {
            "enabled": True,
            "formats": ["html", "json", "markdown"],
            "output_directory": "reports/statistical",
            "template_directory": "templates/reports",
        }
    )

    # Module-specific reporting
    modules: dict[str, Any] = Field(
        default_factory=lambda: {
            "sbir_enrichment": {
                "enabled": True,
                "include_coverage_analysis": True,
                "include_source_breakdown": True,
            },
            "patent_analysis": {
                "enabled": True,
                "include_validation_details": True,
                "include_loading_statistics": True,
            },
            "cet_classification": {
                "enabled": True,
                "include_confidence_distribution": True,
                "include_taxonomy_breakdown": True,
            },
            "transition_detection": {
                "enabled": True,
                "include_success_stories": True,
                "include_trend_analysis": True,
            },
        }
    )

    # Insight generation
    insights: dict[str, Any] = Field(
        default_factory=lambda: {
            "anomaly_detection": {
                "enabled": True,
                "sensitivity": "medium",  # low, medium, high
                "lookback_periods": 5,
            },
            "recommendations": {
                "enabled": True,
                "include_actionable_steps": True,
            },
            "success_stories": {
                "enabled": True,
                "min_impact_threshold": 0.8,
            },
        }
    )

    # Output format configuration
    formats: dict[str, Any] = Field(
        default_factory=lambda: {
            "html": {
                "include_interactive_charts": True,
                "chart_library": "plotly",
                "theme": "default",
            },
            "json": {
                "include_raw_data": False,
                "pretty_print": True,
            },
            "markdown": {
                "max_length": 2000,
                "include_links": True,
            },
            "executive": {
                "include_visualizations": True,
                "focus_areas": ["impact", "quality", "trends"],
            },
        }
    )

    # CI/CD integration
    cicd: dict[str, Any] = Field(
        default_factory=lambda: {
            "github_actions": {
                "enabled": True,
                "upload_artifacts": True,
                "post_pr_comments": True,
                "artifact_retention_days": 30,
            },
            "report_comparison": {
                "enabled": True,
                "baseline_comparison": True,
                "trend_analysis_periods": [7, 30, 90],
            },
        }
    )

    # Quality thresholds for reporting
    quality_thresholds: dict[str, Any] = Field(
        default_factory=lambda: {
            "data_completeness_warning": 0.90,
            "data_completeness_error": 0.80,
            "enrichment_success_warning": 0.85,
            "enrichment_success_error": 0.70,
            "performance_degradation_warning": 1.5,  # 50% slower
            "performance_degradation_error": 2.0,  # 100% slower
        }
    )

    @field_validator("quality_thresholds")
    @classmethod
    def validate_quality_thresholds(cls, v: Mapping[str, Any]) -> dict[str, float]:
        """Validate and coerce quality threshold values to floats."""
        if not isinstance(v, Mapping):
            raise TypeError("Expected a mapping for quality thresholds")

        out: dict[str, float] = {}
        for key, value in v.items():
            try:
                num = float(value)
            except (TypeError, ValueError) as e:
                raise ValueError(f"{key} must be a number, got {value!r}") from e

            # Validate threshold ranges based on key type
            if "warning" in key or "error" in key:
                if key.startswith("data_completeness") or key.startswith("enrichment_success"):
                    if not (0.0 <= num <= 1.0):
                        raise ValueError(f"{key} must be between 0.0 and 1.0, got {num}")
                elif key.startswith("performance_degradation"):
                    if num < 1.0:
                        raise ValueError(f"{key} must be >= 1.0 (1.0 = no degradation), got {num}")

            out[key] = num
        return out


class TaxParameterConfig(BaseModel):
    """Configuration for federal tax calculation parameters."""

    # Individual income tax parameters
    individual_income_tax: dict[str, Any] = Field(
        default_factory=lambda: {
            "effective_rate": 0.22,  # Average effective federal income tax rate
            "progressive_rates": {
                "10_percent": 0.10,
                "12_percent": 0.12,
                "22_percent": 0.22,
                "24_percent": 0.24,
                "32_percent": 0.32,
                "35_percent": 0.35,
                "37_percent": 0.37,
            },
            "standard_deduction": 13850,  # 2023 standard deduction (single)
        }
    )

    # Payroll tax parameters
    payroll_tax: dict[str, Any] = Field(
        default_factory=lambda: {
            "social_security_rate": 0.062,  # Employee portion
            "medicare_rate": 0.0145,  # Employee portion
            "unemployment_rate": 0.006,  # FUTA rate
            "wage_base_limit": 160200,  # 2023 Social Security wage base
        }
    )

    # Corporate income tax parameters
    corporate_income_tax: dict[str, Any] = Field(
        default_factory=lambda: {
            "federal_rate": 0.21,  # Federal corporate tax rate
            "effective_rate": 0.18,  # Average effective rate accounting for deductions
        }
    )

    # Excise tax parameters
    excise_tax: dict[str, Any] = Field(
        default_factory=lambda: {
            "fuel_tax_rate": 0.184,  # Federal gasoline tax per gallon
            "general_rate": 0.03,  # General excise tax rate on goods
        }
    )

    @field_validator("individual_income_tax", "payroll_tax", "corporate_income_tax", "excise_tax")
    @classmethod
    def validate_tax_parameters(cls, v: Mapping[str, Any]) -> dict[str, Any]:
        """Validate tax parameter values are reasonable."""
        if not isinstance(v, Mapping):
            raise TypeError("Expected a mapping for tax parameters")

        # Convert to dict and validate rate values
        out: dict[str, Any] = dict(v)
        for key, value in out.items():
            if "rate" in key and isinstance(value, int | float):
                rate = float(value)
                if not (0.0 <= rate <= 1.0):
                    raise ValueError(f"Tax rate {key} must be between 0.0 and 1.0, got {rate}")
                out[key] = rate

        return out


class SensitivityConfig(BaseModel):
    """Configuration for sensitivity analysis and uncertainty quantification."""

    # Parameter sweep configuration
    parameter_sweep: dict[str, Any] = Field(
        default_factory=lambda: {
            "enabled": True,
            "method": "monte_carlo",  # monte_carlo, latin_hypercube, grid_search
            "num_scenarios": 1000,
            "random_seed": 42,
        }
    )

    # Uncertainty parameters
    uncertainty_parameters: dict[str, Any] = Field(
        default_factory=lambda: {
            "tax_rates": {
                "variation_percent": 0.10,  # ±10% variation
                "distribution": "normal",
            },
            "multipliers": {
                "variation_percent": 0.15,  # ±15% variation
                "distribution": "normal",
            },
            "inflation_adjustment": {
                "variation_percent": 0.05,  # ±5% variation
                "distribution": "normal",
            },
        }
    )

    # Confidence interval configuration
    confidence_intervals: dict[str, Any] = Field(
        default_factory=lambda: {
            "levels": [0.90, 0.95, 0.99],  # 90%, 95%, 99% confidence intervals
            "method": "percentile",  # percentile, bootstrap
            "bootstrap_samples": 1000,
        }
    )

    # Performance thresholds
    performance: dict[str, Any] = Field(
        default_factory=lambda: {
            "max_scenarios_parallel": 10,
            "timeout_seconds": 3600,  # 1 hour timeout
            "memory_limit_gb": 8,
        }
    )

    @field_validator("uncertainty_parameters")
    @classmethod
    def validate_uncertainty_parameters(cls, v: Mapping[str, Any]) -> dict[str, Any]:
        """Validate uncertainty parameter values."""
        if not isinstance(v, Mapping):
            raise TypeError("Expected a mapping for uncertainty parameters")

        out: dict[str, Any] = dict(v)
        for param_name, param_config in out.items():
            if isinstance(param_config, dict) and "variation_percent" in param_config:
                variation = param_config["variation_percent"]
                if isinstance(variation, int | float):
                    variation = float(variation)
                    if not (0.0 <= variation <= 1.0):
                        raise ValueError(
                            f"Variation percent for {param_name} must be between 0.0 and 1.0, got {variation}"
                        )
                    param_config["variation_percent"] = variation

        return out


class CLIConfig(BaseModel):
    """Configuration for CLI interface settings."""

    # Display settings
    theme: str = Field(default="default", description="CLI theme (default, dark, light)")
    progress_refresh_rate: float = Field(
        default=0.1, description="Progress bar refresh rate in seconds"
    )
    dashboard_refresh_rate: int = Field(
        default=10, description="Dashboard auto-refresh interval in seconds"
    )

    # Output settings
    max_table_rows: int = Field(default=50, description="Maximum rows to display in tables")
    truncate_long_text: bool = Field(default=True, description="Truncate long text in displays")
    show_timestamps: bool = Field(default=True, description="Show timestamps in output")

    # Performance settings
    api_timeout_seconds: int = Field(default=30, description="API request timeout")
    max_concurrent_operations: int = Field(default=4, description="Maximum concurrent operations")
    cache_metrics_seconds: int = Field(default=60, description="Metrics cache TTL in seconds")

    @field_validator("theme")
    @classmethod
    def validate_theme(cls, v: str) -> str:
        """Validate theme value."""
        if v not in ["default", "dark", "light"]:
            raise ValueError("Theme must be 'default', 'dark', or 'light'")
        return v

    @field_validator("progress_refresh_rate", "dashboard_refresh_rate")
    @classmethod
    def validate_refresh_rate(cls, v: float | int) -> float | int:
        """Validate refresh rate is positive."""
        if v <= 0:
            raise ValueError("Refresh rate must be positive")
        return v


class FiscalAnalysisConfig(BaseModel):
    """Configuration for SBIR fiscal returns analysis."""

    # Base analysis parameters
    base_year: int = Field(default=2023, description="Base year for inflation adjustment")
    inflation_source: str = Field(
        default="bea_gdp_deflator", description="Source for inflation data"
    )
    naics_crosswalk_version: str = Field(
        default="2022", description="NAICS-to-BEA crosswalk version"
    )
    stateio_model_version: str = Field(default="v2.1", description="StateIO model version")

    # Tax calculation parameters
    tax_parameters: TaxParameterConfig = Field(
        default_factory=TaxParameterConfig, description="Federal tax calculation parameters"
    )

    # Sensitivity analysis parameters
    sensitivity_parameters: SensitivityConfig = Field(
        default_factory=SensitivityConfig,
        description="Sensitivity analysis and uncertainty quantification parameters",
    )

    # Data quality thresholds
    quality_thresholds: dict[str, Any] = Field(
        default_factory=lambda: {
            "naics_coverage_rate": 0.85,  # 85% of awards must have NAICS codes
            "geographic_resolution_rate": 0.90,  # 90% must resolve to state level
            "inflation_adjustment_success": 0.95,  # 95% must have valid inflation data
            "bea_sector_mapping_rate": 0.90,  # 90% must map to BEA sectors
        }
    )

    # Performance configuration
    performance: dict[str, Any] = Field(
        default_factory=lambda: {
            "chunk_size": 10000,
            "parallel_processing": True,
            "max_workers": 4,
            "memory_limit_gb": 4,
            "timeout_seconds": 1800,  # 30 minutes
        }
    )

    # Output configuration
    output: dict[str, Any] = Field(
        default_factory=lambda: {
            "formats": ["json", "csv", "html"],
            "include_audit_trail": True,
            "include_sensitivity_analysis": True,
            "output_directory": "reports/fiscal_returns",
        }
    )

    @field_validator("base_year")
    @classmethod
    def validate_base_year(cls, v: int) -> int:
        """Validate base year is reasonable."""
        if not (1980 <= v <= 2030):
            raise ValueError(f"Base year must be between 1980 and 2030, got {v}")
        return v

    @field_validator("quality_thresholds")
    @classmethod
    def validate_quality_thresholds(cls, v: Mapping[str, Any]) -> dict[str, float]:
        """Validate quality threshold values."""
        if not isinstance(v, Mapping):
            raise TypeError("Expected a mapping for quality thresholds")

        out: dict[str, float] = {}
        for key, value in v.items():
            try:
                num = float(value)
            except (TypeError, ValueError) as e:
                raise ValueError(f"{key} must be a number, got {value!r}") from e

            if not (0.0 <= num <= 1.0):
                raise ValueError(f"{key} must be between 0.0 and 1.0, got {num}")

            out[key] = num
        return out


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

    model_config = ConfigDict(
        validate_assignment=True,
        extra="allow",
    )
