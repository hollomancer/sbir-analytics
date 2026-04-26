"""Pydantic model and signal-class enum for Phase III candidate surfacing.

A ``PhaseIIICandidate`` is one row emitted by the candidate-surfacing pipeline:
a tuple of (prior award, target, signal class) carrying a composite score in
``[0, 1]``, a HIGH-confidence flag, an ``evidence_ref`` pointer into the
per-candidate NDJSON bundle, and per-signal subscores.

The three signal classes share scoring infrastructure but differ in ingestion
corpus, cadence, and precision targets:

- ``RETROSPECTIVE``: FPDS/USAspending contracts that fit Phase III criteria
  but are not coded as such (Element 10Q gap). Precision gate: 0.85.
- ``DIRECTED``: SAM.gov Opportunities notices in ``{sole_source, justification,
  notice_of_intent, award}`` — the statutorily typical Phase III path.
- ``FOLLOWON``: competitive solicitations topically adjacent to a prior
  Phase I/II scope. Not statutory Phase III — always labeled "follow-on
  candidate".
"""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class SignalClass(StrEnum):
    """Candidate signal class — which surfacing pipeline produced the row."""

    RETROSPECTIVE = "retrospective"
    DIRECTED = "directed"
    FOLLOWON = "followon"


TargetType = Literal["fpds_contract", "opportunity"]


class PhaseIIICandidate(BaseModel):
    """One (prior_award, target, signal_class) candidate row.

    Row-level contract for ``data/processed/phase_iii_candidates.parquet``.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    candidate_id: str = Field(..., description="Stable candidate identifier.")
    signal_class: SignalClass = Field(
        ..., description="Which surfacing pipeline produced this row."
    )
    prior_award_id: str = Field(
        ..., description="Upstream Phase I/II award id the candidate is scored against."
    )
    target_type: TargetType = Field(
        ..., description="Corpus the target came from: FPDS contract or SAM.gov opportunity."
    )
    target_id: str = Field(..., description="Identifier of the target (contract_id or notice_id).")
    candidate_score: float = Field(
        ..., ge=0.0, le=1.0, description="Composite score in [0, 1]."
    )
    is_high_confidence: bool = Field(
        ..., description="True iff candidate_score >= the signal-class HIGH threshold."
    )
    evidence_ref: str | None = Field(
        None,
        description=(
            "Pointer into the evidence NDJSON bundle (typically the candidate_id used as "
            "the bundle line key)."
        ),
    )

    # Per-signal subscores (all optional; 0.0 = signal absent or not scored for this class).
    agency_continuity_score: float = Field(0.0, ge=0.0, le=1.0)
    timing_proximity_score: float = Field(0.0, ge=0.0, le=1.0)
    competition_type_score: float = Field(0.0, ge=0.0, le=1.0)
    patent_signal_score: float = Field(0.0, ge=0.0, le=1.0)
    cet_alignment_score: float = Field(0.0, ge=0.0, le=1.0)
    text_similarity_score: float = Field(0.0, ge=0.0, le=1.0)
    lineage_language_score: float = Field(0.0, ge=0.0, le=1.0)

    generated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="When the row was produced."
    )


__all__ = [
    "PhaseIIICandidate",
    "SignalClass",
    "TargetType",
]
