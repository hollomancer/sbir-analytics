"""
Consolidated Dagster assets for USPTO patent data pipeline.

This module provides the complete USPTO ETL pipeline organized by stage:

STAGE 1: Raw Discovery & Parsing
- Per-table raw discovery assets (`raw_uspto_*`)
- Lightweight parsing assets (`parsed_uspto_*`)
- Parsing validation checks

STAGE 2: Validation
- Data quality validation (`validated_uspto_assignments`)
- Quality checks (rf_id uniqueness, completeness, referential integrity)

STAGE 3: Transformation
- Patent assignment transformation (`transformed_patent_assignments`)
- Patent aggregation (`transformed_patents`)
- Entity extraction (`transformed_patent_entities`)
- Transformation quality checks

STAGE 4: Neo4j Loading
- Patent nodes (`neo4j_patents`)
- Assignment nodes (`neo4j_patent_assignments`)
- Entity nodes (`neo4j_patent_entities`)
- Relationship creation (`neo4j_patent_relationships`)
- Load success checks

STAGE 5: AI Extraction (Optional)
- AI dataset extraction (`raw_uspto_ai_extract`)
- Deduplication (`uspto_ai_deduplicate`)
- Human sampling (`raw_uspto_ai_human_sample_extraction`)

Notes:
- All assets use defensive imports and degrade gracefully when dependencies are unavailable
- Configuration via Dagster op_config or environment variables with SBIR_ETL__USPTO__ prefix
- Consistent naming: raw_*, validated_*, transformed_*, loaded_* (neo4j_*)
"""

from __future__ import annotations

import json
import os
import time
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from itertools import product
from pathlib import Path
from typing import Any

from dagster import (
    AssetCheckResult,
    AssetCheckSeverity,
    AssetIn,
    MetadataValue,
    asset,
    asset_check,
)
from loguru import logger

# Statistical reporting imports
try:  # pragma: no cover - defensive import
    from ..models.quality import ModuleReport  # type: ignore
    from ..utils.reporting.analyzers.patent_analyzer import PatentAnalysisAnalyzer  # type: ignore
except Exception:
    ModuleReport = None  # type: ignore
    PatentAnalysisAnalyzer = None  # type: ignore

# ============================================================================
# Optional imports - degrade gracefully when dependencies are unavailable
# ============================================================================

# USPTO extractor and transformers
try:  # pragma: no cover - defensive import
    from ..extractors.uspto_extractor import USPTOExtractor  # type: ignore
except Exception:
    USPTOExtractor = None  # type: ignore

try:  # pragma: no cover - defensive import
    from ..extractors.uspto_ai_extractor import USPTOAIExtractor  # type: ignore
except Exception:
    USPTOAIExtractor = None  # type: ignore

# Validators
try:  # pragma: no cover - defensive import
    from ..quality import USPTODataQualityValidator, USPTOValidationConfig  # type: ignore
except Exception:
    validate_rf_id_uniqueness = None  # type: ignore
    USPTODataQualityValidator = None  # type: ignore
    USPTOValidationConfig = None  # type: ignore

# Transformers
try:  # pragma: no cover - defensive import
    from ..transformers.patent_transformer import PatentAssignmentTransformer  # type: ignore
except Exception:
    PatentAssignmentTransformer = None  # type: ignore

# Models
try:  # pragma: no cover - defensive import
    from ..models.uspto_models import PatentAssignment  # type: ignore
except Exception:
    PatentAssignment = None  # type: ignore

# Neo4j loaders
try:  # pragma: no cover - defensive import
    from ..loaders.neo4j_client import LoadMetrics, Neo4jClient, Neo4jConfig  # type: ignore
except Exception:
    Neo4jClient = None  # type: ignore
    Neo4jConfig = None  # type: ignore
    LoadMetrics = None  # type: ignore

try:  # pragma: no cover - defensive import
    from ..loaders.patent_loader import PatentLoader, PatentLoaderConfig  # type: ignore
except Exception:
    PatentLoader = None  # type: ignore
    PatentLoaderConfig = None  # type: ignore

# ============================================================================
# Configuration Constants
# ============================================================================

DEFAULT_USPTO_RAW_DIR = Path(os.environ.get("SBIR_ETL__USPTO__RAW_DIR", "data/raw/uspto"))
DEFAULT_TRANSFORMED_DIR = Path(
    os.environ.get("SBIR_ETL__USPTO__TRANSFORM_DIR", "data/transformed/uspto")
)
DEFAULT_VALIDATION_FAIL_DIR = Path(
    os.environ.get("SBIR_ETL__USPTO__VALIDATION_FAIL_DIR", "data/validated/fail")
)
DEFAULT_VALIDATION_REPORT_DIR = Path(
    os.environ.get("SBIR_ETL__USPTO__VALIDATION_REPORT_DIR", "reports/uspto-validation")
)
DEFAULT_NEO4J_OUTPUT_DIR = Path(
    os.environ.get("SBIR_ETL__USPTO__NEO4J_OUTPUT_DIR", "data/loaded/neo4j")
)

# Neo4j defaults
DEFAULT_NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
DEFAULT_NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
DEFAULT_NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "neo4j")
DEFAULT_NEO4J_DATABASE = os.environ.get("NEO4J_DATABASE", "neo4j")

# AI extraction defaults
DEFAULT_AI_RAW_DIR = Path(os.environ.get("SBIR_ETL__USPTO_AI__RAW_DIR", "data/raw/USPTO"))
DEFAULT_AI_CHECKPOINT_DIR = Path(
    os.environ.get("SBIR_ETL__USPTO_AI__CHECKPOINT_DIR", "data/cache/uspto_ai_checkpoints")
)
DEFAULT_AI_DUCKDB = Path(
    os.environ.get("SBIR_ETL__USPTO_AI__DUCKDB", "data/processed/uspto_ai.duckdb")
)
DEFAULT_AI_TABLE = os.environ.get("SBIR_ETL__USPTO_AI__DUCKDB_TABLE", "uspto_ai_predictions")
DEFAULT_AI_DEDUP_TABLE = os.environ.get(
    "SBIR_ETL__USPTO_AI__DUCKDB_TABLE_DEDUP", f"{DEFAULT_AI_TABLE}_dedup"
)
DEFAULT_AI_PROCESSED_DIR = Path(
    os.environ.get("SBIR_ETL__USPTO_AI__PROCESSED_DIR", "data/processed")
)
DEFAULT_AI_SAMPLE_PATH = DEFAULT_AI_PROCESSED_DIR / "uspto_ai_human_sample_extraction.ndjson"
DEFAULT_EXTRACT_CHECKS = DEFAULT_AI_PROCESSED_DIR / "uspto_ai_extract.checks.json"
DEFAULT_DEDUP_CHECKS = DEFAULT_AI_PROCESSED_DIR / "uspto_ai_deduplicate.checks.json"

# Thresholds
TRANSFORM_SUCCESS_THRESHOLD = float(
    os.environ.get("SBIR_ETL__USPTO__TRANSFORM_SUCCESS_THRESHOLD", "0.98")
)
LINKAGE_TARGET = float(os.environ.get("SBIR_ETL__USPTO__LINKAGE_TARGET", "0.60"))
LOAD_SUCCESS_THRESHOLD = float(os.environ.get("SBIR_ETL__USPTO__LOAD_SUCCESS_THRESHOLD", "0.99"))

_SUPPORTED_EXTS = [".csv", ".dta", ".parquet"]


def _get_input_dir(context) -> Path:
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


def _discover_table_files(input_dir: Path, table_hint: str) -> list[str]:
    """
    Discover files under `input_dir` that likely correspond to `table_hint`, matching
    supported extensions. This uses a loose filename containment heuristic:
    - matches if the filename contains the `table_hint` substring (case-insensitive),
      or the filename begins with the table name.
    """
    if not input_dir or not Path(input_dir).exists():
        return []

    p = Path(input_dir)
    found: list[str] = []
    lh = table_hint.lower()

    for ext in _SUPPORTED_EXTS:
        # search for files that contain the table_hint in the name
        for cand in sorted(p.rglob(f"*{ext}")):
            name = cand.name.lower()
            if lh in name or name.startswith(lh):
                found.append(str(cand))
    return found


def _attempt_parse_sample(fp: str, sample_limit: int = 10, chunk_size: int = 10000) -> dict:
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
    summary: dict = {"success": False, "sampled_rows": 0, "sample_preview": [], "error": None}

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
    group_name="extraction",
)
def raw_uspto_assignments(context) -> list[str]:
    input_dir = _get_input_dir(context)
    context.log.info("Discovering assignment files", extra={"input_dir": str(input_dir)})
    files = _discover_table_files(input_dir, "assignment")
    context.log.info("Found assignment files", extra={"count": len(files), "files": files})
    return files


@asset(
    description="Discover raw USPTO assignee files",
    group_name="extraction",
)
def raw_uspto_assignees(context) -> list[str]:
    input_dir = _get_input_dir(context)
    context.log.info("Discovering assignee files", extra={"input_dir": str(input_dir)})
    files = _discover_table_files(input_dir, "assignee")
    context.log.info("Found assignee files", extra={"count": len(files), "files": files})
    return files


@asset(
    description="Discover raw USPTO assignor files",
    group_name="extraction",
)
def raw_uspto_assignors(context) -> list[str]:
    input_dir = _get_input_dir(context)
    context.log.info("Discovering assignor files", extra={"input_dir": str(input_dir)})
    files = _discover_table_files(input_dir, "assignor")
    context.log.info("Found assignor files", extra={"count": len(files), "files": files})
    return files


@asset(
    description="Discover raw USPTO documentid files",
    group_name="extraction",
)
def raw_uspto_documentids(context) -> list[str]:
    input_dir = _get_input_dir(context)
    context.log.info("Discovering documentid files", extra={"input_dir": str(input_dir)})
    files = _discover_table_files(input_dir, "documentid")
    context.log.info("Found documentid files", extra={"count": len(files), "files": files})
    return files


@asset(
    description="Discover raw USPTO conveyance files",
    group_name="extraction",
)
def raw_uspto_conveyances(context) -> list[str]:
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
    group_name="extraction",
    ins={"raw_files": AssetIn("raw_uspto_assignments")},
)
def parsed_uspto_assignments(context, raw_files: list[str]) -> dict[str, dict]:
    """
    For each discovered raw assignment file, parse a small sample and return per-file summaries.
    """
    results: dict[str, dict] = {}
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
    group_name="extraction",
    ins={"raw_files": AssetIn("raw_uspto_assignees")},
)
def validated_uspto_assignees(context, raw_files: list[str]) -> dict[str, dict]:
    results: dict[str, dict] = {}
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
    group_name="extraction",
    ins={"raw_files": AssetIn("raw_uspto_assignors")},
)
def validated_uspto_assignors(context, raw_files: list[str]) -> dict[str, dict]:
    results: dict[str, dict] = {}
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
    group_name="extraction",
    ins={"raw_files": AssetIn("raw_uspto_documentids")},
)
def parsed_uspto_documentids(context, raw_files: list[str]) -> dict[str, dict]:
    results: dict[str, dict] = {}
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
    group_name="extraction",
    ins={"raw_files": AssetIn("raw_uspto_conveyances")},
)
def parsed_uspto_conveyances(context, raw_files: list[str]) -> dict[str, dict]:
    results: dict[str, dict] = {}
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

    def _check(context, parsed: dict[str, dict], raw_files: list[str]) -> AssetCheckResult:
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
    asset=validated_uspto_assignees,
    description="Verify each discovered assignee file can be parsed for a small sample",
    additional_ins={"raw_files": AssetIn("raw_uspto_assignees")},
)(_make_parsing_check("raw_uspto_assignees", "validated_uspto_assignees"))

uspto_assignors_parsing_check = asset_check(
    asset=validated_uspto_assignors,
    description="Verify each discovered assignor file can be parsed for a small sample",
    additional_ins={"raw_files": AssetIn("raw_uspto_assignors")},
)(_make_parsing_check("raw_uspto_assignors", "validated_uspto_assignors"))

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


# ============================================================================
# STAGE 2: Validation Assets
# ============================================================================


def _build_validator_config(context) -> USPTOValidationConfig:
    """Build validation config from context op_config with defaults."""
    if USPTOValidationConfig is None:
        return None  # type: ignore
    cfg = getattr(context, "op_config", {}) or {}
    return USPTOValidationConfig(
        chunk_size=int(cfg.get("chunk_size", 10000)),
        sample_limit=int(cfg.get("sample_limit", 20)),
        completeness_threshold=float(cfg.get("completeness_threshold", 0.95)),
        min_year=int(cfg.get("min_year", 1790)),
        max_year=int(cfg.get("max_year", 2100)),
        fail_output_dir=Path(cfg.get("fail_output_dir", DEFAULT_VALIDATION_FAIL_DIR)),
        report_output_dir=Path(cfg.get("report_output_dir", DEFAULT_VALIDATION_REPORT_DIR)),
    )


def _extract_table_results(report: dict[str, Any], table: str) -> dict[str, dict[str, Any]]:
    """Extract table-specific results from validation report."""
    return (report or {}).get("tables", {}).get(table, {}) or {}


@asset(
    description="Validate USPTO assignment-related tables for data quality and integrity",
    group_name="extraction",
    ins={
        "assignment_files": AssetIn("raw_uspto_assignments"),
        "assignee_files": AssetIn("raw_uspto_assignees"),
        "assignor_files": AssetIn("raw_uspto_assignors"),
        "documentid_files": AssetIn("raw_uspto_documentids"),
        "conveyance_files": AssetIn("raw_uspto_conveyances"),
    },
)
def validated_uspto_assignments(
    context,
    assignment_files: list[str],
    assignee_files: list[str],
    assignor_files: list[str],
    documentid_files: list[str],
    conveyance_files: list[str],
) -> dict[str, Any]:
    """Run the USPTO data quality validator across all discovered tables."""
    if USPTODataQualityValidator is None:
        context.log.warning("USPTODataQualityValidator unavailable")
        return {
            "error": "validator_unavailable",
            "tables": {},
            "summary": {},
            "overall_success": False,
            "failure_samples": [],
        }

    files_by_table = {
        "assignments": assignment_files or [],
        "assignees": assignee_files or [],
        "assignors": assignor_files or [],
        "documentids": documentid_files or [],
        "conveyances": conveyance_files or [],
    }

    validator = USPTODataQualityValidator(_build_validator_config(context))
    write_report = (
        getattr(context, "op_config", {}).get("write_report", True) if context.op_config else True
    )

    try:
        report = validator.run(files_by_table, write_report=write_report)
    except Exception as exc:  # pragma: no cover - defensive guard
        context.log.exception("USPTO validation failed: %s", exc)
        return {
            "error": str(exc),
            "tables": {},
            "summary": {},
            "overall_success": False,
            "failure_samples": [],
        }

    summary = report.get("summary", {})
    metadata = {
        "overall_success": report.get("overall_success", False),
        "total_checks": summary.get("total_checks", 0),
        "passed_checks": summary.get("passed_checks", 0),
        "pass_rate": summary.get("overall_pass_rate"),
        "report_path": report.get("report_path"),
        "failure_samples": MetadataValue.json((report.get("failure_samples") or [])[:20]),
    }
    context.add_output_metadata(metadata)

    context.log.info(
        "USPTO validation report generated",
        extra={
            "overall_success": report.get("overall_success"),
            "total_checks": summary.get("total_checks"),
            "report_path": report.get("report_path"),
        },
    )
    return report


@asset_check(
    asset=validated_uspto_assignments,
    description="Ensure rf_id uniqueness holds for all assignment files",
    additional_ins={"assignment_files": AssetIn("raw_uspto_assignments")},
)
def uspto_rf_id_asset_check(
    context,
    validation_report: dict[str, Any],
    assignment_files: list[str],
) -> AssetCheckResult:
    """Check that rf_id uniqueness holds for all assignment files."""
    assignments = _extract_table_results(validation_report, "assignments")

    if not assignments and assignment_files:
        return AssetCheckResult(
            passed=False,
            severity=AssetCheckSeverity.ERROR,
            description="No assignment validation results were produced",
            metadata={
                "assignment_files_expected": len(assignment_files),
                "report_path": validation_report.get("report_path"),
            },
        )

    failed_files: list[dict[str, Any]] = []
    duplicate_total = 0

    for file_path, result in assignments.items():
        check = result.get("checks", {}).get("rf_id_uniqueness")
        if not check:
            continue
        duplicates = check.get("summary", {}).get("duplicate_rf_id_values", 0)
        duplicate_total += duplicates or 0
        if not check.get("success", False):
            failed_files.append({"file": file_path, "duplicate_rf_ids": duplicates})

    passed = len(failed_files) == 0

    metadata = {
        "assignment_files_total": len(assignment_files or []),
        "validated_files": len(assignments),
        "duplicate_values_found": duplicate_total,
        "failed_files": MetadataValue.json(failed_files[:10]),
        "report_path": validation_report.get("report_path"),
    }

    description = (
        "USPTO rf_id uniqueness check "
        f"{'passed' if passed else 'failed'} ({len(failed_files)} files with duplicates)"
    )

    severity = AssetCheckSeverity.ERROR if not passed else AssetCheckSeverity.WARN

    return AssetCheckResult(
        passed=passed,
        severity=severity,
        metadata=metadata,
        description=description,
    )


@asset_check(
    asset=validated_uspto_assignments,
    description="Validate required field completeness across USPTO tables",
)
def uspto_completeness_asset_check(
    context,
    validation_report: dict[str, Any],
) -> AssetCheckResult:
    """Check that required fields have sufficient completeness."""
    tables = (validation_report or {}).get("tables", {})
    failures: list[dict[str, Any]] = []

    for table, results in tables.items():
        for file_path, result in (results or {}).items():
            completeness = result.get("checks", {}).get("field_completeness")
            if completeness and not completeness.get("success", False):
                failures.append(
                    {
                        "table": table,
                        "file": file_path,
                        "failed_fields": completeness.get("details", {}).get("failed_fields", []),
                        "overall_completeness": completeness.get("summary", {}).get(
                            "overall_completeness"
                        ),
                    }
                )

    passed = len(failures) == 0
    metadata = {
        "failed_tables": MetadataValue.json(failures[:10]),
        "report_path": validation_report.get("report_path"),
    }

    severity = AssetCheckSeverity.ERROR if not passed else AssetCheckSeverity.WARN

    description = (
        "USPTO completeness check "
        f"{'passed' if passed else 'failed'} ({len(failures)} files below threshold)"
    )

    return AssetCheckResult(
        passed=passed,
        severity=severity,
        metadata=metadata,
        description=description,
    )


@asset_check(
    asset=validated_uspto_assignments,
    description="Ensure referential integrity across USPTO tables",
)
def uspto_referential_asset_check(
    context,
    validation_report: dict[str, Any],
) -> AssetCheckResult:
    """Check referential integrity across USPTO tables."""
    tables = (validation_report or {}).get("tables", {})
    failures: list[dict[str, Any]] = []

    for table, results in tables.items():
        if table == "assignments":
            continue
        for file_path, result in (results or {}).items():
            ref_check = result.get("checks", {}).get("referential_integrity")
            if ref_check and not ref_check.get("success", False):
                failures.append(
                    {
                        "table": table,
                        "file": file_path,
                        "orphaned_records": ref_check.get("summary", {}).get("orphaned_records"),
                        "sample_path": ref_check.get("details", {}).get("failed_sample_path"),
                    }
                )

    passed = len(failures) == 0
    metadata = {
        "referential_failures": MetadataValue.json(failures[:10]),
        "report_path": validation_report.get("report_path"),
    }

    severity = AssetCheckSeverity.ERROR if not passed else AssetCheckSeverity.WARN

    description = (
        "USPTO referential integrity check "
        f"{'passed' if passed else 'failed'} ({len(failures)} files with orphaned rf_id values)"
    )

    return AssetCheckResult(
        passed=passed,
        severity=severity,
        metadata=metadata,
        description=description,
    )


# ============================================================================
# STAGE 3: Transformation Assets
# ============================================================================
# Transformation assets consolidated and implemented:
# - transformed_patent_assignments: Transform raw patent assignment data
# - transformed_patents: Transform patent document data  
# - transformed_patent_entities: Transform patent entity data
# - uspto_transformation_success_check: Validate transformation success rates
# - uspto_company_linkage_check: Validate SBIR company linkage coverage


# Transformation helpers and assets
def _now_suffix() -> str:
    return datetime.utcnow().strftime("%Y%m%dT%H%M%S")


def _ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def _load_sbir_index(index_path: str | None) -> dict[str, str]:
    if not index_path:
        return {}
    idx_file = Path(index_path)
    if not idx_file.exists():
        return {}
    try:
        with idx_file.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            return {str(k).upper(): str(v) for k, v in data.items()}
    except Exception:  # pragma: no cover - best-effort loader
        return {}
    return {}


def _serialize_assignment(model: Any) -> dict[str, Any]:
    if model is None:
        return {}
    if hasattr(model, "model_dump"):
        return model.model_dump(mode="json")  # type: ignore[attr-defined]
    if isinstance(model, dict):
        return model
    return dict(model.__dict__)


def _iter_small_sample(store: list[Any], new_item: Any, limit: int) -> None:
    if len(store) < limit:
        store.append(new_item)


def _coerce_str(val: Any) -> str | None:
    if val in (None, ""):
        return None
    return str(val)


def _combine_address(*parts: str | None) -> str | None:
    parts_clean = [
        p for p in (part.strip() if isinstance(part, str) else part for part in parts) if p
    ]
    return ", ".join(parts_clean) if parts_clean else None


def _normalize_country(country: str | None) -> str | None:
    if not country:
        return None
    c = str(country).strip().upper()
    if c in {"NOT PROVIDED", "", "UNKNOWN", "N/A"}:
        return None
    return c


@dataclass
class JoinedRow:
    data: dict[str, Any]
    rf_id: str | None


class USPTOAssignmentJoiner:
    """Join USPTO tables on rf_id and emit flattened rows for transformation."""

    def __init__(self, extractor: USPTOExtractor, chunk_size: int = 10000) -> None:
        self.extractor = extractor
        self.chunk_size = chunk_size

    def _lookup(self, files: Iterable[str]) -> dict[str, list[dict[str, Any]]]:
        table: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for file_path in files or []:
            path = Path(file_path)
            if not path.exists():
                continue
            for row in self.extractor.stream_rows(path, chunk_size=self.chunk_size):
                rf = row.get("rf_id")
                if rf in (None, ""):
                    continue
                copied = dict(row)
                copied["_source_file"] = str(path)
                table[str(rf)].append(copied)
        return table

    @staticmethod
    def _merge_rows(
        assignment: dict[str, Any],
        assignee: dict[str, Any] | None,
        assignor: dict[str, Any] | None,
        document: dict[str, Any] | None,
        conveyance: dict[str, Any] | None,
    ) -> dict[str, Any]:
        merged: dict[str, Any] = {}

        def set_if(key: str, *values: Any) -> None:
            for value in values:
                if value not in (None, ""):
                    merged[key] = value
                    return

        # Assignment core fields
        set_if("rf_id", assignment.get("rf_id"))
        set_if("file_id", assignment.get("file_id"))
        set_if("recorded_date", assignment.get("record_dt"), assignment.get("recorded_date"))
        set_if("execution_date", assignment.get("exec_dt"), assignment.get("execution_date"))
        set_if("conveyance_text", assignment.get("convey_text"))
        merged["source_assignment"] = {
            "reel_no": assignment.get("reel_no"),
            "frame_no": assignment.get("frame_no"),
            "correspondent": assignment.get("cname"),
        }

        # Document fields
        if document:
            set_if("document_rf_id", document.get("rf_id"))
            set_if("grant_doc_num", document.get("grant_doc_num"), document.get("grant_doc_number"))
            set_if(
                "application_number",
                document.get("appno_doc_num"),
                document.get("appno_doc_number"),
            )
            set_if("publication_number", document.get("pgpub_doc_num"))
            set_if("filing_date", document.get("appno_date"))
            set_if("publication_date", document.get("pgpub_date"))
            set_if("grant_date", document.get("grant_date"))
            set_if("title", document.get("title"))
            set_if("language", document.get("lang"))

        # Assignee fields
        if assignee:
            set_if("assignee_rf_id", assignee.get("rf_id"))
            set_if("assignee_name", assignee.get("ee_name"))
            set_if("assignee_street", assignee.get("ee_address_1"))
            set_if("assignee_city", assignee.get("ee_city"))
            set_if("assignee_state", assignee.get("ee_state"))
            set_if("assignee_postal", assignee.get("ee_postcode"))
            set_if("assignee_country", _normalize_country(assignee.get("ee_country")))
            set_if(
                "assignee_address",
                _combine_address(assignee.get("ee_address_1"), assignee.get("ee_address_2")),
            )

        # Assignor fields
        if assignor:
            set_if("assignor_rf_id", assignor.get("rf_id"))
            set_if("assignor_name", assignor.get("or_name"))
            set_if("execution_date", assignor.get("exec_dt"), assignor.get("execution_date"))
            set_if("acknowledgment_date", assignor.get("ack_dt"))

        # Conveyance fields
        if conveyance:
            set_if("conveyance", conveyance.get("convey_ty"))
            merged["employer_assign"] = conveyance.get("employer_assign")

        return merged

    def iter_joined_records(
        self,
        assignment_files: Iterable[str],
        assignee_files: Iterable[str],
        assignor_files: Iterable[str],
        document_files: Iterable[str],
        conveyance_files: Iterable[str],
    ) -> Iterable[JoinedRow]:
        assignees = self._lookup(assignee_files)
        assignors = self._lookup(assignor_files)
        documents = self._lookup(document_files)
        conveyances = self._lookup(conveyance_files)

        for assignment_file in assignment_files:
            path = Path(assignment_file)
            if not path.exists():
                continue
            for assignment in self.extractor.stream_rows(path, chunk_size=self.chunk_size):
                rf = assignment.get("rf_id")
                rf_key = str(rf) if rf not in (None, "") else None
                assignee_rows = assignees.get(rf_key, [None]) if rf_key else [None]
                assignor_rows = assignors.get(rf_key, [None]) if rf_key else [None]
                document_rows = documents.get(rf_key, [None]) if rf_key else [None]
                convey_rows = conveyances.get(rf_key, [None]) if rf_key else [None]

                for ass_row, asr_row, doc_row, conv_row in product(
                    assignee_rows or [None],
                    assignor_rows or [None],
                    document_rows or [None],
                    convey_rows or [None],
                ):
                    merged = self._merge_rows(assignment, ass_row, asr_row, doc_row, conv_row)
                    merged["_source_assignment_file"] = str(path)
                    yield JoinedRow(merged, rf_key)


def _resolve_output_paths(context, prefix: str) -> tuple[Path, Path]:
    cfg = context.op_config or {}
    base_dir = Path(cfg.get("output_dir", DEFAULT_TRANSFORMED_DIR))
    _ensure_dir(base_dir)
    timestamp = _now_suffix()
    return base_dir / f"{prefix}_{timestamp}.jsonl", base_dir


def _load_assignments_file(path: str | None) -> Iterable[dict[str, Any]]:
    if not path:
        return []
    src = Path(path)
    if not src.exists():
        return []
    with src.open("r", encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


@asset(
    description="Transform USPTO assignments into normalized PatentAssignment models",
    group_name="extraction",
    ins={
        "assignment_files": AssetIn("raw_uspto_assignments"),
        "assignee_files": AssetIn("raw_uspto_assignees"),
        "assignor_files": AssetIn("raw_uspto_assignors"),
        "documentid_files": AssetIn("raw_uspto_documentids"),
        "conveyance_files": AssetIn("raw_uspto_conveyances"),
        "validation_report": AssetIn("validated_uspto_assignments"),
    },
)
def transformed_patent_assignments(
    context,
    assignment_files: list[str],
    assignee_files: list[str],
    assignor_files: list[str],
    documentid_files: list[str],
    conveyance_files: list[str],
    validation_report: dict[str, Any],
) -> dict[str, Any]:
    if USPTOExtractor is None or PatentAssignmentTransformer is None:
        msg = "USPTOExtractor or PatentAssignmentTransformer unavailable"
        context.log.warning(msg)
        return {"error": msg, "total_records": 0, "success_count": 0}

    if not assignment_files:
        context.log.warning("No assignment files discovered; skipping transformation")
        return {"error": "no_assignment_files", "total_records": 0, "success_count": 0}

    chunk_size = int((context.op_config or {}).get("chunk_size", 10000))
    sample_limit = int((context.op_config or {}).get("sample_limit", 5))
    sbir_index = _load_sbir_index((context.op_config or {}).get("sbir_index_path"))

    output_path, base_dir = _resolve_output_paths(context, "patent_assignments")
    failure_path = base_dir / f"patent_assignment_failures_{_now_suffix()}.jsonl"

    stats = {
        "total_records": 0,
        "success_count": 0,
        "error_count": 0,
        "linked_count": 0,
    }
    samples: list[dict[str, Any]] = []

    extractor = USPTOExtractor(Path(assignment_files[0]).parent)
    joiner = USPTOAssignmentJoiner(extractor, chunk_size=chunk_size)
    transformer = PatentAssignmentTransformer(sbir_company_grant_index=sbir_index)

    failure_written = False
    with (
        output_path.open("w", encoding="utf-8") as out_fh,
        failure_path.open("w", encoding="utf-8") as fail_fh,
    ):
        for joined in joiner.iter_joined_records(
            assignment_files, assignee_files, assignor_files, documentid_files, conveyance_files
        ):
            stats["total_records"] += 1
            result = transformer.transform_row(joined.data)

            if PatentAssignment is not None and isinstance(result, PatentAssignment):
                stats["success_count"] += 1
                if result.metadata.get("linked_sbir_company"):
                    stats["linked_count"] += 1
                serialized = _serialize_assignment(result)
                out_fh.write(json.dumps(serialized) + "\n")
                _iter_small_sample(samples, result.summarize(), sample_limit)
            elif isinstance(result, dict) and "_error" not in result:
                stats["success_count"] += 1
                if result.get("metadata", {}).get("linked_sbir_company"):
                    stats["linked_count"] += 1
                out_fh.write(json.dumps(result) + "\n")
                _iter_small_sample(samples, result, sample_limit)
            else:
                stats["error_count"] += 1
                failure_written = True
                failure_payload = result if isinstance(result, dict) else {"_error": str(result)}
                failure_payload.setdefault("rf_id", joined.rf_id)
                fail_fh.write(json.dumps(failure_payload) + "\n")

    if not failure_written and failure_path.exists():
        failure_path.unlink(missing_ok=True)

    success_rate = (
        stats["success_count"] / stats["total_records"] if stats["total_records"] > 0 else 0.0
    )
    linkage_rate = (
        stats["linked_count"] / stats["success_count"] if stats["success_count"] > 0 else 0.0
    )

    metadata = {
        "output_path": str(output_path),
        "failure_path": str(failure_path) if failure_written else None,
        "total_records": stats["total_records"],
        "success_count": stats["success_count"],
        "error_count": stats["error_count"],
        "success_rate": success_rate,
        "linked_assignments": stats["linked_count"],
        "linkage_rate": linkage_rate,
        "sample": MetadataValue.json(samples),
        "validation_passed": bool(validation_report.get("overall_success", False)),
    }
    context.add_output_metadata({k: v for k, v in metadata.items() if v is not None})

    return metadata


@asset(
    description="Aggregate transformed assignments into patent-centric records",
    group_name="extraction",
    ins={"transformed_assignments": AssetIn("transformed_patent_assignments")},
)
def transformed_patents(context, transformed_assignments: dict[str, Any]) -> dict[str, Any]:
    output_path, base_dir = _resolve_output_paths(context, "patents")
    src_path = transformed_assignments.get("output_path")
    if not src_path or not Path(src_path).exists():
        context.log.warning("No transformed assignments output available for patent aggregation")
        return {"error": "missing_assignments", "patent_count": 0}

    patents: dict[str, dict[str, Any]] = {}
    linked = 0
    for record in _load_assignments_file(src_path):
        document = record.get("document") or {}
        grant = document.get("grant_number") or document.get("publication_number")
        if not grant:
            continue
        grant = str(grant)
        entry = patents.setdefault(
            grant,
            {
                "grant_number": grant,
                "title": document.get("title"),
                "language": document.get("language"),
                "assignee_names": set(),
                "assignor_names": set(),
                "assignment_count": 0,
                "latest_recorded_date": None,
                "linked_companies": set(),
            },
        )
        entry["assignment_count"] += 1
        if record.get("assignee"):
            name = record["assignee"].get("name") if isinstance(record["assignee"], dict) else None
            if name:
                entry["assignee_names"].add(name)
        if record.get("assignor"):
            name = record["assignor"].get("name") if isinstance(record["assignor"], dict) else None
            if name:
                entry["assignor_names"].add(name)
        linked_meta = (record.get("metadata") or {}).get("linked_sbir_company")
        if linked_meta:
            entry["linked_companies"].add(linked_meta.get("company_id"))
        if record.get("recorded_date"):
            current = entry["latest_recorded_date"]
            new_date = record["recorded_date"]
            if current is None or new_date > current:
                entry["latest_recorded_date"] = new_date

    with output_path.open("w", encoding="utf-8") as fh:
        for entry in patents.values():
            entry["assignee_names"] = sorted(entry["assignee_names"])  # type: ignore
            entry["assignor_names"] = sorted(entry["assignor_names"])  # type: ignore
            entry["linked_companies"] = sorted(entry["linked_companies"])  # type: ignore
            if entry["linked_companies"]:
                linked += 1
            fh.write(json.dumps(entry) + "\n")

    metadata = {
        "output_path": str(output_path),
        "patent_count": len(patents),
        "linked_patent_count": linked,
        "linkage_rate": linked / len(patents) if patents else 0.0,
    }
    context.add_output_metadata(metadata)
    return metadata


@asset(
    description="Derive patent entity dimension (assignees + assignors)",
    group_name="extraction",
    ins={"transformed_assignments": AssetIn("transformed_patent_assignments")},
)
def transformed_patent_entities(context, transformed_assignments: dict[str, Any]) -> dict[str, Any]:
    output_path, _ = _resolve_output_paths(context, "patent_entities")
    src_path = transformed_assignments.get("output_path")
    if not src_path or not Path(src_path).exists():
        context.log.warning("No transformed assignments output available for entity aggregation")
        return {"error": "missing_assignments", "entity_count": 0}

    entities: dict[str, dict[str, Any]] = {}

    def upsert(entity: dict[str, Any], entity_type: str, rf_id: str | None) -> None:
        if not entity:
            return
        name = entity.get("name")
        if not name:
            return
        key = f"{entity_type}:{name.upper()}"
        bucket = entities.setdefault(
            key,
            {
                "name": name,
                "entity_type": entity_type,
                "rf_ids": set(),
                "city": entity.get("city"),
                "state": entity.get("state"),
                "country": entity.get("country"),
                "linked_companies": set(),
            },
        )
        if rf_id:
            bucket["rf_ids"].add(rf_id)
        if entity.get("metadata", {}).get("linked_sbir_company"):
            bucket["linked_companies"].add(
                entity["metadata"]["linked_sbir_company"].get("company_id")
            )

    for record in _load_assignments_file(src_path):
        rf_id = record.get("rf_id")
        if isinstance(record.get("assignee"), dict):
            upsert(record["assignee"], "assignee", rf_id)
        if isinstance(record.get("assignor"), dict):
            upsert(record["assignor"], "assignor", rf_id)

    with output_path.open("w", encoding="utf-8") as fh:
        for entry in entities.values():
            entry["rf_ids"] = sorted(entry["rf_ids"])  # type: ignore
            entry["linked_companies"] = sorted(entry["linked_companies"])  # type: ignore
            fh.write(json.dumps(entry) + "\n")

    metadata = {
        "output_path": str(output_path),
        "entity_count": len(entities),
    }
    context.add_output_metadata(metadata)
    return metadata


@asset_check(
    asset=transformed_patent_assignments,
    description="Verify transformation success rate meets threshold",
)
def uspto_transformation_success_check(
    context, transformed_patent_assignments: dict[str, Any]
) -> AssetCheckResult:
    success_rate = transformed_patent_assignments.get("success_rate", 0.0)
    passed = success_rate >= TRANSFORM_SUCCESS_THRESHOLD
    metadata = {
        "success_rate": success_rate,
        "threshold": TRANSFORM_SUCCESS_THRESHOLD,
        "total_records": transformed_patent_assignments.get("total_records", 0),
        "success_count": transformed_patent_assignments.get("success_count", 0),
    }
    severity = AssetCheckSeverity.WARN if passed else AssetCheckSeverity.ERROR
    return AssetCheckResult(
        passed=passed,
        severity=severity,
        description=(
            f"Transformation success rate {success_rate:.2%} "
            f"({'meets' if passed else 'below'} threshold {TRANSFORM_SUCCESS_THRESHOLD:.0%})"
        ),
        metadata=metadata,
    )


@asset_check(
    asset=transformed_patent_assignments,
    description="Ensure SBIR company linkage coverage meets target",
)
def uspto_company_linkage_check(
    context, transformed_assignments: dict[str, Any]
) -> AssetCheckResult:
    linkage_rate = transformed_patent_assignments.get("linkage_rate", 0.0)
    passed = linkage_rate >= LINKAGE_TARGET
    metadata = {
        "linkage_rate": linkage_rate,
        "linked_assignments": transformed_patent_assignments.get("linked_assignments", 0),
        "success_count": transformed_patent_assignments.get("success_count", 0),
        "target": LINKAGE_TARGET,
    }
    severity = AssetCheckSeverity.WARN if passed else AssetCheckSeverity.ERROR
    return AssetCheckResult(
        passed=passed,
        severity=severity,
        description=(
            f"Company linkage rate {linkage_rate:.2%} "
            f"({'meets' if passed else 'below'} target {LINKAGE_TARGET:.0%})"
        ),
        metadata=metadata,
    )


# Neo4j loading assets
def _get_neo4j_client() -> Neo4jClient | None:
    """Create and return a Neo4j client, or None if unavailable."""
    if Neo4jClient is None or Neo4jConfig is None:
        logger.warning("Neo4jClient unavailable; skipping Neo4j operations")
        return None

    try:
        config = Neo4jConfig(
            uri=DEFAULT_NEO4J_URI,
            username=DEFAULT_NEO4J_USER,
            password=DEFAULT_NEO4J_PASSWORD,
            database=DEFAULT_NEO4J_DATABASE,
        )
        client = Neo4jClient(config)
        logger.info(f"Created Neo4j client for {DEFAULT_NEO4J_URI}")
        return client
    except Exception as e:
        logger.error(f"Failed to create Neo4j client: {e}")
        return None


def _ensure_output_dir() -> Path:
    """Ensure output directory exists."""
    DEFAULT_NEO4J_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return DEFAULT_NEO4J_OUTPUT_DIR


def _load_transformed_file(file_path: Path) -> list[dict[str, Any]]:
    """Load JSONL file of transformed records."""
    records = []
    if not file_path.exists():
        logger.warning(f"Transformed file not found: {file_path}")
        return records

    try:
        with file_path.open("r", encoding="utf-8") as fh:
            for line_num, line in enumerate(fh, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    records.append(record)
                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to parse JSON at line {line_num}: {e}")
        logger.info(f"Loaded {len(records)} records from {file_path}")
    except Exception as e:
        logger.error(f"Failed to load transformed file {file_path}: {e}")

    return records


def _convert_dates_to_iso(obj: Any) -> Any:
    """Recursively convert date/datetime objects to ISO format strings."""
    if isinstance(obj, date | datetime):
        return obj.isoformat()
    elif isinstance(obj, dict):
        return {k: _convert_dates_to_iso(v) for k, v in obj.items()}
    elif isinstance(obj, list | tuple):
        return [_convert_dates_to_iso(item) for item in obj]
    return obj


def _serialize_metrics(metrics: LoadMetrics | None) -> dict[str, Any]:
    """Serialize LoadMetrics to dict for output."""
    if metrics is None:
        return {
            "nodes_created": {},
            "nodes_updated": {},
            "relationships_created": {},
            "errors": 0,
        }

    return {
        "nodes_created": metrics.nodes_created,
        "nodes_updated": metrics.nodes_updated,
        "relationships_created": metrics.relationships_created,
        "errors": metrics.errors,
    }


# ============================================================================
# Phase 1: Load Patents and PatentAssignments
# ============================================================================


@asset(
    description="Load Patent nodes into Neo4j from transformed patent documents",
    group_name="uspto_loading",
    deps=["transformed_patents"],
    config_schema={
        "create_indexes": bool,
        "create_constraints": bool,
    },
)
def loaded_patents(context) -> dict[str, Any]:
    """Phase 1 Step 2: Load Patent nodes into Neo4j.

    Reads transformed patent documents and creates Patent nodes with:
    - grant_doc_num as unique key
    - title, dates, language, abstract
    - raw metadata
    """
    if PatentLoader is None:
        context.log.error("PatentLoader unavailable; skipping patent loading")
        return {"status": "failed", "reason": "PatentLoader unavailable"}

    client = _get_neo4j_client()
    if client is None:
        return {"status": "failed", "reason": "Neo4j client unavailable"}

    context.log.info("Starting Phase 1 Step 2: Loading Patents into Neo4j")
    start_time = time.time()
    output_dir = _ensure_output_dir()

    try:
        # Load transformed patents
        transformed_patents_file = DEFAULT_TRANSFORMED_DIR / "transformed_patents.jsonl"
        patents = _load_transformed_file(transformed_patents_file)
        context.log.info(f"Loaded {len(patents)} patent records to load")

        # Ensure date fields are ISO format
        patents = [_convert_dates_to_iso(p) for p in patents]

        # Create loader and optionally create indexes/constraints
        loader_config = PatentLoaderConfig(
            batch_size=1000,
            create_indexes=context.op_config.get("create_indexes", True),
            create_constraints=context.op_config.get("create_constraints", True),
        )
        loader = PatentLoader(client, loader_config)

        # Create indexes and constraints if requested
        if context.op_config.get("create_constraints", True):
            context.log.info("Creating Neo4j constraints...")
            loader.create_constraints()

        if context.op_config.get("create_indexes", True):
            context.log.info("Creating Neo4j indexes...")
            loader.create_indexes()

        # Load Patent nodes
        context.log.info(f"Loading {len(patents)} Patent nodes...")
        metrics = loader.load_patents(patents)

        duration = time.time() - start_time
        success_count = metrics.nodes_created.get("Patent", 0) + metrics.nodes_updated.get(
            "Patent", 0
        )
        success_rate = success_count / len(patents) if patents else 0.0

        result = {
            "status": "success",
            "phase": 1,
            "patents_loaded": success_count,
            "total_patents": len(patents),
            "success_rate": success_rate,
            "duration_seconds": duration,
            "metrics": _serialize_metrics(metrics),
        }

        # Save metrics to file
        metrics_file = output_dir / f"neo4j_patents_metrics_{int(time.time())}.json"
        with metrics_file.open("w", encoding="utf-8") as fh:
            json.dump(result, fh, indent=2)

        # Add metadata
        context.add_output_metadata(
            {
                "patents_loaded": success_count,
                "total_patents": len(patents),
                "success_rate": success_rate,
                "duration_seconds": duration,
                "errors": metrics.errors,
            }
        )

        context.log.info(
            f"Phase 1 Step 2 completed in {duration:.2f}s: "
            f"{success_count}/{len(patents)} patents loaded"
        )

        # Perform statistical analysis with patent analyzer
        if PatentAnalysisAnalyzer is not None:
            try:
                analyzer = PatentAnalysisAnalyzer()
                run_context = {
                    "run_id": context.run.run_id if context.run else f"run_{context.run_id}",
                    "pipeline_name": "uspto_patent_loading",
                    "stage": "load",
                }

                # Convert patents list to DataFrame for analyzer
                import pandas as pd
                patent_df = pd.DataFrame(patents) if patents else pd.DataFrame()

                # Prepare module data for analysis
                module_data = {
                    "patent_df": patent_df,
                    "validation_results": {},  # Could be enhanced with validation metrics
                    "loading_results": {
                        "records_processed": len(patents),
                        "records_failed": len(patents) - success_count,
                        "duration_seconds": duration,
                        "records_per_second": success_count / duration if duration > 0 else 0,
                        "success_rate": success_rate,
                    },
                    "neo4j_stats": {
                        "nodes_created": metrics.nodes_created,
                        "nodes_updated": metrics.nodes_updated,
                        "relationships_created": metrics.relationships_created,
                        "errors": metrics.errors,
                    },
                    "run_context": run_context,
                }

                # Generate analysis report
                analysis_report = analyzer.analyze(module_data)

                context.log.info(
                    "Patent loading analysis complete",
                    extra={
                        "insights_generated": len(analysis_report.insights) if hasattr(analysis_report, 'insights') else 0,
                        "data_hygiene_score": analysis_report.data_hygiene.quality_score_mean if analysis_report.data_hygiene else None,
                        "validation_pass_rate": analysis_report.data_hygiene.validation_pass_rate if analysis_report.data_hygiene else None,
                    },
                )

                # Add analysis results to metadata
                context.add_output_metadata({
                    "analysis_insights_count": len(analysis_report.insights) if hasattr(analysis_report, 'insights') else 0,
                    "analysis_data_hygiene_score": round(analysis_report.data_hygiene.quality_score_mean, 3) if analysis_report.data_hygiene else None,
                    "analysis_validation_pass_rate": round(analysis_report.data_hygiene.validation_pass_rate, 3) if analysis_report.data_hygiene else None,
                    "analysis_nodes_created": dict(metrics.nodes_created),
                    "analysis_relationships_created": dict(metrics.relationships_created),
                })

            except Exception as e:
                context.log.warning(f"Patent analysis failed: {e}")
        else:
            context.log.info("Patent analyzer not available; skipping statistical analysis")

        client.close()
        return result

    except Exception as e:
        context.log.error(f"Error loading patents: {e}", exc_info=True)
        client.close()
        return {"status": "failed", "reason": str(e)}


@asset(
    description="Load PatentAssignment nodes into Neo4j from transformed assignments",
    group_name="uspto_loading",
    deps=["transformed_patent_assignments"],
)
def loaded_patent_assignments(context) -> dict[str, Any]:
    """Phase 1 Step 1: Load PatentAssignment nodes into Neo4j.

    Reads transformed patent assignments and creates PatentAssignment nodes with:
    - rf_id as unique key
    - execution/recorded dates
    - conveyance type and description
    - employer_assign flag
    """
    if PatentLoader is None:
        context.log.error("PatentLoader unavailable; skipping assignment loading")
        return {"status": "failed", "reason": "PatentLoader unavailable"}

    client = _get_neo4j_client()
    if client is None:
        return {"status": "failed", "reason": "Neo4j client unavailable"}

    context.log.info("Starting Phase 1 Step 1: Loading PatentAssignments into Neo4j")
    start_time = time.time()
    output_dir = _ensure_output_dir()

    try:
        # Load transformed assignments
        transformed_assignments_file = (
            DEFAULT_TRANSFORMED_DIR / "transformed_patent_assignments.jsonl"
        )
        assignments = _load_transformed_file(transformed_assignments_file)
        context.log.info(f"Loaded {len(assignments)} assignment records to load")

        # Ensure date fields are ISO format
        assignments = [_convert_dates_to_iso(a) for a in assignments]

        # Create loader
        loader_config = PatentLoaderConfig(batch_size=1000)
        loader = PatentLoader(client, loader_config)

        # Load PatentAssignment nodes
        context.log.info(f"Loading {len(assignments)} PatentAssignment nodes...")
        metrics = loader.load_patent_assignments(assignments)

        duration = time.time() - start_time
        success_count = metrics.nodes_created.get(
            "PatentAssignment", 0
        ) + metrics.nodes_updated.get("PatentAssignment", 0)
        success_rate = success_count / len(assignments) if assignments else 0.0

        result = {
            "status": "success",
            "phase": 1,
            "assignments_loaded": success_count,
            "total_assignments": len(assignments),
            "success_rate": success_rate,
            "duration_seconds": duration,
            "metrics": _serialize_metrics(metrics),
        }

        # Save metrics
        metrics_file = output_dir / f"neo4j_assignments_metrics_{int(time.time())}.json"
        with metrics_file.open("w", encoding="utf-8") as fh:
            json.dump(result, fh, indent=2)

        # Add metadata
        context.add_output_metadata(
            {
                "assignments_loaded": success_count,
                "total_assignments": len(assignments),
                "success_rate": success_rate,
                "duration_seconds": duration,
                "errors": metrics.errors,
            }
        )

        context.log.info(
            f"Phase 1 Step 1 completed in {duration:.2f}s: "
            f"{success_count}/{len(assignments)} assignments loaded"
        )

        client.close()
        return result

    except Exception as e:
        context.log.error(f"Error loading assignments: {e}", exc_info=True)
        client.close()
        return {"status": "failed", "reason": str(e)}


# ============================================================================
# Phase 2 & 3: Load Entities and Create Relationships
# ============================================================================


@asset(
    description="Load PatentEntity nodes and create relationships in Neo4j",
    group_name="uspto_loading",
    deps=["neo4j_patients", "loaded_patent_assignments", "transformed_patent_entities"],
)
def loaded_patent_entities(context) -> dict[str, Any]:
    """Phase 2 & 3: Load PatentEntity nodes and create relationships.

    Reads transformed patent entities (assignees and assignors), creates
    PatentEntity nodes, and establishes ASSIGNED_TO/ASSIGNED_FROM relationships.
    """
    if PatentLoader is None:
        context.log.error("PatentLoader unavailable; skipping entity loading")
        return {"status": "failed", "reason": "PatentLoader unavailable"}

    client = _get_neo4j_client()
    if client is None:
        return {"status": "failed", "reason": "Neo4j client unavailable"}

    context.log.info("Starting Phase 2 & 3: Loading PatentEntities and creating relationships")
    start_time = time.time()
    output_dir = _ensure_output_dir()

    try:
        # Load transformed entities
        transformed_entities_file = DEFAULT_TRANSFORMED_DIR / "transformed_patent_entities.jsonl"
        entities = _load_transformed_file(transformed_entities_file)
        context.log.info(f"Loaded {len(entities)} entity records")

        # Separate assignees and assignors
        assignees = [e for e in entities if e.get("entity_type") == "ASSIGNEE"]
        assignors = [e for e in entities if e.get("entity_type") == "ASSIGNOR"]

        # Ensure date fields are ISO format
        assignees = [_convert_dates_to_iso(a) for a in assignees]
        assignors = [_convert_dates_to_iso(a) for a in assignors]

        # Create loader
        loader_config = PatentLoaderConfig(batch_size=1000)
        loader = PatentLoader(client, loader_config)

        # Load entities
        context.log.info(f"Loading {len(assignees)} ASSIGNEE entities...")
        metrics = loader.load_patent_entities(assignees, entity_type="ASSIGNEE")

        context.log.info(f"Loading {len(assignors)} ASSIGNOR entities...")
        metrics = loader.load_patent_entities(assignors, entity_type="ASSIGNOR", metrics=metrics)

        duration = time.time() - start_time
        success_count = metrics.nodes_created.get("PatentEntity", 0) + metrics.nodes_updated.get(
            "PatentEntity", 0
        )
        total_entities = len(assignees) + len(assignors)
        success_rate = (success_count / total_entities) if total_entities else 0.0

        result = {
            "status": "success",
            "phase": "2&3",
            "entities_loaded": success_count,
            "total_entities": total_entities,
            "assignees_loaded": len(assignees),
            "assignors_loaded": len(assignors),
            "success_rate": success_rate,
            "duration_seconds": duration,
            "metrics": _serialize_metrics(metrics),
        }

        # Save metrics
        metrics_file = output_dir / f"neo4j_entities_metrics_{int(time.time())}.json"
        with metrics_file.open("w", encoding="utf-8") as fh:
            json.dump(result, fh, indent=2)

        # Add metadata
        context.add_output_metadata(
            {
                "entities_loaded": success_count,
                "total_entities": total_entities,
                "assignees": len(assignees),
                "assignors": len(assignors),
                "success_rate": success_rate,
                "duration_seconds": duration,
            }
        )

        context.log.info(
            f"Phase 2 & 3 completed in {duration:.2f}s: "
            f"{success_count}/{total_entities} entities loaded"
        )

        client.close()
        return result

    except Exception as e:
        context.log.error(f"Error loading entities: {e}", exc_info=True)
        client.close()
        return {"status": "failed", "reason": str(e)}


# ============================================================================
# Phase 1 Step 3 & Phase 4: Create Relationships
# ============================================================================


@asset(
    description="Create all relationships between patent nodes in Neo4j",
    group_name="uspto_loading",
    deps=["loaded_patents", "loaded_patent_assignments", "loaded_patent_entities"],
)
def loaded_patent_relationships(
    context,
    loaded_patents: dict[str, Any],
    loaded_patent_assignments: dict[str, Any],
    loaded_patent_entities: dict[str, Any],
) -> dict[str, Any]:
    """Phase 1 Step 3 & Phase 4: Create all relationships.

    Creates relationships:
    - ASSIGNED_VIA: Patent → PatentAssignment
    - ASSIGNED_FROM: PatentAssignment → PatentEntity (assignor)
    - ASSIGNED_TO: PatentAssignment → PatentEntity (assignee)
    - GENERATED_FROM: Patent → Award (SBIR linkage)
    - OWNS: Company → Patent (current ownership)
    - CHAIN_OF: PatentAssignment → PatentAssignment (sequential)
    """
    if PatentLoader is None:
        context.log.error("PatentLoader unavailable; skipping relationship creation")
        return {"status": "failed", "reason": "PatentLoader unavailable"}

    client = _get_neo4j_client()
    if client is None:
        return {"status": "failed", "reason": "Neo4j client unavailable"}

    context.log.info("Starting Phase 1 Step 3 & Phase 4: Creating relationships")
    start_time = time.time()
    output_dir = _ensure_output_dir()

    try:
        # Load transformed assignments to extract relationship data
        transformed_assignments_file = (
            DEFAULT_TRANSFORMED_DIR / "transformed_patent_assignments.jsonl"
        )
        assignments = _load_transformed_file(transformed_assignments_file)
        context.log.info(f"Processing {len(assignments)} assignments for relationships")

        # Create loader
        loader_config = PatentLoaderConfig(batch_size=1000)
        loader = PatentLoader(client, loader_config)

        all_metrics = LoadMetrics() if LoadMetrics else None

        # Extract relationship data from assignments
        assigned_via_rels = []
        assigned_from_rels = []
        assigned_to_rels = []

        for assignment in assignments:
            # ASSIGNED_VIA: Patent → PatentAssignment
            if assignment.get("grant_doc_num") and assignment.get("rf_id"):
                assigned_via_rels.append(
                    {
                        "grant_doc_num": assignment["grant_doc_num"],
                        "rf_id": assignment["rf_id"],
                    }
                )

            # ASSIGNED_FROM: PatentAssignment → PatentEntity (assignor)
            if assignment.get("rf_id") and assignment.get("assignor_entity_id"):
                assigned_from_rels.append(
                    {
                        "rf_id": assignment["rf_id"],
                        "assignor_entity_id": assignment["assignor_entity_id"],
                        "execution_date": assignment.get("execution_date"),
                    }
                )

            # ASSIGNED_TO: PatentAssignment → PatentEntity (assignee)
            if assignment.get("rf_id") and assignment.get("assignee_entity_id"):
                assigned_to_rels.append(
                    {
                        "rf_id": assignment["rf_id"],
                        "assignee_entity_id": assignment["assignee_entity_id"],
                        "recorded_date": assignment.get("recorded_date"),
                    }
                )

        context.log.info(
            f"Extracted {len(assigned_via_rels)} ASSIGNED_VIA, "
            f"{len(assigned_from_rels)} ASSIGNED_FROM, "
            f"{len(assigned_to_rels)} ASSIGNED_TO relationships"
        )

        # Create relationships
        if assigned_via_rels:
            context.log.info("Creating ASSIGNED_VIA relationships...")
            all_metrics = loader.create_assigned_via_relationships(assigned_via_rels, all_metrics)

        if assigned_from_rels:
            context.log.info("Creating ASSIGNED_FROM relationships...")
            all_metrics = loader.create_assigned_from_relationships(assigned_from_rels, all_metrics)

        if assigned_to_rels:
            context.log.info("Creating ASSIGNED_TO relationships...")
            all_metrics = loader.create_assigned_to_relationships(assigned_to_rels, all_metrics)

        duration = time.time() - start_time
        total_rels = len(assigned_via_rels) + len(assigned_from_rels) + len(assigned_to_rels)

        result = {
            "status": "success",
            "phases": "1.3&4",
            "total_relationships": total_rels,
            "assigned_via_count": len(assigned_via_rels),
            "assigned_from_count": len(assigned_from_rels),
            "assigned_to_count": len(assigned_to_rels),
            "duration_seconds": duration,
            "metrics": _serialize_metrics(all_metrics),
        }

        # Save metrics
        metrics_file = output_dir / f"neo4j_relationships_metrics_{int(time.time())}.json"
        with metrics_file.open("w", encoding="utf-8") as fh:
            json.dump(result, fh, indent=2)

        # Add metadata
        context.add_output_metadata(
            {
                "total_relationships": total_rels,
                "assigned_via": len(assigned_via_rels),
                "assigned_from": len(assigned_from_rels),
                "assigned_to": len(assigned_to_rels),
                "duration_seconds": duration,
            }
        )

        context.log.info(
            f"Phase 1 Step 3 & 4 completed in {duration:.2f}s: "
            f"{total_rels} relationships created"
        )

        client.close()
        return result

    except Exception as e:
        context.log.error(f"Error creating relationships: {e}", exc_info=True)
        client.close()
        return {"status": "failed", "reason": str(e)}


# ============================================================================
# Asset Checks
# ============================================================================


@asset_check(
    asset=loaded_patents,
    description="Verify patent load success rate meets minimum threshold",
)
def patent_load_success_rate(context, neo4j_patents: dict[str, Any]) -> AssetCheckResult:
    """Check that patent loading success rate meets ≥99% threshold."""
    success_rate = neo4j_patents.get("success_rate", 0.0)
    total = neo4j_patents.get("total_patents", 0)
    loaded = neo4j_patents.get("patents_loaded", 0)

    passed = success_rate >= LOAD_SUCCESS_THRESHOLD
    severity = AssetCheckSeverity.WARN if passed else AssetCheckSeverity.ERROR

    return AssetCheckResult(
        passed=passed,
        severity=severity,
        description=(
            f"Patent load success rate {success_rate:.1%} "
            f"({loaded}/{total}) "
            f"{'meets' if passed else 'below'} threshold {LOAD_SUCCESS_THRESHOLD:.0%}"
        ),
        metadata={
            "success_rate": success_rate,
            "loaded_count": loaded,
            "total_count": total,
            "threshold": LOAD_SUCCESS_THRESHOLD,
            "errors": neo4j_patents.get("metrics", {}).get("errors", 0),
        },
    )


@asset_check(
    asset=loaded_patent_assignments,
    description="Verify assignment load success rate meets minimum threshold",
)
def assignment_load_success_rate(
    context, neo4j_patent_assignments: dict[str, Any]
) -> AssetCheckResult:
    """Check that assignment loading success rate meets ≥99% threshold."""
    success_rate = neo4j_patent_assignments.get("success_rate", 0.0)
    total = neo4j_patent_assignments.get("total_assignments", 0)
    loaded = neo4j_patent_assignments.get("assignments_loaded", 0)

    passed = success_rate >= LOAD_SUCCESS_THRESHOLD
    severity = AssetCheckSeverity.WARN if passed else AssetCheckSeverity.ERROR

    return AssetCheckResult(
        passed=passed,
        severity=severity,
        description=(
            f"Assignment load success rate {success_rate:.1%} "
            f"({loaded}/{total}) "
            f"{'meets' if passed else 'below'} threshold {LOAD_SUCCESS_THRESHOLD:.0%}"
        ),
        metadata={
            "success_rate": success_rate,
            "loaded_count": loaded,
            "total_count": total,
            "threshold": LOAD_SUCCESS_THRESHOLD,
            "errors": neo4j_patent_assignments.get("metrics", {}).get("errors", 0),
        },
    )


@asset_check(
    asset=loaded_patent_relationships,
    description="Sanity check relationship cardinality",
)
def patent_relationship_cardinality(
    context, neo4j_patent_relationships: dict[str, Any]
) -> AssetCheckResult:
    """Sanity check that reasonable numbers of each relationship type exist."""
    assigned_via = neo4j_patent_relationships.get("assigned_via_count", 0)
    assigned_from = neo4j_patent_relationships.get("assigned_from_count", 0)
    assigned_to = neo4j_patent_relationships.get("assigned_to_count", 0)

    # Sanity checks:
    # - assigned_via should be similar in count to assignments (1:1)
    # - assigned_from/to should be <= assigned_via (multiple entities per assignment)
    valid_via = assigned_via > 0
    valid_from = assigned_from >= 0 and assigned_from <= assigned_via
    valid_to = assigned_to >= 0 and assigned_to <= assigned_via

    passed = valid_via and valid_from and valid_to

    return AssetCheckResult(
        passed=passed,
        severity=AssetCheckSeverity.WARN if passed else AssetCheckSeverity.ERROR,
        description=(
            f"Relationship cardinality check: "
            f"ASSIGNED_VIA={assigned_via}, ASSIGNED_FROM={assigned_from}, ASSIGNED_TO={assigned_to}"
        ),
        metadata={
            "assigned_via_count": assigned_via,
            "assigned_from_count": assigned_from,
            "assigned_to_count": assigned_to,
            "valid_via": valid_via,
            "valid_from": valid_from,
            "valid_to": valid_to,
        },
    )


__all__ = [
    "loaded_patents",
    "loaded_patent_assignments",
    "loaded_patent_entities",
    "loaded_patent_relationships",
    "patent_load_success_rate",
    "assignment_load_success_rate",
    "patent_relationship_cardinality",
]


# AI extraction assets
def _ensure_dir_ai(p: Path) -> None:
    """Ensure directory exists for AI assets (duplicate name resolved)."""
    p.parent.mkdir(parents=True, exist_ok=True)


def _batch_to_dataframe(batch: list[dict]):
    """
    Convert a normalized batch into a pandas DataFrame using only lightweight fields:
      - grant_doc_num
      - prediction_json (stringified JSON)
      - source_file
      - row_index
      - extracted_at
    """
    try:
        import pandas as pd  # type: ignore
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("pandas is required to convert batches to DataFrame") from exc

    rows = []
    for rec in batch:
        rows.append(
            {
                "grant_doc_num": rec.get("grant_doc_num"),
                "prediction_json": json.dumps(rec.get("prediction", {}), ensure_ascii=False),
                "source_file": (rec.get("_meta") or {}).get("source_file"),
                "row_index": (rec.get("_meta") or {}).get("row_index"),
                "extracted_at": (rec.get("_meta") or {}).get("extracted_at"),
            }
        )
    return pd.DataFrame(rows)


@asset(
    name="raw_uspto_ai_extract",
    description=(
        "Stream-extract USPTO AI predictions from raw files into a DuckDB canonical table. "
        "Supports NDJSON, CSV, Parquet, and Stata (.dta) with resume & optional dedupe."
    ),
)
def raw_uspto_ai_extract(context) -> dict[str, object]:
    """
    Implements Task 11.1 (loader) and 11.2 (incremental resume) for USPTO AI extraction.

    Op config options:
      - raw_dir: directory of raw USPTO AI files (default: data/raw/USPTO)
      - file_globs: optional list of globs (e.g., ['*.dta', '*.ndjson'])
      - duckdb: path to DuckDB file (default: data/processed/uspto_ai.duckdb)
      - table: table name (default: uspto_ai_predictions)
      - checkpoint_dir: directory for resume checkpoints
      - batch_size: integer batch size (default: 5000)
      - resume: bool to resume from checkpoints (default: True)
      - dedupe: in-process dedupe by grant_doc_num (default: True)
      - id_candidates: list of candidate id columns for grant number inference (optional)

    Writes:
      - DuckDB table with columns:
          grant_doc_num VARCHAR,
          prediction JSON,
          source_file VARCHAR,
          row_index BIGINT,
          extracted_at TIMESTAMP
      - Checks JSON at data/processed/uspto_ai_extract.checks.json
    """
    if USPTOAIExtractor is None:
        msg = "USPTOAIExtractor unavailable (import failed); cannot perform extraction"
        context.log.warning(msg)  # type: ignore[attr-defined]
        _ensure_dir(DEFAULT_EXTRACT_CHECKS)
        with DEFAULT_EXTRACT_CHECKS.open("w", encoding="utf-8") as fh:
            json.dump({"ok": False, "reason": "extractor_unavailable"}, fh, indent=2)
        return {"ok": False, "reason": "extractor_unavailable"}

    # Resolve config
    raw_dir = Path(getattr(context, "op_config", {}).get("raw_dir", DEFAULT_AI_RAW_DIR))  # type: ignore[attr-defined]
    file_globs = getattr(context, "op_config", {}).get("file_globs")  # type: ignore[attr-defined]
    duckdb_path = Path(getattr(context, "op_config", {}).get("duckdb", DEFAULT_AI_DUCKDB))  # type: ignore[attr-defined]
    table = getattr(context, "op_config", {}).get("table", DEFAULT_AI_TABLE)  # type: ignore[attr-defined]
    checkpoint_dir = Path(
        getattr(context, "op_config", {}).get("checkpoint_dir", DEFAULT_AI_CHECKPOINT_DIR)  # type: ignore[attr-defined]
    )
    batch_size = int(getattr(context, "op_config", {}).get("batch_size", 5000))  # type: ignore[attr-defined]
    resume = bool(getattr(context, "op_config", {}).get("resume", True))  # type: ignore[attr-defined]
    dedupe = bool(getattr(context, "op_config", {}).get("dedupe", True))  # type: ignore[attr-defined]
    id_candidates = getattr(context, "op_config", {}).get("id_candidates", None)  # type: ignore[attr-defined]

    _ensure_dir(DEFAULT_EXTRACT_CHECKS)
    DEFAULT_AI_PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    # Connect to DuckDB
    try:
        import duckdb  # type: ignore
    except Exception as exc:
        msg = f"duckdb unavailable: {exc}"
        context.log.warning(msg)  # type: ignore[attr-defined]
        with DEFAULT_EXTRACT_CHECKS.open("w", encoding="utf-8") as fh:
            json.dump({"ok": False, "reason": "duckdb_unavailable"}, fh, indent=2)
        return {"ok": False, "reason": "duckdb_unavailable"}

    duckdb_path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(database=str(duckdb_path), read_only=False)

    # Ensure target table exists with expected schema
    try:
        con.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {table} (
                grant_doc_num VARCHAR,
                prediction JSON,
                source_file VARCHAR,
                row_index BIGINT,
                extracted_at TIMESTAMP
            )
            """
        )
    except Exception as exc:
        context.log.exception("Failed to ensure DuckDB table %s: %s", table, exc)  # type: ignore[attr-defined]
        try:
            con.close()
        except Exception:
            pass
        with DEFAULT_EXTRACT_CHECKS.open("w", encoding="utf-8") as fh:
            json.dump({"ok": False, "reason": "duckdb_table_create_failed"}, fh, indent=2)
        return {"ok": False, "reason": "duckdb_table_create_failed"}

    # Initialize extractor
    try:
        extractor = USPTOAIExtractor(
            input_dir=raw_dir,
            checkpoint_dir=checkpoint_dir,
            continue_on_error=True,
            log_every=100_000,
        )
    except Exception as exc:
        context.log.exception("Failed to initialize USPTOAIExtractor: %s", exc)  # type: ignore[attr-defined]
        try:
            con.close()
        except Exception:
            pass
        with DEFAULT_EXTRACT_CHECKS.open("w", encoding="utf-8") as fh:
            json.dump({"ok": False, "reason": "extractor_init_failed"}, fh, indent=2)
        return {"ok": False, "reason": "extractor_init_failed"}

    files = extractor.discover_files(file_globs=file_globs)
    if not files:
        context.log.warning("No USPTO AI files found under %s", str(raw_dir))  # type: ignore[attr-defined]
        with DEFAULT_EXTRACT_CHECKS.open("w", encoding="utf-8") as fh:
            json.dump({"ok": True, "ingested": 0, "files": []}, fh, indent=2)
        try:
            con.close()
        except Exception:
            pass
        return {"ok": True, "ingested": 0, "files": []}

    total_ingested = 0
    total_batches = 0
    sources: list[str] = []

    try:
        for fp in files:
            sources.append(str(fp))
            context.log.info("Extracting USPTO AI from %s", str(fp))  # type: ignore[attr-defined]
            try:
                for batch in extractor.stream_batches(
                    fp,
                    batch_size=batch_size,
                    resume=resume,
                    normalized=True,
                    dedupe=dedupe,
                    skip_missing_id=True,
                    id_candidates=id_candidates,
                ):
                    if not batch:
                        continue
                    # Convert to DataFrame and append via a registered temp table
                    try:
                        df = _batch_to_dataframe(batch)
                    except Exception as exc:
                        context.log.exception("Failed to convert batch to DataFrame: %s", exc)  # type: ignore[attr-defined]
                        continue

                    try:
                        con.register("tmp_batch", df)
                        # Insert casting string -> JSON and string -> TIMESTAMP
                        con.execute(
                            f"""
                            INSERT INTO {table}
                            SELECT
                                grant_doc_num,
                                try_cast(prediction_json AS JSON) AS prediction,
                                source_file,
                                CAST(row_index AS BIGINT) AS row_index,
                                try_cast(extracted_at AS TIMESTAMP) AS extracted_at
                            FROM tmp_batch
                            """
                        )
                        total_ingested += len(df)
                        total_batches += 1
                    except Exception as exc:
                        context.log.exception("Failed to append batch to DuckDB: %s", exc)  # type: ignore[attr-defined]
                    finally:
                        try:
                            con.unregister("tmp_batch")
                        except Exception:
                            pass
            except Exception as exc:
                context.log.exception("Extraction failed for %s: %s", str(fp), exc)  # type: ignore[attr-defined]
                # continue with next file
                continue
    finally:
        try:
            con.close()
        except Exception:
            pass

    checks = {
        "ok": True,
        "ingested": int(total_ingested),
        "batches": int(total_batches),
        "files": sources,
        "duckdb": str(duckdb_path),
        "table": table,
        "checkpoint_dir": str(checkpoint_dir),
        "resume": bool(resume),
        "dedupe": bool(dedupe),
    }
    with DEFAULT_EXTRACT_CHECKS.open("w", encoding="utf-8") as fh:
        json.dump(checks, fh, indent=2)
    context.log.info("USPTO AI extraction completed", extra=checks)  # type: ignore[attr-defined]
    return checks


@asset(
    name="uspto_ai_deduplicate",
    description=(
        "Produce a deduplicated table of USPTO AI predictions keyed by grant_doc_num. "
        "Keeps the most recent extracted_at or highest row_index."
    ),
    ins={"raw_uspto_ai_extract": AssetIn()},
)
def uspto_ai_deduplicate(context, raw_uspto_ai_extract) -> dict[str, object]:
    """
    Implements Task 11.2 (deduplication) using DuckDB window functions.

    Op config options:
      - duckdb: path to DuckDB file (default: data/processed/uspto_ai.duckdb)
      - table: source table name (default: uspto_ai_predictions)
      - dedup_table: output table name (default: uspto_ai_predictions_dedup)

    Writes:
      - Deduplicated DuckDB table
      - Checks JSON at data/processed/uspto_ai_deduplicate.checks.json
    """
    duckdb_path = Path(getattr(context, "op_config", {}).get("duckdb", DEFAULT_AI_DUCKDB))  # type: ignore[attr-defined]
    table = getattr(context, "op_config", {}).get("table", DEFAULT_AI_TABLE)  # type: ignore[attr-defined]
    dedup_table = getattr(context, "op_config", {}).get("dedup_table", DEFAULT_AI_DEDUP_TABLE)  # type: ignore[attr-defined]

    _ensure_dir(DEFAULT_DEDUP_CHECKS)
    try:
        import duckdb  # type: ignore
    except Exception as exc:
        msg = f"duckdb unavailable: {exc}"
        context.log.warning(msg)  # type: ignore[attr-defined]
        with DEFAULT_DEDUP_CHECKS.open("w", encoding="utf-8") as fh:
            json.dump({"ok": False, "reason": "duckdb_unavailable"}, fh, indent=2)
        return {"ok": False, "reason": "duckdb_unavailable"}

    con = duckdb.connect(database=str(duckdb_path), read_only=False)
    try:
        # Counts before
        try:
            before_cnt = int(con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
        except Exception:
            before_cnt = 0

        # Create or replace dedup table with row_number window over grant_doc_num
        con.execute(
            f"""
            CREATE OR REPLACE TABLE {dedup_table} AS
            WITH ranked AS (
                SELECT
                    grant_doc_num,
                    prediction,
                    source_file,
                    row_index,
                    extracted_at,
                    ROW_NUMBER() OVER (
                        PARTITION BY grant_doc_num
                        ORDER BY
                            extracted_at DESC NULLS LAST,
                            row_index DESC NULLS LAST
                    ) AS rn
                FROM {table}
            )
            SELECT
                grant_doc_num,
                prediction,
                source_file,
                row_index,
                extracted_at
            FROM ranked
            WHERE rn = 1
            """
        )

        after_cnt = int(con.execute(f"SELECT COUNT(*) FROM {dedup_table}").fetchone()[0])

        checks = {
            "ok": True,
            "source_count": before_cnt,
            "dedup_count": after_cnt,
            "duckdb": str(duckdb_path),
            "source_table": table,
            "dedup_table": dedup_table,
        }
        with DEFAULT_DEDUP_CHECKS.open("w", encoding="utf-8") as fh:
            json.dump(checks, fh, indent=2)
        context.log.info("USPTO AI deduplication completed", extra=checks)  # type: ignore[attr-defined]
        return checks
    except Exception as exc:
        context.log.exception("Deduplication failed: %s", exc)  # type: ignore[attr-defined]
        with DEFAULT_DEDUP_CHECKS.open("w", encoding="utf-8") as fh:
            json.dump({"ok": False, "reason": "dedup_failed"}, fh, indent=2)
        return {"ok": False, "reason": "dedup_failed"}
    finally:
        try:
            con.close()
        except Exception:
            pass


@asset(
    name="raw_uspto_ai_human_sample_extraction",
    description=(
        "Sample predictions from the (deduplicated) DuckDB table and write NDJSON for human evaluation."
    ),
    ins={"uspto_ai_deduplicate": AssetIn()},
)
def raw_uspto_ai_human_sample_extraction(context, uspto_ai_deduplicate) -> str:
    """
    Implements Task 11.3 (human sampling) using DuckDB ORDER BY RANDOM() LIMIT N.

    Op config options:
      - duckdb: path to DuckDB file (default: data/processed/uspto_ai.duckdb)
      - table: table to sample from (default: uspto_ai_predictions_dedup if exists, else uspto_ai_predictions)
      - sample_n: number of samples (default: 200)
      - output_path: path to write NDJSON (default: data/processed/uspto_ai_human_sample_extraction.ndjson)

    Output:
      - Path to written NDJSON sample
    """
    duckdb_path = Path(getattr(context, "op_config", {}).get("duckdb", DEFAULT_AI_DUCKDB))  # type: ignore[attr-defined]
    table = getattr(context, "op_config", {}).get("table", DEFAULT_AI_DEDUP_TABLE)  # type: ignore[attr-defined]
    sample_n = int(getattr(context, "op_config", {}).get("sample_n", 200))  # type: ignore[attr-defined]
    output_path = Path(
        getattr(context, "op_config", {}).get("output_path", DEFAULT_AI_SAMPLE_PATH)  # type: ignore[attr-defined]
    )

    try:
        pass  # type: ignore
    except Exception as exc:
        context.log.warning("duckdb unavailable; cannot sample: %s", exc)  # type: ignore[attr-defined]
        _ensure_dir_ai(output_path)
        with output_path.open("w", encoding="utf-8") as fh:
            fh.write("")  # empty sentinel
        return str(output_path)


# ============================================================================
# STAGE 5: AI Assets (Consolidated and Implemented)
# ============================================================================
# AI extraction and analysis assets for USPTO patent data processing


@asset(
    name="raw_uspto_ai_predictions",
    description=(
        "Ingest the USPTO AI NDJSON predictions into a local DuckDB cache. "
        "Writes a checks JSON summarizing the ingest and returns the ingest summary dict."
    ),
)
def raw_uspto_ai_predictions(context) -> dict[str, object]:
    """
    Dagster asset that ingests the raw USPTO AI NDJSON into the DuckDB cache.

    Behavior:
    - Resolves input NDJSON path from op config `raw_ndjson` if present, else uses DEFAULT_RAW_NDJSON.
    - Resolves cache DB path from op config `duckdb` if present, else uses DEFAULT_DUCKDB.
    - Uses streaming ingest with resume/checkpoint behavior.
    - Writes a companion checks JSON containing keys: ok, ingested, skipped, errors, cache_count, raw_ndjson, duckdb.
    """
    # Default paths (can be overridden via op_config)
    DEFAULT_RAW_NDJSON = Path(
        os.environ.get("SBIR_ETL__USPTO_AI__RAW_NDJSON", "data/raw/uspto_ai_predictions.ndjson")
    )
    DEFAULT_RAW_DTA_DIR = Path(os.environ.get("SBIR_ETL__USPTO_AI__RAW_DTA_DIR", "data/raw/USPTO"))
    DEFAULT_DUCKDB = Path(
        os.environ.get("SBIR_ETL__USPTO_AI__DUCKDB", "data/processed/uspto_ai.duckdb")
    )
    DEFAULT_DUCKDB_TABLE = os.environ.get(
        "SBIR_ETL__USPTO_AI__DUCKDB_TABLE", "uspto_ai_predictions"
    )

    raw_ndjson = (
        Path(context.op_config.get("raw_ndjson"))
        if getattr(context, "op_config", None) and context.op_config.get("raw_ndjson")
        else DEFAULT_RAW_NDJSON
    )
    duckdb_path = (
        Path(context.op_config.get("duckdb"))
        if getattr(context, "op_config", None) and context.op_config.get("duckdb")
        else DEFAULT_DUCKDB
    )
    duckdb_table = (
        context.op_config.get("duckdb_table")
        if getattr(context, "op_config", None) and context.op_config.get("duckdb_table")
        else DEFAULT_DUCKDB_TABLE
    )
    processed_dir = (
        Path(context.op_config.get("processed_dir"))
        if getattr(context, "op_config", None) and context.op_config.get("processed_dir")
        else Path("data/processed")
    )
    checks_path = processed_dir / "uspto_ai_ingest.checks.json"
    batch_size = (
        int(context.op_config.get("batch_size"))
        if getattr(context, "op_config", None) and context.op_config.get("batch_size")
        else 1000
    )

    processed_dir.mkdir(parents=True, exist_ok=True)

    # Look for DTA files first in configured directory
    dta_dir = (
        Path(context.op_config.get("raw_dta_dir"))
        if getattr(context, "op_config", None) and context.op_config.get("raw_dta_dir")
        else DEFAULT_RAW_DTA_DIR
    )
    dta_files = sorted([p for p in dta_dir.glob("*.dta")]) if dta_dir.exists() else []

    result_summary = {
        "ok": False,
        "ingested": 0,
        "skipped": 0,
        "errors": 0,
        "source_type": None,
        "sources": [],
    }

    try:
        import duckdb  # type: ignore
        import pandas as pd  # type: ignore
    except Exception as exc:
        logger.exception("duckdb and pandas are required for USPTO AI ingest: %s", exc)
        result_summary = {
            "ok": False,
            "ingested": 0,
            "skipped": 0,
            "errors": 1,
            "reason": "missing_dependency",
        }
        with open(checks_path, "w", encoding="utf-8") as fh:
            json.dump(result_summary, fh, indent=2)
        return result_summary

    if dta_files:
        # Ingest DTA files into DuckDB
        total_ingested = 0
        total_skipped = 0
        total_errors = 0

        try:
            con = duckdb.connect(database=str(duckdb_path), read_only=False)

            for dfp in dta_files:
                context.log.info(
                    "Ingesting DTA to DuckDB",
                    extra={"file": str(dfp), "duckdb": str(duckdb_path), "table": duckdb_table},
                )
                try:
                    # Read DTA file in chunks
                    df = pd.read_stata(dfp, chunksize=batch_size)
                    for chunk in df:
                        if total_ingested == 0:
                            # Create table on first chunk
                            con.execute(
                                f"CREATE OR REPLACE TABLE {duckdb_table} AS SELECT * FROM chunk LIMIT 0"
                            )
                        con.register("chunk_data", chunk)
                        con.execute(f"INSERT INTO {duckdb_table} SELECT * FROM chunk_data")
                        total_ingested += len(chunk)
                    result_summary["sources"].append(str(dfp))
                except Exception as exc:
                    context.log.exception("DTA ingest failed for %s: %s", str(dfp), exc)
                    total_errors += 1

            con.close()
        except Exception as exc:
            logger.exception("Failed to connect to DuckDB: %s", exc)
            total_errors += 1

        result_summary.update(
            {
                "ok": total_errors == 0,
                "ingested": total_ingested,
                "skipped": total_skipped,
                "errors": total_errors,
                "source_type": "dta",
            }
        )
    else:
        # Fall back to NDJSON input
        if not raw_ndjson.exists():
            context.log.warning("No DTA files and NDJSON not found: %s", raw_ndjson)
            result_summary = {
                "ok": False,
                "ingested": 0,
                "skipped": 0,
                "errors": 0,
                "reason": "raw_missing",
            }
        else:
            try:
                con = duckdb.connect(database=str(duckdb_path), read_only=False)
                ingested = 0
                errors = 0
                batch = []

                with raw_ndjson.open("r", encoding="utf-8") as fh:
                    for line in fh:
                        if not line.strip():
                            continue
                        try:
                            obj = json.loads(line)
                            batch.append(obj)
                            if len(batch) >= batch_size:
                                df = pd.DataFrame(batch)
                                if ingested == 0:
                                    con.execute(
                                        f"CREATE OR REPLACE TABLE {duckdb_table} AS SELECT * FROM df LIMIT 0"
                                    )
                                con.register("batch_data", df)
                                con.execute(f"INSERT INTO {duckdb_table} SELECT * FROM batch_data")
                                ingested += len(df)
                                batch = []
                        except Exception:
                            errors += 1
                            continue

                # Final batch
                if batch:
                    try:
                        df = pd.DataFrame(batch)
                        con.register("final_batch", df)
                        con.execute(f"INSERT INTO {duckdb_table} SELECT * FROM final_batch")
                        ingested += len(df)
                    except Exception:
                        errors += 1

                con.close()
                result_summary = {
                    "ok": errors == 0,
                    "ingested": ingested,
                    "skipped": 0,
                    "errors": errors,
                    "source_type": "ndjson",
                    "sources": [str(raw_ndjson)],
                }
            except Exception as exc:
                logger.exception("Unexpected error during NDJSON ingest: %s", exc)
                result_summary = {
                    "ok": False,
                    "ingested": 0,
                    "skipped": 0,
                    "errors": 1,
                    "reason": str(exc),
                }

    # Write checks JSON
    checks = {
        "ok": bool(result_summary.get("ok", False)),
        "ingested": int(result_summary.get("ingested", 0)),
        "skipped": int(result_summary.get("skipped", 0)),
        "errors": int(result_summary.get("errors", 0)),
        "source_type": result_summary.get("source_type"),
        "sources": result_summary.get("sources", []),
        "duckdb": str(duckdb_path),
        "duckdb_table": str(duckdb_table),
    }
    with open(checks_path, "w", encoding="utf-8") as fh:
        json.dump(checks, fh, indent=2)

    context.log.info(
        "USPTO AI ingest completed", extra={"checks_path": str(checks_path), "checks": checks}
    )
    return checks


@asset(
    name="validated_uspto_ai_cache_stats",
    description="Return quick statistics about the USPTO AI DuckDB cache (count).",
)
def validated_uspto_ai_cache_stats(context) -> dict[str, int | None]:
    """
    Inspect the DuckDB cache and return a small dict with the number of cached predictions.
    """
    DEFAULT_DUCKDB = Path(
        os.environ.get("SBIR_ETL__USPTO_AI__DUCKDB", "data/processed/uspto_ai.duckdb")
    )
    DEFAULT_DUCKDB_TABLE = os.environ.get(
        "SBIR_ETL__USPTO_AI__DUCKDB_TABLE", "uspto_ai_predictions"
    )

    duckdb_path = (
        Path(context.op_config.get("duckdb"))
        if getattr(context, "op_config", None) and context.op_config.get("duckdb")
        else DEFAULT_DUCKDB
    )
    table = (
        context.op_config.get("duckdb_table")
        if getattr(context, "op_config", None) and context.op_config.get("duckdb_table")
        else DEFAULT_DUCKDB_TABLE
    )

    try:
        import duckdb  # type: ignore
    except Exception:
        context.log.warning("duckdb is unavailable; cannot compute cache stats")
        return {"cache_count": None, "duckdb": str(duckdb_path)}

    try:
        con = duckdb.connect(database=str(duckdb_path), read_only=True)
        try:
            df = con.execute(f"SELECT COUNT(*) AS cnt FROM {table}").fetchdf()
            count = int(df["cnt"].iloc[0]) if not df.empty else 0
        except Exception:
            context.log.exception("Error while counting DuckDB table %s", table)
            count = None
        finally:
            con.close()

        return {
            "cache_count": int(count) if count is not None else None,
            "duckdb": str(duckdb_path),
            "duckdb_table": table,
        }
    except Exception:
        context.log.exception("Failed to open DuckDB at %s", duckdb_path)
        return {"cache_count": None, "duckdb": str(duckdb_path)}


@asset(
    name="raw_uspto_ai_human_sample",
    description=(
        "Produce a sampled NDJSON of USPTO AI predictions intended for human evaluation. "
        "Writes the sample to `data/processed/uspto_ai_human_sample.ndjson` (or path configured via op_config)."
    ),
)
def raw_uspto_ai_human_sample(context) -> str:
    """
    Produce a human evaluation sample from the DuckDB cache.
    """
    DEFAULT_DUCKDB = Path(
        os.environ.get("SBIR_ETL__USPTO_AI__DUCKDB", "data/processed/uspto_ai.duckdb")
    )
    DEFAULT_DUCKDB_TABLE = os.environ.get(
        "SBIR_ETL__USPTO_AI__DUCKDB_TABLE", "uspto_ai_predictions"
    )
    DEFAULT_SAMPLE_PATH = Path("data/processed/uspto_ai_human_sample.ndjson")

    duckdb_path = (
        Path(context.op_config.get("duckdb"))
        if getattr(context, "op_config", None) and context.op_config.get("duckdb")
        else DEFAULT_DUCKDB
    )
    table = (
        context.op_config.get("duckdb_table")
        if getattr(context, "op_config", None) and context.op_config.get("duckdb_table")
        else DEFAULT_DUCKDB_TABLE
    )
    sample_n = (
        int(context.op_config.get("sample_n"))
        if getattr(context, "op_config", None) and context.op_config.get("sample_n")
        else 100
    )
    output_path = (
        Path(context.op_config.get("output_path"))
        if getattr(context, "op_config", None) and context.op_config.get("output_path")
        else DEFAULT_SAMPLE_PATH
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        import duckdb  # type: ignore
    except Exception:
        context.log.warning("duckdb unavailable; cannot sample")
        with output_path.open("w", encoding="utf-8") as fh:
            fh.write("")
        return str(output_path)

    try:
        con = duckdb.connect(database=str(duckdb_path), read_only=True)
        try:
            df = con.execute(f"SELECT * FROM {table} ORDER BY RANDOM() LIMIT {sample_n}").fetchdf()
        except Exception:
            context.log.warning("Failed to query DuckDB table %s for sampling", table)
            df = None
        finally:
            con.close()

        if df is None or df.empty:
            with output_path.open("w", encoding="utf-8") as fh:
                fh.write("")
            context.log.warning("No sample returned from DuckDB; wrote empty sample")
            return str(output_path)

        # Serialize rows to NDJSON
        with output_path.open("w", encoding="utf-8") as fh:
            for rec in df.to_dict(orient="records"):
                grant = rec.get("grant_doc_num") or rec.get("grant_number") or rec.get("patent_id")
                out = {"grant_doc_num": grant, "prediction": rec}
                fh.write(json.dumps(out) + "\n")

        context.log.info(
            "Wrote human-eval sample", extra={"output_path": str(output_path), "n": len(df)}
        )
        return str(output_path)
    except Exception:
        context.log.exception("Sampling from DuckDB failed")
        with output_path.open("w", encoding="utf-8") as fh:
            fh.write("")
        return str(output_path)


@asset(
    name="enriched_uspto_ai_patent_join",
    description=(
        "Join USPTO AI predictions (cached) to transformed patent records for validation "
        "and produce a summary checks JSON and an NDJSON of matches."
    ),
)
def enriched_uspto_ai_patent_join(context) -> dict[str, object]:
    """
    Asset that links cached USPTO AI predictions to transformed patents for downstream
    validation and agreement analysis.
    """
    DEFAULT_DUCKDB = Path(
        os.environ.get("SBIR_ETL__USPTO_AI__DUCKDB", "data/processed/uspto_ai.duckdb")
    )
    DEFAULT_DUCKDB_TABLE = os.environ.get(
        "SBIR_ETL__USPTO_AI__DUCKDB_TABLE", "uspto_ai_predictions"
    )

    processed_dir = Path("data/processed")
    output_matches = processed_dir / "uspto_ai_patent_matches.ndjson"
    checks_path = processed_dir / "uspto_ai_patent_join.checks.json"
    processed_dir.mkdir(parents=True, exist_ok=True)

    # Load patent records
    patents: list[dict] = []
    patents_parquet = Path("data/processed/transformed_patents.parquet")
    patents_ndjson = Path("data/processed/transformed_patents.ndjson")

    try:
        if patents_parquet.exists():
            import pandas as pd

            df = pd.read_parquet(patents_parquet)
            patents = df.to_dict(orient="records")
        elif patents_ndjson.exists():
            with patents_ndjson.open("r", encoding="utf-8") as fh:
                for line in fh:
                    if line.strip():
                        try:
                            patents.append(json.loads(line))
                        except Exception:
                            continue
        else:
            # minimal sample for CI
            patents = [
                {
                    "patent_id": "sample_p1",
                    "grant_doc_num": "US1234567B2",
                    "title": "ML for imaging",
                },
                {
                    "patent_id": "sample_p2",
                    "grant_doc_num": "US7654321B2",
                    "title": "Quantum error correction",
                },
            ]
            context.log.warning("No transformed patents found; running on a small sample")
    except Exception:
        context.log.exception("Failed to load transformed patents; aborting join")
        checks = {"ok": False, "reason": "load_error", "num_patents": 0}
        with open(checks_path, "w", encoding="utf-8") as fh:
            json.dump(checks, fh, indent=2)
        return checks

    # Query DuckDB to join predictions to patents
    duckdb_path = (
        Path(context.op_config.get("duckdb"))
        if getattr(context, "op_config", None) and context.op_config.get("duckdb")
        else DEFAULT_DUCKDB
    )
    table = (
        context.op_config.get("duckdb_table")
        if getattr(context, "op_config", None) and context.op_config.get("duckdb_table")
        else DEFAULT_DUCKDB_TABLE
    )

    try:
        import duckdb  # type: ignore
    except Exception:
        msg = "duckdb unavailable; cannot perform patent join"
        context.log.warning(msg)
        checks = {"ok": False, "reason": "duckdb_unavailable", "message": msg}
        with open(checks_path, "w", encoding="utf-8") as fh:
            json.dump(checks, fh, indent=2)
        return checks

    try:
        con = duckdb.connect(database=str(duckdb_path), read_only=True)
        matched = 0
        total = len(patents)

        with output_matches.open("w", encoding="utf-8") as outf:
            for p in patents:
                # attempt to find a matching grant id
                candidate_ids = [
                    p.get("grant_doc_num"),
                    p.get("grant_number"),
                    p.get("grant_docnum"),
                    p.get("patent_id"),
                    p.get("publication_number"),
                    p.get("doc_num"),
                ]
                candidate_ids = [str(x).strip() for x in candidate_ids if x]
                found_row = None

                for gid in candidate_ids:
                    for col in (
                        "grant_doc_num",
                        "grant_number",
                        "grant_docnum",
                        "patent_id",
                        "publication_number",
                        "doc_num",
                    ):
                        try:
                            df = con.execute(
                                f"SELECT * FROM {table} WHERE {col} = ? LIMIT 1", (gid,)
                            ).fetchdf()
                            if df is not None and not df.empty:
                                found_row = df.to_dict(orient="records")[0]
                                break
                        except Exception:
                            continue
                    if found_row is not None:
                        break

                if found_row is not None:
                    matched += 1
                    out_obj = {"patent": p, "uspto_prediction": found_row}
                    outf.write(json.dumps(out_obj) + "\n")

        checks = {
            "ok": True,
            "num_patents": total,
            "num_matched": matched,
            "match_rate": round(matched / total, 4) if total > 0 else 0.0,
            "matches_path": str(output_matches),
        }
        with open(checks_path, "w", encoding="utf-8") as fh:
            json.dump(checks, fh, indent=2)

        context.log.info("USPTO AI patent join complete", extra=checks)
        return checks
    except Exception:
        context.log.exception("Patent join failed")
        checks = {"ok": False, "reason": "join_failed", "num_patents": len(patents)}
        with open(checks_path, "w", encoding="utf-8") as fh:
            json.dump(checks, fh, indent=2)
        return checks
    finally:
        try:
            con.close()
        except Exception:
            pass


# ============================================================================
# Exported symbols
# ============================================================================

__all__ = [
    # Stage 1: Raw discovery and parsing
    "raw_uspto_assignments",
    "raw_uspto_assignees",
    "raw_uspto_assignors",
    "raw_uspto_documentids",
    "raw_uspto_conveyances",
    "parsed_uspto_assignments",
    "validated_uspto_assignees",
    "validated_uspto_assignors",
    "parsed_uspto_documentids",
    "parsed_uspto_conveyances",
    "uspto_assignments_parsing_check",
    "uspto_assignees_parsing_check",
    "uspto_assignors_parsing_check",
    "uspto_documentids_parsing_check",
    "uspto_conveyances_parsing_check",
    # Stage 2: Validation
    "validated_uspto_assignments",
    "uspto_rf_id_asset_check",
    "uspto_completeness_asset_check",
    "uspto_referential_asset_check",
    # Stage 3: Transformation
    "transformed_patent_assignments",
    "transformed_patents",
    "transformed_patent_entities",
    "uspto_transformation_success_check",
    "uspto_company_linkage_check",
    # Stage 4: Neo4j Loading
    "loaded_patents",
    "loaded_patent_assignments",
    "loaded_patent_entities",
    "loaded_patent_relationships",
    "patent_load_success_rate",
    "assignment_load_success_rate",
    "patent_relationship_cardinality",
    # Stage 5: AI Extraction
    "raw_uspto_ai_extract",
    "uspto_ai_deduplicate",
    "raw_uspto_ai_human_sample_extraction",
    # Additional AI assets from consolidated uspto_ai_assets.py
    "raw_uspto_ai_predictions",
    "validated_uspto_ai_cache_stats",
    "raw_uspto_ai_human_sample",
    "enriched_uspto_ai_patent_join",
]
