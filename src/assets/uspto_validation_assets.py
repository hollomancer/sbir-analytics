"""Dagster assets for USPTO patent assignment data validation."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List

from dagster import (
    AssetCheckResult,
    AssetCheckSeverity,
    AssetExecutionContext,
    AssetIn,
    MetadataValue,
    asset,
    asset_check,
)

from ..quality import USPTODataQualityValidator, USPTOValidationConfig

DEFAULT_FAIL_DIR = Path(
    os.environ.get("SBIR_ETL__USPTO__VALIDATION_FAIL_DIR", "data/validated/fail")
)
DEFAULT_REPORT_DIR = Path(
    os.environ.get("SBIR_ETL__USPTO__VALIDATION_REPORT_DIR", "reports/uspto-validation")
)


def _build_validator_config(context: "AssetExecutionContext") -> USPTOValidationConfig:
    cfg = getattr(context, "op_config", {}) or {}

    return USPTOValidationConfig(
        chunk_size=int(cfg.get("chunk_size", 10000)),
        sample_limit=int(cfg.get("sample_limit", 20)),
        completeness_threshold=float(cfg.get("completeness_threshold", 0.95)),
        min_year=int(cfg.get("min_year", 1790)),
        max_year=int(cfg.get("max_year", 2100)),
        fail_output_dir=Path(cfg.get("fail_output_dir", DEFAULT_FAIL_DIR)),
        report_output_dir=Path(cfg.get("report_output_dir", DEFAULT_REPORT_DIR)),
    )


def _extract_table_results(report: Dict[str, Any], table: str) -> Dict[str, Dict[str, Any]]:
    return (report or {}).get("tables", {}).get(table, {}) or {}


@asset(
    description="Validate USPTO assignment-related tables for data quality and integrity",
    group_name="uspto",
    ins={
        "assignment_files": AssetIn("raw_uspto_assignments"),
        "assignee_files": AssetIn("raw_uspto_assignees"),
        "assignor_files": AssetIn("raw_uspto_assignors"),
        "documentid_files": AssetIn("raw_uspto_documentids"),
        "conveyance_files": AssetIn("raw_uspto_conveyances"),
    },
)
def validated_uspto_assignments(
    context: "AssetExecutionContext",
    assignment_files: List[str],
    assignee_files: List[str],
    assignor_files: List[str],
    documentid_files: List[str],
    conveyance_files: List[str],
) -> Dict[str, Any]:
    """Run the USPTO data quality validator across all discovered tables."""

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
    context: "AssetExecutionContext",
    validation_report: Dict[str, Any],
    assignment_files: List[str],
) -> AssetCheckResult:
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

    failed_files: List[Dict[str, Any]] = []
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
    context: "AssetExecutionContext",
    validation_report: Dict[str, Any],
) -> AssetCheckResult:
    tables = (validation_report or {}).get("tables", {})
    failures: List[Dict[str, Any]] = []

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
    context: "AssetExecutionContext",
    validation_report: Dict[str, Any],
) -> AssetCheckResult:
    tables = (validation_report or {}).get("tables", {})
    failures: List[Dict[str, Any]] = []

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


__all__ = [
    "validated_uspto_assignments",
    "uspto_rf_id_asset_check",
    "uspto_completeness_asset_check",
    "uspto_referential_asset_check",
]
