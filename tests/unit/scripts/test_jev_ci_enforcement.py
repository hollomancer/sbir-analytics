"""Tests for deterministic Jev preflight CI enforcement."""

import argparse
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from scripts.jev_preflight.cli import run_ci_annual_report
from scripts.jev_preflight.enforce import (
    EnforcementClaim,
    EnforcementPolicy,
    evaluate_annual_report_policy,
    load_enforcement_policy,
)
from scripts.jev_preflight.models import BlockerCode, ReadinessStatus


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
POLICY_PATH = REPOSITORY_ROOT / "specs" / "jev-ci-enforcement" / "policy.yaml"


def _policy() -> EnforcementPolicy:
    return load_enforcement_policy(POLICY_PATH)


def test_current_annual_report_policy_passes_offline() -> None:
    report = evaluate_annual_report_policy(REPOSITORY_ROOT, _policy())

    assert report.passed is True
    assert report.violations == []
    assert [decision.case_id for decision in report.decisions] == [
        "annual-report-published-reproduction",
        "annual-report-structural-check",
    ]
    assert all(decision.matches for decision in report.decisions)
    assert report.authoritative_source == "deterministic_preflight"
    assert report.citable is False


def test_policy_rejects_duplicate_case_ids() -> None:
    policy = _policy()

    with pytest.raises(ValidationError, match="duplicate policy case IDs"):
        EnforcementPolicy.model_validate(
            {
                **policy.model_dump(mode="json"),
                "claims": [
                    policy.claims[0].model_dump(mode="json"),
                    policy.claims[0].model_dump(mode="json"),
                ],
            }
        )


def test_ruleset_drift_fails_closed() -> None:
    policy = _policy().model_copy(update={"ruleset_version": "preflight-rules-v999"})

    report = evaluate_annual_report_policy(REPOSITORY_ROOT, policy)

    assert report.passed is False
    assert [violation.code for violation in report.violations] == ["ruleset_mismatch"]


def test_status_and_blocker_drift_both_fail() -> None:
    policy = _policy()
    structural = policy.claims[1].model_copy(
        update={
            "expected_status": ReadinessStatus.REDESIGN,
            "expected_first_blocker": BlockerCode.INPUT_UNPINNED,
        }
    )
    modified = policy.model_copy(update={"claims": [policy.claims[0], structural]})

    report = evaluate_annual_report_policy(REPOSITORY_ROOT, modified)

    assert report.passed is False
    assert [violation.code for violation in report.violations] == [
        "status_mismatch",
        "first_blocker_mismatch",
    ]
    assert report.decisions[1].matches is False


def test_policy_requires_complete_and_exact_claim_coverage() -> None:
    policy = _policy()
    unknown = EnforcementClaim(
        case_id="unknown-claim",
        expected_status=ReadinessStatus.GO,
        expected_first_blocker=None,
    )
    modified = policy.model_copy(update={"claims": [policy.claims[0], unknown]})

    report = evaluate_annual_report_policy(REPOSITORY_ROOT, modified)

    assert report.passed is False
    assert [(violation.code, violation.case_id) for violation in report.violations] == [
        ("missing_policy_case", "annual-report-structural-check"),
        ("unknown_policy_case", "unknown-claim"),
    ]


def test_cli_writes_stable_report_and_returns_success(tmp_path: Path) -> None:
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    common = {"repository_root": REPOSITORY_ROOT, "policy": POLICY_PATH}

    assert run_ci_annual_report(argparse.Namespace(**common, output=first)) == 0
    assert run_ci_annual_report(argparse.Namespace(**common, output=second)) == 0
    assert first.read_bytes() == second.read_bytes()


def test_cli_writes_failure_report_for_invalid_policy(tmp_path: Path) -> None:
    invalid_policy = tmp_path / "invalid.yaml"
    invalid_policy.write_text("schema_version: 1\nunknown: true\n", encoding="utf-8")
    output = tmp_path / "report.json"

    exit_code = run_ci_annual_report(
        argparse.Namespace(
            repository_root=REPOSITORY_ROOT,
            policy=invalid_policy,
            output=output,
        )
    )

    report = json.loads(output.read_text(encoding="utf-8"))
    assert exit_code == 1
    assert report["passed"] is False
    assert report["violations"][0]["code"] == "configuration_error"


def test_ci_workflow_has_no_live_jev_credentials_or_request() -> None:
    workflow = (REPOSITORY_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    makefile = (REPOSITORY_ROOT / "Makefile").read_text(encoding="utf-8")
    job = workflow.split("  jev-preflight:\n", maxsplit=1)[1].split("\n  docker:", maxsplit=1)[0]

    assert "TYPESAFE_API_KEY" not in job
    assert "shadow-" not in job
    assert "make check-jev-preflight" in job
    assert "ci-annual-report" in makefile
    assert "if: always()" in job


def test_ci_workflow_scopes_the_gate_to_declared_paths() -> None:
    workflow = (REPOSITORY_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    path_filter = workflow.split("            jev_preflight:\n", maxsplit=1)[1].split(
        "\n\n  jev-preflight:", maxsplit=1
    )[0]

    expected_paths = {
        "studies/sba-annual-report-tables/**",
        "scripts/jev_preflight/**",
        "specs/jev-preflight/**",
        "specs/jev-ci-enforcement/**",
        "tests/unit/scripts/test_jev_preflight.py",
        "tests/unit/scripts/test_jev_ci_enforcement.py",
        ".github/workflows/ci.yml",
        "pyproject.toml",
        "uv.lock",
    }
    assert expected_paths == {
        line.strip().removeprefix("- ").strip("'")
        for line in path_filter.splitlines()
        if line.strip().startswith("- ")
    }
