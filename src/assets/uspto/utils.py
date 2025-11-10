"""Shared utilities for USPTO assets.

This module provides:
- Dagster import re-exports
- Helper functions for file discovery, parsing, validation
- Data serialization utilities
- Path management utilities
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from dagster import AssetCheckResult, AssetCheckSeverity, AssetIn, MetadataValue, asset_check
from loguru import logger

from ..exceptions import DependencyError

# Import parsed/validated assets needed for asset_check decorators
# These need to be imported before being referenced in asset_check() calls
from .parsing import (
    parsed_uspto_assignments,
    parsed_uspto_conveyances,
    parsed_uspto_documentids,
    validated_uspto_assignees,
    validated_uspto_assignors,
)


# Statistical reporting imports
try:  # pragma: no cover - defensive import
    from ..models.quality import ModuleReport  # type: ignore
    from ..utils.reporting.analyzers.patent_analyzer import PatentAnalysisAnalyzer  # type: ignore
except Exception:
    ModuleReport = None
    PatentAnalysisAnalyzer = None

# ============================================================================
# Optional imports - degrade gracefully when dependencies are unavailable
# ============================================================================

# USPTO extractor and transformers
try:  # pragma: no cover - defensive import
    from ..extractors.uspto_extractor import USPTOExtractor  # type: ignore
except Exception:
    USPTOExtractor = None

try:  # pragma: no cover - defensive import
    from ..extractors.uspto_ai_extractor import USPTOAIExtractor  # type: ignore
except Exception:
    USPTOAIExtractor = None

# Validators
try:  # pragma: no cover - defensive import
    from ..quality import USPTODataQualityValidator, USPTOValidationConfig  # type: ignore
except Exception:
    validate_rf_id_uniqueness = None
    USPTODataQualityValidator = None
    USPTOValidationConfig = None

# Transformers
try:  # pragma: no cover - defensive import
    from ..transformers.patent_transformer import PatentAssignmentTransformer  # type: ignore
except Exception:
    PatentAssignmentTransformer = None

# Models
try:  # pragma: no cover - defensive import
    from ..models.uspto_models import PatentAssignment  # type: ignore
except Exception:
    PatentAssignment = None

# Neo4j loaders
try:  # pragma: no cover - defensive import
    from ..loaders.neo4j import LoadMetrics, Neo4jClient, Neo4jConfig  # type: ignore
except Exception:
    Neo4jClient = None
    Neo4jConfig = None
    LoadMetrics = None

try:  # pragma: no cover - defensive import
    from ..loaders.neo4j import PatentLoader, PatentLoaderConfig
except Exception:
    PatentLoader = None
    PatentLoaderConfig = None

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




def _get_input_dir(context: Any) -> Path:
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


def _make_parsing_check(
    table_asset_name: str,
    parsed_asset_name: str,
):
    """
    Factory to produce an asset_check function that inspects the parsed asset summaries
    and fails the check if any file reported parsing failures.
    """

    def _check(context: Any, parsed: dict[str, dict], raw_files: list[str]) -> AssetCheckResult:
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


def _build_validator_config(context: Any) -> USPTOValidationConfig:
    """Build validation config from context op_config with defaults."""
    if USPTOValidationConfig is None:
        return None
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
        return model.model_dump(mode="json")
    if isinstance(model, dict):
        return model
    return dict(model.__dict__)


def _iter_small_sample(store: list[Any], new_item, limit: int) -> None:
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


def _resolve_output_paths(context: Any, prefix: str) -> tuple[Path, Path]:
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




def _ensure_output_dir() -> Path:
    """Ensure output directory exists."""
    DEFAULT_NEO4J_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return DEFAULT_NEO4J_OUTPUT_DIR


def _load_transformed_file(file_path: Path) -> list[dict[str, Any]]:
    """Load JSONL file of transformed records."""
    records: list[Any] = []
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
        import pandas as pd
    except Exception as exc:  # pragma: no cover
        raise DependencyError(
            "pandas is required to convert batches to DataFrame",
            dependency_name="pandas",
            component="assets.uspto_assets",
            operation="batch_to_dataframe",
            details={"install_command": "poetry install"},
            cause=exc,
        ) from exc

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


