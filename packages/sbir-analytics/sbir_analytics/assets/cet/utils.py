"""Shared utilities for CET assets.

This module provides:
- Dagster re-exports shared by the CET asset modules
- Common data I/O functions (parquet/JSON)
- Utility functions for metrics serialization
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from dagster import (
    AssetCheckResult,
    AssetCheckSeverity,
    AssetExecutionContext,
    AssetIn,
    AssetKey,
    MetadataValue,
    Output,
    asset,
    asset_check,
)


# ============================================================================
# Data I/O Functions
# ============================================================================


# Import centralized file I/O utilities
from sbir_etl.utils.data.file_io import save_dataframe_parquet


# Re-export for backward compatibility
__all__ = [
    "AssetCheckResult",
    "AssetCheckSeverity",
    "AssetExecutionContext",
    "AssetIn",
    "AssetKey",
    "MetadataValue",
    "Output",
    "asset",
    "asset_check",
    "save_dataframe_parquet",
]


def _read_parquet_or_ndjson(
    parquet_path: Path,
    json_path: Path,
    expected_columns: tuple,
    *,
    allow_empty: bool = False,
) -> list[dict]:
    """Read and validate a parquet or NDJSON artifact without hiding malformed input."""
    if parquet_path.exists():
        df = pd.read_parquet(parquet_path)
        missing = set(expected_columns) - set(df.columns)
        if missing:
            names = ", ".join(sorted(missing))
            raise ValueError(f"{parquet_path} is missing required columns: {names}")
        records = df.to_dict(orient="records")
        if not records and not allow_empty:
            raise ValueError(f"{parquet_path} contains no records")
        return records

    if json_path.exists():
        records = []
        with json_path.open("r", encoding="utf-8") as fh:
            for line_number, line in enumerate(fh, start=1):
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"Invalid JSON in {json_path} at line {line_number}") from exc
                if not isinstance(record, dict):
                    raise ValueError(f"Expected an object in {json_path} at line {line_number}")
                missing = set(expected_columns) - set(record)
                if missing:
                    names = ", ".join(sorted(missing))
                    raise ValueError(
                        f"{json_path} line {line_number} is missing required fields: {names}"
                    )
                records.append(record)
        if not records and not allow_empty:
            raise ValueError(f"{json_path} contains no records")
        return records

    raise FileNotFoundError(f"No input artifact found at {parquet_path} or {json_path}")
