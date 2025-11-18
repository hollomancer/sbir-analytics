"""Schemas related to enrichment services and refresh cadence."""

from __future__ import annotations

from pydantic import BaseModel, Field


class EnrichmentConfig(BaseModel):
    """Configuration for data enrichment services."""

    sam_gov: dict[str, object] = Field(
        default_factory=lambda: {
            "base_url": "https://api.sam.gov/entity-information/v3",
            "api_key_env_var": "SAM_GOV_API_KEY",
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
            "base_url": "https://search.patentsview.org/api",
            "api_key_env_var": "PATENTSVIEW_API_KEY",
            "rate_limit_per_minute": 60,
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

    class CacheConfig(BaseModel):
        """Configuration for API response caching."""

        enabled: bool = Field(default=True, description="Enable caching of API responses")
        ttl_seconds: int = Field(default=86400, ge=60, description="Cache TTL seconds")
        max_entries: int = Field(default=1000, ge=10, description="Max cached responses")
        backend: str = Field(default="filesystem", description="Cache backend type")

    cache: CacheConfig = Field(
        default_factory=CacheConfig, description="API response caching configuration"
    )


class EnrichmentRefreshConfig(BaseModel):
    """Configuration for enrichment refresh cadence and freshness tracking."""

    usaspending: EnrichmentSourceConfig = Field(
        default_factory=EnrichmentSourceConfig, description="USAspending refresh settings"
    )
    sam_gov: EnrichmentSourceConfig = Field(
        default_factory=EnrichmentSourceConfig, description="SAM.gov refresh settings"
    )
    patentsview: EnrichmentSourceConfig = Field(
        default_factory=EnrichmentSourceConfig, description="PatentsView refresh settings"
    )


__all__ = ["EnrichmentConfig", "EnrichmentRefreshConfig", "EnrichmentSourceConfig"]
