"""Schemas related to enrichment services and refresh cadence."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


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
            "base_url": "https://search.patentsview.org/api",
            "api_key_env_var": "PATENTSVIEW_API_KEY",  # pragma: allowlist secret
            "rate_limit_per_minute": 60,
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
