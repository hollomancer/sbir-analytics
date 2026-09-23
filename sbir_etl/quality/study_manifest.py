"""Versioned contracts for research studies and approved external evidence."""

import hashlib
import json
import unicodedata
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
    APPROVED = "approved"
    RETIRED = "retired"


class FrozenArtifact(BaseModel):
    """An exact artifact whose bytes are part of the study contract.

    An external source is acquired separately and cannot be checked during a
    source-free repository validation. Its study producer must verify the
    declared digest before use.
    """

    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    external_source: bool = False


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
    """Whether production outputs may currently be generated.

    This operational authorization is independent of evidence status. Opening
    the gate does not approve a claim, and approving a claim does not authorize
    a production run.
    """

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


def claim_boundary_sha256(
    estimand: str, permitted_claims: list[str], limitations: list[str]
) -> str:
    """Return the SHA-256 of a manifest's claim boundary in canonical JSON form.

    The digest covers ``estimand``, ``permitted_claims``, and ``limitations``,
    with lists in their listed order, so any edit, addition, removal, or
    reordering changes it. Text is NFC-normalized first, so two Unicode
    spellings of the same characters give the same digest.
    """

    def nfc(text: str) -> str:
        return unicodedata.normalize("NFC", text)

    boundary = {
        "estimand": nfc(estimand),
        "limitations": [nfc(item) for item in limitations],
        "permitted_claims": [nfc(item) for item in permitted_claims],
    }
    canonical = json.dumps(boundary, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class ClaimApproval(BaseModel):
    """One final, pinned review approving the manifest's claim boundary.

    ``claim_boundary_sha256`` binds the approval to the exact ``estimand``,
    ``permitted_claims``, and ``limitations`` that were reviewed. A later edit to
    any of them breaks the approval until a new review records the new digest.
    """

    model_config = ConfigDict(extra="forbid")

    review_path: str = Field(min_length=1)
    review_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    claim_boundary_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    approved_on: date

    @field_validator("review_path")
    @classmethod
    def reject_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("must not be blank")
        return v


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
    threshold_value: float | None = Field(default=None, gt=0.0)
    frozen_population_artifact: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def threshold_value_agrees_with_its_basis(self) -> "ValidationDesign":
        """Keep the declared basis and the quantity it is stated in consistent.

        ``decision_threshold`` is prose, so a count floor written as "10
        distinct pairs" can sit under ``threshold_basis: proportion`` and no
        text check would catch it. ``threshold_value`` restates the same
        threshold as a number the basis can be checked against.
        """
        if self.threshold_basis is None or self.threshold_value is None:
            return self
        if self.threshold_basis is ThresholdBasis.PROPORTION and self.threshold_value > 1.0:
            raise ValueError(
                f"threshold_basis 'proportion' requires threshold_value in (0, 1]; "
                f"got {self.threshold_value}. A floor stated as a count needs "
                "threshold_basis 'count_on_frozen_population'."
            )
        if (
            self.threshold_basis is ThresholdBasis.COUNT_ON_FROZEN_POPULATION
            and self.threshold_value != int(self.threshold_value)
        ):
            raise ValueError(
                f"threshold_basis 'count_on_frozen_population' requires a whole-number "
                f"threshold_value; got {self.threshold_value}"
            )
        return self

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
    the design was run as written and its outcome is on the record; ``approved``
    additionally requires the threshold to have been met and a pinned review
    approving the claim boundary.

    ``design_path`` and ``design_sha256`` together name the exact bytes that were
    evaluated, and the manifest checks that pair against ``frozen_artifacts``. A
    study may pin several designs -- a pilot and a confirmatory one -- so the path
    is required rather than inferred.

    ``confirmatory`` asserts that those bytes were fixed in git before the
    evaluated run. **The schema does not verify that claim**: it checks only that
    the hash matches the pinned design. Establishing that the freeze predates
    ``evaluated_on`` is an auditor step against git history. A result from a
    design changed after data were seen may be reported under
    ``post_hoc_analyses`` but must not be marked confirmatory.
    """

    model_config = ConfigDict(extra="forbid")

    design_path: str = Field(min_length=1)
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

    @field_validator("design_path", "metric", "interval_method", mode="after")
    @classmethod
    def reject_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("must not be blank")
        return v

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


class LiveSource(BaseModel):
    """One input this study reads from outside the repository.

    A live source cannot be frozen by bytes: it is updated by someone else, on
    their schedule. What can be frozen is the *retrieval* -- the record of what
    was fetched, when, and how large the upstream was at that moment. That
    record is what turns a later difference into a diagnosable one.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    retrieval_manifest: str = Field(min_length=1)
    upstream_measure: str = Field(min_length=1)
    identity_grain: str = Field(min_length=1)

    @field_validator("name", "retrieval_manifest", "upstream_measure", "identity_grain")
    @classmethod
    def reject_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("must not be blank")
        return v


class ReproductionTolerance(BaseModel):
    """How far one reported quantity may move on a rebuild and still agree.

    ``derivation`` carries the same weight as ``threshold_derivation`` in
    ``ValidationDesign``: a band with no stated basis is not a contract, and a
    band wide enough to admit any rebuild is a defect the derivation is meant to
    expose.
    """

    model_config = ConfigDict(extra="forbid")

    quantity: str = Field(min_length=1)
    absolute_band: int = Field(ge=0)
    derivation: str = Field(min_length=1)

    @field_validator("quantity", "derivation")
    @classmethod
    def reject_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("must not be blank")
        return v


class ReproductionContract(BaseModel):
    """What reproduction means for a study whose inputs include a live source.

    ``reproducible`` reads as bit-exact, which is unachievable against a source
    someone else updates, and so gets quietly ignored rather than enforced. A
    study that declares live sources states instead which quantities are checked
    and how far each may move.
    """

    model_config = ConfigDict(extra="forbid")

    live_sources: list[LiveSource] = Field(min_length=1)
    tolerances: list[ReproductionTolerance] = Field(min_length=1)

    @model_validator(mode="after")
    def quantities_are_distinct(self) -> "ReproductionContract":
        seen = [t.quantity for t in self.tolerances]
        duplicates = sorted({q for q in seen if seen.count(q) > 1})
        if duplicates:
            raise ValueError(f"duplicate reproduction tolerance for quantity: {duplicates}")
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
    reproduction: ReproductionContract | None = None
    claim_approval: ClaimApproval | None = None

    @model_validator(mode="after")
    def require_validation_design_after_reproducible(self) -> "StudyManifest":
        if self.evidence_status in {EvidenceStatus.VALIDATED, EvidenceStatus.APPROVED}:
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
        if self.evidence_status not in {EvidenceStatus.VALIDATED, EvidenceStatus.APPROVED}:
            return self
        status = self.evidence_status.value
        design = self.validation_design
        if design is not None and design.threshold_basis is None:
            raise ValueError(
                f"evidence_status '{status}' requires validation_design.threshold_basis"
            )
        if design is not None and design.threshold_value is None:
            raise ValueError(
                f"evidence_status '{status}' requires validation_design.threshold_value, "
                "the decision threshold restated as a number its basis can be checked against"
            )
        result = self.validation_result
        if result is None:
            raise ValueError(f"evidence_status '{status}' requires a validation_result block")
        if not result.confirmatory:
            raise ValueError(
                f"evidence_status '{status}' requires a confirmatory validation_result; a "
                "post-hoc result may be reported but cannot promote a study"
            )
        frozen_by_path = {artifact.path: artifact.sha256 for artifact in self.frozen_artifacts}
        pinned_sha = frozen_by_path.get(result.design_path)
        if pinned_sha is None:
            raise ValueError(
                f"validation_result.design_path {result.design_path!r} is not listed in "
                "frozen_artifacts; the evaluated design must be pinned"
            )
        if pinned_sha != result.design_sha256:
            raise ValueError(
                f"validation_result.design_sha256 does not match the frozen hash of "
                f"{result.design_path!r}; the evaluated design is not the pinned one"
            )
        if self.evidence_status is EvidenceStatus.APPROVED and not result.threshold_met:
            raise ValueError(
                "evidence_status 'approved' requires validation_result.threshold_met to be true"
            )
        return self

    @model_validator(mode="after")
    def approved_claim_has_pinned_review(self) -> "StudyManifest":
        """Approval is one auditable decision, not a stack of release ceremonies."""

        approval = self.claim_approval
        if self.evidence_status is not EvidenceStatus.APPROVED:
            if approval is not None:
                raise ValueError(
                    f"claim_approval is only allowed at evidence_status 'approved', not "
                    f"'{self.evidence_status.value}'"
                )
            return self
        if approval is None:
            raise ValueError("evidence_status 'approved' requires a claim_approval block")
        frozen_by_path = {artifact.path: artifact.sha256 for artifact in self.frozen_artifacts}
        pinned_sha = frozen_by_path.get(approval.review_path)
        if pinned_sha is None:
            raise ValueError(
                f"claim_approval.review_path {approval.review_path!r} is not listed in "
                "frozen_artifacts"
            )
        if pinned_sha != approval.review_sha256:
            raise ValueError(
                "claim_approval.review_sha256 does not match the frozen hash of "
                f"{approval.review_path!r}"
            )
        study_inputs = {self.validation_result.design_path} if self.validation_result else set()
        if self.validation_design and self.validation_design.frozen_population_artifact:
            study_inputs.add(self.validation_design.frozen_population_artifact)
        if approval.review_path in study_inputs:
            raise ValueError(
                f"claim_approval.review_path {approval.review_path!r} is a validation input, "
                "not a separate approval review"
            )
        if approval.claim_boundary_sha256 != claim_boundary_sha256(
            self.estimand, self.permitted_claims, self.limitations
        ):
            raise ValueError(
                "claim_approval.claim_boundary_sha256 does not match the manifest's "
                "estimand, permitted_claims, and limitations; the approved claim boundary "
                "has changed"
            )
        result = self.validation_result
        if result is not None and approval.approved_on < result.evaluated_on:
            raise ValueError("claim_approval.approved_on cannot predate the validation result")
        return self

    @model_validator(mode="after")
    def live_source_manifests_must_be_frozen(self) -> "StudyManifest":
        """A declared retrieval manifest has to be pinned to be evidence.

        Naming a path that is not in ``frozen_artifacts`` is what
        ``transition-scoring`` effectively did: its provenance chain terminated
        in ``/tmp/gsa_award_grain``, so the rebuild it later claimed could not
        be classified.
        """
        contract = self.reproduction
        if contract is None:
            return self
        frozen_paths = {artifact.path for artifact in self.frozen_artifacts}
        for source in contract.live_sources:
            if source.retrieval_manifest not in frozen_paths:
                raise ValueError(
                    f"live source {source.name!r} names retrieval_manifest "
                    f"{source.retrieval_manifest!r}, which is not listed in frozen_artifacts"
                )
        return self

    @model_validator(mode="after")
    def tolerance_quantities_are_measurable(self) -> "StudyManifest":
        """A tolerance must name a quantity some live source actually measures.

        A band on a quantity nothing reports is unfalsifiable: no rebuild can
        ever breach it, so it reads as a contract while constraining nothing.
        The upstream measure of each live source is always admissible; any other
        quantity has to be named in the study's own text so a reader can find
        what it refers to.
        """
        contract = self.reproduction
        if contract is None:
            return self
        upstream = {source.upstream_measure for source in contract.live_sources}
        described = " ".join(self.permitted_claims + self.limitations + [self.estimand])
        for tolerance in contract.tolerances:
            if tolerance.quantity in upstream:
                continue
            if tolerance.quantity not in described:
                raise ValueError(
                    f"reproduction tolerance names quantity {tolerance.quantity!r}, which is "
                    "neither an upstream_measure nor mentioned in the study's estimand, "
                    "permitted_claims, or limitations; a band on an unreported quantity "
                    "cannot be breached"
                )
        return self

    @model_validator(mode="after")
    def promoted_live_source_study_declares_reproduction(self) -> "StudyManifest":
        """At ``reproducible`` and above, a declared live source needs a contract.

        The schema cannot tell whether a study *has* an external input -- that
        is an auditor judgement. It can require that a study which says it has
        one also says what reproduction means for it.
        """
        if self.evidence_status is EvidenceStatus.EXPLORATORY:
            return self
        if self.evidence_status is EvidenceStatus.RETIRED:
            return self
        contract = self.reproduction
        if contract is not None and not contract.tolerances:
            raise ValueError(
                f"evidence_status '{self.evidence_status.value}' with declared live sources "
                "requires at least one reproduction tolerance"
            )
        return self


def load_study_manifest(path: Path) -> StudyManifest:
    """Load and validate a study manifest from YAML."""

    raw = read_yaml_mapping(path, description="study manifest")
    return StudyManifest.model_validate(raw)


__all__ = [
    "ClaimApproval",
    "EvidenceStatus",
    "FrozenArtifact",
    "IdentityPolicy",
    "ImplementationReference",
    "LiveSource",
    "MaterializationGate",
    "StudyManifest",
    "ReproductionContract",
    "ReproductionTolerance",
    "ThresholdBasis",
    "ValidationDesign",
    "ValidationResult",
    "claim_boundary_sha256",
    "load_study_manifest",
]
