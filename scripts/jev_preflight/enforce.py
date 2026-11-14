"""Offline CI enforcement for configured deterministic preflight decisions."""

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from sbir_etl.config.yaml_io import read_yaml_mapping

from .annual_report import build_annual_report_preflight, load_annual_report_claims
from .engine import assess_readiness
from .models import BlockerCode, RULESET_VERSION, ReadinessStatus


EPISTEMIC_TIER = "exploratory"


class EnforcementClaim(BaseModel):
    """Expected deterministic outcome for one configured claim."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    expected_status: ReadinessStatus
    expected_first_blocker: BlockerCode | None


class EnforcementPolicy(BaseModel):
    """Versioned CI policy for one preflight application."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    ruleset_version: str = Field(min_length=1)
    application: Literal["annual-report"]
    claims: list[EnforcementClaim] = Field(min_length=1)

    @model_validator(mode="after")
    def claim_ids_are_unique(self) -> "EnforcementPolicy":
        case_ids = [claim.case_id for claim in self.claims]
        duplicates = sorted({case_id for case_id in case_ids if case_ids.count(case_id) > 1})
        if duplicates:
            raise ValueError(f"duplicate policy case IDs: {duplicates}")
        return self


class EnforcementDecision(BaseModel):
    """Expected and observed decision for one configured claim."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str
    expected_status: ReadinessStatus
    observed_status: ReadinessStatus
    expected_first_blocker: BlockerCode | None
    observed_first_blocker: BlockerCode | None
    inputs_pinned: bool
    matches: bool


class EnforcementViolation(BaseModel):
    """One policy or decision mismatch that blocks the CI check."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    code: Literal[
        "ruleset_mismatch",
        "missing_policy_case",
        "unknown_policy_case",
        "status_mismatch",
        "first_blocker_mismatch",
        "frozen_input_invalid",
        "configuration_error",
    ]
    case_id: str | None = None
    message: str = Field(min_length=1)


class EnforcementReport(BaseModel):
    """Stable, non-citable output from deterministic CI enforcement."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    epistemic_tier: Literal["exploratory"] = "exploratory"
    citable: Literal[False] = False
    authoritative_source: Literal["deterministic_preflight"] = "deterministic_preflight"
    application: Literal["annual-report"] = "annual-report"
    ruleset_version: str
    policy_ruleset_version: str | None
    passed: bool
    decisions: list[EnforcementDecision]
    violations: list[EnforcementViolation]


def load_enforcement_policy(path: Path) -> EnforcementPolicy:
    """Load and strictly validate one enforcement policy."""

    raw = read_yaml_mapping(path, description="Jev CI enforcement policy")
    return EnforcementPolicy.model_validate(raw)


def evaluate_annual_report_policy(
    repository_root: Path,
    policy: EnforcementPolicy,
) -> EnforcementReport:
    """Compare annual-report decisions with the reviewed CI policy."""

    violations: list[EnforcementViolation] = []
    if policy.ruleset_version != RULESET_VERSION:
        violations.append(
            EnforcementViolation(
                code="ruleset_mismatch",
                message=(
                    f"Policy expects {policy.ruleset_version}; active ruleset is {RULESET_VERSION}."
                ),
            )
        )

    available_ids = set(load_annual_report_claims(repository_root))
    policy_by_id = {claim.case_id: claim for claim in policy.claims}
    policy_ids = set(policy_by_id)

    for case_id in sorted(available_ids - policy_ids):
        violations.append(
            EnforcementViolation(
                code="missing_policy_case",
                case_id=case_id,
                message=f"Annual-report claim {case_id!r} has no CI policy entry.",
            )
        )
    for case_id in sorted(policy_ids - available_ids):
        violations.append(
            EnforcementViolation(
                code="unknown_policy_case",
                case_id=case_id,
                message=f"CI policy case {case_id!r} is not in the annual-report claim registry.",
            )
        )

    decisions: list[EnforcementDecision] = []
    for case_id in sorted(available_ids & policy_ids):
        expected = policy_by_id[case_id]
        preflight = build_annual_report_preflight(repository_root, case_id)
        result = assess_readiness(preflight)
        observed_blocker = result.first_blocker.code if result.first_blocker else None
        status_matches = result.status is expected.expected_status
        blocker_matches = observed_blocker is expected.expected_first_blocker
        inputs_pinned = preflight.facts.inputs_pinned
        decisions.append(
            EnforcementDecision(
                case_id=case_id,
                expected_status=expected.expected_status,
                observed_status=result.status,
                expected_first_blocker=expected.expected_first_blocker,
                observed_first_blocker=observed_blocker,
                inputs_pinned=inputs_pinned,
                matches=status_matches and blocker_matches and inputs_pinned,
            )
        )
        if not inputs_pinned:
            violations.append(
                EnforcementViolation(
                    code="frozen_input_invalid",
                    case_id=case_id,
                    message="One or more required frozen artifacts are missing or fail hash validation.",
                )
            )
        if not status_matches:
            violations.append(
                EnforcementViolation(
                    code="status_mismatch",
                    case_id=case_id,
                    message=(
                        f"Expected status {expected.expected_status.value}; observed "
                        f"{result.status.value}."
                    ),
                )
            )
        if not blocker_matches:
            expected_value = (
                expected.expected_first_blocker.value
                if expected.expected_first_blocker is not None
                else "none"
            )
            observed_value = observed_blocker.value if observed_blocker is not None else "none"
            violations.append(
                EnforcementViolation(
                    code="first_blocker_mismatch",
                    case_id=case_id,
                    message=(
                        f"Expected first blocker {expected_value}; observed {observed_value}."
                    ),
                )
            )

    return EnforcementReport(
        ruleset_version=RULESET_VERSION,
        policy_ruleset_version=policy.ruleset_version,
        passed=not violations,
        decisions=decisions,
        violations=violations,
    )


def configuration_error_report(error: Exception) -> EnforcementReport:
    """Create a fail-closed report when policy or adapter validation cannot run."""

    return EnforcementReport(
        ruleset_version=RULESET_VERSION,
        policy_ruleset_version=None,
        passed=False,
        decisions=[],
        violations=[
            EnforcementViolation(
                code="configuration_error",
                message=f"{type(error).__name__}: {error}",
            )
        ],
    )
