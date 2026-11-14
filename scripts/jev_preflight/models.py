"""Strict contracts for the exploratory Jev Preflight vertical slice."""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from sbir_etl.quality.study_manifest import EvidenceStatus


EPISTEMIC_TIER = "exploratory"
RULESET_VERSION = "preflight-rules-v1"


class ReadinessStatus(StrEnum):
    """Closed readiness vocabulary selected by deterministic policy."""

    GO = "GO"
    NARROW = "NARROW"
    REDESIGN = "REDESIGN"
    STOP = "STOP"


class EvidenceLabel(StrEnum):
    """How directly one decision fact is supported."""

    OBSERVED = "OBSERVED"
    INFERRED = "INFERRED"
    UNSUPPORTED = "UNSUPPORTED"
    BLOCKED = "BLOCKED"


class SourceOutcome(StrEnum):
    """Whether the source outcome required by the claim can be obtained."""

    AVAILABLE = "available"
    REMEDIABLE = "remediable"
    IMPOSSIBLE = "impossible"
    NOT_APPLICABLE = "not_applicable"


class RequiredSourceOutcome(StrEnum):
    """Named source relationship required by a claim."""

    GENERIC = "generic"
    PUBLISHED_SAMPLE_REPRODUCTION = "published_sample_reproduction"
    CURRENT_SNAPSHOT_STRUCTURAL_CHECK = "current_snapshot_structural_check"


class BlockerCode(StrEnum):
    """Versioned deterministic blocker classes in evaluation order."""

    SOURCE_OUTCOME_IMPOSSIBLE = "source_outcome_impossible"
    SOURCE_OUTCOME_REMEDIABLE = "source_outcome_remediable"
    INPUT_UNPINNED = "input_unpinned"
    DEFINITION_MISSING = "definition_missing"
    VALIDATION_INCOMPLETE = "validation_incomplete"
    EVIDENCE_STATUS_INSUFFICIENT = "evidence_status_insufficient"


class EvidenceReference(BaseModel):
    """One inspectable repository location supporting a fact."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str = Field(min_length=1)
    field: str = Field(min_length=1)

    @field_validator("path", "field")
    @classmethod
    def reject_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value


class EvidenceItem(BaseModel):
    """One fact and its epistemic label."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    fact_id: str = Field(pattern=r"^[a-z0-9]+(?:_[a-z0-9]+)*$")
    label: EvidenceLabel
    value: bool | str
    detail: str = Field(min_length=1)
    references: list[EvidenceReference] = Field(min_length=1)


class ClaimContract(BaseModel):
    """The claim dimensions a researcher must state before preflight."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    claim: str = Field(min_length=1)
    population: str = Field(min_length=1)
    denominator: str = Field(min_length=1)
    measurement: str = Field(min_length=1)
    horizon: str = Field(min_length=1)
    decision_use: str = Field(min_length=1)
    target_evidence_status: EvidenceStatus
    required_source_outcome: RequiredSourceOutcome = RequiredSourceOutcome.GENERIC
    inputs_must_be_pinned: bool = True
    definitions_must_be_complete: bool = True
    validation_required: bool = False
    narrower_claim: str | None = Field(default=None, min_length=1)

    @field_validator(
        "claim",
        "population",
        "denominator",
        "measurement",
        "horizon",
        "decision_use",
        "narrower_claim",
    )
    @classmethod
    def reject_blank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("must not be blank")
        return value


class ReadinessFacts(BaseModel):
    """Facts consumed by deterministic readiness rules."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_outcome: SourceOutcome
    inputs_pinned: bool
    definitions_complete: bool
    validation_complete: bool
    current_evidence_status: EvidenceStatus


class PreflightInput(BaseModel):
    """Complete deterministic input for one claim decision."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    claim: ClaimContract
    facts: ReadinessFacts
    evidence: list[EvidenceItem] = Field(min_length=1)

    @model_validator(mode="after")
    def fact_evidence_is_complete(self) -> "PreflightInput":
        required = {
            "source_outcome",
            "inputs_pinned",
            "definitions_complete",
            "validation_complete",
            "current_evidence_status",
        }
        present = {item.fact_id for item in self.evidence}
        missing = sorted(required - present)
        if missing:
            raise ValueError(f"missing evidence items for facts: {missing}")
        return self


class BlockingConstraint(BaseModel):
    """One matched rule with a concrete next test."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    code: BlockerCode
    status: ReadinessStatus
    message: str = Field(min_length=1)
    minimum_next_test: str = Field(min_length=1)
    evidence_fact_ids: list[str] = Field(min_length=1)


class ReadinessResult(BaseModel):
    """Authoritative deterministic result for one preflight input."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    epistemic_tier: str = "exploratory"
    citable: bool = False
    ruleset_version: str = RULESET_VERSION
    case_id: str
    status: ReadinessStatus
    summary: str
    first_blocker: BlockingConstraint | None
    blocking_constraints: list[BlockingConstraint]
    allowed_claim_now: list[str]
    not_allowed_now: list[str]
    minimum_next_test: list[str]
    evidence: list[EvidenceItem]


class MatrixCase(BaseModel):
    """One frozen synthetic readiness case."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    input: PreflightInput
    expected_status: ReadinessStatus


class MatrixReport(BaseModel):
    """Non-citable contract report for the synthetic matrix."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    epistemic_tier: str = "exploratory"
    citable: bool = False
    synthetic_fixture: bool = True
    case_count: int
    correct_count: int
    incorrect_case_ids: list[str]
    decisions: dict[str, ReadinessStatus]


class ShadowEvaluationReport(BaseModel):
    """Private comparison of saved Jev predictions with frozen policy."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    epistemic_tier: str = "exploratory"
    citable: bool = False
    private_shadow: bool = True
    synthetic_fixture: bool = True
    case_count: int
    matched_count: int
    missing_case_ids: list[str]
    unexpected_case_ids: list[str]
    status_disagreement_case_ids: list[str]
    first_blocker_disagreement_case_ids: list[str]
    full_agreement_count: int
