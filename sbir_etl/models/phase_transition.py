"""Pydantic contracts for Phase II -> Phase III transition latency assets.

These contracts define the row-level shape of the four phase-transition assets:

- ``PhaseIIAward``: unified Phase II population (contracts + grants, reconciled
  against SBIR.gov when federal-system phase coding is missing).
- ``PhaseIIIContract``: FPDS Phase III contract rows (known undercount — the
  ``sbir_phase`` flag is sparse outside of DoD).
- ``PhaseTransitionPair``: one row per matched (Phase II, Phase III) pair.
  Multi-award firms emit all valid pairs; views for "earliest" and
  "any-within-5-years" are derived downstream.
- ``PhaseTransitionSurvival``: one row per Phase II award with a
  time-to-event-or-censor frame suitable for Kaplan-Meier fitting.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

PhaseIISource = Literal["fpds_contract", "usaspending_assistance", "sbir_gov"]
IdentifierBasis = Literal["uei", "duns_crosswalk", "name_fallback"]


class PhaseIIAward(BaseModel):
    """A single Phase II award unified across contracts, grants, and SBIR.gov."""

    award_id: str = Field(..., description="Stable award identifier from source system.")
    recipient_uei: str | None = Field(None, description="12-char UEI, if known.")
    recipient_duns: str | None = Field(None, description="9-digit DUNS, if known.")
    recipient_name: str | None = Field(None, description="Firm name at time of award.")
    agency: str | None = Field(None, description="Awarding agency (top-tier).")
    sub_agency: str | None = Field(None, description="Awarding sub-agency / branch.")
    award_amount: float | None = Field(None, description="Obligated amount in USD.")
    award_date: date | None = Field(None, description="Award action date.")
    period_of_performance_start: date | None = Field(
        None, description="Phase II period-of-performance start."
    )
    period_of_performance_end: date | None = Field(
        None,
        description=(
            "Phase II period-of-performance current end date. This is the anchor "
            "used for latency: `Phase III action_date - this field`."
        ),
    )
    source: PhaseIISource = Field(
        ..., description="Federal source system this Phase II row came from."
    )
    phase_coding_reconciled: bool = Field(
        False,
        description=(
            "True if federal-system phase coding was missing and we recovered "
            "'Phase II' by joining against SBIR.gov on award_id / agency_tracking."
        ),
    )

    model_config = ConfigDict(str_strip_whitespace=True)


class PhaseIIIContract(BaseModel):
    """A single FPDS Phase III contract row."""

    contract_id: str = Field(..., description="PIID or generated_unique_award_id.")
    recipient_uei: str | None = Field(None, description="12-char UEI, if known.")
    recipient_duns: str | None = Field(None, description="9-digit DUNS, if known.")
    recipient_name: str | None = Field(None, description="Vendor name at time of award.")
    agency: str | None = Field(None, description="Awarding agency (top-tier).")
    sub_agency: str | None = Field(None, description="Awarding sub-agency.")
    obligated_amount: float | None = Field(None, description="Federal action obligation in USD.")
    action_date: date = Field(..., description="FPDS action_date — Phase III start anchor.")
    period_of_performance_start: date | None = Field(None)
    period_of_performance_end: date | None = Field(None)

    model_config = ConfigDict(str_strip_whitespace=True)


class PhaseTransitionPair(BaseModel):
    """One row per (Phase II, subsequent Phase III) candidate pair."""

    recipient_uei: str | None = Field(None, description="Match key — UEI preferred.")
    recipient_duns: str | None = Field(None, description="Fallback match key for pre-2022 rows.")
    identifier_basis: IdentifierBasis = Field(
        ..., description="Which identifier produced the join."
    )
    phase_ii_award_id: str = Field(..., description="Phase II award_id.")
    phase_ii_source: PhaseIISource
    phase_ii_agency: str | None = Field(None)
    phase_ii_end_date: date = Field(
        ..., description="Phase II period_of_performance end — latency anchor."
    )
    phase_iii_contract_id: str = Field(...)
    phase_iii_agency: str | None = Field(None)
    phase_iii_action_date: date = Field(..., description="Phase III action date — latency anchor.")
    latency_days: int = Field(
        ...,
        description=(
            "`phase_iii_action_date - phase_ii_end_date` in days. Negative values "
            "are preserved (Phase III can legally precede Phase II end)."
        ),
    )
    same_agency: bool = Field(
        ..., description="True if Phase II and Phase III share top-tier agency."
    )

    model_config = ConfigDict(str_strip_whitespace=True)


class PhaseTransitionSurvival(BaseModel):
    """One row per Phase II award with a KM-ready time-to-event frame.

    Phase IIs without a matched Phase III are right-censored at the configured
    data-cut date.
    """

    phase_ii_award_id: str = Field(...)
    recipient_uei: str | None = Field(None)
    recipient_duns: str | None = Field(None)
    phase_ii_agency: str | None = Field(None)
    phase_ii_end_date: date = Field(...)
    event_observed: bool = Field(
        ..., description="True iff a matched Phase III was observed before the data cut."
    )
    event_date: date = Field(
        ...,
        description=(
            "For observed events: earliest Phase III action_date. "
            "For censored rows: the data-cut date."
        ),
    )
    time_days: int = Field(
        ...,
        description=(
            "Days from `phase_ii_end_date` to `event_date`. Can be negative for "
            "observed events where Phase III preceded Phase II end."
        ),
    )

    model_config = ConfigDict(str_strip_whitespace=True)


__all__ = [
    "IdentifierBasis",
    "PhaseIIAward",
    "PhaseIISource",
    "PhaseIIIContract",
    "PhaseTransitionPair",
    "PhaseTransitionSurvival",
]
