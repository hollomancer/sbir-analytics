"""Frozen record types for candidate transition assertions (ADR-005).

Design rules encoded here rather than left to producers:

* No field has an evidential default. The legacy producer defaulted a missing
  score to ``0.5`` and then mapped it to a ``"possible"`` confidence label,
  which turned absence into a measured mid-confidence claim. A missing score is
  now a validation error, not a value.
* Typed absence is structural: a dimension carries *either* a bounded score or
  a reason it has none, never both and never neither.
* Action roles stay separate fields. Signed latency is preserved; no
  post-completion or positive-dollar filter is applied at construction time.
  Those are downstream study inclusion rules.
"""

from __future__ import annotations

import math
from datetime import date, datetime
from typing import Annotated, Any, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from sbir_etl.assertions.enums import (
    ActionRole,
    ClaimStatus,
    ContractKeyMethod,
    DimensionStatus,
    PermittedUse,
    SignalAbsentReason,
    SupportClass,
)
from sbir_etl.assertions.identifiers import (
    CLAIM_FAMILY,
    LEGACY_NAMESPACE,
    USAID_NAMESPACE,
    assertion_id,
    assertion_revision_id,
)

__all__ = [
    "ActionReference",
    "AssertionRecord",
    "AssertionSnapshotManifest",
    "DimensionAssessment",
    "InputReference",
]

_FROZEN = ConfigDict(frozen=True, extra="forbid", use_enum_values=False)

Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class DimensionAssessment(BaseModel):
    """One evidence dimension, with measurement and absence kept distinct."""

    model_config = _FROZEN

    dimension: str = Field(min_length=1)
    status: DimensionStatus
    score: float | None = None
    absent_reason: SignalAbsentReason | None = None
    detail: str | None = None

    @model_validator(mode="after")
    def _check_typed_absence(self) -> Self:
        if self.status.is_measured:
            if self.score is None:
                raise ValueError(
                    f"dimension {self.dimension!r} is MEASURED but carries no score; "
                    "a measured dimension requires a bounded, finite value "
                    "(zero is a measured no-signal)"
                )
            if not math.isfinite(self.score):
                raise ValueError(
                    f"dimension {self.dimension!r} score must be finite, got {self.score!r}"
                )
            if not 0.0 <= self.score <= 1.0:
                raise ValueError(
                    f"dimension {self.dimension!r} score must be within [0, 1], got {self.score!r}"
                )
            if self.absent_reason is not None:
                raise ValueError(
                    f"dimension {self.dimension!r} is MEASURED and must not carry "
                    f"an absent_reason (got {self.absent_reason!r})"
                )
            return self

        if self.score is not None:
            raise ValueError(
                f"dimension {self.dimension!r} has status {self.status.value!r} and "
                f"must not carry a score (got {self.score!r}); a non-measured "
                "dimension has no value, not a placeholder value"
            )
        if self.absent_reason is None:
            raise ValueError(
                f"dimension {self.dimension!r} has status {self.status.value!r} and "
                "requires a typed absent_reason"
            )
        return self


class ActionReference(BaseModel):
    """One contract action supporting an assertion, in a declared role."""

    model_config = _FROZEN

    action_key: str = Field(min_length=1)
    role: ActionRole
    action_date: date | None = None
    obligation: float | None = None


class AssertionRecord(BaseModel):
    """One immutable revision of one candidate award-to-contract assertion."""

    model_config = _FROZEN

    assertion_id: Sha256
    assertion_revision_id: Sha256
    claim_family: str = CLAIM_FAMILY

    source_row_key: str = Field(min_length=1)
    contract_key: str = Field(min_length=1)
    contract_key_method: ContractKeyMethod

    detector_method: str = Field(min_length=1)
    method_run_id: str = Field(min_length=1)

    claim_status: ClaimStatus = ClaimStatus.CANDIDATE
    support_class: SupportClass = SupportClass.C
    permitted_use: PermittedUse = PermittedUse.INVESTIGATIVE_ONLY

    dimensions: tuple[DimensionAssessment, ...] = Field(min_length=1)
    actions: tuple[ActionReference, ...] = Field(min_length=1)

    detector_selected_action_key: str = Field(min_length=1)
    earliest_award_action_key: str = Field(min_length=1)
    earliest_award_action_date: date | None = None
    earliest_positive_obligation_action_key: str | None = None
    earliest_positive_obligation_action_date: date | None = None

    award_anchor_latency_days: int | None = None
    cet_area: str | None = None

    created_at: datetime

    @model_validator(mode="after")
    def _check_record(self) -> Self:
        if self.claim_family != CLAIM_FAMILY:
            raise ValueError(
                f"claim_family must be {CLAIM_FAMILY!r} in V1, got {self.claim_family!r}"
            )
        if not self.contract_key.startswith((USAID_NAMESPACE, LEGACY_NAMESPACE)):
            raise ValueError(f"contract_key must be namespaced; got {self.contract_key!r}")
        expected_namespace = (
            USAID_NAMESPACE
            if self.contract_key_method is ContractKeyMethod.GENERATED_UNIQUE_AWARD_ID
            else LEGACY_NAMESPACE
        )
        if not self.contract_key.startswith(expected_namespace):
            raise ValueError(
                f"contract_key_method {self.contract_key_method.value!r} requires the "
                f"{expected_namespace!r} namespace; got {self.contract_key!r}"
            )

        names = [dimension.dimension for dimension in self.dimensions]
        if len(names) != len(set(names)):
            raise ValueError(f"duplicate dimension names: {sorted(names)}")

        keys = {action.action_key for action in self.actions}
        for label, key in (
            ("detector_selected_action_key", self.detector_selected_action_key),
            ("earliest_award_action_key", self.earliest_award_action_key),
            (
                "earliest_positive_obligation_action_key",
                self.earliest_positive_obligation_action_key,
            ),
        ):
            if key is not None and key not in keys:
                raise ValueError(
                    f"{label} {key!r} is not present in actions; every anchor must be "
                    "backed by a retained supporting action"
                )

        has_positive_key = self.earliest_positive_obligation_action_key is not None
        has_positive_date = self.earliest_positive_obligation_action_date is not None
        if has_positive_date and not has_positive_key:
            raise ValueError("earliest_positive_obligation_action_date requires its action key")

        expected_logical = assertion_id(
            source_row_key=self.source_row_key, contract_key=self.contract_key
        )
        if self.assertion_id != expected_logical:
            raise ValueError(
                "assertion_id is not derived from (source_row_key, contract_key); "
                "identity must be deterministic, never minted"
            )

        expected_revision = assertion_revision_id(
            logical_id=self.assertion_id, payload=self.revision_payload()
        )
        if self.assertion_revision_id != expected_revision:
            raise ValueError("assertion_revision_id does not match the canonical payload digest")
        return self

    def revision_payload(self) -> dict[str, Any]:
        """Canonical payload used to derive ``assertion_revision_id``."""
        return {
            "claim_family": self.claim_family,
            "source_row_key": self.source_row_key,
            "contract_key": self.contract_key,
            "contract_key_method": self.contract_key_method.value,
            "detector_method": self.detector_method,
            "claim_status": self.claim_status.value,
            "support_class": self.support_class.value,
            "permitted_use": self.permitted_use.value,
            "dimensions": [
                {
                    "dimension": dimension.dimension,
                    "status": dimension.status.value,
                    "score": dimension.score,
                    "absent_reason": (
                        dimension.absent_reason.value
                        if dimension.absent_reason is not None
                        else None
                    ),
                }
                for dimension in sorted(self.dimensions, key=lambda d: d.dimension)
            ],
            "actions": [
                {
                    "action_key": action.action_key,
                    "role": action.role.value,
                    "action_date": action.action_date,
                    "obligation": action.obligation,
                }
                for action in sorted(self.actions, key=lambda a: (a.action_key, a.role.value))
            ],
            "detector_selected_action_key": self.detector_selected_action_key,
            "earliest_award_action_key": self.earliest_award_action_key,
            "earliest_award_action_date": self.earliest_award_action_date,
            "earliest_positive_obligation_action_key": self.earliest_positive_obligation_action_key,
            "earliest_positive_obligation_action_date": self.earliest_positive_obligation_action_date,
            "award_anchor_latency_days": self.award_anchor_latency_days,
            "cet_area": self.cet_area,
        }


class InputReference(BaseModel):
    """One pinned input or output artifact, by content digest and row count."""

    model_config = _FROZEN

    name: str = Field(min_length=1)
    path: str = Field(min_length=1)
    sha256: Sha256
    n: int = Field(ge=0)
    gitignored: bool = False


class AssertionSnapshotManifest(BaseModel):
    """Manifest pinning one content-addressed assertion snapshot.

    Field shape follows the existing run-manifest convention in
    ``studies/ma-discovery-recall/confirmatory-run-manifest.json`` so study
    tooling can consume snapshots the same way it already consumes study runs.
    ``rule_versions`` is the addition: it is the field whose absence let an
    entity-resolution rule change retire a finished study.
    """

    model_config = _FROZEN

    snapshot_id: Sha256
    claim_family: str = CLAIM_FAMILY
    as_of_utc: datetime
    rule_versions: dict[str, str] = Field(min_length=1)
    inputs: tuple[InputReference, ...] = Field(min_length=1)
    outputs: tuple[InputReference, ...] = Field(min_length=1)
    assertion_count: int = Field(ge=0)
    logical_assertion_count: int = Field(ge=0)
    contract_key_method_counts: dict[str, int] = Field(default_factory=dict)
    citable: bool = False
    tier: str = "exploratory"
    notice: str = (
        "Candidate assertions under ADR-005: CANDIDATE / C / INVESTIGATIVE_ONLY. "
        "Not citable. Frozen study inputs remain the citability boundary."
    )

    @model_validator(mode="after")
    def _check_manifest(self) -> Self:
        if self.citable:
            raise ValueError("V1 assertion snapshots are never citable (ADR-005 §9, §14)")
        if self.logical_assertion_count > self.assertion_count:
            raise ValueError("logical_assertion_count cannot exceed assertion_count")
        return self
