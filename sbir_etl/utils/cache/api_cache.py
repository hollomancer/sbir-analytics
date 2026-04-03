"""File-based DataFrame cache for API responses.

Provides caching of API responses as parquet files with TTL-based expiration,
metadata tracking, and cache management (clear, stats).
"""

import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
from loguru import logger


class APICache:
    """File-based cache for API responses stored as DataFrames."""

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
        self.cache_dir = Path(cache_dir)
        self.enabled = enabled
        self.ttl_hours = ttl_hours
        self.default_cache_type = default_cache_type

        if self.enabled:
            from sbir_etl.utils.path_utils import ensure_dir

            ensure_dir(self.cache_dir)
            logger.debug(
                f"APICache initialized at {self.cache_dir} (TTL: {ttl_hours}h)"
            )

    def _generate_cache_key(
        self,
        uei: str | None = None,
        duns: str | None = None,
        company_name: str | None = None,
        cache_type: str = "default",
    ) -> str:
        """Generate a cache key from company identifiers.

        Args:
            uei: Company UEI
            duns: Company DUNS number
            company_name: Company name
            cache_type: Type of cache entry

        Returns:
            Cache key (SHA256 hash of normalized identifiers)
        """
        parts = []
        if uei:
            parts.append(f"uei:{uei.strip().upper()}")
        if duns:
            parts.append(f"duns:{str(duns).strip()}")
        if company_name:
            normalized_name = " ".join(company_name.strip().upper().split())
            parts.append(f"name:{normalized_name}")

        if not parts:
            raise ValueError("At least one identifier (UEI, DUNS, or name) must be provided")

        parts.append(f"type:{cache_type}")
        key_string = "|".join(sorted(parts))
        return hashlib.sha256(key_string.encode("utf-8")).hexdigest()

    def _get_cache_path(self, cache_key: str) -> Path:
        """Get the file path for a cache key."""
        return self.cache_dir / f"{cache_key}.parquet"

    def _get_metadata_path(self, cache_key: str) -> Path:
        """Get the metadata file path for a cache key."""
        return self.cache_dir / f"{cache_key}.meta.json"

    def _is_expired(self, metadata: dict[str, Any]) -> bool:
        """Check if a cache entry is expired."""
        if "cached_at" not in metadata:
            return True

        cached_at = datetime.fromisoformat(metadata["cached_at"])
        expiration_time = cached_at + timedelta(hours=self.ttl_hours)
        return datetime.now() > expiration_time

    def get(
        self,
        uei: str | None = None,
        duns: str | None = None,
        company_name: str | None = None,
        cache_type: str | None = None,
    ) -> pd.DataFrame | None:
        """Retrieve cached data if available and not expired.

        Args:
            uei: Company UEI
            duns: Company DUNS number
            company_name: Company name
            cache_type: Type of cache entry (uses default if not provided)

        Returns:
            Cached DataFrame if found and valid, None otherwise
        """
        if not self.enabled:
            return None

        if cache_type is None:
            cache_type = self.default_cache_type

        try:
            cache_key = self._generate_cache_key(
                uei=uei, duns=duns, company_name=company_name, cache_type=cache_type
            )
            cache_path = self._get_cache_path(cache_key)
            metadata_path = self._get_metadata_path(cache_key)

            if not cache_path.exists() or not metadata_path.exists():
                return None

            with open(metadata_path) as f:
                metadata = json.load(f)

            if self._is_expired(metadata):
                logger.debug(
                    f"Cache entry expired for {cache_key[:8]}... (cached at {metadata.get('cached_at')})"
                )
                cache_path.unlink(missing_ok=True)
                metadata_path.unlink(missing_ok=True)
                return None

            df = pd.read_parquet(cache_path)
            logger.debug(
                f"Cache hit for {cache_key[:8]}... ({len(df)} rows, cached at {metadata.get('cached_at')})"
            )
            return df

        except Exception as e:
            logger.warning(f"Error reading cache: {e}")
            try:
                cache_path.unlink(missing_ok=True)
                metadata_path.unlink(missing_ok=True)
            except Exception:
                pass
            return None

    def set(
        self,
        df: pd.DataFrame,
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
            cache_type: Type of cache entry (uses default if not provided)
            **metadata: Additional metadata to store
        """
        if not self.enabled:
            return

        if cache_type is None:
            cache_type = self.default_cache_type

        # Remove identifiers from metadata if present to avoid conflict
        metadata.pop("uei", None)
        metadata.pop("duns", None)
        metadata.pop("company_name", None)

        try:
            cache_key = self._generate_cache_key(
                uei=uei, duns=duns, company_name=company_name, cache_type=cache_type
            )
            cache_path = self._get_cache_path(cache_key)
            metadata_path = self._get_metadata_path(cache_key)

            from sbir_etl.utils.data.file_io import save_dataframe_parquet

            save_dataframe_parquet(df, cache_path, index=False)

            metadata_dict = {
                "cached_at": datetime.now().isoformat(),
                "cache_key": cache_key,
                "cache_type": cache_type,
                "row_count": len(df),
                **metadata,
            }
            with open(metadata_path, "w") as f:
                json.dump(metadata_dict, f, indent=2)

            logger.debug(f"Cached {len(df)} rows for {cache_key[:8]}...")

        except Exception as e:
            logger.warning(f"Error writing cache: {e}")

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
                if not expired_only:
                    cache_file.unlink(missing_ok=True)
                    cleared_count += 1
                continue

            try:
                with open(metadata_path) as f:
                    metadata = json.load(f)
            except Exception:
                if not expired_only:
                    cache_file.unlink(missing_ok=True)
                    metadata_path.unlink(missing_ok=True)
                    cleared_count += 1
                continue

            if cache_type and metadata.get("cache_type") != cache_type:
                continue

            if expired_only and not self._is_expired(metadata):
                continue

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
                    with open(metadata_path) as f:
                        metadata = json.load(f)
                    if self._is_expired(metadata):
                        is_expired = True
                except Exception:
                    is_expired = True
            else:
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
            "default_type": self.default_cache_type,
        }


# Backward compatibility alias
BaseDataFrameCache = APICache
