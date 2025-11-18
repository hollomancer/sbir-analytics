"""PatentsView API response cache utility.

This module provides file-based caching for PatentsView API responses to avoid
repeated API calls when running scripts multiple times. Cache entries are keyed
by company identifiers (UEI/DUNS/name) and include metadata for cache invalidation.
"""

import json
from pathlib import Path

from loguru import logger

from .base_cache import BaseDataFrameCache


class PatentsViewCache(BaseDataFrameCache):
    """File-based cache for PatentsView API responses."""

    def __init__(
        self,
        cache_dir: str | Path = "data/cache/patentsview",
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
        """Get the default cache type for PatentsView cache.

        Returns:
            Default cache type: "patents"
        """
        return "patents"

    def clear(self, cache_type: str | None = None) -> None:
        """Clear cache entries.

        Args:
            cache_type: Optional cache type to clear (if None, clears all)
        """
        if not self.cache_dir.exists():
            return

        cleared_count = 0
        for cache_file in self.cache_dir.glob("*.parquet"):
            cache_key = cache_file.stem

            # Check cache type if specified
            if cache_type:
                metadata_path = self._get_metadata_path(cache_key)
                if metadata_path.exists():
                    try:
                        with open(metadata_path, "r") as f:
                            metadata = json.load(f)
                        if metadata.get("cache_type") != cache_type:
                            continue
                    except Exception:
                        continue

            # Delete cache and metadata files
            cache_file.unlink(missing_ok=True)
            metadata_path = self._get_metadata_path(cache_key)
            if metadata_path.exists():
                metadata_path.unlink(missing_ok=True)
            cleared_count += 1

        logger.info(f"Cleared {cleared_count} cache entries")

