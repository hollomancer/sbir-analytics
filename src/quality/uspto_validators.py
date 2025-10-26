# sbir-etl/src/quality/uspto_validators.py
"""
USPTO data quality validators.

This module provides basic validators for USPTO extract files. The
primary implemented validator is:

- validate_rf_id_uniqueness: Check rf_id uniqueness within a file or a
  stream of rows. Returns a summary dict with counts and a small sample
  of duplicate rf_id values.

Notes:
- The implementation is intentionally conservative and uses streaming
  reads where possible to avoid loading entire large files into memory.
- This is a validator skeleton: additional validators (referential
  integrity, completeness, date range checks, etc.) can be added in the
  same style.
"""

from __future__ import annotations

import csv
import logging
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Generator, Iterable, List, Optional, Tuple, Union

LOG = logging.getLogger(__name__)

# Optional heavy deps: attempted imports will be handled at runtime
try:
    import pandas as pd  # type: ignore
except Exception:
    pd = None  # type: ignore

try:
    import pyreadstat  # type: ignore
except Exception:
    pyreadstat = None  # type: ignore

try:
    import pyarrow.parquet as pq  # type: ignore
except Exception:
    pq = None  # type: ignore


@dataclass
class ValidatorResult:
    """
    Structured result returned by validators.
    """

    success: bool
    summary: Dict[str, Any]
    details: Dict[str, Any]


def _iter_rows_from_csv(
    path: Path, chunk_size: int = 10000
) -> Generator[Dict[str, Any], None, None]:
    """
    Stream rows from a CSV using the built-in csv module for minimal dependency.
    Yields dictionaries (header->value). This is robust and memory-light.
    """
    with path.open("r", newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            yield row


def _iter_rows_from_parquet(
    path: Path, chunk_size: int = 10000
) -> Generator[Dict[str, Any], None, None]:
    """
    Stream parquet rows using pyarrow if available. Falls back to pandas if pyarrow
    not present (and pandas is available) — note this may load the whole table into memory.
    """
    if pq is not None:
        pf = pq.ParquetFile(str(path))
        for rg in range(pf.num_row_groups):
            table = pf.read_row_group(rg)
            # convert to pandas then yield in chunks
            df = table.to_pandas()
            for i in range(0, len(df), chunk_size):
                batch = df.iloc[i : i + chunk_size]
                for rec in batch.to_dict(orient="records"):
                    yield rec
        return
    if pd is not None:
        df = pd.read_parquet(str(path))
        for i in range(0, len(df), chunk_size):
            batch = df.iloc[i : i + chunk_size]
            for rec in batch.to_dict(orient="records"):
                yield rec
        return
    raise RuntimeError("No parquet reader available (pyarrow or pandas required)")


def _iter_rows_from_dta(
    path: Path, chunk_size: int = 10000
) -> Generator[Dict[str, Any], None, None]:
    """
    Stream .dta (Stata) rows. Prefer pyreadstat's row_limit capability if available,
    otherwise fall back to pandas (may be memory heavy).
    """
    # Use pyreadstat chunked reads if available
    if pyreadstat is not None:
        offset = 0
        while True:
            try:
                df, meta = pyreadstat.read_dta(str(path), row_limit=chunk_size, row_offset=offset)
            except Exception as exc:
                LOG.debug("pyreadstat read_dta chunk failed at offset %s: %s", offset, exc)
                raise
            if df is None or df.shape[0] == 0:
                break
            for rec in df.to_dict(orient="records"):
                yield rec
            offset += df.shape[0]
        return
    # pandas fallback
    if pd is not None:
        # try iterator-based pandas read_stata if supported
        try:
            reader = pd.read_stata(str(path), iterator=True, convert_categoricals=False)  # type: ignore
            while True:
                try:
                    chunk = reader.get_chunk(chunk_size)  # type: ignore
                except StopIteration:
                    break
                for rec in chunk.to_dict(orient="records"):
                    yield rec
            return
        except Exception:
            # last resort: read entirely
            df = pd.read_stata(str(path), convert_categoricals=False)  # type: ignore
            for i in range(0, len(df), chunk_size):
                chunk = df.iloc[i : i + chunk_size]
                for rec in chunk.to_dict(orient="records"):
                    yield rec
            return
    raise RuntimeError("No Stata reader available (pyreadstat or pandas required)")


def iter_rows_from_path(
    path: Union[str, Path], chunk_size: int = 10000
) -> Generator[Dict[str, Any], None, None]:
    """
    High-level wrapper that yields rows from a file path. Chooses a reader based
    on file extension.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"File not found: {p}")
    ext = p.suffix.lower()
    if ext == ".csv":
        yield from _iter_rows_from_csv(p, chunk_size=chunk_size)
    elif ext == ".parquet":
        yield from _iter_rows_from_parquet(p, chunk_size=chunk_size)
    elif ext == ".dta":
        yield from _iter_rows_from_dta(p, chunk_size=chunk_size)
    else:
        raise ValueError(f"Unsupported extension for USPTO validator: {ext}")


def validate_rf_id_uniqueness_from_iterator(
    rows: Iterable[Dict[str, Any]],
    rf_id_field_names: Optional[Iterable[str]] = None,
    sample_limit: int = 20,
) -> ValidatorResult:
    """
    Validate rf_id uniqueness given an iterator of rows (dictionaries).

    Parameters
    ----------
    rows: Iterable[Dict[str, Any]]
        Iterable producing row dicts (key -> value).
    rf_id_field_names: Optional iterable of possible column names to consider
        for the rf_id (defaults to common names).
    sample_limit: maximum number of duplicate samples to include in result.

    Returns
    -------
    ValidatorResult with summary and details:
      - summary: contains total_rows, missing_rf_id_count, unique_rf_ids, duplicate_count
      - details: contains duplicate_samples (list), duplicate_examples (dict rf_id -> count)
    """
    field_choices = (
        list(rf_id_field_names)
        if rf_id_field_names
        else [
            "rf_id",
            "record_id",
            "id",
        ]
    )

    seen: Dict[str, int] = {}  # rf_id -> count
    missing_rf_id = 0
    total = 0

    # store a few examples of duplicate rows keyed by rf_id
    duplicate_examples: Dict[str, int] = defaultdict(int)

    for row in rows:
        total += 1
        # find first available rf_id field
        rf_id_val = None
        for f in field_choices:
            if f in row and row.get(f) not in (None, ""):
                rf_id_val = row.get(f)
                break
        if rf_id_val is None or str(rf_id_val).strip() == "":
            missing_rf_id += 1
            continue
        key = str(rf_id_val).strip()
        count = seen.get(key, 0) + 1
        seen[key] = count
        if count > 1:
            duplicate_examples[key] += 1
            # keep duplicate_examples bounded to sample_limit keys
            if len(duplicate_examples) > sample_limit:
                # drop arbitrary oldest key (not deterministic) to bound memory
                duplicate_examples.pop(next(iter(duplicate_examples)))

    unique_count = sum(1 for c in seen.values() if c == 1)
    duplicate_count = sum(1 for c in seen.values() if c > 1)
    total_rf_ids = len(seen)

    duplicate_samples = list(duplicate_examples.items())[:sample_limit]

    summary = {
        "total_rows": total,
        "total_rf_ids_found": total_rf_ids,
        "unique_rf_id_values": unique_count,
        "duplicate_rf_id_values": duplicate_count,
        "missing_rf_id_count": missing_rf_id,
    }

    details = {
        "duplicate_samples": duplicate_samples,
        "duplicate_examples_counts": dict(list(duplicate_examples.items())[:sample_limit]),
    }

    success = duplicate_count == 0

    return ValidatorResult(success=success, summary=summary, details=details)


def validate_rf_id_uniqueness(
    file_path: Union[str, Path],
    chunk_size: int = 10000,
    rf_id_field_names: Optional[Iterable[str]] = None,
    sample_limit: int = 20,
) -> ValidatorResult:
    """
    Validate rf_id uniqueness for a file on disk.

    Parameters
    ----------
    file_path: path to file (csv, parquet, dta)
    chunk_size: chunk size for streaming readers
    rf_id_field_names: optional alternative field names to look at
    sample_limit: number of duplicate samples to return in details

    Returns
    -------
    ValidatorResult
    """
    p = Path(file_path)
    if not p.exists():
        raise FileNotFoundError(f"Input file not found: {p}")

    try:
        row_iter = iter_rows_from_path(p, chunk_size=chunk_size)
        result = validate_rf_id_uniqueness_from_iterator(
            row_iter, rf_id_field_names=rf_id_field_names, sample_limit=sample_limit
        )
        return result
    except Exception as exc:
        LOG.exception("validate_rf_id_uniqueness failed for %s: %s", p, exc)
        return ValidatorResult(
            success=False,
            summary={"error": str(exc)},
            details={},
        )


# Small convenience CLI-like entrypoint for interactive runs
def main_validate_rf_id_uniqueness(file_path: Union[str, Path]) -> Tuple[bool, Dict[str, Any]]:
    """
    Run rf_id uniqueness validator and print a concise summary.
    Returns (success, summary_dict)
    """
    res = validate_rf_id_uniqueness(file_path)
    LOG.info("RF ID uniqueness validation result for %s: success=%s", file_path, res.success)
    LOG.info("Summary: %s", res.summary)
    if not res.success:
        LOG.info("Details (duplicates sample): %s", res.details.get("duplicate_samples"))
    return res.success, res.summary


# Expose module API
__all__ = [
    "ValidatorResult",
    "validate_rf_id_uniqueness",
    "validate_rf_id_uniqueness_from_iterator",
    "iter_rows_from_path",
    "main_validate_rf_id_uniqueness",
]
