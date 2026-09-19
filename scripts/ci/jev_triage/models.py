"""Typed contracts for the exploratory Jev CI triage pilot."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


EPISTEMIC_TIER = "exploratory"


class CommandFamily(StrEnum):
    """Supported families of deterministic CI checks."""

    PYTEST = "pytest"
    RUFF = "ruff"
    MYPY = "mypy"
    DAGSTER = "dagster"
    DOCKER = "docker"
    REPOSITORY_GUARD = "repository_guard"
    UNKNOWN = "unknown"


class FailureClass(StrEnum):
    """Bounded failure categories that Jev may select."""

    CODE_DEFECT = "code_defect"
    TEST_DEFECT = "test_defect"
    KNOWN_FLAKE = "known_flake"
    DEPENDENCY = "dependency"
    RUNNER_ENVIRONMENT = "runner_environment"
    CONFIGURATION = "configuration"
    UNKNOWN = "unknown"


class OwnerArea(StrEnum):
    """Coarse repository areas for human routing."""

    IDENTITY = "identity"
    DAGSTER = "dagster"
    GRAPH = "graph"
    STUDIES = "studies"
    PACKAGING = "packaging"
    CI_INFRASTRUCTURE = "ci_infrastructure"
    GENERAL = "general"


class RecommendedAction(StrEnum):
    """Actions selected by deterministic policy, never directly by Jev."""

    RETRY_ONCE = "retry_once"
    HUMAN_TRIAGE = "human_triage"


class PolicyReason(StrEnum):
    """Stable reasons emitted by the deterministic action policy."""

    ELIGIBLE_KNOWN_FLAKE = "eligible_known_flake"
    ATTEMPT_LIMIT_REACHED = "attempt_limit_reached"
    THRESHOLD_NOT_MET = "threshold_not_met"


class FailureEnvelope(BaseModel):
    """Strict, redacted input that may cross the future Jev API boundary."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    check_name: str = Field(min_length=1, max_length=120)
    command_family: CommandFamily
    exit_code: int
    failed_test_ids: list[str] = Field(default_factory=list, max_length=20)
    exception_types: list[str] = Field(default_factory=list, max_length=20)
    diagnostic_excerpts: list[str] = Field(default_factory=list, max_length=20)
    changed_path_groups: list[str] = Field(default_factory=list, max_length=20)
    runner_os: str = Field(min_length=1, max_length=40)
    attempt_number: int = Field(ge=1, le=10)


class JevTriageDecision(BaseModel):
    """Typed decisions returned by a Jev-compatible transport."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    failure_class: FailureClass
    failure_class_confidence: float = Field(ge=0.0, le=1.0)
    owner_area: OwnerArea
    owner_area_confidence: float = Field(ge=0.0, le=1.0)
    changed_code_implicated_probability: float = Field(ge=0.0, le=1.0)
    external_service_implicated_probability: float = Field(ge=0.0, le=1.0)
    known_flake_probability: float = Field(ge=0.0, le=1.0)
    retry_success_probability: float = Field(ge=0.0, le=1.0)


class RetryPolicy(BaseModel):
    """Frozen local thresholds for a retry recommendation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    known_flake_threshold: float = Field(default=0.95, ge=0.0, le=1.0)
    retry_success_threshold: float = Field(default=0.90, ge=0.0, le=1.0)
    maximum_attempt_number: int = Field(default=1, ge=1, le=10)


class PolicyOutcome(BaseModel):
    """Deterministic action selected from a typed model decision."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    action: RecommendedAction
    reason: PolicyReason


class TriageResult(BaseModel):
    """Complete hermetic triage result."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    envelope: FailureEnvelope
    decision: JevTriageDecision
    policy_outcome: PolicyOutcome
