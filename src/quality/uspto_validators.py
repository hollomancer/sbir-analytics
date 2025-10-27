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


def validate_referential_integrity(
    child_file_path: Union[str, Path],
    parent_file_path: Union[str, Path],
    child_fk_field: str = "rf_id",
    parent_pk_field: str = "rf_id",
    chunk_size: int = 10000,
    sample_limit: int = 20,
) -> ValidatorResult:
    """
    Validate referential integrity between a child table and parent table.

    Checks that all rf_id values in the child table exist in the parent table.

    Parameters
    ----------
    child_file_path: path to child table file
    parent_file_path: path to parent table file (should contain primary keys)
    child_fk_field: foreign key field name in child table
    parent_pk_field: primary key field name in parent table
    chunk_size: chunk size for streaming
    sample_limit: number of orphaned records to sample

    Returns
    -------
    ValidatorResult with:
      - success: True if all child FKs reference valid parent PKs
      - summary: total_child_rows, total_parent_keys, orphaned_count, orphaned_sample
    """
    try:
        # First pass: collect all parent keys
        LOG.info("Loading parent keys from %s", parent_file_path)
        parent_keys = set()
        for row in iter_rows_from_path(parent_file_path, chunk_size=chunk_size):
            pk_val = row.get(parent_pk_field)
            if pk_val is not None and str(pk_val).strip():
                parent_keys.add(str(pk_val).strip())

        # Second pass: check child FKs
        LOG.info("Validating child foreign keys from %s", child_file_path)
        orphaned_records = []
        total_child_rows = 0
        orphaned_count = 0
        missing_fk_count = 0

        for row in iter_rows_from_path(child_file_path, chunk_size=chunk_size):
            total_child_rows += 1
            fk_val = row.get(child_fk_field)

            if fk_val is None or str(fk_val).strip() == "":
                missing_fk_count += 1
                continue

            fk_key = str(fk_val).strip()
            if fk_key not in parent_keys:
                orphaned_count += 1
                if len(orphaned_records) < sample_limit:
                    orphaned_records.append({child_fk_field: fk_key, "row": row})

        success = orphaned_count == 0

        summary = {
            "total_child_rows": total_child_rows,
            "total_parent_keys": len(parent_keys),
            "orphaned_records": orphaned_count,
            "missing_fk_count": missing_fk_count,
            "referential_integrity_rate": (
                1.0 - (orphaned_count / max(total_child_rows - missing_fk_count, 1))
                if total_child_rows > missing_fk_count
                else 0.0
            ),
        }

        details = {
            "orphaned_sample": orphaned_records[:sample_limit],
        }

        return ValidatorResult(success=success, summary=summary, details=details)

    except Exception as exc:
        LOG.exception("validate_referential_integrity failed: %s", exc)
        return ValidatorResult(
            success=False,
            summary={"error": str(exc)},
            details={},
        )


def validate_field_completeness(
    file_path: Union[str, Path],
    required_fields: List[str],
    chunk_size: int = 10000,
    completeness_threshold: float = 0.95,
) -> ValidatorResult:
    """
    Validate that required fields meet a completeness threshold.

    Parameters
    ----------
    file_path: path to file
    required_fields: list of field names that should be present and non-null
    chunk_size: chunk size for streaming
    completeness_threshold: minimum acceptable completeness rate (0.0-1.0)

    Returns
    -------
    ValidatorResult with field-level completeness metrics
    """
    try:
        field_stats = {field: {"present": 0, "missing": 0} for field in required_fields}
        total_rows = 0

        for row in iter_rows_from_path(file_path, chunk_size=chunk_size):
            total_rows += 1
            for field in required_fields:
                val = row.get(field)
                if val is not None and str(val).strip():
                    field_stats[field]["present"] += 1
                else:
                    field_stats[field]["missing"] += 1

        # Calculate completeness rates
        completeness_rates = {}
        failed_fields = []

        for field, stats in field_stats.items():
            rate = stats["present"] / max(total_rows, 1)
            completeness_rates[field] = rate
            if rate < completeness_threshold:
                failed_fields.append(field)

        overall_completeness = sum(stats["present"] for stats in field_stats.values()) / max(
            total_rows * len(required_fields), 1
        )

        success = len(failed_fields) == 0

        summary = {
            "total_rows": total_rows,
            "required_fields": required_fields,
            "overall_completeness": overall_completeness,
            "completeness_threshold": completeness_threshold,
            "failed_fields_count": len(failed_fields),
        }

        details = {
            "field_completeness_rates": completeness_rates,
            "field_stats": field_stats,
            "failed_fields": failed_fields,
        }

        return ValidatorResult(success=success, summary=summary, details=details)

    except Exception as exc:
        LOG.exception("validate_field_completeness failed: %s", exc)
        return ValidatorResult(
            success=False,
            summary={"error": str(exc)},
            details={},
        )


def validate_date_fields(
    file_path: Union[str, Path],
    date_fields: List[str],
    min_year: int = 1790,
    max_year: int = 2100,
    chunk_size: int = 10000,
    sample_limit: int = 20,
) -> ValidatorResult:
    """
    Validate date fields for format and reasonable ranges.

    Parameters
    ----------
    file_path: path to file
    date_fields: list of date field names to validate
    min_year: minimum acceptable year
    max_year: maximum acceptable year
    chunk_size: chunk size for streaming
    sample_limit: number of invalid date samples to collect

    Returns
    -------
    ValidatorResult with date validation metrics
    """
    from datetime import datetime

    try:
        field_stats = {
            field: {
                "valid": 0,
                "invalid_format": 0,
                "out_of_range": 0,
                "missing": 0,
                "invalid_samples": [],
            }
            for field in date_fields
        }
        total_rows = 0

        def parse_date(val: Any) -> Optional[datetime]:
            """Try to parse date from various formats."""
            if val is None:
                return None

            val_str = str(val).strip()
            if not val_str or val_str.lower() in ("nan", "nat", "none", "null"):
                return None

            # Try common date formats
            for fmt in [
                "%Y-%m-%d",
                "%Y/%m/%d",
                "%m/%d/%Y",
                "%m-%d-%Y",
                "%Y-%m-%d %H:%M:%S",
                "%Y/%m/%d %H:%M:%S",
            ]:
                try:
                    return datetime.strptime(val_str, fmt)
                except ValueError:
                    continue

            # Try pandas-style timestamp parsing
            try:
                if pd is not None:
                    return pd.to_datetime(val_str)
            except Exception:
                pass

            return None

        for row in iter_rows_from_path(file_path, chunk_size=chunk_size):
            total_rows += 1
            for field in date_fields:
                val = row.get(field)

                if val is None or str(val).strip() == "":
                    field_stats[field]["missing"] += 1
                    continue

                parsed_date = parse_date(val)

                if parsed_date is None:
                    field_stats[field]["invalid_format"] += 1
                    if len(field_stats[field]["invalid_samples"]) < sample_limit:
                        field_stats[field]["invalid_samples"].append(
                            {
                                "field": field,
                                "value": str(val),
                                "reason": "invalid_format",
                            }
                        )
                elif parsed_date.year < min_year or parsed_date.year > max_year:
                    field_stats[field]["out_of_range"] += 1
                    if len(field_stats[field]["invalid_samples"]) < sample_limit:
                        field_stats[field]["invalid_samples"].append(
                            {
                                "field": field,
                                "value": str(val),
                                "year": parsed_date.year,
                                "reason": "out_of_range",
                            }
                        )
                else:
                    field_stats[field]["valid"] += 1

        # Calculate validation rates
        validation_rates = {}
        failed_fields = []

        for field, stats in field_stats.items():
            total_non_missing = total_rows - stats["missing"]
            if total_non_missing > 0:
                rate = stats["valid"] / total_non_missing
                validation_rates[field] = rate
                if rate < 0.95:  # 95% validity threshold
                    failed_fields.append(field)
            else:
                validation_rates[field] = 0.0

        total_invalid = sum(
            stats["invalid_format"] + stats["out_of_range"] for stats in field_stats.values()
        )

        success = total_invalid == 0

        summary = {
            "total_rows": total_rows,
            "date_fields": date_fields,
            "total_invalid_dates": total_invalid,
            "failed_fields_count": len(failed_fields),
            "min_year": min_year,
            "max_year": max_year,
        }

        details = {
            "field_validation_rates": validation_rates,
            "field_stats": {
                field: {k: v for k, v in stats.items() if k != "invalid_samples"}
                for field, stats in field_stats.items()
            },
            "invalid_samples": [
                sample
                for stats in field_stats.values()
                for sample in stats["invalid_samples"][:sample_limit]
            ],
            "failed_fields": failed_fields,
        }

        return ValidatorResult(success=success, summary=summary, details=details)

    except Exception as exc:
        LOG.exception("validate_date_fields failed: %s", exc)
        return ValidatorResult(
            success=False,
            summary={"error": str(exc)},
            details={},
        )


def validate_duplicate_records(
    file_path: Union[str, Path],
    key_fields: List[str],
    chunk_size: int = 10000,
    sample_limit: int = 20,
) -> ValidatorResult:
    """
    Validate that records are unique based on a composite key.

    Parameters
    ----------
    file_path: path to file
    key_fields: list of field names that form the composite key
    chunk_size: chunk size for streaming
    sample_limit: number of duplicate samples to collect

    Returns
    -------
    ValidatorResult with duplicate detection metrics
    """
    try:
        seen_keys: Dict[str, int] = {}
        duplicate_samples = []
        total_rows = 0
        missing_key_count = 0

        for row in iter_rows_from_path(file_path, chunk_size=chunk_size):
            total_rows += 1

            # Build composite key
            key_parts = []
            has_missing = False

            for field in key_fields:
                val = row.get(field)
                if val is None or str(val).strip() == "":
                    has_missing = True
                    break
                key_parts.append(str(val).strip())

            if has_missing:
                missing_key_count += 1
                continue

            composite_key = "||".join(key_parts)
            count = seen_keys.get(composite_key, 0) + 1
            seen_keys[composite_key] = count

            if count > 1 and len(duplicate_samples) < sample_limit:
                duplicate_samples.append(
                    {
                        "key": composite_key,
                        "count": count,
                        "row_sample": row,
                    }
                )

        duplicate_count = sum(1 for c in seen_keys.values() if c > 1)
        unique_count = sum(1 for c in seen_keys.values() if c == 1)

        success = duplicate_count == 0

        summary = {
            "total_rows": total_rows,
            "key_fields": key_fields,
            "unique_records": unique_count,
            "duplicate_records": duplicate_count,
            "missing_key_count": missing_key_count,
            "uniqueness_rate": unique_count / max(len(seen_keys), 1),
        }

        details = {
            "duplicate_samples": duplicate_samples,
        }

        return ValidatorResult(success=success, summary=summary, details=details)

    except Exception as exc:
        LOG.exception("validate_duplicate_records failed: %s", exc)
        return ValidatorResult(
            success=False,
            summary={"error": str(exc)},
            details={},
        )


# Expose module API
__all__ = [
    "ValidatorResult",
    "validate_rf_id_uniqueness",
    "validate_rf_id_uniqueness_from_iterator",
    "validate_referential_integrity",
    "validate_field_completeness",
    "validate_date_fields",
    "validate_duplicate_records",
    "iter_rows_from_path",
    "main_validate_rf_id_uniqueness",
]
