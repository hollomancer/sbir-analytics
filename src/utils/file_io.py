"""Centralized file I/O utilities for consistent data persistence.

This module provides:
- Unified parquet saving with NDJSON fallback
- Atomic JSON write operations
- NDJSON writing utilities
- Unified parquet/NDJSON reading
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

import pandas as pd
from loguru import logger


# Import centralized path utilities
from src.utils.path_utils import ensure_parent_dir as _ensure_parent_dir


def _to_jsonable(x: Any) -> Any:
    """Convert a value to JSON-serializable format.
    
    Handles pandas Timestamps, NumPy scalars, NaN/NaT values, and nested containers.
    
    Args:
        x: Value to convert
        
    Returns:
        JSON-serializable value
    """
    try:
        if pd.isna(x):
            return None
    except Exception:
        pass
    
    # pandas Timestamps
    if hasattr(x, "isoformat"):
        try:
            return x.isoformat()
        except Exception:
            pass
    
    # NumPy scalars
    try:
        import numpy as _np

        if isinstance(x, _np.generic):
            try:
                return x.item()
            except Exception:
                pass
    except Exception:
        pass
    
    # Containers
    if isinstance(x, dict):
        return {str(k): _to_jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple, set)):
        return [_to_jsonable(v) for v in list(x)]
    
    return x


def save_dataframe_parquet(
    df: pd.DataFrame,
    path: Path,
    index: bool = False,
    fallback_to_ndjson: bool = True,
    **kwargs: Any,
) -> None:
    """Save DataFrame to Parquet format with NDJSON fallback.
    
    Attempts to save as Parquet first. If that fails and fallback_to_ndjson is True,
    falls back to NDJSON format in the same directory with .ndjson suffix.
    
    Args:
        df: DataFrame to save
        path: Destination path for Parquet file
        index: Whether to include DataFrame index in output
        fallback_to_ndjson: If True, fall back to NDJSON if Parquet save fails
        **kwargs: Additional arguments passed to pandas.DataFrame.to_parquet()
    """
    _ensure_parent_dir(path)
    
    try:
        df.to_parquet(path, index=index, **kwargs)
        logger.debug(f"Saved DataFrame to Parquet: {path}")
        return
    except Exception as e:
        if not fallback_to_ndjson:
            logger.error(f"Failed to save Parquet and fallback disabled: {e}")
            raise
        
        # Fallback to NDJSON in the same directory with .ndjson suffix
        ndjson_path = path.with_suffix(".ndjson")
        logger.warning(
            f"Parquet save failed, falling back to NDJSON: {e}",
            path=str(ndjson_path),
        )
        
        with ndjson_path.open("w", encoding="utf-8") as fh:
            for _, row in df.iterrows():
                record = {k: _to_jsonable(v) for k, v in row.items()}
                fh.write(json.dumps(record) + "\n")
        
        logger.info(f"Saved DataFrame to NDJSON fallback: {ndjson_path}")


def write_json_atomic(
    target: Path,
    data: dict[str, Any] | list[Any],
    indent: int = 2,
    sort_keys: bool = False,
    ensure_ascii: bool = False,
    default: Any = str,
) -> None:
    """Write JSON atomically to target path using a temp file + os.replace.
    
    This ensures that the target file is either completely written or not modified,
    preventing partial writes in case of interruption.
    
    Args:
        target: Target path for JSON file
        data: Data to write (dict or list)
        indent: JSON indentation level
        sort_keys: Whether to sort dictionary keys
        ensure_ascii: Whether to escape non-ASCII characters
        default: Function to handle non-serializable objects
    """
    _ensure_parent_dir(target)
    
    # Create temp file in same directory for atomicity
    fd, tmp_path = tempfile.mkstemp(
        prefix=target.stem + "_", suffix=".json.tmp", dir=str(target.parent)
    )
    
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=indent, sort_keys=sort_keys, ensure_ascii=ensure_ascii, default=default)
            fh.flush()
            os.fsync(fh.fileno())
        
        # Atomic replace
        os.replace(tmp_path, str(target))
        logger.debug(f"Atomically wrote JSON: {target}")
    except Exception as e:
        # Clean up temp file on error
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass
        logger.error(f"Failed to write JSON atomically: {e}")
        raise


def write_json(
    path: Path,
    payload: dict[str, Any] | list[Any],
    indent: int = 2,
    ensure_ascii: bool = False,
) -> None:
    """Write JSON to file (non-atomic, simple write).
    
    For atomic writes, use write_json_atomic() instead.
    
    Args:
        path: Path to write JSON file
        payload: Data to write (dict or list)
        indent: JSON indentation level
        ensure_ascii: Whether to escape non-ASCII characters
    """
    _ensure_parent_dir(path)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=indent, ensure_ascii=ensure_ascii)


def write_ndjson(path: Path, records: list[dict[str, Any]]) -> None:
    """Write records as newline-delimited JSON (NDJSON).
    
    Each record is written as a single JSON object on its own line.
    
    Args:
        path: Path to write NDJSON file
        records: List of dictionaries to write
    """
    _ensure_parent_dir(path)
    with path.open("w", encoding="utf-8") as fh:
        for record in records:
            # Convert to JSON-serializable format
            jsonable_record = {k: _to_jsonable(v) for k, v in record.items()}
            fh.write(json.dumps(jsonable_record) + "\n")
    
    logger.debug(f"Wrote {len(records)} records to NDJSON: {path}")


def read_parquet_or_ndjson(parquet_path: Path, json_path: Path | None = None) -> pd.DataFrame:
    """Read data from Parquet file, falling back to NDJSON if Parquet doesn't exist.
    
    Args:
        parquet_path: Path to Parquet file
        json_path: Optional path to NDJSON fallback file. If None, uses parquet_path with .ndjson suffix.
        
    Returns:
        DataFrame with loaded data, or empty DataFrame if neither file exists
        
    Raises:
        FileNotFoundError: If neither Parquet nor NDJSON file exists
    """
    if json_path is None:
        json_path = parquet_path.with_suffix(".ndjson")
    
    # Try Parquet first
    if parquet_path.exists():
        try:
            df = pd.read_parquet(parquet_path)
            logger.debug(f"Read DataFrame from Parquet: {parquet_path}")
            return df
        except Exception as e:
            logger.warning(f"Failed to read Parquet, trying NDJSON fallback: {e}")
    
    # Fallback to NDJSON
    if json_path.exists():
        records = []
        with json_path.open("r", encoding="utf-8") as fh:
            for line_num, line in enumerate(fh, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError as e:
                    logger.warning(f"Skipping invalid JSON at line {line_num} in {json_path}: {e}")
                    continue
        
        if records:
            df = pd.DataFrame(records)
            logger.debug(f"Read {len(records)} records from NDJSON: {json_path}")
            return df
    
    # Neither file exists
    raise FileNotFoundError(
        f"Neither Parquet ({parquet_path}) nor NDJSON ({json_path}) file exists"
    )

