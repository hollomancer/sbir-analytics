"""Domain-specific configuration schemas.

Consolidated from enrichment.py, fiscal.py, ml.py, and reporting.py.
Covers: enrichment services, fiscal analysis, ML/PaECTER, and reporting.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, Field, field_validator

from .data import _coerce_percentage_mapping


# ---------------------------------------------------------------------------
# Enrichment schemas
# ---------------------------------------------------------------------------


class EnrichmentPerformanceConfig(BaseModel):
    """Performance configuration for enrichment operations."""

    chunk_size: int = Field(default=1000, ge=1, description="Chunk size for batch processing")
    memory_threshold_mb: int = Field(default=1024, ge=1, description="Memory threshold in MB")
    timeout_seconds: int = Field(default=300, ge=1, description="Operation timeout in seconds")
    high_confidence_threshold: float = Field(
        default=0.9, ge=0.0, le=1.0, description="High confidence threshold"
    )
    low_confidence_threshold: float = Field(
        default=0.7, ge=0.0, le=1.0, description="Low confidence threshold"
    )
    enable_memory_monitoring: bool = Field(default=True, description="Enable memory monitoring")
    enable_fuzzy_matching: bool = Field(default=True, description="Enable fuzzy matching")
    enable_progress_tracking: bool = Field(default=True, description="Enable progress tracking")


class EnrichmentConfig(BaseModel):
    """Configuration for data enrichment services."""

    sam_gov: dict[str, object] = Field(
        default_factory=lambda: {
            "base_url": "https://api.sam.gov/entity-information/v3",
            "api_key_env_var": "SAM_GOV_API_KEY",  # pragma: allowlist secret
            "rate_limit_per_minute": 60,
            "timeout_seconds": 30,
            "retry_attempts": 3,
            "retry_backoff_seconds": 1,
        }
    )
    usaspending_api: dict[str, object] = Field(
        default_factory=lambda: {
            "base_url": "https://api.usaspending.gov/api/v2",
            "timeout_seconds": 30,
            "retry_attempts": 3,
            "retry_backoff_seconds": 2,
        }
    )
    patentsview_api: dict[str, object] = Field(
        default_factory=lambda: {
            "base_url": "https://data.uspto.gov/api/v1/patent/applications",
            "api_key_env_var": "USPTO_ODP_API_KEY",  # pragma: allowlist secret
            "rate_limit_per_minute": 60,
            "timeout_seconds": 30,
            "retry_attempts": 3,
            "retry_backoff_seconds": 2,
        }
    )
    sec_edgar: dict[str, object] = Field(
        default_factory=lambda: {
            "base_url": "https://efts.sec.gov/LATEST",
            "facts_base_url": "https://data.sec.gov/api/xbrl",
            "filings_base_url": "https://data.sec.gov/submissions",
            "contact_email_env_var": "SEC_EDGAR_CONTACT_EMAIL",
            "rate_limit_per_minute": 600,
            "timeout_seconds": 30,
            "retry_attempts": 3,
            "retry_backoff_seconds": 2,
        }
    )
    performance: EnrichmentPerformanceConfig = Field(
        default_factory=EnrichmentPerformanceConfig, description="Performance configuration"
    )


class EnrichmentSourceConfig(BaseModel):
    """Configuration for a single enrichment source's iterative refresh settings."""

    enabled: bool = Field(
        default=True,
        description="Feature flag to enable/disable this source. "
        "Set to False to opt-out until legal/data-sharing reviews complete.",
    )
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

    class CacheConfig(BaseModel):
        """Configuration for API response caching."""

        enabled: bool = Field(default=True, description="Enable caching of API responses")
        ttl_seconds: int = Field(default=86400, ge=60, description="Cache TTL seconds")
        ttl_hours: int | None = Field(
            default=None, description="Cache TTL hours (derived from ttl_seconds)"
        )
        cache_dir: str = Field(default="data/cache/usaspending", description="Cache directory path")
        max_entries: int = Field(default=1000, ge=10, description="Max cached responses")
        backend: str = Field(default="filesystem", description="Cache backend type")

        def model_post_init(self, __context: Any) -> None:
            """Derive ttl_hours from ttl_seconds if not set."""
            if self.ttl_hours is None:
                self.ttl_hours = self.ttl_seconds // 3600

    cache: CacheConfig = Field(
        default_factory=CacheConfig, description="API response caching configuration"
    )


class EnrichmentRefreshConfig(BaseModel):
    """Configuration for enrichment refresh cadence and freshness tracking.

    Phase 1: USAspending is the only fully implemented source.
    Phase 2+: Other sources have configuration stubs with ``enabled=False``
    feature flags.
    """

    usaspending: EnrichmentSourceConfig = Field(
        default_factory=EnrichmentSourceConfig, description="USAspending refresh settings"
    )
    sam_gov: EnrichmentSourceConfig = Field(
        default_factory=EnrichmentSourceConfig, description="SAM.gov refresh settings"
    )
    patentsview: EnrichmentSourceConfig = Field(
        default_factory=EnrichmentSourceConfig, description="PatentsView refresh settings"
    )
    sec_edgar: EnrichmentSourceConfig = Field(
        default_factory=lambda: EnrichmentSourceConfig(
            enabled=False,
            cadence_days=7,
            sla_staleness_days=30,
            batch_size=50,
            max_concurrent_requests=3,
            rate_limit_per_minute=600,
        ),
        description="SEC EDGAR refresh settings (opt-in, disabled by default)",
    )


# ---------------------------------------------------------------------------
# Fiscal analysis schemas
# ---------------------------------------------------------------------------


class TaxParameterConfig(BaseModel):
    """Configuration for federal tax calculation parameters."""

    individual_income_tax: dict[str, Any] = Field(
        default_factory=lambda: {
            "effective_rate": 0.22,
            "progressive_rates": {
                "10_percent": 0.10, "12_percent": 0.12, "22_percent": 0.22,
                "24_percent": 0.24, "32_percent": 0.32, "35_percent": 0.35,
                "37_percent": 0.37,
            },
            "standard_deduction": 13850,
        }
    )
    payroll_tax: dict[str, Any] = Field(
        default_factory=lambda: {
            "social_security_rate": 0.062,
            "medicare_rate": 0.0145,
            "unemployment_rate": 0.006,
            "wage_base_limit": 160200,
        }
    )
    corporate_income_tax: dict[str, Any] = Field(
        default_factory=lambda: {
            "federal_rate": 0.21,
            "effective_rate": 0.18,
        }
    )
    excise_tax: dict[str, Any] = Field(
        default_factory=lambda: {
            "fuel_tax_rate": 0.184,
            "general_rate": 0.03,
        }
    )

    @field_validator("individual_income_tax", "payroll_tax", "corporate_income_tax", "excise_tax")
    @classmethod
    def validate_tax_parameters(cls, value: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(value, Mapping):
            raise TypeError("Expected a mapping for tax parameters")
        normalized: dict[str, Any] = dict(value)
        for key, raw in normalized.items():
            if "rate" in key and isinstance(raw, int | float):
                rate = float(raw)
                if not (0.0 <= rate <= 1.0):
                    raise ValueError(f"Tax rate {key} must be between 0.0 and 1.0, got {rate}")
                normalized[key] = rate
        return normalized


class SensitivityConfig(BaseModel):
    """Configuration for sensitivity analysis and uncertainty quantification."""

    parameter_sweep: dict[str, Any] = Field(
        default_factory=lambda: {
            "enabled": True,
            "method": "monte_carlo",
            "num_scenarios": 1000,
            "random_seed": 42,
        }
    )
    uncertainty_parameters: dict[str, Any] = Field(
        default_factory=lambda: {
            "tax_rates": {"variation_percent": 0.10, "distribution": "normal"},
            "multipliers": {"variation_percent": 0.15, "distribution": "normal"},
            "inflation_adjustment": {"variation_percent": 0.05, "distribution": "normal"},
        }
    )
    confidence_intervals: dict[str, Any] = Field(
        default_factory=lambda: {
            "levels": [0.90, 0.95, 0.99],
            "method": "percentile",
            "bootstrap_samples": 1000,
        }
    )
    performance: dict[str, Any] = Field(
        default_factory=lambda: {
            "max_scenarios_parallel": 10,
            "timeout_seconds": 3600,
            "memory_limit_gb": 8,
        }
    )

    @field_validator("uncertainty_parameters")
    @classmethod
    def validate_uncertainty_parameters(cls, value: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(value, Mapping):
            raise TypeError("Expected a mapping for uncertainty parameters")
        normalized: dict[str, Any] = dict(value)
        for param_name, param_config in normalized.items():
            if isinstance(param_config, dict) and "variation_percent" in param_config:
                variation = param_config["variation_percent"]
                if isinstance(variation, int | float):
                    variation = float(variation)
                    if not (0.0 <= variation <= 1.0):
                        raise ValueError(
                            f"Variation percent for {param_name} must be between 0.0 and 1.0, got {variation}"
                        )
                    param_config["variation_percent"] = variation
        return normalized


class FiscalAnalysisConfig(BaseModel):
    """Configuration for SBIR fiscal returns analysis."""

    base_year: int = Field(default=2023, description="Base year for inflation adjustment")
    inflation_source: str = Field(
        default="bea_gdp_deflator", description="Source for inflation data"
    )
    naics_crosswalk_version: str = Field(
        default="2022", description="NAICS-to-BEA crosswalk version"
    )
    stateio_model_version: str = Field(default="v2.1", description="BEA I-O model version")
    tax_parameters: TaxParameterConfig = Field(
        default_factory=TaxParameterConfig, description="Federal tax calculation parameters"
    )
    sensitivity_parameters: SensitivityConfig = Field(
        default_factory=SensitivityConfig,
        description="Sensitivity analysis and uncertainty quantification parameters",
    )
    quality_thresholds: dict[str, Any] = Field(
        default_factory=lambda: {
            "naics_coverage_rate": 0.85,
            "geographic_resolution_rate": 0.90,
            "inflation_adjustment_success": 0.95,
            "bea_sector_mapping_rate": 0.90,
        }
    )
    performance: dict[str, Any] = Field(
        default_factory=lambda: {
            "chunk_size": 10000,
            "parallel_processing": True,
            "max_workers": 4,
            "memory_limit_gb": 4,
            "timeout_seconds": 1800,
        }
    )
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
    def validate_base_year(cls, value: int) -> int:
        if not (1980 <= value <= 2030):
            raise ValueError(f"Base year must be between 1980 and 2030, got {value}")
        return value

    @field_validator("quality_thresholds")
    @classmethod
    def validate_quality_thresholds(cls, value: Mapping[str, Any]) -> dict[str, float]:
        return _coerce_percentage_mapping(value, field_name="fiscal_quality")


# ---------------------------------------------------------------------------
# ML schemas
# ---------------------------------------------------------------------------


class PaECTERApiConfig(BaseModel):
    """Configuration for PaECTER HuggingFace Inference API."""

    token_env: str = Field(
        default="HF_TOKEN", description="Environment variable for HuggingFace API token"
    )
    batch_size: int = Field(default=32, ge=1, description="Batch size for API requests")
    max_qps: int = Field(default=10, ge=1, description="Maximum queries per second")
    timeout_seconds: int = Field(default=60, ge=1, description="API request timeout")
    max_retries: int = Field(default=5, ge=0, description="Maximum retry attempts")
    retry_backoff_seconds: float = Field(
        default=2.0, ge=0, description="Base backoff between retries"
    )


class PaECTERLocalConfig(BaseModel):
    """Configuration for local embedding model inference (ModernBERT-Embed)."""

    model_name: str = Field(
        default="nomic-ai/modernbert-embed-base", description="HuggingFace model identifier"
    )
    device: str = Field(default="auto", description="Device for inference (auto, cpu, cuda)")
    batch_size: int = Field(default=32, ge=1, description="Batch size for local inference")


class PaECTERTextConfig(BaseModel):
    """Configuration for text preprocessing before embedding."""

    max_length: int = Field(default=512, ge=1, description="Maximum token length (truncation)")
    award_fields: list[str] = Field(
        default_factory=lambda: ["solicitation_title", "abstract", "award_title"],
        description="Award fields to concatenate for embedding",
    )
    patent_fields: list[str] = Field(
        default_factory=lambda: ["title", "abstract"],
        description="Patent fields to concatenate for embedding",
    )



class PaECTERConfig(BaseModel):
    """Configuration for PaECTER patent-award similarity embeddings."""

    provider: str = Field(
        default="huggingface",
        description="Provider selection: huggingface (API) or local (sentence-transformers)",
    )
    use_local: bool = Field(default=False, description="Use local model instead of API")
    api: PaECTERApiConfig = Field(default_factory=PaECTERApiConfig)
    local: PaECTERLocalConfig = Field(default_factory=PaECTERLocalConfig)
    text: PaECTERTextConfig = Field(default_factory=PaECTERTextConfig)

    similarity_threshold: float = Field(
        default=0.80, ge=0.0, le=1.0,
        description="Minimum similarity score to include in results",
    )
    top_k: int = Field(default=10, ge=1, description="Number of top matches per award")
    coverage_threshold_awards: float = Field(
        default=0.95, ge=0.0, le=1.0,
        description="Minimum fraction of awards with valid embeddings",
    )
    coverage_threshold_patents: float = Field(
        default=0.98, ge=0.0, le=1.0,
        description="Minimum fraction of patents with valid embeddings",
    )
    enable_cache: bool = Field(default=False, description="Enable embedding caching to disk")


class MLConfig(BaseModel):
    """Machine learning configuration."""

    paecter: PaECTERConfig = Field(
        default_factory=PaECTERConfig,
        description="PaECTER patent-award similarity configuration",
    )


# ---------------------------------------------------------------------------
# Reporting schemas
# ---------------------------------------------------------------------------


class StatisticalReportingConfig(BaseModel):
    """Configuration for statistical reporting and automated insights."""

    enabled: bool = True
    output_directory: str = Field(default="reports/statistics")
    report_types: list[str] = Field(
        default_factory=lambda: [
            "data_quality", "enrichment_performance", "pipeline_performance",
            "anomaly_detection", "success_metrics",
        ]
    )
    schedules: dict[str, Any] = Field(
        default_factory=lambda: {
            "daily": {"enabled": True, "hour": 2, "minute": 0, "include_summary": True},
            "weekly": {
                "enabled": True, "weekday": "monday", "hour": 6,
                "minute": 0, "include_trends": True,
            },
        }
    )
    distribution: dict[str, Any] = Field(
        default_factory=lambda: {
            "email": {
                "enabled": True,
                "recipients": ["analytics_team@example.com"],
                "attach_reports": True,
            },
            "slack": {
                "enabled": True,
                "channel": "#analytics-updates",
                "include_summary": True,
            },
        }
    )
    sections: dict[str, Any] = Field(
        default_factory=lambda: {
            "pipeline_health": {
                "enabled": True, "include_validation_details": True,
                "include_loading_statistics": True,
            },
            "cet_classification": {
                "enabled": True, "include_confidence_distribution": True,
                "include_taxonomy_breakdown": True,
            },
            "transition_detection": {
                "enabled": True, "include_success_stories": True,
                "include_trend_analysis": True,
            },
        }
    )
    insights: dict[str, Any] = Field(
        default_factory=lambda: {
            "anomaly_detection": {"enabled": True, "sensitivity": "medium", "lookback_periods": 5},
            "recommendations": {"enabled": True, "include_actionable_steps": True},
            "success_stories": {"enabled": True, "min_impact_threshold": 0.8},
        }
    )
    formats: dict[str, Any] = Field(
        default_factory=lambda: {
            "html": {"include_interactive_charts": True, "chart_library": "plotly", "theme": "default"},
            "json": {"include_raw_data": False, "pretty_print": True},
            "markdown": {"max_length": 2000, "include_links": True},
            "executive": {"include_visualizations": True, "focus_areas": ["impact", "quality", "trends"]},
        }
    )
    cicd: dict[str, Any] = Field(
        default_factory=lambda: {
            "github_actions": {
                "enabled": True, "upload_artifacts": True,
                "post_pr_comments": True, "artifact_retention_days": 30,
            },
            "report_comparison": {
                "enabled": True, "baseline_comparison": True,
                "trend_analysis_periods": [7, 30, 90],
            },
        }
    )
    quality_thresholds: dict[str, Any] = Field(
        default_factory=lambda: {
            "data_completeness_warning": 0.90,
            "data_completeness_error": 0.80,
            "enrichment_success_warning": 0.85,
            "enrichment_success_error": 0.70,
            "performance_degradation_warning": 1.5,
            "performance_degradation_error": 2.0,
        }
    )

    @field_validator("quality_thresholds")
    @classmethod
    def validate_quality_thresholds(cls, value: Mapping[str, Any]) -> dict[str, float]:
        if not isinstance(value, Mapping):
            raise TypeError("Expected a mapping for quality thresholds")
        normalized: dict[str, float] = {}
        for key, raw in value.items():
            try:
                number = float(raw)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{key} must be a number, got {raw!r}") from exc
            if "warning" in key or "error" in key:
                if key.startswith(("data_completeness", "enrichment_success")):
                    if not (0.0 <= number <= 1.0):
                        raise ValueError(f"{key} must be between 0.0 and 1.0, got {number}")
                elif key.startswith("performance_degradation") and number < 1.0:
                    raise ValueError(f"{key} must be >= 1.0 (1.0 = no degradation), got {number}")
            normalized[key] = number
        return normalized


__all__ = [
    "EnrichmentConfig",
    "EnrichmentRefreshConfig",
    "EnrichmentSourceConfig",
    "FiscalAnalysisConfig",
    "MLConfig",
    "PaECTERApiConfig",
    "PaECTERConfig",
    "PaECTERLocalConfig",
    "PaECTERTextConfig",
    "SensitivityConfig",
    "StatisticalReportingConfig",
    "TaxParameterConfig",
]
