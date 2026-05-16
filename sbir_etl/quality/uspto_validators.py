"""USPTO data quality validators.

Streaming-friendly validators plus a coordinator (`USPTODataQualityValidator`)
that runs the required checks for the USPTO patent assignment pipeline:

- `validate_rf_id_uniqueness`: rf_id uniqueness per file/iterator
- `validate_referential_integrity`: ensure child rf_id values exist in parent table
- `validate_field_completeness`: completeness threshold enforcement
- `validate_date_fields`: date parsing and range validation
- `validate_duplicate_records`: composite key duplicate detection

Implementation favors chunked iteration to avoid loading multi-GB USPTO files
into memory.
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from collections.abc import Generator, Iterable
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

from sbir_etl.utils.date_utils import parse_date as _parse_date_util
from sbir_etl.utils.path_utils import ensure_dir, normalize_path_list as _ensure_path_list


# Optional heavy deps loaded at import time; readers fall back gracefully.
try:
    import pandas as pd
except Exception:
    pd = None  # type: ignore[assignment, unused-ignore]

try:
    import pyreadstat
except Exception:
    pyreadstat = None  # type: ignore[assignment, unused-ignore]

try:
    import pyarrow.parquet as pq
except Exception:
    pq = None  # type: ignore[assignment, unused-ignore]


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass
class ValidatorResult:
    """Structured result returned by validators."""

    success: bool
    summary: dict[str, Any]
    details: dict[str, Any]


def _failure(exc: BaseException) -> ValidatorResult:
    return ValidatorResult(success=False, summary={"error": str(exc)}, details={})


# ---------------------------------------------------------------------------
# Row iterators
# ---------------------------------------------------------------------------


def _iter_rows_from_csv(path: Path) -> Generator[dict[str, Any], None, None]:
    """Stream rows from CSV using the stdlib csv module (memory-light)."""
    with path.open("r", newline="", encoding="utf-8") as fh:
        yield from csv.DictReader(fh)


def _iter_rows_from_parquet(
    path: Path, chunk_size: int = 10000
) -> Generator[dict[str, Any], None, None]:
    """Stream parquet via pyarrow row groups; fall back to pandas (full load) if absent."""
    if pq is not None:
        pf = pq.ParquetFile(str(path))
        for rg in range(pf.num_row_groups):
            df = pf.read_row_group(rg).to_pandas()
            for i in range(0, len(df), chunk_size):
                yield from df.iloc[i : i + chunk_size].to_dict(orient="records")
        return
    if pd is not None:
        df = pd.read_parquet(str(path))
        for i in range(0, len(df), chunk_size):
            yield from df.iloc[i : i + chunk_size].to_dict(orient="records")  # type: ignore[misc]
        return
    raise RuntimeError("No parquet reader available (pyarrow or pandas required)")


def _iter_rows_from_dta(
    path: Path, chunk_size: int = 10000
) -> Generator[dict[str, Any], None, None]:
    """Stream Stata .dta files. Prefers pyreadstat; falls back to pandas iterator."""
    if pyreadstat is not None:
        offset = 0
        while True:
            df, _ = pyreadstat.read_dta(str(path), row_limit=chunk_size, row_offset=offset)
            if df is None or df.shape[0] == 0:
                return
            yield from df.to_dict(orient="records")
            offset += df.shape[0]
    if pd is not None:
        try:
            reader = pd.read_stata(
                str(path), iterator=True, convert_categoricals=False, chunksize=chunk_size
            )
            for chunk in reader:
                yield from chunk.to_dict(orient="records")  # type: ignore[misc]
            return
        except Exception:
            df = pd.read_stata(str(path), convert_categoricals=False)
            for i in range(0, len(df), chunk_size):
                yield from df.iloc[i : i + chunk_size].to_dict(orient="records")  # type: ignore[misc]
            return
    raise RuntimeError("No Stata reader available (pyreadstat or pandas required)")


def iter_rows_from_path(
    path: str | Path, chunk_size: int = 10000
) -> Generator[dict[str, Any], None, None]:
    """Yield rows from a USPTO data file; reader is chosen by extension."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"File not found: {p}")
    ext = p.suffix.lower()
    if ext == ".csv":
        yield from _iter_rows_from_csv(p)
    elif ext == ".parquet":
        yield from _iter_rows_from_parquet(p, chunk_size=chunk_size)
    elif ext == ".dta":
        yield from _iter_rows_from_dta(p, chunk_size=chunk_size)
    else:
        raise ValueError(f"Unsupported extension for USPTO validator: {ext}")


def _nonempty(val: Any) -> bool:
    return val is not None and str(val).strip() != ""


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------


def validate_rf_id_uniqueness_from_iterator(
    rows: Iterable[dict[str, Any]],
    rf_id_field_names: Iterable[str] | None = None,
    sample_limit: int = 20,
) -> ValidatorResult:
    """Validate rf_id uniqueness across the supplied row iterator."""
    field_choices = list(rf_id_field_names) if rf_id_field_names else ["rf_id", "record_id", "id"]

    seen: dict[str, int] = {}
    duplicate_examples: dict[str, int] = defaultdict(int)
    missing = 0
    total = 0

    for row in rows:
        total += 1
        rf_id = next((row.get(f) for f in field_choices if _nonempty(row.get(f))), None)
        if not _nonempty(rf_id):
            missing += 1
            continue
        key = str(rf_id).strip()
        seen[key] = seen.get(key, 0) + 1
        if seen[key] > 1:
            duplicate_examples[key] += 1
            if len(duplicate_examples) > sample_limit:
                duplicate_examples.pop(next(iter(duplicate_examples)))

    unique_count = sum(1 for c in seen.values() if c == 1)
    duplicate_count = sum(1 for c in seen.values() if c > 1)
    duplicate_samples = list(duplicate_examples.items())[:sample_limit]

    return ValidatorResult(
        success=duplicate_count == 0,
        summary={
            "total_rows": total,
            "total_rf_ids_found": len(seen),
            "unique_rf_id_values": unique_count,
            "duplicate_rf_id_values": duplicate_count,
            "missing_rf_id_count": missing,
        },
        details={
            "duplicate_samples": duplicate_samples,
            "duplicate_examples_counts": dict(duplicate_samples),
        },
    )


def validate_rf_id_uniqueness(
    file_path: str | Path,
    chunk_size: int = 10000,
    rf_id_field_names: Iterable[str] | None = None,
    sample_limit: int = 20,
) -> ValidatorResult:
    """Validate rf_id uniqueness for a file on disk."""
    p = Path(file_path)
    if not p.exists():
        raise FileNotFoundError(f"Input file not found: {p}")
    try:
        return validate_rf_id_uniqueness_from_iterator(
            iter_rows_from_path(p, chunk_size=chunk_size),
            rf_id_field_names=rf_id_field_names,
            sample_limit=sample_limit,
        )
    except Exception as exc:
        logger.exception("validate_rf_id_uniqueness failed for %s: %s", p, exc)
        return _failure(exc)


def main_validate_rf_id_uniqueness(file_path: str | Path) -> tuple[bool, dict[str, Any]]:
    """Run rf_id uniqueness validator and log a concise summary."""
    res = validate_rf_id_uniqueness(file_path)
    logger.info("RF ID uniqueness validation result for %s: success=%s", file_path, res.success)
    logger.info("Summary: %s", res.summary)
    if not res.success:
        logger.info("Details (duplicates sample): %s", res.details.get("duplicate_samples"))
    return res.success, res.summary


def validate_referential_integrity(
    child_file_path: str | Path,
    parent_file_path: str | Path | Iterable[str | Path],
    child_fk_field: str = "rf_id",
    parent_pk_field: str = "rf_id",
    chunk_size: int = 10000,
    sample_limit: int = 20,
) -> ValidatorResult:
    """Verify all child FK values reference an existing parent PK."""
    try:
        parent_paths = _ensure_path_list(parent_file_path)
        logger.info("Loading parent keys from %s", ", ".join(str(p) for p in parent_paths))
        parent_keys: set[str] = set()
        for parent_path in parent_paths:
            for row in iter_rows_from_path(parent_path, chunk_size=chunk_size):
                pk = row.get(parent_pk_field)
                if _nonempty(pk):
                    parent_keys.add(str(pk).strip())

        logger.info("Validating child foreign keys from %s", child_file_path)
        orphaned: list[dict[str, Any]] = []
        orphaned_count = 0
        missing_fk = 0
        total_child = 0
        for row in iter_rows_from_path(child_file_path, chunk_size=chunk_size):
            total_child += 1
            fk = row.get(child_fk_field)
            if not _nonempty(fk):
                missing_fk += 1
                continue
            fk_key = str(fk).strip()
            if fk_key not in parent_keys:
                orphaned_count += 1
                if len(orphaned) < sample_limit:
                    orphaned.append({child_fk_field: fk_key, "row": row})

        non_missing = total_child - missing_fk
        rate = 1.0 - (orphaned_count / non_missing) if non_missing > 0 else 0.0
        return ValidatorResult(
            success=orphaned_count == 0,
            summary={
                "total_child_rows": total_child,
                "total_parent_keys": len(parent_keys),
                "parent_files_count": len(parent_paths),
                "orphaned_records": orphaned_count,
                "missing_fk_count": missing_fk,
                "referential_integrity_rate": rate,
            },
            details={"orphaned_sample": orphaned[:sample_limit]},
        )
    except Exception as exc:
        logger.exception("validate_referential_integrity failed: %s", exc)
        return _failure(exc)


def validate_field_completeness(
    file_path: str | Path,
    required_fields: list[str],
    chunk_size: int = 10000,
    completeness_threshold: float = 0.95,
) -> ValidatorResult:
    """Verify each required field meets the per-field completeness threshold."""
    try:
        present: dict[str, int] = dict.fromkeys(required_fields, 0)
        missing: dict[str, int] = dict.fromkeys(required_fields, 0)
        total = 0
        for row in iter_rows_from_path(file_path, chunk_size=chunk_size):
            total += 1
            for f in required_fields:
                if _nonempty(row.get(f)):
                    present[f] += 1
                else:
                    missing[f] += 1

        rates = {f: present[f] / max(total, 1) for f in required_fields}
        failed = [f for f, r in rates.items() if r < completeness_threshold]
        overall = sum(present.values()) / max(total * len(required_fields), 1)

        return ValidatorResult(
            success=not failed,
            summary={
                "total_rows": total,
                "required_fields": required_fields,
                "overall_completeness": overall,
                "completeness_threshold": completeness_threshold,
                "failed_fields_count": len(failed),
            },
            details={
                "field_completeness_rates": rates,
                "field_stats": {
                    f: {"present": present[f], "missing": missing[f]} for f in required_fields
                },
                "failed_fields": failed,
            },
        )
    except Exception as exc:
        logger.exception("validate_field_completeness failed: %s", exc)
        return _failure(exc)


def validate_date_fields(
    file_path: str | Path,
    date_fields: list[str],
    min_year: int = 1790,
    max_year: int = 2100,
    chunk_size: int = 10000,
    sample_limit: int = 20,
) -> ValidatorResult:
    """Validate date fields parse correctly and fall inside [min_year, max_year]."""
    try:
        # Per-field counters and bounded samples.
        counts = {
            f: {"valid": 0, "invalid_format": 0, "out_of_range": 0, "missing": 0}
            for f in date_fields
        }
        samples: dict[str, list[dict[str, Any]]] = {f: [] for f in date_fields}
        total = 0

        def _parse(value: Any) -> datetime | None:
            try:
                result = _parse_date_util(value, return_datetime=True)
            except (ValueError, TypeError):
                return None
            return result if isinstance(result, datetime) else None

        for row in iter_rows_from_path(file_path, chunk_size=chunk_size):
            total += 1
            for f in date_fields:
                val = row.get(f)
                if not _nonempty(val):
                    counts[f]["missing"] += 1
                    continue
                parsed = _parse(val)
                if parsed is None:
                    counts[f]["invalid_format"] += 1
                    if len(samples[f]) < sample_limit:
                        samples[f].append(
                            {"field": f, "value": str(val), "reason": "invalid_format"}
                        )
                elif not (min_year <= parsed.year <= max_year):
                    counts[f]["out_of_range"] += 1
                    if len(samples[f]) < sample_limit:
                        samples[f].append(
                            {
                                "field": f,
                                "value": str(val),
                                "year": parsed.year,
                                "reason": "out_of_range",
                            }
                        )
                else:
                    counts[f]["valid"] += 1

        rates: dict[str, float] = {}
        failed: list[str] = []
        for f in date_fields:
            non_missing = total - counts[f]["missing"]
            if non_missing > 0:
                rates[f] = counts[f]["valid"] / non_missing
                if rates[f] < 0.95:
                    failed.append(f)
            else:
                rates[f] = 0.0
        total_invalid = sum(c["invalid_format"] + c["out_of_range"] for c in counts.values())

        return ValidatorResult(
            success=total_invalid == 0,
            summary={
                "total_rows": total,
                "date_fields": date_fields,
                "total_invalid_dates": total_invalid,
                "failed_fields_count": len(failed),
                "min_year": min_year,
                "max_year": max_year,
            },
            details={
                "field_validation_rates": rates,
                "field_stats": counts,
                "invalid_samples": [s for slist in samples.values() for s in slist[:sample_limit]],
                "failed_fields": failed,
            },
        )
    except Exception as exc:
        logger.exception("validate_date_fields failed: %s", exc)
        return _failure(exc)


def validate_duplicate_records(
    file_path: str | Path,
    key_fields: list[str],
    chunk_size: int = 10000,
    sample_limit: int = 20,
) -> ValidatorResult:
    """Detect duplicates by composite key (any row missing any key field is skipped)."""
    try:
        seen: dict[str, int] = {}
        duplicate_samples: list[dict[str, Any]] = []
        total = 0
        missing_key = 0

        for row in iter_rows_from_path(file_path, chunk_size=chunk_size):
            total += 1
            parts: list[str] = []
            for f in key_fields:
                v = row.get(f)
                if not _nonempty(v):
                    parts = []
                    break
                parts.append(str(v).strip())
            if not parts:
                missing_key += 1
                continue
            composite = "||".join(parts)
            seen[composite] = seen.get(composite, 0) + 1
            if seen[composite] > 1 and len(duplicate_samples) < sample_limit:
                duplicate_samples.append(
                    {"key": composite, "count": seen[composite], "row_sample": row}
                )

        unique_count = sum(1 for c in seen.values() if c == 1)
        duplicate_count = sum(1 for c in seen.values() if c > 1)
        return ValidatorResult(
            success=duplicate_count == 0,
            summary={
                "total_rows": total,
                "key_fields": key_fields,
                "unique_records": unique_count,
                "duplicate_records": duplicate_count,
                "missing_key_count": missing_key,
                "uniqueness_rate": unique_count / max(len(seen), 1),
            },
            details={"duplicate_samples": duplicate_samples},
        )
    except Exception as exc:
        logger.exception("validate_duplicate_records failed: %s", exc)
        return _failure(exc)


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def _default_required_fields() -> dict[str, list[str]]:
    return {
        "assignments": ["rf_id", "record_dt", "cname"],
        "assignees": ["rf_id", "ee_name"],
        "assignors": ["rf_id", "or_name"],
        "documentids": ["rf_id", "grant_doc_num"],
    }


def _default_date_fields() -> dict[str, list[str]]:
    return {
        "assignments": ["record_dt", "last_update_dt"],
        "assignors": ["exec_dt", "ack_dt"],
        "documentids": ["appno_date", "grant_date", "pgpub_date"],
    }


def _default_duplicate_key_fields() -> dict[str, list[str]]:
    return {
        "assignments": ["rf_id"],
        "assignees": ["rf_id", "ee_name"],
        "assignors": ["rf_id", "or_name"],
        "documentids": ["rf_id", "grant_doc_num", "appno_doc_num"],
        "conveyances": ["rf_id", "convey_ty"],
    }


@dataclass
class USPTOValidationConfig:
    """Configuration for the ``USPTODataQualityValidator`` orchestrator."""

    chunk_size: int = 10000
    sample_limit: int = 20
    completeness_threshold: float = 0.95
    min_year: int = 1790
    max_year: int = 2100
    fail_output_dir: Path = Path("data/validated/fail")
    report_output_dir: Path = Path("reports/uspto-validation")
    required_fields: dict[str, list[str]] = field(default_factory=_default_required_fields)
    date_fields: dict[str, list[str]] = field(default_factory=_default_date_fields)
    duplicate_key_fields: dict[str, list[str]] = field(
        default_factory=_default_duplicate_key_fields
    )


def _result_to_dict(result: ValidatorResult) -> dict[str, Any]:
    return {
        "success": result.success,
        "summary": dict(result.summary),
        "details": deepcopy(result.details),
    }


class USPTODataQualityValidator:
    """Run the suite of USPTO data quality validators and aggregate results."""

    def __init__(self, config: USPTOValidationConfig | None = None) -> None:
        self.config = config or USPTOValidationConfig()
        ensure_dir(self.config.fail_output_dir)
        ensure_dir(self.config.report_output_dir)
        self._failure_samples: list[dict[str, Any]] = []

    def _write_failure_sample(self, label: str, sample: list[dict[str, Any]]) -> str | None:
        if not sample:
            return None
        safe_label = label.replace("/", "_").replace(" ", "_")
        timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
        path = self.config.fail_output_dir / f"{safe_label}_{timestamp}.json"
        try:
            with path.open("w", encoding="utf-8") as fh:
                json.dump(sample, fh, ensure_ascii=False, indent=2, default=str)
        except Exception as exc:  # pragma: no cover - IO guard
            logger.exception("Failed to write failure sample %s: %s", path, exc)
            return None
        self._failure_samples.append(
            {"label": label, "path": str(path), "sample_size": len(sample)}
        )
        return str(path)

    def _run_table_checks(
        self,
        table: str,
        files: list[str | Path],
        parent_files: list[str | Path] | None = None,
    ) -> dict[str, dict[str, Any]]:
        """Run the standard checks against `files` for `table`.

        For ``assignments`` (no `parent_files`), runs rf_id uniqueness.
        For child tables, runs referential_integrity against `parent_files` instead.
        Both then run field_completeness / duplicate_records / date_fields when the
        corresponding config lists are non-empty.
        """
        cfg = self.config
        results: dict[str, dict[str, Any]] = {}

        for file_path in files:
            file_str = str(file_path)
            stem = Path(file_str).stem
            checks: dict[str, dict[str, Any]] = {}

            # rf_id uniqueness (assignments only) or referential integrity (children).
            if parent_files is None:
                rf_result = validate_rf_id_uniqueness(
                    file_path,
                    chunk_size=cfg.chunk_size,
                    sample_limit=cfg.sample_limit,
                )
                checks["rf_id_uniqueness"] = _result_to_dict(rf_result)
            elif parent_files:
                ref_result = validate_referential_integrity(
                    file_path,
                    parent_files,
                    child_fk_field="rf_id",
                    parent_pk_field="rf_id",
                    chunk_size=cfg.chunk_size,
                    sample_limit=cfg.sample_limit,
                )
                ref_dict = _result_to_dict(ref_result)
                self._attach_failure_sample(
                    ref_dict,
                    label=f"{table}_orphans_{stem}",
                    rows=[
                        rec.get("row", {})
                        for rec in ref_result.details.get("orphaned_sample", [])
                        if isinstance(rec, dict)
                    ],
                )
                checks["referential_integrity"] = ref_dict

            # Field completeness.
            if required := cfg.required_fields.get(table, []):
                checks["field_completeness"] = _result_to_dict(
                    validate_field_completeness(
                        file_path,
                        required_fields=required,
                        chunk_size=cfg.chunk_size,
                        completeness_threshold=cfg.completeness_threshold,
                    )
                )

            # Duplicate records (composite key).
            if dup_keys := cfg.duplicate_key_fields.get(table, []):
                dup_result = validate_duplicate_records(
                    file_path,
                    key_fields=dup_keys,
                    chunk_size=cfg.chunk_size,
                    sample_limit=cfg.sample_limit,
                )
                dup_dict = _result_to_dict(dup_result)
                self._attach_failure_sample(
                    dup_dict,
                    label=f"{table}_duplicates_{stem}",
                    rows=[
                        s.get("row_sample", {})
                        for s in dup_result.details.get("duplicate_samples", [])
                        if isinstance(s, dict)
                    ],
                )
                checks["duplicate_records"] = dup_dict

            # Date fields.
            if dates := cfg.date_fields.get(table, []):
                date_result = validate_date_fields(
                    file_path,
                    date_fields=dates,
                    min_year=cfg.min_year,
                    max_year=cfg.max_year,
                    chunk_size=cfg.chunk_size,
                    sample_limit=cfg.sample_limit,
                )
                date_dict = _result_to_dict(date_result)
                self._attach_failure_sample(
                    date_dict,
                    label=f"{table}_invalid_dates_{stem}",
                    rows=date_result.details.get("invalid_samples", []),
                )
                checks["date_fields"] = date_dict

            results[file_str] = {
                "checks": checks,
                "overall_success": all(c.get("success", False) for c in checks.values()),
            }
        return results

    def _attach_failure_sample(
        self, result_dict: dict[str, Any], *, label: str, rows: list[dict[str, Any]]
    ) -> None:
        sample_path = self._write_failure_sample(label, rows)
        if sample_path:
            result_dict.setdefault("details", {})["failed_sample_path"] = sample_path

    def _summarize_tables(
        self, table_results: dict[str, dict[str, dict[str, Any]]]
    ) -> dict[str, Any]:
        summary: dict[str, Any] = {}
        total_checks = 0
        passed_checks = 0
        for table, results in table_results.items():
            if not results:
                summary[table] = {"files": 0, "files_passing": 0, "pass_rate": None}
                continue
            successes = [res.get("overall_success", False) for res in results.values()]
            summary[table] = {
                "files": len(results),
                "files_passing": sum(successes),
                "pass_rate": sum(successes) / max(len(successes), 1),
            }
            for res in results.values():
                for check in res.get("checks", {}).values():
                    total_checks += 1
                    if check.get("success"):
                        passed_checks += 1

        return {
            "table_breakdown": summary,
            "total_checks": total_checks,
            "passed_checks": passed_checks,
            "overall_pass_rate": passed_checks / max(total_checks, 1) if total_checks else 1.0,
        }

    def run(
        self,
        files_by_table: dict[str, list[str | Path]],
        write_report: bool = True,
    ) -> dict[str, Any]:
        """Execute all validators and return a structured report."""
        self._failure_samples = []
        assignments = files_by_table.get("assignments", []) or []

        table_results = {
            "assignments": self._run_table_checks("assignments", assignments),
            "assignees": self._run_table_checks(
                "assignees", files_by_table.get("assignees", []) or [], assignments
            ),
            "assignors": self._run_table_checks(
                "assignors", files_by_table.get("assignors", []) or [], assignments
            ),
            "documentids": self._run_table_checks(
                "documentids", files_by_table.get("documentids", []) or [], assignments
            ),
            "conveyances": self._run_table_checks(
                "conveyances", files_by_table.get("conveyances", []) or [], assignments
            ),
        }

        per_file_success = [
            res.get("overall_success", False)
            for table_dict in table_results.values()
            for res in table_dict.values()
        ]
        report = {
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "tables": table_results,
            "summary": self._summarize_tables(table_results),
            "overall_success": all(per_file_success) if per_file_success else True,
            "failure_samples": self._failure_samples,
        }

        if write_report:
            if path := self._write_report(report):
                report["report_path"] = path
        return report

    def _write_report(self, report: dict[str, Any]) -> str | None:
        timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
        report_path = self.config.report_output_dir / f"uspto_validation_{timestamp}.json"
        try:
            with report_path.open("w", encoding="utf-8") as fh:
                json.dump(report, fh, ensure_ascii=False, indent=2, default=str)
        except Exception as exc:  # pragma: no cover - IO guard
            logger.exception("Failed to write validation report %s: %s", report_path, exc)
            return None
        return str(report_path)


__all__ = [
    "USPTODataQualityValidator",
    "USPTOValidationConfig",
    "ValidatorResult",
    "iter_rows_from_path",
    "main_validate_rf_id_uniqueness",
    "validate_date_fields",
    "validate_duplicate_records",
    "validate_field_completeness",
    "validate_referential_integrity",
    "validate_rf_id_uniqueness",
    "validate_rf_id_uniqueness_from_iterator",
]
