"""PatentsView API response cache utility.

This module provides file-based caching for PatentsView API responses to avoid
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


class PatentsViewCache:
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
        self.cache_dir = Path(cache_dir)
        self.enabled = enabled
        self.ttl_hours = ttl_hours

        if self.enabled:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            logger.debug(
                f"PatentsView cache initialized at {self.cache_dir} (TTL: {ttl_hours}h)"
            )

    def _generate_cache_key(
        self,
        uei: str | None = None,
        duns: str | None = None,
        company_name: str | None = None,
        cache_type: str = "patents",
    ) -> str:
        """Generate a cache key from company identifiers.

        Args:
            uei: Company UEI
            duns: Company DUNS number
            company_name: Company name
            cache_type: Type of cache entry ("patents" for patent queries, "assignments" for assignment queries)

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

        # Add cache type to distinguish different query types
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
        cache_type: str = "patents",
    ) -> pd.DataFrame | None:
        """Retrieve cached data if available and not expired.

        Args:
            uei: Company UEI
            duns: Company DUNS number
            company_name: Company name
            cache_type: Type of cache entry ("patents" for patent queries, "assignments" for assignment queries)

        Returns:
            Cached DataFrame if found and valid, None otherwise
        """
        if not self.enabled:
            return None

        try:
            cache_key = self._generate_cache_key(
                uei=uei, duns=duns, company_name=company_name, cache_type=cache_type
            )
            cache_path = self._get_cache_path(cache_key)
            metadata_path = self._get_metadata_path(cache_key)

            # Check if cache files exist
            if not cache_path.exists() or not metadata_path.exists():
                return None

            # Load and check metadata
            with open(metadata_path, "r") as f:
                metadata = json.load(f)

            if self._is_expired(metadata):
                logger.debug(f"Cache expired for key {cache_key[:16]}...")
                return None

            # Load cached DataFrame
            df = pd.read_parquet(cache_path)
            logger.debug(
                f"Cache hit for {company_name or uei or duns or 'unknown'} "
                f"(cached at {metadata.get('cached_at', 'unknown')})"
            )
            return df

        except Exception as e:
            logger.warning(f"Error reading cache: {e}")
            return None

    def set(
        self,
        df: pd.DataFrame,
        uei: str | None = None,
        duns: str | None = None,
        company_name: str | None = None,
        cache_type: str = "patents",
    ) -> None:
        """Store data in cache.

        Args:
            df: DataFrame to cache
            uei: Company UEI
            duns: Company DUNS number
            company_name: Company name
            cache_type: Type of cache entry ("patents" for patent queries, "assignments" for assignment queries)
        """
        if not self.enabled:
            return

        try:
            cache_key = self._generate_cache_key(
                uei=uei, duns=duns, company_name=company_name, cache_type=cache_type
            )
            cache_path = self._get_cache_path(cache_key)
            metadata_path = self._get_metadata_path(cache_key)

            # Save DataFrame using centralized utility
            from src.utils.file_io import save_dataframe_parquet
            
            save_dataframe_parquet(df, cache_path, index=False)

            # Save metadata
            metadata = {
                "cached_at": datetime.now().isoformat(),
                "ttl_hours": self.ttl_hours,
                "row_count": len(df),
                "cache_type": cache_type,
            }
            with open(metadata_path, "w") as f:
                json.dump(metadata, f, indent=2)

            logger.debug(
                f"Cached {len(df)} rows for {company_name or uei or duns or 'unknown'} "
                f"(key: {cache_key[:16]}...)"
            )

        except Exception as e:
            logger.warning(f"Error writing cache: {e}")

    def clear(self, cache_type: str | None = None) -> None:
        """Clear cache entries.

        Args:
            cache_type: Optional cache type to clear (if None, clears all)
        """
        if not self.cache_dir.exists():
            return

        cleared_count = 0
        for cache_file in self.cache_dir.glob("*.parquet"):
            cache_key = cache_file.stem.replace(".parquet", "")

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
            cache_file.unlink()
            metadata_path = self._get_metadata_path(cache_key)
            if metadata_path.exists():
                metadata_path.unlink()
            cleared_count += 1

        logger.info(f"Cleared {cleared_count} cache entries")

