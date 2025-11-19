"""Generic API response cache utility.

This module provides a unified file-based caching mechanism for API responses,
replacing the separate PatentsViewCache and USAspendingCache implementations.
It supports flexible cache keys, metadata, and expiration.
"""

import json
from pathlib import Path
from typing import Any

from loguru import logger

from .base_cache import BaseDataFrameCache


class APICache(BaseDataFrameCache):
    """Generic file-based cache for API responses."""

    def __init__(
        self,
        cache_dir: str | Path,
        default_cache_type: str = "default",
        enabled: bool = True,
        ttl_hours: int = 24,
    ):
        """Initialize the cache.

        Args:
            cache_dir: Directory to store cache files
            default_cache_type: Default type string for cache entries
            enabled: Whether caching is enabled
            ttl_hours: Time-to-live for cache entries in hours (default: 24)
        """
        super().__init__(cache_dir=cache_dir, enabled=enabled, ttl_hours=ttl_hours)
        self._default_cache_type_value = default_cache_type

    def _get_default_cache_type(self) -> str:
        """Get the default cache type.

        Returns:
            Default cache type string
        """
        return self._default_cache_type_value

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
            cache_type: Type of cache entry
            **metadata: Additional metadata to store
        """
        if cache_type is None:
            cache_type = self._get_default_cache_type()

        # Remove identifiers from metadata if present to avoid conflict
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

    def clear(self, cache_type: str | None = None, expired_only: bool = False) -> int:
        """Clear cache entries.

        Args:
            cache_type: Optional cache type to clear (if None, clears all types)
            expired_only: If True, only clear expired entries.

        Returns:
            Number of cache entries cleared
        """
        if not self.cache_dir.exists():
            return 0

        cleared_count = 0
        for cache_file in self.cache_dir.glob("*.parquet"):
            cache_key = cache_file.stem
            metadata_path = self._get_metadata_path(cache_key)

            if not metadata_path.exists():
                # Orphaned cache file or no metadata, safe to delete if we are not strict
                if not expired_only:
                     cache_file.unlink(missing_ok=True)
                     cleared_count += 1
                continue

            try:
                with open(metadata_path, "r") as f:
                    metadata = json.load(f)
            except Exception:
                # Corrupted metadata
                if not expired_only:
                    cache_file.unlink(missing_ok=True)
                    metadata_path.unlink(missing_ok=True)
                    cleared_count += 1
                continue

            # Filter by cache type if specified
            if cache_type and metadata.get("cache_type") != cache_type:
                continue

            # Check expiration if requested
            if expired_only and not self._is_expired(metadata):
                continue

            # Delete files
            cache_file.unlink(missing_ok=True)
            metadata_path.unlink(missing_ok=True)
            cleared_count += 1

        if cleared_count > 0:
            logger.info(
                f"Cleared {cleared_count} cache entries "
                f"(type={cache_type or 'all'}, expired_only={expired_only})"
            )
        return cleared_count

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
            
            is_expired = False
            if metadata_path.exists():
                try:
                    with open(metadata_path, "r") as f:
                        metadata = json.load(f)
                    if self._is_expired(metadata):
                        is_expired = True
                except Exception:
                    is_expired = True
            else:
                # No metadata = effectively expired/invalid
                is_expired = True
            
            if is_expired:
                expired_entries += 1

        return {
            "enabled": self.enabled,
            "total_entries": total_entries,
            "expired_entries": expired_entries,
            "valid_entries": total_entries - expired_entries,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "cache_dir": str(self.cache_dir),
            "ttl_hours": self.ttl_hours,
            "default_type": self._default_cache_type_value,
        }
