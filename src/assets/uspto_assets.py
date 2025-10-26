"""
Dagster assets for USPTO extraction & validation.

Provides:
- raw_uspto_assignments: discovers USPTO raw files under a configured directory.
- validated_uspto_assignments: runs rf_id uniqueness validator against discovered files.
- uspto_rf_id_asset_check: an asset_check that fails if any file has duplicate rf_id values.

This module uses the streaming validators implemented in `sbir-etl/src/quality/uspto_validators.py`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

from dagster import (
    AssetExecutionContext,
    AssetIn,
    AssetKey,
    AssetCheckResult,
    AssetCheckSeverity,
    MetadataValue,
    asset,
    asset_check,
)
from loguru import logger

# Local validator exports (package-level quality helpers)
from ..quality import validate_rf_id_uniqueness  # type: ignore

# Default directory where raw USPTO files are expected during pipeline runs
DEFAULT_USPTO_RAW_DIR = Path("data/raw/uspto")


@asset(
    description="Discover raw USPTO assignment files for ingestion/validation",
    group_name="uspto",
)
def raw_uspto_assignments(context: AssetExecutionContext) -> List[str]:
    """
    Discover supported USPTO files (.csv, .dta, .parquet) under the configured raw directory.

    Returns:
        List[str]: paths (as strings) to discovered raw USPTO files.
    """
    # Allow optional override via context resources or config - fall back to DEFAULT_USPTO_RAW_DIR
    input_dir = Path(context.op_config["input_dir"]) if context.op_config else DEFAULT_USPTO_RAW_DIR
    if not isinstance(input_dir, Path):
        input_dir = Path(input_dir)

    context.log.info("Discovering USPTO raw files", extra={"input_dir": str(input_dir)})
    logger.info("Discovering USPTO raw files in %s", input_dir)

    if not input_dir.exists():
        context.log.warning(
            "USPTO raw input directory does not exist", extra={"input_dir": str(input_dir)}
        )
        return []

    supported_exts = [".csv", ".dta", ".parquet"]
    found: List[str] = []
    for ext in supported_exts:
        for p in sorted(input_dir.rglob(f"*{ext}")):
            found.append(str(p))

    context.log.info(f"Found {len(found)} USPTO files", extra={"file_count": len(found)})
    logger.debug("USPTO files discovered: %s", found)

    # Provide metadata for Dagster UI
    try:
        context.log.info("usp_to_discovery", extra={"files": found})
    except Exception:
        # Some execution contexts may not accept complex `extra` payloads; swallow safely
        logger.debug("usp_to_discovery (fallback log): %s", found)

    return found


@asset(
    description="Validate USPTO assignment files (rf_id uniqueness and basic checks)",
    group_name="uspto",
    ins={"raw_files": AssetIn("raw_uspto_assignments")},
)
def validated_uspto_assignments(
    context: AssetExecutionContext, raw_files: List[str]
) -> Dict[str, dict]:
    """
    Run file-level validators (starting with rf_id uniqueness) for each discovered USPTO file.

    Returns:
        Dict[file_path -> validator_summary]
    """
    results: Dict[str, dict] = {}

    if not raw_files:
        context.log.info("No USPTO raw files to validate")
        return results

    for fp in raw_files:
        context.log.info("Validating rf_id uniqueness for file", extra={"file": fp})
        logger.debug("Running validate_rf_id_uniqueness for %s", fp)
        try:
            validation = validate_rf_id_uniqueness(fp, chunk_size=10000, sample_limit=20)
            # `validation` is a ValidatorResult dataclass; convert to serializable dict for metadata
            summary = {
                "success": bool(validation.success),
                "summary": validation.summary if hasattr(validation, "summary") else {},
                "details": validation.details if hasattr(validation, "details") else {},
            }
            results[fp] = summary
            context.log.info(
                "Validation completed",
                extra={
                    "file": fp,
                    "success": summary["success"],
                    "total_rows": summary["summary"].get("total_rows"),
                    "duplicate_count": summary["summary"].get("duplicate_rf_id_values"),
                },
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("Validation failed for file %s: %s", fp, exc)
            context.log.error("Validation error", extra={"file": fp, "error": str(exc)})
            results[fp] = {"success": False, "summary": {"error": str(exc)}, "details": {}}

    # Attach summary metadata for Dagster UI
    total_files = len(results)
    files_failed = [f for f, r in results.items() if not r.get("success", False)]
    metadata = {
        "total_files_validated": total_files,
        "files_failed_count": len(files_failed),
        "files_failed": MetadataValue.json(files_failed),
        "per_file_summary": MetadataValue.json(results),
    }

    try:
        context.log.info("USPTO validation pass complete", extra=metadata)
    except Exception:
        logger.debug("USPTO validation metadata: %s", json.dumps(metadata))

    return results


@asset_check(
    asset=validated_uspto_assignments,
    description="Asset check that verifies rf_id uniqueness across USPTO assignment files",
    additional_ins={"raw_files": AssetIn("raw_uspto_assignments")},
)
def uspto_rf_id_asset_check(
    context: AssetExecutionContext,
    validated_uspto_assignments: Dict[str, dict],
    raw_files: List[str],
) -> AssetCheckResult:
    """
    Asset check wraps rf_id uniqueness validator results and fails if any file has duplicates.

    This check will mark the asset as failed (ERROR severity) when any file's validator reports duplicates.
    """
    total_files = len(validated_uspto_assignments)
    failed_files = []
    total_duplicates = 0

    for fp, res in validated_uspto_assignments.items():
        if not res.get("success", False):
            failed_files.append(fp)
            # attempt to read duplicate count from summary
            dup_count = res.get("summary", {}).get("duplicate_rf_id_values")
            if isinstance(dup_count, int):
                total_duplicates += dup_count
            else:
                # if validation failed due to error, count as unknown
                total_duplicates += 1

    passed = len(failed_files) == 0

    if passed:
        severity = AssetCheckSeverity.WARN
        description = f"✓ USPTO rf_id uniqueness check passed for {total_files} files"
    else:
        severity = AssetCheckSeverity.ERROR
        description = (
            f"✗ USPTO rf_id uniqueness check failed for {len(failed_files)}/{total_files} files"
        )

    metadata = {
        "total_files_checked": total_files,
        "failed_files_count": len(failed_files),
        "total_duplicate_values_found": total_duplicates,
        "failed_files_sample": MetadataValue.json(failed_files[:10]),
    }

    context.log.info("US PTO asset check result", extra=metadata)
    logger.debug("uspto_rf_id_asset_check metadata: %s", metadata)

    return AssetCheckResult(
        passed=passed, severity=severity, description=description, metadata=metadata
    )
