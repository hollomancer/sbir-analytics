"""USAspending API response cache utility.

This module provides file-based caching for USAspending API responses to avoid
repeated API calls when running scripts multiple times. Cache entries are keyed
by company identifiers (UEI/DUNS/name) and include metadata for cache invalidation.
"""

import json
from pathlib import Path
from typing import Any

from loguru import logger

from .base_cache import BaseDataFrameCache


class USAspendingCache(BaseDataFrameCache):
    """File-based cache for USAspending API responses."""

    def __init__(
        self,
        cache_dir: str | Path = "data/cache/usaspending",
        enabled: bool = True,
        ttl_hours: int = 24,
    ):
        """Initialize the cache.

        Args:
            cache_dir: Directory to store cache files
            enabled: Whether caching is enabled
            ttl_hours: Time-to-live for cache entries in hours (default: 24)
        """
        super().__init__(cache_dir=cache_dir, enabled=enabled, ttl_hours=ttl_hours)

    def _get_default_cache_type(self) -> str:
        """Get the default cache type for USAspending cache.

        Returns:
            Default cache type: "contracts"
        """
        return "contracts"

    def set(
        self,
        df,
        uei: str | None = None,
        duns: str | None = None,
        company_name: str | None = None,
        cache_type: str | None = None,
        **metadata: Any,
    ) -> None:
        """Store data in cache.

        Args:
            df: DataFrame to cache
            uei: Company UEI
            duns: Company DUNS number
            company_name: Company name
            cache_type: Type of cache entry ("contracts" for non-SBIR, "sbir" for SBIR-only)
            **metadata: Additional metadata to store
        """
        if cache_type is None:
            cache_type = self._get_default_cache_type()

        # Remove uei, duns, company_name from metadata if present to avoid conflict
        # with explicit keyword arguments. These are passed as explicit args, not in metadata.
        metadata.pop("uei", None)
        metadata.pop("duns", None)
        metadata.pop("company_name", None)

        super().set(
            df=df,
            uei=uei,
            duns=duns,
            company_name=company_name,
            cache_type=cache_type,
            **metadata,
        )

    def clear(self, expired_only: bool = False) -> int:
        """Clear cache entries.

        Args:
            expired_only: If True, only clear expired entries. If False, clear all.

        Returns:
            Number of cache entries cleared
        """
        if not self.cache_dir.exists():
            return 0

        cleared = 0
        for cache_file in self.cache_dir.glob("*.parquet"):
            cache_key = cache_file.stem
            metadata_path = self._get_metadata_path(cache_key)

            if expired_only:
                if not metadata_path.exists():
                    continue
                try:
                    with open(metadata_path) as f:
                        metadata = json.load(f)
                    if not self._is_expired(metadata):
                        continue
                except Exception:
                    # If metadata is corrupted, treat as expired
                    pass

            # Remove cache files
            cache_file.unlink(missing_ok=True)
            metadata_path.unlink(missing_ok=True)
            cleared += 1

        if cleared > 0:
            logger.info(
                f"Cleared {cleared} cache entries ({'expired only' if expired_only else 'all'})"
            )
        return cleared

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics.

        Returns:
            Dictionary with cache statistics
        """
        if not self.cache_dir.exists():
            return {
                "enabled": self.enabled,
                "total_entries": 0,
                "expired_entries": 0,
                "valid_entries": 0,
                "total_size_mb": 0.0,
            }

        total_entries = 0
        expired_entries = 0
        total_size = 0

        for cache_file in self.cache_dir.glob("*.parquet"):
            total_entries += 1
            total_size += cache_file.stat().st_size

            cache_key = cache_file.stem
            metadata_path = self._get_metadata_path(cache_key)
            if metadata_path.exists():
                try:
                    with open(metadata_path) as f:
                        metadata = json.load(f)
                    if self._is_expired(metadata):
                        expired_entries += 1
                except Exception:
                    expired_entries += 1

        return {
            "enabled": self.enabled,
            "total_entries": total_entries,
            "expired_entries": expired_entries,
            "valid_entries": total_entries - expired_entries,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "cache_dir": str(self.cache_dir),
            "ttl_hours": self.ttl_hours,
        }
