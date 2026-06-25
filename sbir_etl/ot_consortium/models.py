"""Pydantic models for OT consortium Phase III verification tiering.

These models cover the unit of classification (``OTAward``), the per-record
audit trail (``TierEvidenceItem`` / ``TierAssignment``), the optional audit-mode
input (``CoveredSalesClaim``), and the aggregate output (``MagnitudeReport``).

Design rule (enforced by the classifier, documented here): the tiers are NOT a
quality score to be maximized. ``T1`` is the only member-confirmed tier; the
rest are first-class *unverifiable* results. Never upgrade a tier on weak
evidence — absence of contradiction is not confirmation.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class VerificationTier(StrEnum):
    """Honest verification tier for one OT-consortium-linked award.

    - ``T1`` — member-confirmed: ``Consortia = Yes`` and the
      ``Primary Consortia Member UEI`` resolves to the claiming firm by *UEI*
      (never name alone), with a PIID 9th-position research/prototype code.
    - ``T2`` — rollup-only: obligation recorded against a known Consortium
      Management Firm (CMF) with no member UEI populated; attribution
      impossible.
    - ``T3`` — structurally invisible: modification-based consortium OT whose
      member field is unfillable by construction; member identity not derivable
      from federal data.
    - ``T4`` — no federal record: claimed award not located in USAspending/FPDS.
    """

    MEMBER_CONFIRMED = "T1_member_confirmed"
    ROLLUP_ONLY = "T2_rollup_only"
    STRUCTURALLY_INVISIBLE = "T3_structurally_invisible"
    NO_FEDERAL_RECORD = "T4_no_federal_record"


#: Tiers whose attribution cannot be verified from federal data. The magnitude
#: report surfaces the union of these as a first-class "unverifiable share" and
#: never folds it into a verified total.
UNVERIFIABLE_TIERS: frozenset[VerificationTier] = frozenset(
    {
        VerificationTier.ROLLUP_ONLY,
        VerificationTier.STRUCTURALLY_INVISIBLE,
        VerificationTier.NO_FEDERAL_RECORD,
    }
)


class FirmUEISource(StrEnum):
    """Provenance of the claiming firm's UEI used for the T1 match.

    ``T1`` is permitted when a firm cited only a name *and* that name resolves to
    a canonical SBIR-firm UEI, because the match still happens UEI-to-UEI against
    the federal member field. The provenance is recorded so name-resolved firms
    are visible and their confidence note reflects the weaker anchor.
    """

    PROVIDED = "provided"
    NAME_RESOLVED = "name_resolved"
    UNRESOLVED = "unresolved"


class OTAward(BaseModel):
    """An OT award record linked to a firm, as seen in federal data.

    This is the unit the classifier tiers. ``None`` on the DoD ``Consortia`` and
    ``Primary Consortia Member UEI`` fields means *not populated* (the ~16%+
    completion gap) — which is itself evidence, never silently treated as "No".
    """

    model_config = ConfigDict(validate_assignment=True)

    award_id: str = Field(..., description="Stable id for this OT award row (PIID or synthetic).")
    piid: str | None = Field(
        None, description="Award PIID; 9th position drives the T1 research/prototype rule."
    )
    parent_piid: str | None = Field(
        None, description="Base OT / IDV this order sits under, if any (base→order linkage)."
    )
    base_recipient_uei: str | None = Field(
        None,
        description="UEI recorded on the base/parent OT. When the base is a CMF and this order's "
        "recipient is the firm, the order-level recipient authoritatively attributes the award.",
    )
    base_recipient_name: str | None = Field(
        None, description="Recipient name recorded on the base/parent OT (CMF in consortium cases)."
    )
    recipient_uei: str | None = Field(
        None, description="FPDS recorded recipient/vendor UEI (the CMF UEI in rollup cases)."
    )
    recipient_name: str | None = Field(
        None, description="FPDS recorded recipient/vendor name (the CMF name in rollup cases)."
    )
    consortia_flag: bool | None = Field(
        None, description="DoD 'Consortia' Y/N field; None when the field is not populated."
    )
    primary_consortia_member_uei: str | None = Field(
        None, description="DoD 'Primary Consortia Member UEI'; None when not populated."
    )
    is_modification: bool | None = Field(
        None,
        description="True if this row is a modification to a base agreement (T3 signal).",
    )
    obligation_amount: float | None = Field(
        None,
        description="Obligated dollars on the record. When the CMF is the vendor this is the "
        "rollup total across members, NOT an amount attributable to the firm.",
    )
    agency: str | None = Field(None, description="Awarding agency / sub-agency.")
    fiscal_year: int | None = Field(None, description="Federal fiscal year of the action.")
    found_in_federal_data: bool = Field(
        True,
        description="False only in audit mode when a claimed award has no federal record (T4).",
    )
    metadata: dict[str, object] = Field(default_factory=dict)


class TierEvidenceItem(BaseModel):
    """One field-level fact that drove (or blocked) a tier assignment.

    Mirrors the evidence-item idiom used by transition detection so a human can
    spot-check exactly which fields were inspected and how each rule fired.
    """

    model_config = ConfigDict(validate_assignment=True)

    field: str = Field(..., description="Source field name that was inspected.")
    value: object | None = Field(None, description="Observed value of that field.")
    rule: str = Field(..., description="Which tier rule this fact bears on.")
    note: str = Field("", description="Human-readable interpretation of the fact.")


class TierAssignment(BaseModel):
    """Result of classifying one OT award: the tier plus its full audit trail."""

    model_config = ConfigDict(validate_assignment=True)

    award_id: str = Field(..., description="Award being classified.")
    tier: VerificationTier = Field(..., description="The assigned verification tier.")
    piid: str | None = Field(None, description="Award PIID (carried for the graph chain / audit).")
    parent_piid: str | None = Field(None, description="Base OT this order rolls up to, if any.")
    firm_uei: str | None = Field(None, description="Claiming firm UEI used for the T1 match.")
    firm_uei_source: FirmUEISource = Field(
        FirmUEISource.UNRESOLVED, description="Provenance of the firm UEI."
    )
    resolution_method: str | None = Field(
        None,
        description="How the member UEI linked to the firm. 'uei' for a confirmed T1 match; a "
        "'name_*' value records a REJECTED name-only near-miss that must not reach T1.",
    )
    cmf_name: str | None = Field(
        None, description="Resolved CMF (rollup vendor) canonical name when applicable."
    )
    obligation_amount: float | None = Field(
        None, description="Obligation on the record (carried through for the magnitude report)."
    )
    agency: str | None = Field(None, description="Awarding agency / sub-agency.")
    fiscal_year: int | None = Field(None, description="Federal fiscal year.")
    evidence: list[TierEvidenceItem] = Field(
        default_factory=list, description="Per-record audit trail: which fields drove the tier."
    )
    confidence_note: str = Field(
        "", description="Why this tier, and explicitly why not a higher one."
    )
    classified_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @property
    def is_verifiable(self) -> bool:
        """True only for T1 — the single member-confirmed tier."""
        return self.tier == VerificationTier.MEMBER_CONFIRMED


class CoveredSalesClaim(BaseModel):
    """One firm-reported covered-sales / Phase-III-via-OT claim (audit-mode input).

    Schema is intentionally permissive: firm-reported data is messy, so PIID and
    UEI are optional and a firm-internal reference is accepted. Aggregated
    covered-sales totals that cannot be tied to a specific award carry
    ``is_attributable = False`` — they are reported separately and never tiered.
    """

    model_config = ConfigDict(validate_assignment=True)

    claim_id: str = Field(..., description="Stable id for this claim row.")
    firm_name: str = Field(..., description="Claiming firm legal name.")
    firm_uei: str | None = Field(None, description="Claiming firm UEI; enables direct T1 match.")
    firm_uei_source: FirmUEISource = Field(
        FirmUEISource.UNRESOLVED, description="Provenance of firm_uei (set by the loader)."
    )
    firm_internal_ref: str | None = Field(
        None, description="Firm's own contract/project id when no PIID is cited."
    )
    firm_duns: str | None = Field(None, description="Legacy DUNS; fallback only.")
    claimed_award_piid: str | None = Field(None, description="PIID/order number as cited by firm.")
    claimed_parent_piid: str | None = Field(
        None, description="Base OT / IDV the order sits under, if cited."
    )
    cmf_name: str | None = Field(
        None, description="Consortium Management Firm the award flowed through, if cited."
    )
    claimed_phase_iii: bool = Field(
        True, description="Firm characterizes this as a Phase III transition."
    )
    claimed_obligation_usd: float | None = Field(
        None, ge=0, description="Dollar amount the firm attributes to itself."
    )
    agency: str | None = Field(None, description="Awarding agency / sub-agency as cited.")
    fiscal_year: int | None = Field(None, ge=1982, description="Claimed FY (SBIR began FY1982).")
    period_of_performance_start: date | None = None
    period_of_performance_end: date | None = None
    is_attributable: bool = Field(
        True,
        description="False for aggregated covered-sales totals that cannot be tied to a specific "
        "award; such dollars are reported separately and never tiered.",
    )
    source_document: str | None = Field(
        None, description="Provenance: firm cert, proposal, spreadsheet ref."
    )
    metadata: dict[str, object] = Field(default_factory=dict)


class TierBucket(BaseModel):
    """Count and obligated dollars for a single tier."""

    model_config = ConfigDict(validate_assignment=True)

    tier: VerificationTier
    count: int = 0
    obligated_usd: float = 0.0


class MagnitudeReport(BaseModel):
    """Aggregate magnitude report: counts and obligated $ per tier and breakdown.

    The unverifiable share (T2+T3+T4) is a first-class headline number and is
    never absorbed into the verified total.
    """

    model_config = ConfigDict(validate_assignment=True)

    mode: str = Field(..., description="'baseline' (population proxy) or 'audit' (claims).")
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    total_count: int = 0
    total_obligated_usd: float = 0.0

    by_tier: list[TierBucket] = Field(default_factory=list)

    verified_count: int = Field(0, description="T1 only.")
    verified_obligated_usd: float = 0.0
    unverifiable_count: int = Field(0, description="T2 + T3 + T4 — reported prominently.")
    unverifiable_obligated_usd: float = 0.0

    non_attributable_count: int = Field(
        0, description="Audit mode: claimed dollars not tied to a specific award (untiered)."
    )
    non_attributable_obligated_usd: float = 0.0

    breakdowns: dict[str, object] = Field(
        default_factory=dict, description="Nested count+$ by CMF, agency, and fiscal year."
    )
    fpds_lag_note: str = Field(
        "DoD OT actions reach FPDS/USAspending with an ~90-day reporting lag; recent fiscal "
        "years undercount and the Consortia / member-UEI fields are more sparsely populated.",
        description="Provenance caveat carried on every report.",
    )

    @property
    def unverifiable_share(self) -> float:
        """Fraction of tiered records that are unverifiable (by count)."""
        return self.unverifiable_count / self.total_count if self.total_count else 0.0
