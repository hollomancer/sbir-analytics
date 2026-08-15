"""Synthetic-only tests for SBIR↔Form D exclusive-route review validation."""

import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest


REPO_ROOT = Path(__file__).parents[3]
SCRIPT = REPO_ROOT / "scripts/data/validate_sbir_form_d_identity_reviews.py"
CODE_VERSION = "b" * 40


def _load_script() -> Any:
    spec = importlib.util.spec_from_file_location("validate_sbir_form_d_identity_reviews", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def module() -> Any:
    return _load_script()


def _jsonl(path: Path, rows: list[dict[str, Any]]) -> str:
    data = b"".join(
        (json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n").encode() for row in rows
    )
    path.write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def _product(path: Path, row_count: int) -> dict[str, Any]:
    data = path.read_bytes()
    return {
        "path": path.name,
        "row_count": row_count,
        "sha256": hashlib.sha256(data).hexdigest(),
        "size_bytes": len(data),
    }


def _sample(tmp_path: Path, module: Any) -> tuple[Path, str, dict[str, str]]:
    case_map_path = tmp_path / "private_case_map.jsonl"
    case_strata: dict[str, str] = {}
    rows: list[dict[str, Any]] = []
    case_number = 0
    for route in module.ROUTE_ORDER:
        for _ in range(100):
            case_number += 1
            case_id = f"case_{case_number:04d}"
            case_strata[case_id] = route
            rows.append(
                {
                    "case_id": case_id,
                    "case_map_contract": module.CASE_MAP_CONTRACT,
                    "exclusive_stratum": route,
                    "schema_version": 1,
                }
            )
    _jsonl(case_map_path, rows)
    manifest = {
        "complete": True,
        "complete_sbir_exclusion": False,
        "counts": {"selected_pairs_by_exclusive_stratum": dict.fromkeys(module.ROUTE_ORDER, 100)},
        "covariates_ready": False,
        "estimand": module.ESTIMAND,
        "exclusion_eligible": False,
        "exclusion_recall": "unknown",
        "exclusive_route_validation_passed": dict.fromkeys(module.ROUTE_ORDER, False),
        "human_labels_present": False,
        "identity_accepted": False,
        "identity_only": True,
        "instrument_only": True,
        "matching_eligible": False,
        "outputs": {"private_case_map": _product(case_map_path, len(rows))},
        "rate_eligible": False,
        "ready_for_matching": False,
        "recall": "unknown",
        "schema_version": 1,
    }
    manifest_path = tmp_path / "sample.manifest.json"
    data = json.dumps(manifest, indent=2, sort_keys=True).encode() + b"\n"
    manifest_path.write_bytes(data)
    return manifest_path, hashlib.sha256(data).hexdigest(), case_strata


def _write_ledgers(
    tmp_path: Path,
    module: Any,
    case_strata: dict[str, str],
) -> dict[str, Any]:
    final_by_case: dict[str, str] = {}
    case_ids_by_route = {
        route: [case_id for case_id, stratum in case_strata.items() if stratum == route]
        for route in module.ROUTE_ORDER
    }
    for index, case_id in enumerate(case_ids_by_route["exact_normalized_name"]):
        final_by_case[case_id] = "same_organization" if index < 96 else "different_organization"
    for index, case_id in enumerate(case_ids_by_route["strong_name"]):
        final_by_case[case_id] = "same_organization" if index < 95 else "insufficient_evidence"
    for case_id in case_ids_by_route["state_supported"]:
        final_by_case[case_id] = "same_organization"
    for index, case_id in enumerate(case_ids_by_route["zip_supported"]):
        final_by_case[case_id] = (
            "different_organization" if index % 2 == 0 else "insufficient_evidence"
        )

    disagreement_cases = {case_ids_by_route[route][0] for route in module.ROUTE_ORDER}
    opposite = {
        "same_organization": "different_organization",
        "different_organization": "same_organization",
        "insufficient_evidence": "same_organization",
    }
    rows_a = [
        {
            "case_id": case_id,
            "decision": final_by_case[case_id],
            "reviewer_id": "reviewer-a",
            "schema_version": 1,
        }
        for case_id in sorted(case_strata)
    ]
    rows_b = [
        {
            "case_id": case_id,
            "decision": (
                opposite[final_by_case[case_id]]
                if case_id in disagreement_cases
                else final_by_case[case_id]
            ),
            "reviewer_id": "reviewer-b",
            "schema_version": 1,
        }
        for case_id in sorted(case_strata)
    ]
    adjudication_rows = [
        {
            "adjudicator_id": "reviewer-c",
            "case_id": case_id,
            "decision": final_by_case[case_id],
            "schema_version": 1,
        }
        for case_id in sorted(disagreement_cases)
    ]
    paths = {
        "a": tmp_path / "review-a.jsonl",
        "adjudication": tmp_path / "adjudication.jsonl",
        "b": tmp_path / "review-b.jsonl",
    }
    return {
        "a": paths["a"],
        "a_sha": _jsonl(paths["a"], rows_a),
        "adjudication": paths["adjudication"],
        "adjudication_sha": _jsonl(paths["adjudication"], adjudication_rows),
        "b": paths["b"],
        "b_sha": _jsonl(paths["b"], rows_b),
        "disagreement_cases": disagreement_cases,
        "final": final_by_case,
    }


def _args(
    module: Any,
    sample_path: Path,
    sample_sha: str,
    ledgers: dict[str, Any],
    output: Path,
) -> Any:
    return module.parse_args(
        [
            "--sample-manifest",
            str(sample_path),
            "--sample-manifest-sha256",
            sample_sha,
            "--primary-review-ledger-a",
            str(ledgers["a"]),
            "--primary-review-ledger-a-sha256",
            ledgers["a_sha"],
            "--primary-review-ledger-b",
            str(ledgers["b"]),
            "--primary-review-ledger-b-sha256",
            ledgers["b_sha"],
            "--adjudication-ledger",
            str(ledgers["adjudication"]),
            "--adjudication-ledger-sha256",
            ledgers["adjudication_sha"],
            "--output-dir",
            str(output),
            "--code-version",
            CODE_VERSION,
        ]
    )


def test_synthetic_validation_enforces_wilson_boundary_and_closed_gates(
    module: Any, tmp_path: Path
) -> None:
    sample_path, sample_sha, case_strata = _sample(tmp_path, module)
    ledgers = _write_ledgers(tmp_path, module, case_strata)
    args = _args(module, sample_path, sample_sha, ledgers, tmp_path / "output")

    report = module.evaluate(args)

    assert report["counts"] == {
        "cases": 400,
        "primary_agreements": 396,
        "primary_disagreements": 4,
    }
    assert report["exclusive_route_validation_passed"] == {
        "exact_normalized_name": True,
        "state_supported": True,
        "strong_name": False,
        "zip_supported": False,
    }
    exact = report["exclusive_route_results"]["exact_normalized_name"]
    strong = report["exclusive_route_results"]["strong_name"]
    assert exact["wilson_95"]["successes"] == 96
    assert exact["wilson_95"]["lower_bound"] >= 0.90
    assert strong["wilson_95"]["successes"] == 95
    assert strong["wilson_95"]["lower_bound"] < 0.90
    assert strong["different_or_insufficient_failures"] == 5
    assert report["parameters"]["pooled_precision_reported"] is False
    for gate in (
        "complete_sbir_exclusion",
        "covariates_ready",
        "exclusion_eligible",
        "identity_accepted",
        "matching_eligible",
        "rate_eligible",
        "ready_for_matching",
    ):
        assert report[gate] is False
    assert report["recall"] == "unknown"
    for ledger_metadata in (
        report["inputs"]["primary_review_ledger_a"],
        report["inputs"]["primary_review_ledger_b"],
        report["inputs"]["adjudication_ledger"],
    ):
        assert set(ledger_metadata) == {"row_count", "sha256", "size_bytes"}

    first_path = module._publish_report(tmp_path / "output-a", report)
    second_path = module._publish_report(tmp_path / "output-b", report)
    assert first_path.name == second_path.name
    assert first_path.read_bytes() == second_path.read_bytes()


def test_incomplete_primary_ledger_fails_closed(module: Any, tmp_path: Path) -> None:
    sample_path, sample_sha, case_strata = _sample(tmp_path, module)
    ledgers = _write_ledgers(tmp_path, module, case_strata)
    rows = [json.loads(line) for line in ledgers["a"].read_bytes().splitlines()][:-1]
    ledgers["a_sha"] = _jsonl(ledgers["a"], rows)

    with pytest.raises(module.ValidationError, match="does not cover all"):
        module.evaluate(_args(module, sample_path, sample_sha, ledgers, tmp_path / "output"))


def test_primary_reviewer_ids_must_be_distinct(module: Any, tmp_path: Path) -> None:
    sample_path, sample_sha, case_strata = _sample(tmp_path, module)
    ledgers = _write_ledgers(tmp_path, module, case_strata)
    rows = [json.loads(line) for line in ledgers["b"].read_bytes().splitlines()]
    for row in rows:
        row["reviewer_id"] = "reviewer-a"
    ledgers["b_sha"] = _jsonl(ledgers["b"], rows)

    with pytest.raises(module.ValidationError, match="distinct reviewer IDs"):
        module.evaluate(_args(module, sample_path, sample_sha, ledgers, tmp_path / "output"))


@pytest.mark.parametrize("remove_required", [True, False])
def test_adjudication_must_equal_disagreements(
    module: Any, tmp_path: Path, remove_required: bool
) -> None:
    sample_path, sample_sha, case_strata = _sample(tmp_path, module)
    ledgers = _write_ledgers(tmp_path, module, case_strata)
    rows = [json.loads(line) for line in ledgers["adjudication"].read_bytes().splitlines()]
    if remove_required:
        rows.pop()
    else:
        agreement_case = next(
            case for case in case_strata if case not in ledgers["disagreement_cases"]
        )
        rows.append(
            {
                "adjudicator_id": "reviewer-c",
                "case_id": agreement_case,
                "decision": "same_organization",
                "schema_version": 1,
            }
        )
    ledgers["adjudication_sha"] = _jsonl(ledgers["adjudication"], rows)

    with pytest.raises(module.ValidationError, match="exactly|invalid or duplicate"):
        module.evaluate(_args(module, sample_path, sample_sha, ledgers, tmp_path / "output"))
