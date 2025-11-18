"""Safe configuration access utilities.

This module provides utilities for safely accessing nested configuration values
with dot notation, reducing the need for defensive checks and nested .get() calls.
"""

from __future__ import annotations

from typing import Any

from ..config.schemas import PipelineConfig


class ConfigAccessor:
    """Utility for safely accessing nested configuration values."""

    @staticmethod
    def get_nested(config: PipelineConfig, path: str, default: Any = None) -> Any:
        """Safely access nested config values with dot notation.

        Args:
            config: PipelineConfig instance
            path: Dot-separated path to config value (e.g., "ml.paecter.use_local")
            default: Default value to return if path not found

        Returns:
            Config value at path, or default if not found

        Example:
            >>> config = get_config()
            >>> use_local = ConfigAccessor.get_nested(config, "ml.paecter.use_local", False)
            >>> batch_size = ConfigAccessor.get_nested(config, "ml.paecter.batch_size", 32)
        """
        parts = path.split(".")
        current: Any = config

        for part in parts:
            if current is None:
                return default

            # Try attribute access first
            if hasattr(current, part):
                current = getattr(current, part)
            # Fall back to dict-like access
            elif isinstance(current, dict):
                current = current.get(part)
            else:
                return default

        return current if current is not None else default

    @staticmethod
    def get_nested_dict(config: PipelineConfig, path: str, default: dict[str, Any] | None = None) -> dict[str, Any]:
        """Safely access nested config dictionary.

        Args:
            config: PipelineConfig instance
            path: Dot-separated path to config dict (e.g., "ml.paecter")
            default: Default dict to return if path not found

        Returns:
            Config dict at path, or default if not found

        Example:
            >>> config = get_config()
            >>> paecter_config = ConfigAccessor.get_nested_dict(config, "ml.paecter", {})
            >>> use_local = paecter_config.get("use_local", False)
        """
        result = ConfigAccessor.get_nested(config, path, default)
        if result is None:
            return default or {}
        if isinstance(result, dict):
            return result
        # If result is not a dict, try to convert (e.g., Pydantic model to dict)
        if hasattr(result, "model_dump"):
            return result.model_dump()
        if hasattr(result, "dict"):
            return result.dict()
        return default or {}

