"""Unit tests for base cache utilities."""

from datetime import datetime, timedelta
from unittest.mock import patch

import pandas as pd
import pytest


pytestmark = pytest.mark.fast

from src.utils.cache.base_cache import BaseDataFrameCache


class TestCache(BaseDataFrameCache):
    """Test implementation of BaseDataFrameCache."""

    def _get_default_cache_type(self) -> str:
        return "test"


class TestBaseDataFrameCache:
    """Tests for BaseDataFrameCache base class."""

    @pytest.fixture
    def cache(self, tmp_path):
        """Create a test cache instance."""
        return TestCache(cache_dir=tmp_path / "cache", enabled=True, ttl_hours=24)

    @pytest.fixture
    def disabled_cache(self, tmp_path):
        """Create a disabled test cache instance."""
        return TestCache(cache_dir=tmp_path / "cache", enabled=False, ttl_hours=24)

    def test_init_creates_cache_dir(self, tmp_path):
        """Test that cache directory is created on initialization."""
        cache_dir = tmp_path / "cache"
        assert not cache_dir.exists()

        TestCache(cache_dir=cache_dir, enabled=True)

        assert cache_dir.exists()

    def test_generate_cache_key_with_uei(self, cache):
        """Test cache key generation with UEI."""
        key = cache._generate_cache_key(uei="TEST123456789")
        assert isinstance(key, str)
        assert len(key) == 64  # SHA256 hex digest

    def test_generate_cache_key_with_duns(self, cache):
        """Test cache key generation with DUNS."""
        key = cache._generate_cache_key(duns="123456789")
        assert isinstance(key, str)

    def test_generate_cache_key_with_company_name(self, cache):
        """Test cache key generation with company name."""
        key = cache._generate_cache_key(company_name="Test Company Inc")
        assert isinstance(key, str)

    def test_generate_cache_key_requires_at_least_one_identifier(self, cache):
        """Test cache key generation fails without identifiers."""
        with pytest.raises(ValueError, match="At least one identifier"):
            cache._generate_cache_key()

    def test_generate_cache_key_normalizes_identifiers(self, cache):
        """Test cache key generation normalizes identifiers consistently."""
        key1 = cache._generate_cache_key(uei="test123", company_name="Test Company")
        key2 = cache._generate_cache_key(uei="TEST123", company_name="  test  company  ")
        assert key1 == key2  # Should be the same after normalization

    def test_get_cache_path(self, cache):
        """Test cache path generation."""
        key = "test_key_123"
        path = cache._get_cache_path(key)
        assert path.name == "test_key_123.parquet"
        assert path.parent == cache.cache_dir

    def test_get_metadata_path(self, cache):
        """Test metadata path generation."""
        key = "test_key_123"
        path = cache._get_metadata_path(key)
        assert path.name == "test_key_123.meta.json"
        assert path.parent == cache.cache_dir

    def test_is_expired_with_valid_metadata(self, cache):
        """Test expiration check with valid metadata."""
        metadata = {
            "cached_at": (datetime.now() - timedelta(hours=12)).isoformat(),
        }
        assert not cache._is_expired(metadata)

    def test_is_expired_with_expired_metadata(self, cache):
        """Test expiration check with expired metadata."""
        metadata = {
            "cached_at": (datetime.now() - timedelta(hours=25)).isoformat(),
        }
        assert cache._is_expired(metadata)

    def test_is_expired_without_cached_at(self, cache):
        """Test expiration check without cached_at field."""
        metadata = {}
        assert cache._is_expired(metadata)

    def test_get_returns_none_when_disabled(self, disabled_cache):
        """Test get returns None when cache is disabled."""
        result = disabled_cache.get(uei="TEST123")
        assert result is None

    def test_get_returns_none_when_not_cached(self, cache):
        """Test get returns None when entry doesn't exist."""
        result = cache.get(uei="TEST123")
        assert result is None

    @patch("src.utils.cache.base_cache.save_dataframe_parquet")
    def test_set_when_disabled(self, mock_save, disabled_cache):
        """Test set does nothing when cache is disabled."""
        df = pd.DataFrame({"col": [1, 2, 3]})
        disabled_cache.set(df, uei="TEST123")

        mock_save.assert_not_called()

    @patch("src.utils.cache.base_cache.save_dataframe_parquet")
    def test_set_saves_dataframe(self, mock_save, cache):
        """Test set saves DataFrame and metadata."""
        df = pd.DataFrame({"col": [1, 2, 3]})
        cache.set(df, uei="TEST123")

        mock_save.assert_called_once()
        assert cache.cache_dir / "*.meta.json" in list(cache.cache_dir.glob("*.meta.json"))

    def test_get_default_cache_type(self, cache):
        """Test default cache type."""
        assert cache._get_default_cache_type() == "test"

