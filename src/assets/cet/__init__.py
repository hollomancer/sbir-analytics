"""CET (Critical & Emerging Technologies) assets package.

This package contains modularized Dagster assets for CET taxonomy processing,
classification, training, analytics, validation, and loading.

Exported assets:
- raw_cet_taxonomy: Load and validate CET taxonomy
- cet_taxonomy_completeness_check: Taxonomy validation check
- cet_taxonomy: Alias for raw_cet_taxonomy (backward compatibility)
"""

from __future__ import annotations

# Import all assets from submodules
from .taxonomy import (
    cet_taxonomy,
    cet_taxonomy_completeness_check,
    raw_cet_taxonomy,
    taxonomy_to_dataframe,
)

# Import utility functions for use by other modules
from .utils import (
    AssetCheckResult,
    AssetCheckSeverity,
    AssetExecutionContext,
    AssetIn,
    AssetKey,
    MetadataValue,
    Output,
    _read_parquet_or_ndjson,
    _serialize_metrics,
    asset,
    asset_check,
    save_dataframe_parquet,
)


__all__ = [
    # Taxonomy assets and checks
    "raw_cet_taxonomy",
    "cet_taxonomy",
    "cet_taxonomy_completeness_check",
    "taxonomy_to_dataframe",
    # Utility functions
    "save_dataframe_parquet",
    "_read_parquet_or_ndjson",
    "_serialize_metrics",
    # Dagster imports
    "asset",
    "asset_check",
    "AssetCheckResult",
    "AssetCheckSeverity",
    "AssetExecutionContext",
    "AssetIn",
    "AssetKey",
    "MetadataValue",
    "Output",
]
