"""Pydantic contracts for Phase II -> Phase III transition latency assets.

These contracts define the row-level shape of the four phase-transition assets:

- ``PhaseIIAward``: unified Phase II population (contracts + grants, reconciled
  against SBIR.gov when federal-system phase coding is missing).
- ``PhaseIIIContract``: FPDS Phase III contract rows, either directly coded or
  inherited from a declared Phase III parent IDV (known undercount — the
  ``sbir_phase`` flag is sparse outside of DoD). ``phase_iii_evidence``
  records which of the two produced the row.
- ``PhaseTransitionPair``: one row per matched (Phase II, Phase III) pair.
  Multi-award firms emit all valid pairs; views for "earliest" and
  "any-within-5-years" are derived downstream.
- ``PhaseTransitionSurvival``: one row per Phase II award with a
  time-to-event-or-censor frame suitable for Kaplan-Meier fitting.

Program provenance (SBIR vs. STTR) is carried on all four contracts as a
nullable ``program``, because a research question about STTR specifically
cannot be answered from an outcome table that has dropped it. Program is only
ever recorded when a source states it directly, and ``None`` means "no source
stated it" — not "not SBIR", and not "assume the majority program". Unknown-
program records are excluded from both the numerator and the denominator of
any program-specific measure and reported as their own stratum; see
``sbir_etl.models.sbir_program.program_specific_measure``, which implements
that policy so callers do not each reimplement it.

Task-order inheritance does **not** confer program. A ``parent_declared`` row
keeps ``program=None`` even when its parent IDV is ST3-coded; the reasoning is
recorded on ``PhaseIIIContract.program``.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from sbir_etl.models.sbir_program import SbirProgram

PhaseIISource = Literal["fpds_contract", "usaspending_assistance", "sbir_gov"]
IdentifierBasis = Literal["uei", "duns_crosswalk", "name_fallback"]
PhaseIIIEvidence = Literal[
    "direct_10q",
    "direct_sbir_phase",
    "direct_research",
    "parent_declared",
]

# How a Phase III row's SBIR/STTR program was established. Mirrors
# ``PhaseIIIEvidence``: it names the source of the claim, not its content.
#
# Only one value exists, and that is the finding rather than an oversight.
# FPDS Element 10Q is the single mechanism that states the program on a
# Phase III contract row: ``SR3`` means SBIR and ``ST3`` means STTR. The other
# three ``PhaseIIIEvidence`` paths establish the *phase* and say nothing about
# the program, so rows identified by them carry ``program=None``. Should a
# future path state the program directly, add its value here; do not reuse
# ``direct_10q`` for a claim 10Q did not make.
PhaseIIIProgramEvidence = Literal["direct_10q"]


class PhaseIIAward(BaseModel):
    """A single Phase II award unified across contracts, grants, and SBIR.gov."""

    award_id: str = Field(
        ...,
        description=(
            "Normalized USAspending generated award identifier for federal rows; "
            "original SBIR.gov source identifier when unique within phase, otherwise a "
            "full deterministic SBIRGOV source-row surrogate."
        ),
    )
    source_award_id: str | None = Field(
        None,
        description="Source PIID, contract, or tracking identifier retained for exact audit reconciliation.",
    )
    source_row_sha256: str | None = Field(
        None,
        description=("Full deterministic SBIR.gov source-row fingerprint; null for federal rows."),
    )
    representative_transaction_id: str | None = Field(
        None,
        description="Stable federal transaction selected as the deterministic award-state snapshot.",
    )
    source_transaction_count: int | None = Field(
        None,
        ge=1,
        description="Number of distinct Phase II-coded federal transactions collapsed into the award.",
    )
    recipient_uei: str | None = Field(None, description="12-char UEI, if known.")
    recipient_duns: str | None = Field(None, description="9-digit DUNS, if known.")
    recipient_name: str | None = Field(None, description="Firm name at time of award.")
    agency: str | None = Field(None, description="Awarding agency (top-tier).")
    sub_agency: str | None = Field(None, description="Awarding sub-agency / branch.")
    naics_code: str | None = Field(None, description="Source-reported NAICS code, if known.")
    psc_code: str | None = Field(None, description="Source-reported PSC code, if known.")
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
    program: SbirProgram | None = Field(
        None,
        description=(
            "SBIR or STTR, when a source states it directly: the canonical "
            "SBIR.gov `Program` column for `sbir_gov` rows, or the FPDS "
            "Element 10Q `research` code (SR2/ST2) for federal rows. Null "
            "whenever neither is present — never inferred from firm, agency, "
            "or any other correlate."
        ),
    )
    source: PhaseIISource = Field(
        ..., description="Federal source system this Phase II row came from."
    )
    phase_coding_reconciled: bool = Field(
        False,
        description=(
            "True if federal-system phase coding was missing and we recovered "
            "'Phase II' from an unmatched SBIR.gov source row. Exact source-ID "
            "matches retain the federal row and its false value."
        ),
    )

    model_config = ConfigDict(str_strip_whitespace=True)


class PhaseIIIContract(BaseModel):
    """A single FPDS Phase III contract row.

    Program inheritance is deliberately not implemented. A ``parent_declared``
    row is Phase III because its parent IDV declares SBIR/STTR Phase III, and
    the program is **not** inherited along that edge, for three reasons:

    1. An IDV is a contract vehicle, not a program membership. Task orders
       placed under one vehicle need not share the program of whatever coding
       or description qualified the vehicle.
    2. The parent qualifies through either a 10Q code or the Phase III
       description regex, and that regex matches SBIR *or* STTR by
       construction (``\\b(?:SBIR|STTR)\\b``, and likewise the spelled-out
       form). A description reading "SBIR/STTR Phase III" names both, so for
       description-qualified parents there is frequently no program to inherit
       even in principle.
    3. The error is asymmetric. STTR is the minority program — in the FPDS 10Q
       Phase III population it is roughly 7-12% of coded awards depending on
       agency — so a wrong inheritance pollutes the small stratum far more than
       the large one, which is exactly the stratum an STTR research question
       depends on.

    Inheriting would also be the same class of operation the unknown-program
    policy forbids elsewhere: taking the program from a *different* award
    record. If a future revision does implement it, it must be recorded as its
    own ``PhaseIIIProgramEvidence`` value naming inheritance — never as
    ``direct_10q``, which asserts the row's own 10Q code stated the program.
    """

    contract_id: str = Field(..., description="PIID or generated_unique_award_id.")
    parent_contract_id: str | None = Field(
        None,
        description=(
            "Referenced IDV identifier for a task order, if the row declares one. "
            "Present on direct and inherited rows alike; it records the vehicle, "
            "not the reason the row is Phase III."
        ),
    )
    phase_iii_evidence: PhaseIIIEvidence = Field(
        ...,
        description=(
            "How this row was identified as Phase III. The `direct_*` values come "
            "from the row's own coding; `parent_declared` means the row is a task "
            "order under an unambiguous IDV that declares SBIR/STTR Phase III."
        ),
    )
    phase_iii_inherited: bool = Field(
        False,
        description=(
            "True when the row is Phase III only by parent inheritance. Equivalent "
            "to `phase_iii_evidence == 'parent_declared'`; the two are validated to "
            "agree so a consumer can filter on either."
        ),
    )
    program: SbirProgram | None = Field(
        None,
        description=(
            "SBIR or STTR, when the row's own FPDS Element 10Q `research` code "
            "states it: SR3 -> SBIR, ST3 -> STTR. Null on every other "
            "identification path, because those establish the phase and say "
            "nothing about the program. Never inferred from firm, agency, a "
            "paired Phase II award, the parent IDV, or the match method."
        ),
    )
    program_evidence: PhaseIIIProgramEvidence | None = Field(
        None,
        description=(
            "How `program` was established. Null exactly when `program` is "
            "null; the two are validated to agree so a consumer can filter on "
            "either. Mirrors `phase_iii_evidence`, which records how the "
            "*phase* was established — the two are independent."
        ),
    )
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

    @model_validator(mode="after")
    def _inherited_matches_evidence(self) -> PhaseIIIContract:
        """Reject rows where the inheritance flag and the evidence value disagree."""

        inherited_by_evidence = self.phase_iii_evidence == "parent_declared"
        if self.phase_iii_inherited != inherited_by_evidence:
            raise ValueError(
                f"phase_iii_inherited={self.phase_iii_inherited} contradicts "
                f"phase_iii_evidence={self.phase_iii_evidence!r}"
            )
        return self

    @model_validator(mode="after")
    def _program_matches_program_evidence(self) -> PhaseIIIContract:
        """Reject a program without evidence, or evidence without a program.

        A program with no recorded evidence is an unattributed claim, and
        evidence with no program is a claim that was never made. Both are
        rejected so that `program is None` means exactly "no source stated it".
        """

        if (self.program is None) != (self.program_evidence is None):
            raise ValueError(
                f"program={self.program!r} and program_evidence="
                f"{self.program_evidence!r} must both be set or both be null"
            )
        return self


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
    phase_ii_program: SbirProgram | None = Field(
        None,
        description="`PhaseIIAward.program`, carried through unchanged. Null if unknown.",
    )
    phase_ii_end_date: date = Field(
        ..., description="Phase II period_of_performance end — latency anchor."
    )
    phase_iii_contract_id: str = Field(...)
    phase_iii_agency: str | None = Field(None)
    phase_iii_program: SbirProgram | None = Field(
        None,
        description=(
            "`PhaseIIIContract.program`, carried through unchanged. Null if "
            "unknown. Deliberately independent of `phase_ii_program`: the two "
            "sides are not reconciled and neither fills the other, so a pair "
            "with a known Phase II program and an unknown Phase III program "
            "stays unknown on the Phase III side."
        ),
    )
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
    phase_ii_program: SbirProgram | None = Field(
        None,
        description=(
            "`PhaseIIAward.program`, carried through unchanged, so a survival "
            "frame can be stratified by program. Null if unknown; an "
            "unknown-program row must be dropped from a program-specific fit "
            "rather than pooled into one — see "
            "`sbir_etl.models.sbir_program.program_specific_measure`."
        ),
    )
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
    "PhaseIIIEvidence",
    "PhaseIIIProgramEvidence",
    "PhaseTransitionPair",
    "PhaseTransitionSurvival",
]
