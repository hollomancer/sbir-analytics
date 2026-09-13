"""Versioned contracts for research studies and externally citable evidence."""

from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..config.yaml_io import read_yaml_mapping


class EvidenceStatus(StrEnum):
    """The review and reproducibility level reached by a study.

    This epistemic status is independent of operational materialization authorization.
    A reproducible study may have an open or closed materialization gate.
    """

    EXPLORATORY = "exploratory"
    REPRODUCIBLE = "reproducible"
    VALIDATED = "validated"
    CITABLE = "citable"
    RETIRED = "retired"


class FrozenArtifact(BaseModel):
    """A repository artifact whose exact bytes are part of the study contract."""

    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class ImplementationReference(BaseModel):
    """A checked-in implementation entry point supporting the study."""

    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1)
    symbol: str = Field(min_length=1)


class IdentityPolicy(BaseModel):
    """The entity-resolution contract used by the study."""

    model_config = ConfigDict(extra="forbid")

    strategy: str = Field(min_length=1)
    version: str = Field(min_length=1)
    negative_evidence_allowed: bool


class MaterializationGate(BaseModel):
    """Whether production outputs may currently be generated or quoted."""

    model_config = ConfigDict(extra="forbid")

    allowed: bool
    blockers: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_blocker_when_closed(self) -> "MaterializationGate":
        if not self.allowed and not self.blockers:
            raise ValueError("a closed materialization gate must name at least one blocker")
        if self.allowed and self.blockers:
            raise ValueError("an open materialization gate cannot name blockers")
        return self


class ThresholdBasis(StrEnum):
    """What kind of quantity the decision threshold is stated in.

    An absolute count is only meaningful against a population that was frozen
    with the design; a count floor over a population that shrinks as capture
    proceeds becomes unreachable for reasons unrelated to the study's quality.
    """

    PROPORTION = "proportion"
    COUNT_ON_FROZEN_POPULATION = "count_on_frozen_population"


class ValidationDesign(BaseModel):
    """What the study must show, written before the data is seen.

    The evidence-tier contract checks that a result is pinned. This block also
    records whether the study could distinguish success from failure for its
    addressable population. For a census or enumeration, the fields describe
    expected coverage and reconciliation criteria rather than an effect size.

    ``threshold_basis`` and ``frozen_population_artifact`` are optional while a
    study is below ``validated`` so that existing designs keep loading; the
    manifest validator requires ``threshold_basis`` at ``validated`` and above.
    """

    model_config = ConfigDict(extra="forbid")

    addressable_population: str = Field(min_length=1)
    expected_yield: str = Field(min_length=1)
    decision_threshold: str = Field(min_length=1)
    threshold_derivation: str = Field(min_length=1)
    threshold_basis: ThresholdBasis | None = None
    frozen_population_artifact: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def count_threshold_requires_frozen_population(self) -> "ValidationDesign":
        if (
            self.threshold_basis is ThresholdBasis.COUNT_ON_FROZEN_POPULATION
            and self.frozen_population_artifact is None
        ):
            raise ValueError(
                "a count threshold requires frozen_population_artifact naming the "
                "population the count is taken over"
            )
        return self

    @field_validator(
        "addressable_population",
        "expected_yield",
        "decision_threshold",
        "threshold_derivation",
        "frozen_population_artifact",
        mode="after",
    )
    @classmethod
    def reject_blank(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            raise ValueError("must not be blank")
        return v


class ValidationResult(BaseModel):
    """What the preregistered validation design produced when it was run.

    A result is recorded with its uncertainty and travels with every number the
    study emits. ``threshold_met`` is recorded, not required: ``validated`` means
    the design was run as written and its outcome is on the record; ``citable``
    additionally requires the threshold to have been met. ``confirmatory`` is
    true only when ``design_sha256`` was fixed in git before the evaluated run;
    a result from a design changed after data were seen may be reported under
    ``post_hoc_analyses`` but cannot be confirmatory.
    """

    model_config = ConfigDict(extra="forbid")

    design_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    evaluated_on: date
    metric: str = Field(min_length=1)
    numerator: int = Field(ge=0)
    denominator: int = Field(ge=1)
    interval_low: float = Field(ge=0.0, le=1.0)
    interval_high: float = Field(ge=0.0, le=1.0)
    interval_method: str = Field(min_length=1)
    threshold_met: bool
    confirmatory: bool
    post_hoc_analyses: list[str] = Field(default_factory=list)

    @property
    def point_estimate(self) -> float:
        return self.numerator / self.denominator

    @model_validator(mode="after")
    def interval_is_coherent(self) -> "ValidationResult":
        if self.numerator > self.denominator:
            raise ValueError("numerator cannot exceed denominator")
        if self.interval_low > self.interval_high:
            raise ValueError("interval_low cannot exceed interval_high")
        point = self.point_estimate
        if not (self.interval_low <= point <= self.interval_high):
            raise ValueError(
                f"point estimate {point:.4f} lies outside the reported interval "
                f"[{self.interval_low}, {self.interval_high}]"
            )
        return self


class StudyManifest(BaseModel):
    """The machine-checkable epistemic contract for one study."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1]
    study_id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    title: str = Field(min_length=1)
    evidence_status: EvidenceStatus
    research_questions: list[str] = Field(min_length=1)
    estimand: str = Field(min_length=1)
    frozen_artifacts: list[FrozenArtifact] = Field(min_length=1)
    implementation: list[ImplementationReference] = Field(min_length=1)
    identity_policy: IdentityPolicy
    materialization: MaterializationGate
    permitted_claims: list[str] = Field(min_length=1)
    limitations: list[str] = Field(min_length=1)
    validation_design: ValidationDesign | None = None
    validation_result: ValidationResult | None = None

    @model_validator(mode="after")
    def require_validation_design_after_reproducible(self) -> "StudyManifest":
        if self.evidence_status in {EvidenceStatus.VALIDATED, EvidenceStatus.CITABLE}:
            if self.validation_design is None:
                raise ValueError(
                    f"evidence_status '{self.evidence_status}' requires a validation_design block"
                )
        return self

    @model_validator(mode="after")
    def frozen_population_must_be_a_frozen_artifact(self) -> "StudyManifest":
        design = self.validation_design
        if design is not None and design.frozen_population_artifact is not None:
            frozen_paths = {artifact.path for artifact in self.frozen_artifacts}
            if design.frozen_population_artifact not in frozen_paths:
                raise ValueError(
                    "validation_design.frozen_population_artifact "
                    f"{design.frozen_population_artifact!r} is not listed in frozen_artifacts"
                )
        return self

    @model_validator(mode="after")
    def require_confirmatory_result_after_reproducible(self) -> "StudyManifest":
        if self.evidence_status not in {EvidenceStatus.VALIDATED, EvidenceStatus.CITABLE}:
            return self
        status = self.evidence_status.value
        design = self.validation_design
        if design is not None and design.threshold_basis is None:
            raise ValueError(
                f"evidence_status '{status}' requires validation_design.threshold_basis"
            )
        result = self.validation_result
        if result is None:
            raise ValueError(f"evidence_status '{status}' requires a validation_result block")
        if not result.confirmatory:
            raise ValueError(
                f"evidence_status '{status}' requires a confirmatory validation_result; a "
                "post-hoc result may be reported but cannot promote a study"
            )
        frozen_hashes = {artifact.sha256 for artifact in self.frozen_artifacts}
        if result.design_sha256 not in frozen_hashes:
            raise ValueError(
                "validation_result.design_sha256 does not match any frozen artifact; the "
                "evaluated design must be pinned in frozen_artifacts"
            )
        if self.evidence_status is EvidenceStatus.CITABLE and not result.threshold_met:
            raise ValueError(
                "evidence_status 'citable' requires validation_result.threshold_met to be true"
            )
        return self


def load_study_manifest(path: Path) -> StudyManifest:
    """Load and validate a study manifest from YAML."""

    raw = read_yaml_mapping(path, description="study manifest")
    return StudyManifest.model_validate(raw)


__all__ = [
    "EvidenceStatus",
    "FrozenArtifact",
    "IdentityPolicy",
    "ImplementationReference",
    "MaterializationGate",
    "StudyManifest",
    "ThresholdBasis",
    "ValidationDesign",
    "ValidationResult",
    "load_study_manifest",
]
