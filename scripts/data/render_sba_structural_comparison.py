#!/usr/bin/env python3
"""Render the validated SBA structural comparison for public review.

Epistemic tier: evidence. This study-owned renderer accepts only the frozen
FY2020-FY2022 count-comparison contract. It does not classify differences,
apply tolerances, compare dollars, or authorize citation.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from sbir_etl.quality.study_manifest import EvidenceStatus, StudyManifest, load_study_manifest
from sbir_etl.utils.data.file_io import file_sha256


EPISTEMIC_TIER = "evidence"
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
STUDY_ID = "sba-annual-report-structural-comparison"
STUDY_DIRECTORY = Path("studies") / STUDY_ID
COMPARISON_REFERENCE = (STUDY_DIRECTORY / "results/count-comparison.csv").as_posix()
STUDY_MANIFEST_REFERENCE = (STUDY_DIRECTORY / "study.yaml").as_posix()
SOURCE_MANIFEST_REFERENCE = (STUDY_DIRECTORY / "source-manifest.json").as_posix()
RUN_DIAGNOSTICS_REFERENCE = (
    STUDY_DIRECTORY / "validation/confirmatory/run-diagnostics.json"
).as_posix()
SIDECAR_REFERENCE = (STUDY_DIRECTORY / "release/public-result.json").as_posix()
MARKDOWN_REFERENCE = "docs/public/sba-structural-comparison.md"
RELEASE_STATUS = "Validated, not citable"
PREPARED_FOR = (
    "SBIR program managers and policy analysts in Treasury, OMB, JCT, "
    "and state economic-development offices"
)
REPRODUCTION_COMMAND = "make reproduce-sba-structural"
RENDER_COMMAND = "uv run python scripts/data/render_sba_structural_comparison.py"

COMPARISON_COLUMNS = (
    "report_year",
    "table_number",
    "jurisdiction",
    "program",
    "phase",
    "published_count",
    "recomputed_count",
    "signed_difference",
    "absolute_difference",
    "comparison_status",
)
CELL_KEYS = frozenset(COMPARISON_COLUMNS)
REPORT_TABLES = {2020: 18, 2021: 18, 2022: 20}
EXPECTED_YEAR_CELL_COUNTS = {2020: 212, 2021: 212, 2022: 208}
EXPECTED_YEAR_SUMMARIES = {
    2020: {
        "published_total": 7136,
        "recomputed_total": 7315,
        "signed_difference": 179,
        "absolute_difference": 373,
        "positive_difference_cells": 77,
        "negative_difference_cells": 44,
        "exact_cells": 91,
        "zero_vs_zero_cells": 23,
        "nonzero_union_cells": 189,
        "nonzero_union_exact_cells": 68,
        "unresolved_cells": 121,
    },
    2021: {
        "published_total": 6783,
        "recomputed_total": 6881,
        "signed_difference": 98,
        "absolute_difference": 274,
        "positive_difference_cells": 69,
        "negative_difference_cells": 55,
        "exact_cells": 88,
        "zero_vs_zero_cells": 20,
        "nonzero_union_cells": 192,
        "nonzero_union_exact_cells": 68,
        "unresolved_cells": 124,
    },
    2022: {
        "published_total": 6583,
        "recomputed_total": 6639,
        "signed_difference": 56,
        "absolute_difference": 222,
        "positive_difference_cells": 62,
        "negative_difference_cells": 49,
        "exact_cells": 97,
        "zero_vs_zero_cells": 14,
        "nonzero_union_cells": 194,
        "nonzero_union_exact_cells": 83,
        "unresolved_cells": 111,
    },
}
EXPECTED_CELL_COUNT = 632
EXPECTED_EXACT_COUNT = 276
EXPECTED_UNRESOLVED_COUNT = 356
EXPECTED_AGGREGATE_SUMMARY = {
    "signed_difference": 333,
    "absolute_difference": 869,
    "positive_difference_cells": 208,
    "negative_difference_cells": 148,
    "zero_vs_zero_cells": 57,
    "nonzero_union_cells": 575,
    "nonzero_union_exact_cells": 219,
}
EXPECTED_EXPORT_ROW_HANDLING = {
    "retained_rows_before_blank_state_exclusion": 20836,
    "blank_state_rows_excluded": 1,
    "counted_rows": 20835,
    "zero_filled_eligible_groups": 60,
}
EXPECTED_VALIDATION_COUNT = 1264
EXACT_INTERVAL_METHOD = "exact complete-population point interval; no sampling"
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")

SOURCE_IDS = (
    "sbir-gov-award-export-2026-09-17",
    "sba-annual-report-fy2020",
    "sba-annual-report-fy2021",
    "sba-annual-report-fy2022",
)
SOURCE_LABELS = {
    SOURCE_IDS[0]: "SBIR.gov award export",
    SOURCE_IDS[1]: "FY2020 SBA annual report",
    SOURCE_IDS[2]: "FY2021 SBA annual report",
    SOURCE_IDS[3]: "FY2022 SBA annual report",
}
SOURCE_VINTAGES = {
    SOURCE_IDS[0]: "September 17, 2026 export object version",
    SOURCE_IDS[1]: "FY2020 report, Table 18",
    SOURCE_IDS[2]: "FY2021 report, Table 18",
    SOURCE_IDS[3]: "FY2022 report, Table 20",
}

ARTIFACT_LABELS = {
    SOURCE_MANIFEST_REFERENCE: "Source manifest",
    (STUDY_DIRECTORY / "validation-design-v1.md").as_posix(): "Validation design",
    (STUDY_DIRECTORY / "validation-population-v1.csv").as_posix(): ("Frozen validation population"),
    (
        "packages/sbir-analytics/sbir_analytics/assets/"
        "sba_annual_report_structural_comparison/producer.py"
    ): "Count producer",
    "scripts/data/run_sba_structural_comparison.py": "Count reproduction command",
    "scripts/data/reproduce_sba_structural_comparison.py": "Public reproduction command",
    "scripts/data/render_sba_structural_comparison.py": "Public result renderer",
    "uv.lock": "Environment lock",
    COMPARISON_REFERENCE: "632-cell count comparison",
    (
        STUDY_DIRECTORY / "validation/blind-packet-manifest-v5.json"
    ).as_posix(): "Confirmatory packet manifest",
    (
        STUDY_DIRECTORY / "validation/confirmatory/validation-values.csv"
    ).as_posix(): "Independent validation values",
    RUN_DIAGNOSTICS_REFERENCE: "Confirmatory run diagnostics",
    (
        STUDY_DIRECTORY / "validation/confirmatory/reconciliation.json"
    ).as_posix(): "Confirmatory reconciliation",
    (
        STUDY_DIRECTORY / "validation/confirmatory/attestation.json"
    ).as_posix(): "Confirmatory attestation",
    (
        STUDY_DIRECTORY / "validation/confirmatory/sealed-components.sha256"
    ).as_posix(): "Sealed-component hashes",
    (
        STUDY_DIRECTORY / "reviews/post-result-evidence-audit.md"
    ).as_posix(): "Post-result evidence audit",
}


class PublicResultError(ValueError):
    """Raised when a public result does not satisfy the frozen study contract."""


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_sha256(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return _sha256_bytes(encoded)


def _expect_keys(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    actual = set(value)
    if actual != expected:
        raise PublicResultError(
            f"{label} keys differ: missing={sorted(expected - actual)}, "
            f"extra={sorted(actual - expected)}"
        )


def _integer(value: object, *, field: str, row_number: int) -> int:
    if not isinstance(value, str) or re.fullmatch(r"-?[0-9]+", value) is None:
        raise PublicResultError(f"comparison row {row_number} has invalid {field}: {value!r}")
    return int(value)


def _validate_cell(cell: Mapping[str, Any], *, row_number: int) -> dict[str, Any]:
    _expect_keys(cell, set(CELL_KEYS), f"comparison row {row_number}")
    typed = {
        "report_year": _integer(cell["report_year"], field="report_year", row_number=row_number)
        if isinstance(cell["report_year"], str)
        else cell["report_year"],
        "table_number": _integer(cell["table_number"], field="table_number", row_number=row_number)
        if isinstance(cell["table_number"], str)
        else cell["table_number"],
        "jurisdiction": cell["jurisdiction"],
        "program": cell["program"],
        "phase": cell["phase"],
        "published_count": _integer(
            cell["published_count"], field="published_count", row_number=row_number
        )
        if isinstance(cell["published_count"], str)
        else cell["published_count"],
        "recomputed_count": _integer(
            cell["recomputed_count"], field="recomputed_count", row_number=row_number
        )
        if isinstance(cell["recomputed_count"], str)
        else cell["recomputed_count"],
        "signed_difference": _integer(
            cell["signed_difference"], field="signed_difference", row_number=row_number
        )
        if isinstance(cell["signed_difference"], str)
        else cell["signed_difference"],
        "absolute_difference": _integer(
            cell["absolute_difference"], field="absolute_difference", row_number=row_number
        )
        if isinstance(cell["absolute_difference"], str)
        else cell["absolute_difference"],
        "comparison_status": cell["comparison_status"],
    }
    integer_fields = (
        "report_year",
        "table_number",
        "published_count",
        "recomputed_count",
        "signed_difference",
        "absolute_difference",
    )
    if any(type(typed[field]) is not int for field in integer_fields):
        raise PublicResultError(f"comparison row {row_number} has a non-integer numeric value")
    year = typed["report_year"]
    if year not in REPORT_TABLES or typed["table_number"] != REPORT_TABLES[year]:
        raise PublicResultError(f"comparison row {row_number} has an unexpected year/table pair")
    if not re.fullmatch(r"[A-Z]{2}", str(typed["jurisdiction"])):
        raise PublicResultError(f"comparison row {row_number} has invalid jurisdiction")
    if typed["program"] not in {"SBIR", "STTR"}:
        raise PublicResultError(f"comparison row {row_number} has invalid program")
    if typed["phase"] not in {"Phase I", "Phase II"}:
        raise PublicResultError(f"comparison row {row_number} has invalid phase")
    if typed["published_count"] < 0 or typed["recomputed_count"] < 0:
        raise PublicResultError(f"comparison row {row_number} has a negative count")
    expected_signed = typed["recomputed_count"] - typed["published_count"]
    if typed["signed_difference"] != expected_signed:
        raise PublicResultError(f"comparison row {row_number} has incorrect signed arithmetic")
    if typed["absolute_difference"] != abs(expected_signed):
        raise PublicResultError(f"comparison row {row_number} has incorrect absolute arithmetic")
    expected_status = "exact" if expected_signed == 0 else "unresolved"
    if typed["comparison_status"] != expected_status:
        raise PublicResultError(
            f"comparison row {row_number} has status {typed['comparison_status']!r}; "
            f"expected {expected_status!r}"
        )
    return typed


def load_comparison_cells(path: Path) -> list[dict[str, Any]]:
    """Load and fail closed on any schema, key, arithmetic, or status defect."""

    try:
        with path.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if tuple(reader.fieldnames or ()) != COMPARISON_COLUMNS:
                raise PublicResultError(
                    f"comparison header differs: expected {COMPARISON_COLUMNS!r}, "
                    f"got {tuple(reader.fieldnames or ())!r}"
                )
            cells = [_validate_cell(row, row_number=index) for index, row in enumerate(reader, 2)]
    except (OSError, UnicodeError, csv.Error) as exc:
        raise PublicResultError(f"cannot read comparison CSV {path}: {exc}") from exc

    if len(cells) != EXPECTED_CELL_COUNT:
        raise PublicResultError(
            f"comparison has {len(cells)} cells; expected {EXPECTED_CELL_COUNT}"
        )
    keys = [
        (cell["report_year"], cell["jurisdiction"], cell["program"], cell["phase"])
        for cell in cells
    ]
    if len(set(keys)) != len(keys):
        raise PublicResultError("comparison has a duplicate year/jurisdiction/program/phase key")
    if keys != sorted(keys):
        raise PublicResultError("comparison cells are not in canonical key order")
    year_counts = Counter(cell["report_year"] for cell in cells)
    if dict(year_counts) != EXPECTED_YEAR_CELL_COUNTS:
        raise PublicResultError(
            f"comparison year counts differ: expected {EXPECTED_YEAR_CELL_COUNTS}, "
            f"got {dict(year_counts)}"
        )
    status_counts = Counter(cell["comparison_status"] for cell in cells)
    expected_status_counts = {
        "exact": EXPECTED_EXACT_COUNT,
        "unresolved": EXPECTED_UNRESOLVED_COUNT,
    }
    if dict(status_counts) != expected_status_counts:
        raise PublicResultError(
            f"comparison status counts differ: expected {expected_status_counts}, "
            f"got {dict(status_counts)}"
        )
    summaries = _summarize_years(cells)
    for summary in summaries:
        year = summary["report_year"]
        observed = {key: summary[key] for key in EXPECTED_YEAR_SUMMARIES[year]}
        if observed != EXPECTED_YEAR_SUMMARIES[year]:
            raise PublicResultError(
                f"FY{year} totals differ: expected {EXPECTED_YEAR_SUMMARIES[year]}, got {observed}"
            )
    return cells


def _summarize_years(cells: Sequence[Mapping[str, Any]]) -> list[dict[str, int]]:
    summaries: list[dict[str, int]] = []
    for year, table_number in REPORT_TABLES.items():
        selected = [cell for cell in cells if cell["report_year"] == year]
        summaries.append(
            {
                "report_year": year,
                "table_number": table_number,
                "cell_count": len(selected),
                "published_total": sum(cell["published_count"] for cell in selected),
                "recomputed_total": sum(cell["recomputed_count"] for cell in selected),
                "signed_difference": sum(cell["signed_difference"] for cell in selected),
                "absolute_difference": sum(cell["absolute_difference"] for cell in selected),
                "positive_difference_cells": sum(
                    cell["signed_difference"] > 0 for cell in selected
                ),
                "negative_difference_cells": sum(
                    cell["signed_difference"] < 0 for cell in selected
                ),
                "exact_cells": sum(cell["comparison_status"] == "exact" for cell in selected),
                "zero_vs_zero_cells": sum(
                    cell["published_count"] == 0 and cell["recomputed_count"] == 0
                    for cell in selected
                ),
                "nonzero_union_cells": sum(
                    cell["published_count"] != 0 or cell["recomputed_count"] != 0
                    for cell in selected
                ),
                "nonzero_union_exact_cells": sum(
                    cell["comparison_status"] == "exact"
                    and (cell["published_count"] != 0 or cell["recomputed_count"] != 0)
                    for cell in selected
                ),
                "unresolved_cells": sum(
                    cell["comparison_status"] == "unresolved" for cell in selected
                ),
            }
        )
    return summaries


def _aggregate_summary(cells: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    return {
        "signed_difference": sum(cell["signed_difference"] for cell in cells),
        "absolute_difference": sum(cell["absolute_difference"] for cell in cells),
        "positive_difference_cells": sum(cell["signed_difference"] > 0 for cell in cells),
        "negative_difference_cells": sum(cell["signed_difference"] < 0 for cell in cells),
        "zero_vs_zero_cells": sum(
            cell["published_count"] == 0 and cell["recomputed_count"] == 0 for cell in cells
        ),
        "nonzero_union_cells": sum(
            cell["published_count"] != 0 or cell["recomputed_count"] != 0 for cell in cells
        ),
        "nonzero_union_exact_cells": sum(
            cell["comparison_status"] == "exact"
            and (cell["published_count"] != 0 or cell["recomputed_count"] != 0)
            for cell in cells
        ),
    }


def _frozen_hashes(manifest: StudyManifest) -> dict[str, str]:
    hashes = {artifact.path: artifact.sha256 for artifact in manifest.frozen_artifacts}
    if len(hashes) != len(manifest.frozen_artifacts):
        raise PublicResultError("study manifest repeats a frozen artifact path")
    return hashes


def _verify_repository_artifact(root: Path, reference: str, expected_sha256: str) -> None:
    path = root / reference
    if not path.is_file():
        raise PublicResultError(f"required frozen artifact is missing: {reference}")
    actual = file_sha256(path)
    if actual != expected_sha256:
        raise PublicResultError(
            f"frozen artifact hash differs for {reference}: "
            f"expected {expected_sha256}, got {actual}"
        )


def _read_json_object(path: Path, label: str) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PublicResultError(f"cannot read {label} {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise PublicResultError(f"{label} must contain a JSON object")
    return value


def _bounded_claim(manifest: StudyManifest) -> str:
    if len(manifest.permitted_claims) != 2:
        raise PublicResultError("study manifest must contain two permitted result claims")
    source = manifest.permitted_claims[0]
    prefix = "Validated, not citable: "
    suffix = " This statement is not citable until"
    if not source.startswith(prefix) or suffix not in source:
        raise PublicResultError("study permitted claim does not match the validated release form")
    claim = source.removeprefix(prefix).split(suffix, 1)[0]
    # The folded YAML prose breaks the compound adjective across a source line.
    # Use the separately validated result field as the canonical interval wording.
    claim = claim.replace(
        "exact complete- population point interval; no sampling",
        EXACT_INTERVAL_METHOD,
    )
    claim = claim[0].upper() + claim[1:]
    required_fragments = (
        "all 632 award-count cells",
        "September 17, 2026 SBIR.gov export",
        "EXPORT_ROW_V1",
        "AWARD_YEAR_FIELD_V1",
        "separate blinded-role implementation reproduced 1,264 of 1,264 count operands",
        "[1.0, 1.0]",
        EXACT_INTERVAL_METHOD,
    )
    missing = [fragment for fragment in required_fragments if fragment not in claim]
    if missing:
        raise PublicResultError(f"bounded claim is missing required text: {missing}")
    return claim


def _summary_claim(manifest: StudyManifest) -> str:
    claim = manifest.permitted_claims[1]
    required_fragments = (
        "632 count cells: 276 are exact and 356 are unresolved",
        "Recomputed minus published counts sum to +333",
        "absolute cell differences sum to 869",
        "57 are zero versus zero",
        "575 cells where either source reports a nonzero count, 219 are exact",
        "208 positive and 148 negative",
        "not an omitted-award estimate",
        "source-correctness verdict",
        "causal explanation",
    )
    missing = [fragment for fragment in required_fragments if fragment not in claim]
    if missing:
        raise PublicResultError(f"summary claim is missing required text: {missing}")
    return claim


def _export_row_handling(
    diagnostics: Mapping[str, Any], frozen_hashes: Mapping[str, str]
) -> dict[str, Any]:
    extraction = diagnostics.get("export_extraction")
    if not isinstance(extraction, dict):
        raise PublicResultError("confirmatory diagnostics lacks export_extraction")
    handling = {
        "retained_rows_before_blank_state_exclusion": extraction.get(
            "retained_fy2020_fy2022_rows_before_blank_state_drop"
        ),
        "blank_state_rows_excluded": extraction.get("dropped_blank_state_rows"),
        "counted_rows": extraction.get("retained_counted_rows_after_blank_state_drop"),
        "zero_filled_eligible_groups": extraction.get("zero_filled_eligible_groups"),
    }
    if handling != EXPECTED_EXPORT_ROW_HANDLING:
        raise PublicResultError(
            "confirmatory export-row diagnostics differ: "
            f"expected {EXPECTED_EXPORT_ROW_HANDLING}, got {handling}"
        )
    expected_sha256 = frozen_hashes.get(RUN_DIAGNOSTICS_REFERENCE)
    if expected_sha256 is None:
        raise PublicResultError("study manifest does not freeze confirmatory run diagnostics")
    return {
        **handling,
        "countable_unit": "one parsed export row",
        "artifact_path": RUN_DIAGNOSTICS_REFERENCE,
        "artifact_sha256": expected_sha256,
    }


def _validate_manifest(manifest: StudyManifest) -> None:
    if manifest.study_id != STUDY_ID:
        raise PublicResultError(f"unexpected study_id: {manifest.study_id!r}")
    if manifest.evidence_status is not EvidenceStatus.VALIDATED:
        raise PublicResultError(
            f"public result requires validated status; got {manifest.evidence_status.value!r}"
        )
    if manifest.materialization.allowed:
        raise PublicResultError("release-pending renderer requires a closed materialization gate")
    result = manifest.validation_result
    design = manifest.validation_design
    if result is None or design is None:
        raise PublicResultError("validated study requires validation design and result blocks")
    if (
        result.numerator != EXPECTED_VALIDATION_COUNT
        or result.denominator != EXPECTED_VALIDATION_COUNT
        or result.interval_low != 1.0
        or result.interval_high != 1.0
        or result.interval_method != EXACT_INTERVAL_METHOD
        or not result.threshold_met
        or not result.confirmatory
    ):
        raise PublicResultError("validation result differs from the frozen 1,264/1,264 result")
    if design.threshold_value != EXPECTED_VALIDATION_COUNT:
        raise PublicResultError("validation threshold is not 1,264 frozen operands")
    _bounded_claim(manifest)
    _summary_claim(manifest)


def _source_records(
    source_manifest: Mapping[str, Any], frozen_hashes: Mapping[str, str]
) -> list[dict[str, Any]]:
    if source_manifest.get("schema_version") != 1:
        raise PublicResultError("source manifest schema_version must be 1")
    capture_gate = source_manifest.get("capture_gate")
    if not isinstance(capture_gate, dict) or capture_gate.get("allowed") is not True:
        raise PublicResultError("source manifest capture gate is not open")
    raw_sources = source_manifest.get("sources")
    if not isinstance(raw_sources, list):
        raise PublicResultError("source manifest sources must be an array")
    indexed: dict[str, Mapping[str, Any]] = {}
    for raw in raw_sources:
        if not isinstance(raw, dict) or not isinstance(raw.get("source_id"), str):
            raise PublicResultError("source manifest contains an invalid source record")
        source_id = raw["source_id"]
        if source_id in indexed:
            raise PublicResultError(f"source manifest repeats source_id {source_id!r}")
        indexed[source_id] = raw
    if set(indexed) != set(SOURCE_IDS):
        raise PublicResultError(
            f"source identities differ: expected {list(SOURCE_IDS)}, got {sorted(indexed)}"
        )

    records: list[dict[str, Any]] = []
    for source_id in SOURCE_IDS:
        source = indexed[source_id]
        local_path = source.get("local_path")
        sha256 = source.get("sha256")
        size_bytes = source.get("size_bytes")
        retrieved_on = source.get("retrieved_on")
        clean_retrieved_at = source.get("clean_retrieved_at")
        if (
            not isinstance(local_path, str)
            or not isinstance(sha256, str)
            or SHA256_PATTERN.fullmatch(sha256) is None
            or type(size_bytes) is not int
            or size_bytes < 1
            or not isinstance(retrieved_on, str)
            or not isinstance(clean_retrieved_at, str)
        ):
            raise PublicResultError(f"source record is incomplete: {source_id}")
        if frozen_hashes.get(local_path) != sha256:
            raise PublicResultError(
                f"source hash for {source_id} does not match the study manifest"
            )
        record: dict[str, Any] = {
            "source_id": source_id,
            "label": SOURCE_LABELS[source_id],
            "vintage": SOURCE_VINTAGES[source_id],
            "retrieved_on": retrieved_on,
            "clean_retrieved_at": clean_retrieved_at,
            "size_bytes": size_bytes,
            "sha256": sha256,
        }
        if source_id == SOURCE_IDS[0]:
            version = source.get("upstream_object_version")
            if not isinstance(version, str) or not version:
                raise PublicResultError("award export source lacks an object version")
            record["upstream_object_version"] = version
        records.append(record)
    return records


def _artifact_records(root: Path, frozen_hashes: Mapping[str, str]) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    for reference, label in ARTIFACT_LABELS.items():
        expected = frozen_hashes.get(reference)
        if expected is None:
            raise PublicResultError(f"study manifest does not freeze {reference}")
        _verify_repository_artifact(root, reference, expected)
        records.append({"label": label, "path": reference, "sha256": expected})
    return records


def build_payload(
    repository_root: Path = REPOSITORY_ROOT,
    *,
    comparison_path: Path | None = None,
    study_manifest_path: Path | None = None,
    source_manifest_path: Path | None = None,
    run_diagnostics_path: Path | None = None,
) -> dict[str, Any]:
    """Build the public sidecar from the three declared study inputs."""

    root = repository_root.resolve()
    comparison_path = comparison_path or root / COMPARISON_REFERENCE
    study_manifest_path = study_manifest_path or root / STUDY_MANIFEST_REFERENCE
    source_manifest_path = source_manifest_path or root / SOURCE_MANIFEST_REFERENCE
    run_diagnostics_path = run_diagnostics_path or root / RUN_DIAGNOSTICS_REFERENCE
    manifest = load_study_manifest(study_manifest_path)
    _validate_manifest(manifest)
    frozen_hashes = _frozen_hashes(manifest)

    expected_comparison_sha = frozen_hashes.get(COMPARISON_REFERENCE)
    if expected_comparison_sha is None:
        raise PublicResultError("study manifest does not freeze the count comparison")
    actual_comparison_sha = file_sha256(comparison_path)
    if actual_comparison_sha != expected_comparison_sha:
        raise PublicResultError(
            "count comparison hash differs from the study manifest: "
            f"expected {expected_comparison_sha}, got {actual_comparison_sha}"
        )
    cells = load_comparison_cells(comparison_path)

    expected_source_manifest_sha = frozen_hashes.get(SOURCE_MANIFEST_REFERENCE)
    if expected_source_manifest_sha is None:
        raise PublicResultError("study manifest does not freeze the source manifest")
    actual_source_manifest_sha = file_sha256(source_manifest_path)
    if actual_source_manifest_sha != expected_source_manifest_sha:
        raise PublicResultError(
            "source manifest hash differs from the study manifest: "
            f"expected {expected_source_manifest_sha}, got {actual_source_manifest_sha}"
        )
    source_manifest = _read_json_object(source_manifest_path, "source manifest")

    expected_diagnostics_sha = frozen_hashes.get(RUN_DIAGNOSTICS_REFERENCE)
    if expected_diagnostics_sha is None:
        raise PublicResultError("study manifest does not freeze confirmatory run diagnostics")
    actual_diagnostics_sha = file_sha256(run_diagnostics_path)
    if actual_diagnostics_sha != expected_diagnostics_sha:
        raise PublicResultError(
            "confirmatory run diagnostics hash differs from the study manifest: "
            f"expected {expected_diagnostics_sha}, got {actual_diagnostics_sha}"
        )
    run_diagnostics = _read_json_object(run_diagnostics_path, "confirmatory run diagnostics")

    result = manifest.validation_result
    assert result is not None  # checked by _validate_manifest
    content: dict[str, Any] = {
        "study_id": manifest.study_id,
        "title": manifest.title,
        "release_status": RELEASE_STATUS,
        "prepared_for": PREPARED_FOR,
        "bounded_claim": _bounded_claim(manifest),
        "result_summary_claim": _summary_claim(manifest),
        "rules_plain_language": (
            "Count each parsed export row once, use Award Year as the year, and do not deduplicate."
        ),
        "jurisdiction_rule_plain_language": (
            "Match only the 53 frozen full names exactly, with case and whitespace preserved. "
            "Exclude and count blank State rows; block every other unmapped nonblank State. "
            "Marshall Islands maps to study-only code MH, outside the general canonical set."
        ),
        "comparison": {
            "definition": "signed_difference = recomputed_count - published_count",
            "cell_count": EXPECTED_CELL_COUNT,
            "exact_cells": EXPECTED_EXACT_COUNT,
            "unresolved_cells": EXPECTED_UNRESOLVED_COUNT,
            "aggregate_summary": _aggregate_summary(cells),
            "yearly_summaries": _summarize_years(cells),
            "cells": cells,
            "artifact_path": COMPARISON_REFERENCE,
            "artifact_sha256": expected_comparison_sha,
        },
        "export_row_handling": _export_row_handling(run_diagnostics, frozen_hashes),
        "validation": {
            "scope": "source-capture and transformation fidelity; not source agreement",
            "metric": result.metric,
            "numerator": result.numerator,
            "denominator": result.denominator,
            "interval": [result.interval_low, result.interval_high],
            "interval_method": result.interval_method,
            "threshold_met": result.threshold_met,
            "confirmatory": result.confirmatory,
            "evaluated_on": result.evaluated_on.isoformat(),
            "design_path": result.design_path,
            "design_sha256": result.design_sha256,
        },
        "sources": _source_records(source_manifest, frozen_hashes),
        "non_claims": list(manifest.limitations),
        "release_blockers": list(manifest.materialization.blockers),
        "artifact_hashes": _artifact_records(root, frozen_hashes),
        "reproduction": {
            "setup_command": "make install-core",
            "one_command": REPRODUCTION_COMMAND,
            "renderer_command": RENDER_COMMAND,
        },
    }
    payload = {
        "schema_version": 2,
        "content_sha256": _canonical_sha256(content),
        "content": content,
    }
    _validate_payload(payload)
    return payload


def _validate_payload(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    _expect_keys(payload, {"schema_version", "content_sha256", "content"}, "public sidecar")
    if payload["schema_version"] != 2:
        raise PublicResultError("public sidecar schema_version must be 2")
    content_sha256 = payload["content_sha256"]
    content = payload["content"]
    if not isinstance(content_sha256, str) or SHA256_PATTERN.fullmatch(content_sha256) is None:
        raise PublicResultError("public sidecar content_sha256 is invalid")
    if not isinstance(content, dict):
        raise PublicResultError("public sidecar content must be an object")
    actual = _canonical_sha256(content)
    if content_sha256 != actual:
        raise PublicResultError(
            f"public sidecar content hash differs: expected {content_sha256}, got {actual}"
        )
    expected_content_keys = {
        "study_id",
        "title",
        "release_status",
        "prepared_for",
        "bounded_claim",
        "result_summary_claim",
        "rules_plain_language",
        "jurisdiction_rule_plain_language",
        "comparison",
        "export_row_handling",
        "validation",
        "sources",
        "non_claims",
        "release_blockers",
        "artifact_hashes",
        "reproduction",
    }
    _expect_keys(content, expected_content_keys, "public sidecar content")
    if (
        content["study_id"] != STUDY_ID
        or content["release_status"] != RELEASE_STATUS
        or content["prepared_for"] != PREPARED_FOR
    ):
        raise PublicResultError("public sidecar has the wrong study or release status")
    comparison = content["comparison"]
    if not isinstance(comparison, dict):
        raise PublicResultError("public sidecar comparison must be an object")
    _expect_keys(
        comparison,
        {
            "definition",
            "cell_count",
            "exact_cells",
            "unresolved_cells",
            "aggregate_summary",
            "yearly_summaries",
            "cells",
            "artifact_path",
            "artifact_sha256",
        },
        "public sidecar comparison",
    )
    cells = comparison.get("cells")
    if not isinstance(cells, list):
        raise PublicResultError("public sidecar comparison cells must be an array")
    typed_cells = [_validate_cell(cell, row_number=index) for index, cell in enumerate(cells, 1)]
    summaries = _summarize_years(typed_cells)
    if comparison.get("yearly_summaries") != summaries:
        raise PublicResultError("public sidecar yearly summaries do not match its cells")
    aggregate_summary = _aggregate_summary(typed_cells)
    if comparison.get("aggregate_summary") != aggregate_summary:
        raise PublicResultError("public sidecar aggregate summary does not match its cells")
    if aggregate_summary != EXPECTED_AGGREGATE_SUMMARY:
        raise PublicResultError("public sidecar aggregate summary differs from the frozen result")
    if (
        comparison.get("cell_count") != EXPECTED_CELL_COUNT
        or comparison.get("exact_cells") != EXPECTED_EXACT_COUNT
        or comparison.get("unresolved_cells") != EXPECTED_UNRESOLVED_COUNT
        or len(typed_cells) != EXPECTED_CELL_COUNT
    ):
        raise PublicResultError("public sidecar comparison counts differ from the frozen result")
    status_counts = Counter(cell["comparison_status"] for cell in typed_cells)
    if status_counts != Counter(
        {"exact": EXPECTED_EXACT_COUNT, "unresolved": EXPECTED_UNRESOLVED_COUNT}
    ):
        raise PublicResultError("public sidecar cell statuses do not match its summary")
    validation = content["validation"]
    if not isinstance(validation, dict) or (
        validation.get("numerator") != EXPECTED_VALIDATION_COUNT
        or validation.get("denominator") != EXPECTED_VALIDATION_COUNT
        or validation.get("interval") != [1.0, 1.0]
        or validation.get("interval_method") != EXACT_INTERVAL_METHOD
        or validation.get("threshold_met") is not True
        or validation.get("confirmatory") is not True
    ):
        raise PublicResultError("public sidecar validation result differs from the frozen result")
    export_row_handling = content["export_row_handling"]
    if not isinstance(export_row_handling, dict):
        raise PublicResultError("public sidecar export_row_handling must be an object")
    expected_handling_keys = {
        *EXPECTED_EXPORT_ROW_HANDLING,
        "countable_unit",
        "artifact_path",
        "artifact_sha256",
    }
    _expect_keys(export_row_handling, expected_handling_keys, "public sidecar export_row_handling")
    observed_handling = {key: export_row_handling[key] for key in EXPECTED_EXPORT_ROW_HANDLING}
    if observed_handling != EXPECTED_EXPORT_ROW_HANDLING:
        raise PublicResultError("public sidecar export-row diagnostics differ from the frozen run")
    if (
        export_row_handling["countable_unit"] != "one parsed export row"
        or export_row_handling["artifact_path"] != RUN_DIAGNOSTICS_REFERENCE
        or not isinstance(export_row_handling["artifact_sha256"], str)
        or SHA256_PATTERN.fullmatch(export_row_handling["artifact_sha256"]) is None
    ):
        raise PublicResultError("public sidecar export-row diagnostic provenance is invalid")
    if (
        export_row_handling["counted_rows"]
        != export_row_handling["retained_rows_before_blank_state_exclusion"]
        - export_row_handling["blank_state_rows_excluded"]
        or export_row_handling["counted_rows"]
        != sum(cell["recomputed_count"] for cell in typed_cells)
        or export_row_handling["zero_filled_eligible_groups"]
        != sum(cell["recomputed_count"] == 0 for cell in typed_cells)
    ):
        raise PublicResultError("public sidecar export-row diagnostics fail arithmetic checks")
    for claim_field in (
        "bounded_claim",
        "result_summary_claim",
        "rules_plain_language",
        "jurisdiction_rule_plain_language",
    ):
        if not isinstance(content[claim_field], str) or not content[claim_field].strip():
            raise PublicResultError(f"public sidecar {claim_field} is blank")
    if not isinstance(content["non_claims"], list) or len(content["non_claims"]) != 8:
        raise PublicResultError("public sidecar must carry all eight adjacent non-claims")
    if not isinstance(content["sources"], list) or len(content["sources"]) != 4:
        raise PublicResultError("public sidecar must carry all four source identities")
    return content


def _format_signed(value: int) -> str:
    return f"{value:+,d}"


def render_markdown(payload: Mapping[str, Any]) -> str:
    """Render the public page from one validated sidecar without file access."""

    content = _validate_payload(payload)
    comparison = content["comparison"]
    aggregate = comparison["aggregate_summary"]
    export_rows = content["export_row_handling"]
    validation = content["validation"]
    lines = [
        f"# {content['title']}",
        "",
        f"**Prepared for:** {content['prepared_for']}",
        "",
        f"> **Status: {content['release_status']}.**",
        "",
        "This page reports a validated current-vintage structural comparison. The release",
        "gates are still closed. Do not quote this result as a released finding.",
        "",
        "## Bounded claim",
        "",
        content["bounded_claim"],
        "",
        f"In plain language: {content['rules_plain_language']}",
        "",
        f"Jurisdiction rule: {content['jurisdiction_rule_plain_language']}",
        "",
        "The validation supports source-capture and transformation fidelity. It does not",
        "establish agreement between the SBA annual reports and SBIR.gov.",
        "",
        "## Comparison result",
        "",
        content["result_summary_claim"],
        "",
        "The signed difference is the recomputed count minus the published count. The",
        "absolute difference removes that sign before summing, so positive and negative",
        "cell differences cannot cancel each other.",
        "",
        "| Fiscal year | SBA table | Cells | Published total | Recomputed total | "
        "Signed difference | Absolute difference | Exact | Zero vs. zero | Unresolved |",
        "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for summary in comparison["yearly_summaries"]:
        lines.append(
            f"| FY{summary['report_year']} | {summary['table_number']} | "
            f"{summary['cell_count']:,} | {summary['published_total']:,} | "
            f"{summary['recomputed_total']:,} | "
            f"{_format_signed(summary['signed_difference'])} | "
            f"{summary['absolute_difference']:,} | {summary['exact_cells']:,} | "
            f"{summary['zero_vs_zero_cells']:,} | {summary['unresolved_cells']:,} |"
        )
    lines.extend(
        [
            "| **Total** | — | **632** | **20,502** | **20,835** | "
            f"**{_format_signed(aggregate['signed_difference'])}** | "
            f"**{aggregate['absolute_difference']:,}** | **276** | "
            f"**{aggregate['zero_vs_zero_cells']:,}** | **356** |",
            "",
            "Every nonzero difference remains `unresolved`. The study applies no tolerance",
            "verdict, dollar comparison, or causal mismatch label.",
            "",
            f"The complete cell-level result is in `{comparison['artifact_path']}` "
            f"(SHA-256 `{comparison['artifact_sha256']}`).",
            "",
            "## Export-row handling",
            "",
            f"Of {export_rows['retained_rows_before_blank_state_exclusion']:,} export rows "
            "retained for FY2020–FY2022 before jurisdiction handling, "
            f"{export_rows['blank_state_rows_excluded']} had blank `State` and was excluded "
            "under the frozen rule. This is one export row, not necessarily one unique award. "
            f"The remaining {export_rows['counted_rows']:,} rows were counted.",
            "",
            f"{export_rows['zero_filled_eligible_groups']:,} eligible jurisdiction/program/phase "
            "groups had no retained export row and received a recomputed count of zero. "
            "These are fixed diagnostics for this source vintage, not tolerances.",
            "",
            f"Diagnostics: `{export_rows['artifact_path']}` "
            f"(SHA-256 `{export_rows['artifact_sha256']}`).",
            "",
            "## Validation result",
            "",
            f"The separate blinded role reproduced **{validation['numerator']:,} of "
            f"{validation['denominator']:,}** extracted operands.",
            "",
            f"- Interval: `[{validation['interval'][0]:.1f}, {validation['interval'][1]:.1f}]`",
            f"- Method: `{validation['interval_method']}`",
            f"- Evaluated: `{validation['evaluated_on']}`",
            f"- Frozen design: `{validation['design_path']}`",
            f"- Design SHA-256: `{validation['design_sha256']}`",
            "",
            "This was a complete-population fidelity check. It was not a sample estimate.",
            "It cannot detect a rule error shared by both separate implementations.",
            "",
            "## Sources and vintage",
            "",
            "| Source | Vintage or as-of | Captured | Clean verification | Bytes | SHA-256 |",
            "| --- | --- | --- | --- | ---: | --- |",
        ]
    )
    for source in content["sources"]:
        lines.append(
            f"| {source['label']} | {source['vintage']} | {source['retrieved_on']} | "
            f"{source['clean_retrieved_at']} | {source['size_bytes']:,} | "
            f"`{source['sha256']}` |"
        )
    lines.extend(["", "## Adjacent non-claims", ""])
    lines.extend(f"- {statement}" for statement in content["non_claims"])
    lines.extend(
        [
            "",
            "## Reproduce",
            "",
            "From the repository root in a tagged release checkout, run:",
            "",
            "```bash",
            content["reproduction"]["setup_command"],
            content["reproduction"]["one_command"],
            "```",
            "",
            "To regenerate this JSON sidecar and Markdown page together from the committed",
            "comparison and manifests, run:",
            "",
            "```bash",
            content["reproduction"]["renderer_command"],
            "```",
            "",
            "## Run and artifact hashes",
            "",
            "| Artifact | Path | SHA-256 |",
            "| --- | --- | --- |",
        ]
    )
    for artifact in content["artifact_hashes"]:
        lines.append(f"| {artifact['label']} | `{artifact['path']}` | `{artifact['sha256']}` |")
    lines.extend(
        [
            "",
            f"Public sidecar content SHA-256: `{payload['content_sha256']}`.",
            "This content digest is SHA-256 over the sidecar's `content` object encoded as",
            "canonical JSON with sorted keys and compact separators. It differs from the",
            "whole-file SHA-256 because the file also stores this digest and schema version.",
            "",
            "## Release gates still open",
            "",
        ]
    )
    lines.extend(f"- {blocker}" for blocker in content["release_blockers"])
    return "\n".join(lines) + "\n"


def serialize_payload(payload: Mapping[str, Any]) -> str:
    """Return the canonical checked-in JSON representation."""

    _validate_payload(payload)
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def generate_public_artifacts(
    repository_root: Path = REPOSITORY_ROOT,
    *,
    sidecar_path: Path | None = None,
    markdown_path: Path | None = None,
) -> tuple[Path, Path]:
    """Regenerate the sidecar and page together after all checks pass."""

    root = repository_root.resolve()
    payload = build_payload(root)
    sidecar_path = sidecar_path or root / SIDECAR_REFERENCE
    markdown_path = markdown_path or root / MARKDOWN_REFERENCE
    sidecar_text = serialize_payload(payload)
    markdown_text = render_markdown(payload)
    sidecar_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    sidecar_path.write_text(sidecar_text, encoding="utf-8")
    markdown_path.write_text(markdown_text, encoding="utf-8")
    return sidecar_path, markdown_path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, default=REPOSITORY_ROOT)
    parser.add_argument("--sidecar", type=Path)
    parser.add_argument("--markdown", type=Path)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    sidecar_path, markdown_path = generate_public_artifacts(
        args.repository_root,
        sidecar_path=args.sidecar,
        markdown_path=args.markdown,
    )
    print(f"Wrote {sidecar_path} and {markdown_path}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
