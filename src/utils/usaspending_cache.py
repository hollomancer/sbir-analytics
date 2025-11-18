"""USAspending API response cache utility.

This module provides file-based caching for USAspending API responses to avoid
repeated API calls when running scripts multiple times. Cache entries are keyed
by company identifiers (UEI/DUNS/name) and include metadata for cache invalidation.
"""

import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
from loguru import logger


class USAspendingCache:
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
        self.cache_dir = Path(cache_dir)
        self.enabled = enabled
        self.ttl_hours = ttl_hours

        if self.enabled:
            from src.utils.path_utils import ensure_dir
            
            ensure_dir(self.cache_dir)
            logger.debug(f"USAspending cache initialized at {self.cache_dir} (TTL: {ttl_hours}h)")

    def _generate_cache_key(
        self,
        uei: str | None = None,
        duns: str | None = None,
        company_name: str | None = None,
        cache_type: str = "contracts",
    ) -> str:
        """Generate a cache key from company identifiers.

        Args:
            uei: Company UEI
            duns: Company DUNS number
            company_name: Company name
            cache_type: Type of cache entry ("contracts" for non-SBIR, "sbir" for SBIR-only)

        Returns:
            Cache key (hash of normalized identifiers)
        """
        # Normalize identifiers for consistent hashing
        parts = []
        if uei:
            parts.append(f"uei:{uei.strip().upper()}")
        if duns:
            parts.append(f"duns:{str(duns).strip()}")
        if company_name:
            # Normalize name: strip, uppercase, remove extra whitespace
            normalized_name = " ".join(company_name.strip().upper().split())
            parts.append(f"name:{normalized_name}")

        if not parts:
            raise ValueError("At least one identifier (UEI, DUNS, or name) must be provided")

        # Add cache type to distinguish SBIR vs non-SBIR
        parts.append(f"type:{cache_type}")

        # Create hash of combined identifiers
        key_string = "|".join(sorted(parts))
        key_hash = hashlib.sha256(key_string.encode("utf-8")).hexdigest()
        return key_hash

    def _get_cache_path(self, cache_key: str) -> Path:
        """Get the file path for a cache key.

        Args:
            cache_key: Cache key

        Returns:
            Path to cache file
        """
        return self.cache_dir / f"{cache_key}.parquet"

    def _get_metadata_path(self, cache_key: str) -> Path:
        """Get the metadata file path for a cache key.

        Args:
            cache_key: Cache key

        Returns:
            Path to metadata file
        """
        return self.cache_dir / f"{cache_key}.meta.json"

    def _is_expired(self, metadata: dict[str, Any]) -> bool:
        """Check if a cache entry is expired.

        Args:
            metadata: Cache metadata dict

        Returns:
            True if expired, False otherwise
        """
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
        cache_type: str = "contracts",
    ) -> pd.DataFrame | None:
        """Retrieve cached data if available and not expired.

        Args:
            uei: Company UEI
            duns: Company DUNS number
            company_name: Company name
            cache_type: Type of cache entry ("contracts" for non-SBIR, "sbir" for SBIR-only)

        Returns:
            Cached DataFrame if found and valid, None otherwise
        """
        if not self.enabled:
            return None

        try:
            cache_key = self._generate_cache_key(uei=uei, duns=duns, company_name=company_name, cache_type=cache_type)
            cache_path = self._get_cache_path(cache_key)
            metadata_path = self._get_metadata_path(cache_key)

            # Check if cache files exist
            if not cache_path.exists() or not metadata_path.exists():
                return None

            # Load and check metadata
            with open(metadata_path, "r") as f:
                metadata = json.load(f)

            # Check expiration
            if self._is_expired(metadata):
                logger.debug(f"Cache entry expired for {cache_key[:8]}... (cached at {metadata.get('cached_at')})")
                # Clean up expired files
                cache_path.unlink(missing_ok=True)
                metadata_path.unlink(missing_ok=True)
                return None

            # Load cached DataFrame
            df = pd.read_parquet(cache_path)
            logger.debug(
                f"Cache hit for {cache_key[:8]}... ({len(df)} contracts, cached at {metadata.get('cached_at')})"
            )
            return df

        except Exception as e:
            logger.warning(f"Error reading cache: {e}")
            # Clean up corrupted cache files
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
        cache_type: str = "contracts",
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
        if not self.enabled:
            return

        try:
            cache_key = self._generate_cache_key(uei=uei, duns=duns, company_name=company_name, cache_type=cache_type)
            cache_path = self._get_cache_path(cache_key)
            metadata_path = self._get_metadata_path(cache_key)

            # Save DataFrame using centralized utility
            from src.utils.file_io import save_dataframe_parquet
            
            save_dataframe_parquet(df, cache_path, index=False)

            # Save metadata
            metadata_dict = {
                "cached_at": datetime.now().isoformat(),
                "cache_key": cache_key,
                "uei": uei,
                "duns": duns,
                "company_name": company_name,
                "row_count": len(df),
                **metadata,
            }
            with open(metadata_path, "w") as f:
                json.dump(metadata_dict, f, indent=2)

            logger.debug(f"Cached {len(df)} contracts for {cache_key[:8]}...")

        except Exception as e:
            logger.warning(f"Error writing cache: {e}")

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
                    with open(metadata_path, "r") as f:
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
            logger.info(f"Cleared {cleared} cache entries ({'expired only' if expired_only else 'all'})")
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
                    with open(metadata_path, "r") as f:
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

