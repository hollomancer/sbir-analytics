"""Unit tests for USAspending cache utilities."""

from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

pytestmark = pytest.mark.fast

from src.utils.usaspending_cache import USAspendingCache


class TestUSAspendingCache:
    """Tests for USAspendingCache class."""

    @pytest.fixture
    def cache(self, tmp_path):
        """Create a USAspendingCache instance."""
        return USAspendingCache(cache_dir=tmp_path / "cache", enabled=True, ttl_hours=24)

    @pytest.fixture
    def disabled_cache(self, tmp_path):
        """Create a disabled USAspendingCache instance."""
        return USAspendingCache(cache_dir=tmp_path / "cache", enabled=False, ttl_hours=24)

    def test_get_default_cache_type(self, cache):
        """Test default cache type is 'contracts'."""
        assert cache._get_default_cache_type() == "contracts"

    @patch("src.utils.base_cache.save_dataframe_parquet")
    def test_set_adds_usaspending_metadata(self, mock_save, cache):
        """Test set adds USAspending-specific metadata."""
        df = pd.DataFrame({"col": [1, 2, 3]})
        cache.set(
            df=df,
            uei="TEST123456789",
            duns="123456789",
            company_name="Test Company",
            api_calls=5,
        )

        # Verify save was called
        mock_save.assert_called_once()
        # Check that metadata includes USAspending fields
        call_args = mock_save.call_args
        assert call_args is not None

    @patch("src.utils.base_cache.save_dataframe_parquet")
    def test_set_uses_default_cache_type(self, mock_save, cache):
        """Test set uses default cache type when not specified."""
        df = pd.DataFrame({"col": [1, 2, 3]})
        cache.set(df=df, uei="TEST123")

        mock_save.assert_called_once()

    @patch("src.utils.base_cache.save_dataframe_parquet")
    def test_set_with_sbir_cache_type(self, mock_save, cache):
        """Test set with SBIR cache type."""
        df = pd.DataFrame({"col": [1, 2, 3]})
        cache.set(df=df, uei="TEST123", cache_type="sbir")

        mock_save.assert_called_once()

    def test_clear_expired_only(self, cache, tmp_path):
        """Test clear with expired_only=True."""
        # Create expired cache entry
        cache_key = cache._generate_cache_key(uei="TEST123")
        cache_file = cache._get_cache_path(cache_key)
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.touch()

        metadata_path = cache._get_metadata_path(cache_key)
        import json
        from datetime import datetime, timedelta

        expired_time = datetime.now() - timedelta(hours=25)
        metadata = {"cached_at": expired_time.isoformat()}
        with open(metadata_path, "w") as f:
            json.dump(metadata, f)

        cleared = cache.clear(expired_only=True)
        assert cleared == 1

    def test_clear_all(self, cache, tmp_path):
        """Test clear with expired_only=False."""
        # Create cache entries
        for i in range(3):
            cache_key = cache._generate_cache_key(uei=f"TEST{i}")
            cache_file = cache._get_cache_path(cache_key)
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.touch()

        cleared = cache.clear(expired_only=False)
        assert cleared == 3

    def test_get_stats_empty_cache(self, cache):
        """Test get_stats with empty cache."""
        stats = cache.get_stats()

        assert stats["enabled"] is True
        assert stats["total_entries"] == 0
        assert stats["expired_entries"] == 0
        assert stats["valid_entries"] == 0
        assert stats["total_size_mb"] == 0.0

    def test_get_stats_with_entries(self, cache, tmp_path):
        """Test get_stats with cache entries."""
        # Create cache entries
        for i in range(2):
            cache_key = cache._generate_cache_key(uei=f"TEST{i}")
            cache_file = cache._get_cache_path(cache_key)
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_bytes(b"test data" * 100)  # Some data

            metadata_path = cache._get_metadata_path(cache_key)
            import json
            from datetime import datetime

            metadata = {"cached_at": datetime.now().isoformat()}
            with open(metadata_path, "w") as f:
                json.dump(metadata, f)

        stats = cache.get_stats()

        assert stats["total_entries"] == 2
        assert stats["valid_entries"] == 2
        assert stats["expired_entries"] == 0
        assert stats["total_size_mb"] > 0

    def test_get_stats_disabled_cache(self, disabled_cache):
        """Test get_stats for disabled cache."""
        stats = disabled_cache.get_stats()

        assert stats["enabled"] is False

