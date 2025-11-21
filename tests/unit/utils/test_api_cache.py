"""Tests for APICache."""


import pandas as pd
import pytest


pytestmark = pytest.mark.fast

from src.utils.cache.api_cache import APICache


@pytest.fixture
def cache_dir(tmp_path):
    """Create a temporary cache directory."""
    d = tmp_path / "cache"
    d.mkdir()
    return d


@pytest.fixture
def api_cache(cache_dir):
    """Create an APICache instance."""
    return APICache(cache_dir=cache_dir, enabled=True, ttl_hours=1, default_cache_type="test")


def test_api_cache_initialization(cache_dir):
    """Test initialization of APICache."""
    cache = APICache(cache_dir=cache_dir, default_cache_type="custom")
    assert cache.cache_dir == cache_dir
    assert cache.enabled is True
    assert cache._get_default_cache_type() == "custom"


def test_api_cache_set_get(api_cache):
    """Test setting and getting data from cache."""
    df = pd.DataFrame({"a": [1, 2], "b": [3, 4]})

    # Set data
    api_cache.set(df, company_name="Test Company", some_meta="data")

    # Get data
    cached_df = api_cache.get(company_name="Test Company")

    assert cached_df is not None
    pd.testing.assert_frame_equal(df, cached_df)


def test_api_cache_clear(api_cache):
    """Test clearing the cache."""
    df = pd.DataFrame({"a": [1]})
    api_cache.set(df, company_name="C1", cache_type="type1")
    api_cache.set(df, company_name="C2", cache_type="type2")

    assert len(list(api_cache.cache_dir.glob("*.parquet"))) == 2

    # Clear specific type
    api_cache.clear(cache_type="type1")
    assert len(list(api_cache.cache_dir.glob("*.parquet"))) == 1

    # Clear all
    api_cache.clear()
    assert len(list(api_cache.cache_dir.glob("*.parquet"))) == 0


def test_api_cache_get_stats(api_cache):
    """Test getting cache statistics."""
    df = pd.DataFrame({"a": [1]})
    api_cache.set(df, company_name="C1")

    stats = api_cache.get_stats()
    assert stats["total_entries"] == 1
    assert stats["total_size_mb"] >= 0
