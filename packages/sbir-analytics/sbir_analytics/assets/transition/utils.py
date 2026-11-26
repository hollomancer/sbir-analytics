"""Shared utilities for Transition assets.

This module provides:
- Dagster re-exports shared by the transition asset modules
- Helper functions for file I/O and data processing
- Environment variable utilities
- Data preparation functions
"""

from __future__ import annotations

from datetime import datetime

# Configuration and extractor imports (re-exported for use by other transition modules)
from sbir_etl.config.loader import env_bool as _env_bool
from sbir_etl.config.loader import env_float as _env_float
from sbir_etl.config.loader import env_int as _env_int
from sbir_etl.config.loader import get_config  # noqa: F401
from sbir_etl.extractors.contract_extractor import ContractExtractor  # noqa: F401
from sbir_ml.transition.features.vendor_resolver import VendorRecord, VendorResolver  # noqa: F401


# Statistical reporting imports
try:  # pragma: no cover - defensive import
    from sbir_etl.models.quality import ModuleReport  # type: ignore
    from sbir_etl.utils.reporting.analyzers.transition_analyzer import TransitionDetectionAnalyzer
except Exception:
    ModuleReport = None  # type: ignore[assignment,misc]
    TransitionDetectionAnalyzer = None  # type: ignore[assignment,misc]


from dagster import (
    AssetCheckResult,
    AssetCheckSeverity,
    AssetExecutionContext,
    MetadataValue,
    Output,
    asset,
    asset_check,
)


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
    "_env_float",
    "_env_int",
    "_env_bool",
    "_ensure_parent_dir",
    "save_dataframe_parquet",
    "write_json",
]


def now_utc_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


# -----------------------------
# 0) contracts_ingestion
# -----------------------------
