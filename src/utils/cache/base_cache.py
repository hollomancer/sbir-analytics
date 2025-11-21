"""Base cache class for file-based DataFrame caching.

This module provides a base class for file-based caching of API responses,
with support for TTL-based expiration and metadata tracking.
"""

import hashlib
import json
from abc import ABC
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
from loguru import logger


class BaseDataFrameCache(ABC):  # noqa: B024
    """Base class for file-based DataFrame caching.

    Provides common functionality for caching DataFrames with TTL-based expiration.
    Subclasses should override default_cache_dir and default_cache_type.
    """

    def __init__(
        self,
        cache_dir: str | Path,
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
            from src.utils.common.path_utils import ensure_dir

            ensure_dir(self.cache_dir)
            logger.debug(
                f"{self.__class__.__name__} cache initialized at {self.cache_dir} (TTL: {ttl_hours}h)"
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
            cache_type: Type of cache entry (subclass-specific)

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
            cache_type = self._get_default_cache_type()

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
            with open(metadata_path) as f:
                metadata = json.load(f)

            # Check expiration
            if self._is_expired(metadata):
                logger.debug(
                    f"Cache entry expired for {cache_key[:8]}... (cached at {metadata.get('cached_at')})"
                )
                # Clean up expired files
                cache_path.unlink(missing_ok=True)
                metadata_path.unlink(missing_ok=True)
                return None

            # Load cached DataFrame
            df = pd.read_parquet(cache_path)
            logger.debug(
                f"Cache hit for {cache_key[:8]}... ({len(df)} rows, cached at {metadata.get('cached_at')})"
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
            cache_type = self._get_default_cache_type()

        try:
            cache_key = self._generate_cache_key(
                uei=uei, duns=duns, company_name=company_name, cache_type=cache_type
            )
            cache_path = self._get_cache_path(cache_key)
            metadata_path = self._get_metadata_path(cache_key)

            # Save DataFrame using centralized utility
            from src.utils.data.file_io import save_dataframe_parquet

            save_dataframe_parquet(df, cache_path, index=False)

            # Save metadata
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

    def _get_default_cache_type(self) -> str:
        """Get the default cache type for this cache implementation.

        Subclasses should override this method.

        Returns:
            Default cache type string
        """
        return "default"
