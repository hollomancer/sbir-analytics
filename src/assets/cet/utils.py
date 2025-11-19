"""Shared utilities for CET assets.

This module provides:
- Dagster import shims for testing environments without Dagster installed
- Common data I/O functions (parquet/JSON)
- Utility functions for metrics serialization
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
from loguru import logger


# ============================================================================
# Dagster Import Shims
# ============================================================================

try:
    from dagster import AssetCheckResult, AssetCheckSeverity, AssetIn, asset, asset_check
    from dagster import AssetExecutionContext as _RealAssetExecutionContext

    # Wrap the real AssetExecutionContext to accept no args for testing
    class AssetExecutionContext:
        def __init__(self, op_execution_context: Any = None, op_config: Any = None) -> None:
            if op_execution_context is None:
                # For testing: create a minimal mock-like object with loguru
                from loguru import logger as _logger

                class _L:
                    def info(self, *a: Any, **kw: Any) -> None:  # noqa: D401
                        _logger.info(*a, **kw)

                    def warning(self, *a: Any, **kw: Any) -> None:
                        _logger.warning(*a, **kw)

                    def error(self, *a: Any, **kw: Any) -> None:
                        _logger.error(*a, **kw)

                self.log = _L()
                self.op_config = op_config or {}
                self._is_shim = True
            else:
                # For real usage: use the real Dagster context
                self._real_context = _RealAssetExecutionContext(op_execution_context)
                self.log = self._real_context.log  # type: ignore[assignment]
                # Try to get op_config from the real context if available
                if hasattr(self._real_context, "op_config"):
                    self.op_config = self._real_context.op_config
                elif hasattr(op_execution_context, "op_config"):
                    self.op_config = op_execution_context.op_config
                else:
                    self.op_config = op_config or {}
                self._is_shim = False

except Exception:  # pragma: no cover

    def asset(*args: Any, **kwargs: Any) -> Any:  # type: ignore[no-redef]
        def _wrap(fn: Any) -> Any:
            return fn

        return _wrap

    def asset_check(*args: Any, **kwargs: Any) -> Any:
        def _wrap(fn: Any) -> Any:
            return fn

        return _wrap

    def AssetIn(*args: Any, **kwargs: Any) -> None:  # type: ignore[no-redef]
        return None

    class AssetCheckResult:  # type: ignore[no-redef]
        def __init__(
            self,
            passed: bool,
            severity: Any = None,
            description: Any = None,
            metadata: Any = None,
        ) -> None:
            self.passed = passed
            self.severity = severity
            self.description = description
            self.metadata = metadata

    class AssetCheckSeverity:  # type: ignore[no-redef]
        ERROR = "ERROR"
        WARN = "WARN"

    class AssetExecutionContext:  # type: ignore[no-redef]
        def __init__(self, op_execution_context: Any = None) -> None:
            from loguru import logger as _logger

            class _L:
                def info(self, *a: Any, **kw: Any) -> None:  # noqa: D401
                    _logger.info(*a, **kw)

                def warning(self, *a: Any, **kw: Any) -> None:
                    _logger.warning(*a, **kw)

                def error(self, *a: Any, **kw: Any) -> None:
                    _logger.error(*a, **kw)

            self.log = _L()
            if op_execution_context:
                # Store if provided for compatibility
                self._op_execution_context = op_execution_context


# Dagster Output/asset/AssetKey/MetadataValue stubs
try:
    from dagster import AssetKey, MetadataValue, Output, asset
except Exception:  # pragma: no cover - fallback stubs when dagster is not installed
    # Lightweight stubs so this module can be imported in environments without dagster.
    class Output:  # type: ignore[no-redef]
        def __init__(self, value: Any, metadata=None) -> None:
            self.value = value
            self.metadata = metadata

        def __repr__(self) -> str:
            return f"Output(value={self.value!r}, metadata={self.metadata!r})"

    def asset(*dargs: Any, **dkwargs: Any) -> Any:  # type: ignore[no-redef]
        # decorator passthrough: return the function unchanged
        def _decorator(fn: Any) -> Any:
            return fn

        return _decorator

    class AssetKey:  # type: ignore[no-redef]
        def __init__(self, key: Any) -> None:
            self.key = key

        def __repr__(self) -> str:
            return f"AssetKey({self.key!r})"

    class MetadataValue:  # type: ignore[no-redef]
        @staticmethod
        def text(s: Any) -> Any:
            return s


# ============================================================================
# Data I/O Functions
# ============================================================================


# Import centralized file I/O utilities
from src.utils.data.file_io import save_dataframe_parquet

# Re-export for backward compatibility
__all__ = ["save_dataframe_parquet"]


def _read_parquet_or_ndjson(
    parquet_path: Path, json_path: Path, expected_columns: tuple
) -> list[dict]:
    """Read data from parquet or fallback to NDJSON."""
    try:
        if parquet_path.exists():
            df = pd.read_parquet(parquet_path)
            return df.to_dict(orient="records")
        elif json_path.exists():
            records = []
            with json_path.open("r", encoding="utf-8") as fh:
                for line in fh:
                    if line.strip():
                        try:
                            records.append(json.loads(line))
                        except Exception:
                            continue
            return records
    except Exception:
        pass
    return []


def _serialize_metrics(metrics: Any) -> dict[str, Any]:
    """Serialize LoadMetrics to dict."""
    if metrics is None:
        return {}
    return {
        "nodes_created": getattr(metrics, "nodes_created", 0),
        "nodes_updated": getattr(metrics, "nodes_updated", 0),
        "relationships_created": getattr(metrics, "relationships_created", 0),
        "relationships_updated": getattr(metrics, "relationships_updated", 0),
        "execution_time_ms": getattr(metrics, "execution_time_ms", 0),
    }
