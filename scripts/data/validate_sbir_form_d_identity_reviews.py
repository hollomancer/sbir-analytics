#!/usr/bin/env python3
"""Evaluate independently reviewed SBIR↔Form D identity cases by route.

This script is ready for synthetic tests in PR3a. Real route precision is not
published until two independent human ledgers and a disagreement-only third
adjudication ledger exist.
"""

import argparse
import hashlib
import json
import math
import os
import re
import sys
import tempfile
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
EPISTEMIC_TIER = "evidence"

DEFAULT_SAMPLE_MANIFEST = (
    REPO_ROOT / "data/private/agency_private_capital/identity_review/"
    "sbir_form_d_identity_review_sample.manifest.json"
)
DEFAULT_OUTPUT_DIR = REPO_ROOT / "data/private/agency_private_capital/identity_review_validation"

ESTIMAND = "same organization under frozen administrative evidence"
CASE_MAP_CONTRACT = "sbir-form-d-organizational-identity-review-case-map-v1"
VALIDATION_CONTRACT = "sbir-form-d-exclusive-route-validation-v1"
ROUTE_ORDER = (
    "exact_normalized_name",
    "strong_name",
    "state_supported",
    "zip_supported",
)
ALLOWED_DECISIONS = (
    "same_organization",
    "different_organization",
    "insufficient_evidence",
)
EXPECTED_CASES_PER_STRATUM = 100
EXPECTED_CASE_COUNT = EXPECTED_CASES_PER_STRATUM * len(ROUTE_ORDER)
WILSON_Z_95 = 1.959963984540054
WILSON_LOWER_BOUND_GATE = 0.90
SHA256_RE = re.compile(r"[0-9a-f]{64}")
GIT_COMMIT_RE = re.compile(r"[0-9a-f]{40}")


class ValidationError(RuntimeError):
    """Raised when review inputs cannot support a route validation result."""


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_path(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
            size += len(block)
    return digest.hexdigest(), size


def _external_bytes(path: Path, *, expected_sha256: str, label: str) -> bytes:
    expected = str(expected_sha256).strip().lower()
    if not SHA256_RE.fullmatch(expected):
        raise ValidationError(f"{label} SHA-256 pin must be 64 lowercase hexadecimal characters")
    if not path.is_file():
        raise ValidationError(f"Required {label} is missing: {path}")
    before = path.stat()
    data = path.read_bytes()
    after = path.stat()
    if (
        after.st_size != before.st_size
        or after.st_mtime_ns != before.st_mtime_ns
        or after.st_ino != before.st_ino
    ):
        raise ValidationError(f"{label} changed while it was read")
    if _sha256_bytes(data) != expected:
        raise ValidationError(f"{label} SHA-256 does not match its external pin")
    return data


def _json_object(data: bytes, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(data)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValidationError(f"Invalid {label} JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ValidationError(f"{label} must be a JSON object")
    return value


def _non_negative_int(value: object, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValidationError(f"{label} must be a non-negative integer")
    return value


def _pinned_product(value: object, *, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValidationError(f"Sample manifest does not pin {label}")
    path = value.get("path")
    sha256 = value.get("sha256")
    if (
        not isinstance(path, str)
        or not path
        or path in {".", ".."}
        or Path(path).name != path
        or Path(path).is_absolute()
    ):
        raise ValidationError(f"Pinned {label} path must be one safe filename")
    if not isinstance(sha256, str) or not SHA256_RE.fullmatch(sha256):
        raise ValidationError(f"Pinned {label} has an invalid SHA-256")
    _non_negative_int(value.get("size_bytes"), label=f"Pinned {label} size_bytes")
    _non_negative_int(value.get("row_count"), label=f"Pinned {label} row_count")
    return dict(value)


def _jsonl_rows(data: bytes, *, label: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, raw_line in enumerate(data.splitlines(), start=1):
        if not raw_line.strip():
            raise ValidationError(f"{label} has a blank line at {line_number}")
        try:
            row = json.loads(raw_line)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValidationError(f"Invalid {label} JSON at line {line_number}") from exc
        if not isinstance(row, dict):
            raise ValidationError(f"{label} line {line_number} must be an object")
        rows.append(row)
    return rows


def _load_sample(
    path: Path, *, expected_sha256: str
) -> tuple[dict[str, Any], bytes, dict[str, str]]:
    manifest_data = _external_bytes(
        path,
        expected_sha256=expected_sha256,
        label="review-sample manifest",
    )
    manifest = _json_object(manifest_data, label="review-sample manifest")
    if (
        manifest.get("schema_version") != 1
        or manifest.get("complete") is not True
        or manifest.get("instrument_only") is not True
        or manifest.get("human_labels_present") is not False
        or manifest.get("estimand") != ESTIMAND
    ):
        raise ValidationError("Review-sample manifest has an unsupported contract")
    expected_gates: dict[str, object] = {
        "complete_sbir_exclusion": False,
        "covariates_ready": False,
        "exclusion_eligible": False,
        "exclusion_recall": "unknown",
        "identity_accepted": False,
        "identity_only": True,
        "matching_eligible": False,
        "rate_eligible": False,
        "ready_for_matching": False,
        "recall": "unknown",
    }
    for field, expected in expected_gates.items():
        actual = manifest.get(field)
        valid = actual is expected if isinstance(expected, bool) else actual == expected
        if not valid:
            raise ValidationError(f"Review-sample manifest has unexpected {field}")
    if manifest.get("exclusive_route_validation_passed") != dict.fromkeys(ROUTE_ORDER, False):
        raise ValidationError("Review-sample manifest unexpectedly opens a route-validation gate")
    selected_counts = manifest.get("counts", {}).get("selected_pairs_by_exclusive_stratum")
    if selected_counts != dict.fromkeys(ROUTE_ORDER, EXPECTED_CASES_PER_STRATUM):
        raise ValidationError("Review sample is not the frozen 100-per-stratum design")
    outputs = manifest.get("outputs")
    if not isinstance(outputs, Mapping):
        raise ValidationError("Review-sample manifest has no outputs")
    case_map_product = _pinned_product(outputs.get("private_case_map"), label="private case map")
    if case_map_product["row_count"] != EXPECTED_CASE_COUNT:
        raise ValidationError("Private case map does not pin exactly 400 cases")
    case_map_path = path.parent / case_map_product["path"]
    if case_map_path.parent != path.parent:
        raise ValidationError("Private case-map path escapes the sample directory")
    case_map_data = _external_bytes(
        case_map_path,
        expected_sha256=case_map_product["sha256"],
        label="private case map",
    )
    if len(case_map_data) != case_map_product["size_bytes"]:
        raise ValidationError("Private case-map byte count does not match its manifest")
    rows = _jsonl_rows(case_map_data, label="private case map")
    if len(rows) != case_map_product["row_count"]:
        raise ValidationError("Private case-map row count does not match its manifest")
    case_strata: dict[str, str] = {}
    stratum_counts: Counter[str] = Counter()
    for line_number, row in enumerate(rows, start=1):
        case_id = row.get("case_id")
        stratum = row.get("exclusive_stratum")
        if (
            row.get("schema_version") != 1
            or row.get("case_map_contract") != CASE_MAP_CONTRACT
            or not isinstance(case_id, str)
            or not re.fullmatch(r"case_[0-9]{4}", case_id)
            or case_id in case_strata
            or stratum not in ROUTE_ORDER
        ):
            raise ValidationError(f"Private case-map line {line_number} has an invalid contract")
        case_strata[case_id] = stratum
        stratum_counts[stratum] += 1
    expected_ids = {f"case_{index:04d}" for index in range(1, EXPECTED_CASE_COUNT + 1)}
    if set(case_strata) != expected_ids:
        raise ValidationError("Private case map does not contain the complete neutral case set")
    if dict(stratum_counts) != dict.fromkeys(ROUTE_ORDER, EXPECTED_CASES_PER_STRATUM):
        raise ValidationError("Private case-map strata do not reconcile to the sample design")
    return manifest, manifest_data, case_strata


def _load_primary_ledger(
    path: Path,
    *,
    expected_sha256: str,
    expected_cases: set[str],
    label: str,
) -> tuple[str, dict[str, str], dict[str, Any]]:
    data = _external_bytes(path, expected_sha256=expected_sha256, label=label)
    rows = _jsonl_rows(data, label=label)
    decisions: dict[str, str] = {}
    reviewer_ids: set[str] = set()
    for line_number, row in enumerate(rows, start=1):
        if set(row) != {"case_id", "decision", "reviewer_id", "schema_version"}:
            raise ValidationError(f"{label} line {line_number} has unexpected fields")
        case_id = row.get("case_id")
        reviewer_id = row.get("reviewer_id")
        decision = row.get("decision")
        if row.get("schema_version") != 1:
            raise ValidationError(f"{label} line {line_number} has an unsupported schema")
        if not isinstance(case_id, str) or case_id not in expected_cases or case_id in decisions:
            raise ValidationError(f"{label} line {line_number} has an invalid or duplicate case")
        if not isinstance(reviewer_id, str) or not reviewer_id.strip():
            raise ValidationError(f"{label} line {line_number} has an invalid reviewer ID")
        if decision not in ALLOWED_DECISIONS:
            raise ValidationError(f"{label} line {line_number} has an invalid decision")
        reviewer_ids.add(reviewer_id.strip())
        decisions[case_id] = decision
    if set(decisions) != expected_cases:
        raise ValidationError(f"{label} does not cover all {len(expected_cases)} cases")
    if len(reviewer_ids) != 1:
        raise ValidationError(f"{label} must contain exactly one reviewer ID")
    reviewer_id = next(iter(reviewer_ids))
    return (
        reviewer_id,
        decisions,
        {
            "row_count": len(rows),
            "sha256": _sha256_bytes(data),
            "size_bytes": len(data),
        },
    )


def _load_adjudication_ledger(
    path: Path,
    *,
    expected_sha256: str,
    disagreement_cases: set[str],
    primary_reviewer_ids: set[str],
) -> tuple[dict[str, str], dict[str, Any]]:
    data = _external_bytes(
        path,
        expected_sha256=expected_sha256,
        label="adjudication ledger",
    )
    rows = _jsonl_rows(data, label="adjudication ledger")
    decisions: dict[str, str] = {}
    adjudicator_ids: set[str] = set()
    for line_number, row in enumerate(rows, start=1):
        if set(row) != {"adjudicator_id", "case_id", "decision", "schema_version"}:
            raise ValidationError(f"Adjudication ledger line {line_number} has unexpected fields")
        case_id = row.get("case_id")
        row_adjudicator_id = row.get("adjudicator_id")
        decision = row.get("decision")
        if row.get("schema_version") != 1:
            raise ValidationError(
                f"Adjudication ledger line {line_number} has an unsupported schema"
            )
        if (
            not isinstance(case_id, str)
            or case_id not in disagreement_cases
            or case_id in decisions
        ):
            raise ValidationError(
                f"Adjudication ledger line {line_number} has an invalid or duplicate case"
            )
        if not isinstance(row_adjudicator_id, str) or not row_adjudicator_id.strip():
            raise ValidationError(
                f"Adjudication ledger line {line_number} has an invalid adjudicator ID"
            )
        if decision not in ALLOWED_DECISIONS:
            raise ValidationError(f"Adjudication ledger line {line_number} has an invalid decision")
        adjudicator_ids.add(row_adjudicator_id.strip())
        decisions[case_id] = decision
    if set(decisions) != disagreement_cases:
        raise ValidationError("Adjudication ledger must contain exactly the disagreement cases")
    if disagreement_cases:
        if len(adjudicator_ids) != 1:
            raise ValidationError("Adjudication ledger must contain exactly one adjudicator ID")
        final_adjudicator_id: str | None = next(iter(adjudicator_ids))
        if final_adjudicator_id in primary_reviewer_ids:
            raise ValidationError("Adjudicator must be distinct from both primary reviewers")
    else:
        final_adjudicator_id = None
    return decisions, {
        "row_count": len(rows),
        "sha256": _sha256_bytes(data),
        "size_bytes": len(data),
    }


def _wilson_interval(successes: int, total: int) -> dict[str, float | int]:
    """Dependency-free copy of the repository's Wilson 95% calculation."""
    if total <= 0 or successes < 0 or successes > total:
        raise ValidationError("Wilson inputs must satisfy 0 <= successes <= total")
    proportion = successes / total
    z2 = WILSON_Z_95 * WILSON_Z_95
    denominator = 1 + z2 / total
    centre = (proportion + z2 / (2 * total)) / denominator
    half = (
        WILSON_Z_95
        * math.sqrt(proportion * (1 - proportion) / total + z2 / (4 * total * total))
        / denominator
    )
    return {
        "denominator": total,
        "lower_bound": max(0.0, centre - half),
        "point_estimate": proportion,
        "successes": successes,
        "upper_bound": min(1.0, centre + half),
    }


def evaluate(args: argparse.Namespace) -> dict[str, Any]:
    code_version = str(args.code_version or "").strip()
    if not GIT_COMMIT_RE.fullmatch(code_version):
        raise ValidationError("--code-version must be a full lowercase 40-character git commit")
    sample_path = Path(args.sample_manifest)
    _sample_manifest, sample_data, case_strata = _load_sample(
        sample_path,
        expected_sha256=args.sample_manifest_sha256,
    )
    expected_cases = set(case_strata)
    reviewer_a, decisions_a, input_a = _load_primary_ledger(
        Path(args.primary_review_ledger_a),
        expected_sha256=args.primary_review_ledger_a_sha256,
        expected_cases=expected_cases,
        label="primary review ledger A",
    )
    reviewer_b, decisions_b, input_b = _load_primary_ledger(
        Path(args.primary_review_ledger_b),
        expected_sha256=args.primary_review_ledger_b_sha256,
        expected_cases=expected_cases,
        label="primary review ledger B",
    )
    if reviewer_a == reviewer_b:
        raise ValidationError("Primary review ledgers must have distinct reviewer IDs")
    disagreements = {
        case_id for case_id in expected_cases if decisions_a[case_id] != decisions_b[case_id]
    }
    adjudicated, adjudication_input = _load_adjudication_ledger(
        Path(args.adjudication_ledger),
        expected_sha256=args.adjudication_ledger_sha256,
        disagreement_cases=disagreements,
        primary_reviewer_ids={reviewer_a, reviewer_b},
    )
    final_decisions = {
        case_id: (decisions_a[case_id] if case_id not in disagreements else adjudicated[case_id])
        for case_id in expected_cases
    }

    route_results: dict[str, dict[str, Any]] = {}
    route_gates: dict[str, bool] = {}
    for route in ROUTE_ORDER:
        route_cases = sorted(case_id for case_id, value in case_strata.items() if value == route)
        if len(route_cases) != EXPECTED_CASES_PER_STRATUM:
            raise ValidationError(f"Exclusive stratum {route} does not contain exactly 100 cases")
        successes = sum(final_decisions[case_id] == "same_organization" for case_id in route_cases)
        interval = _wilson_interval(successes, len(route_cases))
        route_gates[route] = float(interval["lower_bound"]) >= WILSON_LOWER_BOUND_GATE
        agreements = sum(case_id not in disagreements for case_id in route_cases)
        route_results[route] = {
            "different_or_insufficient_failures": len(route_cases) - successes,
            "final_decision_counts": {
                decision: sum(final_decisions[case_id] == decision for case_id in route_cases)
                for decision in ALLOWED_DECISIONS
            },
            "primary_agreements": agreements,
            "primary_disagreements": len(route_cases) - agreements,
            "wilson_95": interval,
        }

    producer_path = Path(__file__).resolve()
    producer_sha, producer_size = _sha256_path(producer_path)
    return {
        "complete": True,
        "complete_sbir_exclusion": False,
        "counts": {
            "cases": len(expected_cases),
            "primary_agreements": len(expected_cases) - len(disagreements),
            "primary_disagreements": len(disagreements),
        },
        "covariates_ready": False,
        "estimand": ESTIMAND,
        "exclusion_eligible": False,
        "exclusion_recall": "unknown",
        "exclusive_route_results": route_results,
        "exclusive_route_validation_passed": route_gates,
        "identity_accepted": False,
        "identity_only": True,
        "inputs": {
            "adjudication_ledger": adjudication_input,
            "primary_review_ledger_a": input_a,
            "primary_review_ledger_b": input_b,
            "review_sample_manifest": {
                "path": sample_path.name,
                "sha256": _sha256_bytes(sample_data),
                "size_bytes": len(sample_data),
            },
        },
        "matching_eligible": False,
        "parameters": {
            "allowed_decisions": list(ALLOWED_DECISIONS),
            "different_and_insufficient_are_failures": True,
            "expected_cases_per_exclusive_stratum": EXPECTED_CASES_PER_STRATUM,
            "pooled_precision_reported": False,
            "wilson_confidence_level": 0.95,
            "wilson_lower_bound_gate": WILSON_LOWER_BOUND_GATE,
        },
        "producer": {
            "code_commit": code_version,
            "path": str(producer_path.relative_to(REPO_ROOT)),
            "sha256": producer_sha,
            "size_bytes": producer_size,
        },
        "rate_eligible": False,
        "ready_for_matching": False,
        "recall": "unknown",
        "schema_version": 1,
        "validation_contract": VALIDATION_CONTRACT,
    }


def _publish_report(output_dir: Path, report: Mapping[str, Any]) -> Path:
    data = json.dumps(report, indent=2, sort_keys=True).encode() + b"\n"
    sha256 = _sha256_bytes(data)
    filename = f"sbir_form_d_identity_review_validation.v1.{sha256}.json"
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / filename
    if target.exists():
        if target.read_bytes() != data:
            raise ValidationError(f"Existing content-addressed report disagrees: {target}")
        return target
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{filename}.", dir=output_dir)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()
    return target


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample-manifest", type=Path, default=DEFAULT_SAMPLE_MANIFEST)
    parser.add_argument("--sample-manifest-sha256", required=True)
    parser.add_argument("--primary-review-ledger-a", type=Path, required=True)
    parser.add_argument("--primary-review-ledger-a-sha256", required=True)
    parser.add_argument("--primary-review-ledger-b", type=Path, required=True)
    parser.add_argument("--primary-review-ledger-b-sha256", required=True)
    parser.add_argument("--adjudication-ledger", type=Path, required=True)
    parser.add_argument("--adjudication-ledger-sha256", required=True)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--code-version", required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        args = parse_args(argv)
        report = evaluate(args)
        output = _publish_report(Path(args.output_dir), report)
    except ValidationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"output": str(output), "counts": report["counts"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
