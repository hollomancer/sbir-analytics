"""Backward compatibility shim — BaseDataFrameCache now lives in api_cache.py."""

from .api_cache import APICache as BaseDataFrameCache

__all__ = ["BaseDataFrameCache"]
