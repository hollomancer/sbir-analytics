"""Unit tests for PatentsView cache utilities."""

from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

pytestmark = pytest.mark.fast

from src.utils.patentsview_cache import PatentsViewCache


class TestPatentsViewCache:
    """Tests for PatentsViewCache class."""

    @pytest.fixture
    def cache(self, tmp_path):
        """Create a PatentsViewCache instance."""
        return PatentsViewCache(cache_dir=tmp_path / "cache", enabled=True, ttl_hours=24)

    @pytest.fixture
    def disabled_cache(self, tmp_path):
        """Create a disabled PatentsViewCache instance."""
        return PatentsViewCache(cache_dir=tmp_path / "cache", enabled=False, ttl_hours=24)

    def test_get_default_cache_type(self, cache):
        """Test default cache type is 'patents'."""
        assert cache._get_default_cache_type() == "patents"

    @patch("src.utils.base_cache.save_dataframe_parquet")
    def test_set_adds_patentsview_metadata(self, mock_save, cache):
        """Test set adds PatentsView-specific metadata."""
        df = pd.DataFrame({"col": [1, 2, 3]})
        cache.set(
            df=df,
            uei="TEST123456789",
            duns="123456789",
            company_name="Test Company",
        )

        # Verify save was called
        mock_save.assert_called_once()

    def test_clear_all_entries(self, cache, tmp_path):
        """Test clear removes all cache entries."""
        # Create cache entries
        for i in range(3):
            cache_key = cache._generate_cache_key(uei=f"TEST{i}")
            cache_file = cache._get_cache_path(cache_key)
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.touch()

            metadata_path = cache._get_metadata_path(cache_key)
            import json
            from datetime import datetime

            metadata = {"cached_at": datetime.now().isoformat()}
            with open(metadata_path, "w") as f:
                json.dump(metadata, f)

        cache.clear()

        # Verify all files are removed
        assert len(list(cache.cache_dir.glob("*.parquet"))) == 0

    def test_clear_by_cache_type(self, cache, tmp_path):
        """Test clear filters by cache type."""
        # Create entries with different cache types
        import json
        from datetime import datetime

        for i, cache_type in enumerate(["patents", "assignments", "patents"]):
            cache_key = cache._generate_cache_key(uei=f"TEST{i}", cache_type=cache_type)
            cache_file = cache._get_cache_path(cache_key)
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.touch()

            metadata_path = cache._get_metadata_path(cache_key)
            metadata = {
                "cached_at": datetime.now().isoformat(),
                "cache_type": cache_type,
            }
            with open(metadata_path, "w") as f:
                json.dump(metadata, f)

        # Clear only "patents" type
        cache.clear(cache_type="patents")

        # Should have 1 remaining (assignments)
        remaining = list(cache.cache_dir.glob("*.parquet"))
        assert len(remaining) == 1

    def test_clear_nonexistent_cache_dir(self, cache):
        """Test clear handles nonexistent cache directory."""
        cache.cache_dir = Path("/nonexistent/path")
        # Should not raise an error
        cache.clear()

