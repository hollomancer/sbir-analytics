"""Shared utilities for Transition assets.

This module provides:
- Dagster import shims for testing environments
- Helper functions for file I/O and data processing
- Environment variable utilities
- Data preparation functions
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any
from loguru import logger

# Configuration and extractor imports (re-exported for use by other transition modules)
from sbir_etl.config.loader import get_config  # noqa: F401
from sbir_etl.extractors.contract_extractor import ContractExtractor  # noqa: F401
from sbir_etl.identity import CompanyNameProfile, normalize_company_name
from sbir_ml.transition.features.vendor_resolver import VendorRecord, VendorResolver  # noqa: F401


# Statistical reporting imports
try:  # pragma: no cover - defensive import
    from sbir_etl.models.quality import ModuleReport  # type: ignore
    from sbir_etl.utils.reporting.analyzers.transition_analyzer import TransitionDetectionAnalyzer
except Exception:
    ModuleReport = None  # type: ignore[assignment,misc]
    TransitionDetectionAnalyzer = None  # type: ignore[assignment,misc]


# Import-safe shims for Dagster
try:
    from dagster import (
        AssetCheckResult,
        AssetCheckSeverity,
        MetadataValue,
        Output,
        asset,
        asset_check,
    )
    from dagster import AssetExecutionContext as _RealAssetExecutionContext

    # Wrap the real AssetExecutionContext to accept no args for testing
    class AssetExecutionContext:
        def __init__(self, op_execution_context: Any = None) -> None:
            if op_execution_context is None:
                # For testing: create a minimal mock-like object
                self.log = logger
                self._is_shim = True
            else:
                # For real usage: use the real Dagster context
                self._real_context = _RealAssetExecutionContext(op_execution_context)
                self.log: Any = self._real_context.log  # type: ignore[assignment, no-redef]
                self._is_shim = False

except Exception:  # pragma: no cover
    # Minimal shims so this module can be imported without Dagster installed
    def asset(*args, **kwargs):  # type: ignore
        def _wrap(fn):
            return fn

        return _wrap

    class Output:  # type: ignore
        def __init__(self, value: Any, metadata=None) -> None:
            self.value = value
            self.metadata = metadata or {}

    class MetadataValue:  # type: ignore
        @staticmethod
        def json(v: Any) -> Any:
            return v

    class AssetExecutionContext:  # type: ignore
        def __init__(self, op_execution_context: Any = None) -> None:
            self.log = logger
            if op_execution_context:
                # Store if provided for compatibility
                self._op_execution_context = op_execution_context

    def asset_check(*args, **kwargs):  # type: ignore
        def _wrap(fn):
            return fn

        return _wrap

    class AssetCheckResult:  # type: ignore
        def __init__(
            self,
            passed: bool,
            severity=None,
            description: str = "",
            metadata: dict | None = None,
        ) -> None:
            self.passed = passed
            self.severity = severity
            self.description = description
            self.metadata = metadata or {}

    class AssetCheckSeverity:  # type: ignore
        ERROR = "ERROR"
        WARN = "WARN"


# Import centralized file I/O utilities
from sbir_etl.utils.path_utils import ensure_parent_dir as _ensure_parent_dir
from sbir_etl.utils.data.file_io import save_dataframe_parquet, write_json


# Re-export for use by transition assets
__all__ = [
    "Output",
    "MetadataValue",
    "asset",
    "asset_check",
    "AssetExecutionContext",
    "AssetCheckResult",
    "AssetCheckSeverity",
    "now_utc_iso",
    "_norm_name",
    "_env_float",
    "_env_int",
    "_env_bool",
    "_ensure_parent_dir",
    "save_dataframe_parquet",
    "write_json",
]


def now_utc_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def _norm_name(s: str | None) -> str:
    """Build the company join key via the ``lower-join-v1`` identity profile."""
    return normalize_company_name(s, profile=CompanyNameProfile.LOWER_JOIN_V1)


def _env_float(key: str, default: float) -> float:
    try:
        return float(os.getenv(key, str(default)))
    except Exception:
        return default


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, str(default)))
    except Exception:
        return default


def _env_bool(key: str, default: bool) -> bool:
    v = os.getenv(key)
    if v is None:
        return default
    return v.strip().lower() in {"1", "true", "yes", "on"}


# -----------------------------
# 0) contracts_ingestion
# -----------------------------
