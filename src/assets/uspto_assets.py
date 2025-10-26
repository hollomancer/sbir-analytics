"""
Dagster assets for USPTO per-table raw discovery and basic parsing checks.

This module provides:
- Per-table raw discovery assets:
  - `raw_uspto_assignments`
  - `raw_uspto_assignees`
  - `raw_uspto_assignors`
  - `raw_uspto_documentids`
  - `raw_uspto_conveyances`

- Lightweight per-table parsing assets that attempt to parse a small sample of each discovered file:
  - `parsed_uspto_<table>`

- Asset checks that fail when any discovered file cannot be parsed (basic parsing validation).

Notes:
- This module tries to import the local streaming extractor (`USPTOExtractor`) and the
  rf_id validator where appropriate. If heavy dependencies are not available at import
  time (for example in a constrained environment), parsing assets will report that the
  extractor is unavailable rather than raising on import.
- The discovery functions accept an optional `input_dir` via Dagster op config:
    op_config:
      input_dir: "/app/data/raw/uspto"
  Otherwise the environment variable `SBIR_ETL__USPTO__RAW_DIR` is consulted, and then a
  reasonable default `data/raw/uspto` is used.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, List, Optional

from dagster import (
    AssetExecutionContext,
    AssetIn,
    AssetCheckResult,
    AssetCheckSeverity,
    MetadataValue,
    asset,
    asset_check,
)
from loguru import logger

# Try to import the project's streaming extractor and validators. We allow import-time
# failure and degrade gracefully so repository introspection can proceed in CI environments
# that don't install heavy test/dev dependencies into the image.
try:  # pragma: no cover - defensive import
    from ..extractors.uspto_extractor import USPTOExtractor  # type: ignore
except Exception:
    USPTOExtractor = None  # type: ignore

try:  # pragma: no cover - defensive import
    from ..quality import validate_rf_id_uniqueness  # type: ignore
except Exception:
    validate_rf_id_uniqueness = None  # type: ignore

DEFAULT_USPTO_RAW_DIR = Path(os.environ.get("SBIR_ETL__USPTO__RAW_DIR", "data/raw/uspto"))

_SUPPORTED_EXTS = [".csv", ".dta", ".parquet"]


def _get_input_dir(context: AssetExecutionContext) -> Path:
    """
    Resolve the input directory for USPTO raw files from asset config, env var, or default.
    """
    # Prefer explicit op_config, if provided
    try:
        if context.op_config and "input_dir" in context.op_config:
            return Path(context.op_config["input_dir"])
    except Exception:
        # defensive: if context.op_config isn't dict-like, fall back
        pass

    # Fallback to env var or default
    return Path(os.environ.get("SBIR_ETL__USPTO__RAW_DIR", DEFAULT_USPTO_RAW_DIR))


def _discover_table_files(input_dir: Path, table_hint: str) -> List[str]:
    """
    Discover files under `input_dir` that likely correspond to `table_hint`, matching
    supported extensions. This uses a loose filename containment heuristic:
    - matches if the filename contains the `table_hint` substring (case-insensitive),
      or the filename begins with the table name.
    """
    if not input_dir or not Path(input_dir).exists():
        return []

    p = Path(input_dir)
    found: List[str] = []
    lh = table_hint.lower()

    for ext in _SUPPORTED_EXTS:
        # search for files that contain the table_hint in the name
        for cand in sorted(p.rglob(f"*{ext}")):
            name = cand.name.lower()
            if lh in name or name.startswith(lh):
                found.append(str(cand))
    return found


def _attempt_parse_sample(fp: str, sample_limit: int = 10, chunk_size: int = 10000) -> Dict:
    """
    Attempt to parse a small sample from a file using the USPTOExtractor when available.
    Returns a summary dict:
      {
        "success": bool,
        "sampled_rows": int,
        "sample_preview": [ ... ],
        "error": optional str
      }
    If the extractor is unavailable, returns a descriptive summary with success=False.
    """
    summary: Dict = {"success": False, "sampled_rows": 0, "sample_preview": [], "error": None}

    if USPTOExtractor is None:
        summary["error"] = "USPTOExtractor unavailable (missing dependencies)"
        return summary

    try:
        extractor = USPTOExtractor()
        # stream_rows yields dictionaries/rows; we collect up to sample_limit
        rows = []
        for i, row in enumerate(
            extractor.stream_rows(fp, chunk_size=chunk_size, sample_limit=sample_limit)
        ):
            rows.append(row)
            if i + 1 >= sample_limit:
                break

        summary["success"] = True
        summary["sampled_rows"] = len(rows)
        # Serialize preview with JSON-safe repr for complex objects
        try:
            summary["sample_preview"] = rows
        except Exception:
            # fallback: coerce to string reprs
            summary["sample_preview"] = [repr(r) for r in rows]
    except Exception as exc:  # pragma: no cover - runtime parsing guard
        logger.exception("Failed to parse sample from %s: %s", fp, exc)
        summary["error"] = str(exc)
        summary["success"] = False

    return summary


# -------------------------
# Raw discovery assets
# -------------------------
@asset(
    description="Discover raw USPTO assignment files",
    group_name="uspto",
)
def raw_uspto_assignments(context: AssetExecutionContext) -> List[str]:
    input_dir = _get_input_dir(context)
    context.log.info("Discovering assignment files", extra={"input_dir": str(input_dir)})
    files = _discover_table_files(input_dir, "assignment")
    context.log.info("Found assignment files", extra={"count": len(files), "files": files})
    return files


@asset(
    description="Discover raw USPTO assignee files",
    group_name="uspto",
)
def raw_uspto_assignees(context: AssetExecutionContext) -> List[str]:
    input_dir = _get_input_dir(context)
    context.log.info("Discovering assignee files", extra={"input_dir": str(input_dir)})
    files = _discover_table_files(input_dir, "assignee")
    context.log.info("Found assignee files", extra={"count": len(files), "files": files})
    return files


@asset(
    description="Discover raw USPTO assignor files",
    group_name="uspto",
)
def raw_uspto_assignors(context: AssetExecutionContext) -> List[str]:
    input_dir = _get_input_dir(context)
    context.log.info("Discovering assignor files", extra={"input_dir": str(input_dir)})
    files = _discover_table_files(input_dir, "assignor")
    context.log.info("Found assignor files", extra={"count": len(files), "files": files})
    return files


@asset(
    description="Discover raw USPTO documentid files",
    group_name="uspto",
)
def raw_uspto_documentids(context: AssetExecutionContext) -> List[str]:
    input_dir = _get_input_dir(context)
    context.log.info("Discovering documentid files", extra={"input_dir": str(input_dir)})
    files = _discover_table_files(input_dir, "documentid")
    context.log.info("Found documentid files", extra={"count": len(files), "files": files})
    return files


@asset(
    description="Discover raw USPTO conveyance files",
    group_name="uspto",
)
def raw_uspto_conveyances(context: AssetExecutionContext) -> List[str]:
    input_dir = _get_input_dir(context)
    context.log.info("Discovering conveyance files", extra={"input_dir": str(input_dir)})
    files = _discover_table_files(input_dir, "conveyance")
    context.log.info("Found conveyance files", extra={"count": len(files), "files": files})
    return files


# -------------------------
# Parsing assets (per-table)
# -------------------------
@asset(
    description="Attempt to parse a small sample of each discovered assignment file",
    group_name="uspto",
    ins={"raw_files": AssetIn("raw_uspto_assignments")},
)
def parsed_uspto_assignments(
    context: AssetExecutionContext, raw_files: List[str]
) -> Dict[str, dict]:
    """
    For each discovered raw assignment file, parse a small sample and return per-file summaries.
    """
    results: Dict[str, dict] = {}
    if not raw_files:
        context.log.info("No assignment files to parse")
        return results

    for fp in raw_files:
        context.log.info("Parsing sample from assignment file", extra={"file": fp})
        summary = _attempt_parse_sample(fp, sample_limit=10)
        results[fp] = summary
        context.log.info(
            "Parsed assignment sample",
            extra={"file": fp, "sampled_rows": summary.get("sampled_rows")},
        )
    return results


@asset(
    description="Attempt to parse a small sample of each discovered assignee file",
    group_name="uspto",
    ins={"raw_files": AssetIn("raw_uspto_assignees")},
)
def parsed_uspto_assignees(context: AssetExecutionContext, raw_files: List[str]) -> Dict[str, dict]:
    results: Dict[str, dict] = {}
    if not raw_files:
        context.log.info("No assignee files to parse")
        return results

    for fp in raw_files:
        context.log.info("Parsing sample from assignee file", extra={"file": fp})
        summary = _attempt_parse_sample(fp, sample_limit=8)
        results[fp] = summary
        context.log.info(
            "Parsed assignee sample",
            extra={"file": fp, "sampled_rows": summary.get("sampled_rows")},
        )
    return results


@asset(
    description="Attempt to parse a small sample of each discovered assignor file",
    group_name="uspto",
    ins={"raw_files": AssetIn("raw_uspto_assignors")},
)
def parsed_uspto_assignors(context: AssetExecutionContext, raw_files: List[str]) -> Dict[str, dict]:
    results: Dict[str, dict] = {}
    if not raw_files:
        context.log.info("No assignor files to parse")
        return results

    for fp in raw_files:
        context.log.info("Parsing sample from assignor file", extra={"file": fp})
        summary = _attempt_parse_sample(fp, sample_limit=8)
        results[fp] = summary
        context.log.info(
            "Parsed assignor sample",
            extra={"file": fp, "sampled_rows": summary.get("sampled_rows")},
        )
    return results


@asset(
    description="Attempt to parse a small sample of each discovered documentid file",
    group_name="uspto",
    ins={"raw_files": AssetIn("raw_uspto_documentids")},
)
def parsed_uspto_documentids(
    context: AssetExecutionContext, raw_files: List[str]
) -> Dict[str, dict]:
    results: Dict[str, dict] = {}
    if not raw_files:
        context.log.info("No documentid files to parse")
        return results

    for fp in raw_files:
        context.log.info("Parsing sample from documentid file", extra={"file": fp})
        summary = _attempt_parse_sample(fp, sample_limit=12)
        results[fp] = summary
        context.log.info(
            "Parsed documentid sample",
            extra={"file": fp, "sampled_rows": summary.get("sampled_rows")},
        )
    return results


@asset(
    description="Attempt to parse a small sample of each discovered conveyance file",
    group_name="uspto",
    ins={"raw_files": AssetIn("raw_uspto_conveyances")},
)
def parsed_uspto_conveyances(
    context: AssetExecutionContext, raw_files: List[str]
) -> Dict[str, dict]:
    results: Dict[str, dict] = {}
    if not raw_files:
        context.log.info("No conveyance files to parse")
        return results

    for fp in raw_files:
        context.log.info("Parsing sample from conveyance file", extra={"file": fp})
        summary = _attempt_parse_sample(fp, sample_limit=10)
        results[fp] = summary
        context.log.info(
            "Parsed conveyance sample",
            extra={"file": fp, "sampled_rows": summary.get("sampled_rows")},
        )
    return results


# -------------------------
# Asset checks (per-table parsing checks)
# -------------------------
def _make_parsing_check(
    table_asset_name: str,
    parsed_asset_name: str,
):
    """
    Factory to produce an asset_check function that inspects the parsed asset summaries
    and fails the check if any file reported parsing failures.
    """

    def _check(
        context: AssetExecutionContext, parsed: Dict[str, dict], raw_files: List[str]
    ) -> AssetCheckResult:
        total = len(raw_files)
        failed_files = []
        errors = {}

        # If parsing wasn't performed due to missing extractor, treat as ERROR to surface the issue
        if not parsed:
            msg = f"No parsed summaries produced for {parsed_asset_name} (parsed dict empty)."
            context.log.error(msg)
            return AssetCheckResult(
                passed=False,
                severity=AssetCheckSeverity.ERROR,
                description=msg,
                metadata={"raw_files_count": total},
            )

        for fp, summary in parsed.items():
            if not summary.get("success", False):
                failed_files.append(fp)
                errors[fp] = summary.get("error", "unknown")

        passed = len(failed_files) == 0

        description = (
            f"Parsing check for {table_asset_name}: {'passed' if passed else 'failed'} "
            f"({len(failed_files)}/{total} files)"
        )

        metadata = {
            "total_files": total,
            "failed_files_count": len(failed_files),
            "failed_files_sample": MetadataValue.json(failed_files[:10]),
            "errors": MetadataValue.json(errors),
        }

        severity = AssetCheckSeverity.WARN if passed else AssetCheckSeverity.ERROR

        context.log.info(
            "Parsing asset check result", extra={"asset": table_asset_name, **metadata}
        )
        return AssetCheckResult(
            passed=passed, severity=severity, description=description, metadata=metadata
        )

    # Return the inner function but keep dagster-friendly attributes for introspection
    _check.__name__ = f"{table_asset_name}_parsing_check"
    return _check


# Create concrete asset_check functions and bind them to the parsed assets using the decorator
uspto_assignments_parsing_check = asset_check(
    asset=parsed_uspto_assignments,
    description="Verify each discovered assignment file can be parsed for a small sample",
    additional_ins={"raw_files": AssetIn("raw_uspto_assignments")},
)(_make_parsing_check("raw_uspto_assignments", "parsed_uspto_assignments"))

uspto_assignees_parsing_check = asset_check(
    asset=parsed_uspto_assignees,
    description="Verify each discovered assignee file can be parsed for a small sample",
    additional_ins={"raw_files": AssetIn("raw_uspto_assignees")},
)(_make_parsing_check("raw_uspto_assignees", "parsed_uspto_assignees"))

uspto_assignors_parsing_check = asset_check(
    asset=parsed_uspto_assignors,
    description="Verify each discovered assignor file can be parsed for a small sample",
    additional_ins={"raw_files": AssetIn("raw_uspto_assignors")},
)(_make_parsing_check("raw_uspto_assignors", "parsed_uspto_assignors"))

uspto_documentids_parsing_check = asset_check(
    asset=parsed_uspto_documentids,
    description="Verify each discovered documentid file can be parsed for a small sample",
    additional_ins={"raw_files": AssetIn("raw_uspto_documentids")},
)(_make_parsing_check("raw_uspto_documentids", "parsed_uspto_documentids"))

uspto_conveyances_parsing_check = asset_check(
    asset=parsed_uspto_conveyances,
    description="Verify each discovered conveyance file can be parsed for a small sample",
    additional_ins={"raw_files": AssetIn("raw_uspto_conveyances")},
)(_make_parsing_check("raw_uspto_conveyances", "parsed_uspto_conveyances"))


# Expose symbols for repository import
__all__ = [
    "raw_uspto_assignments",
    "raw_uspto_assignees",
    "raw_uspto_assignors",
    "raw_uspto_documentids",
    "raw_uspto_conveyances",
    "parsed_uspto_assignments",
    "parsed_uspto_assignees",
    "parsed_uspto_assignors",
    "parsed_uspto_documentids",
    "parsed_uspto_conveyances",
    "uspto_assignments_parsing_check",
    "uspto_assignees_parsing_check",
    "uspto_assignors_parsing_check",
    "uspto_documentids_parsing_check",
    "uspto_conveyances_parsing_check",
]
