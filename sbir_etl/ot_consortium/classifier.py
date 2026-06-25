"""Verification-tier classifier for OT-consortium-linked awards.

The single entry point is :func:`assign_tier`. It is pure: callers supply the
federal-record ``OTAward`` plus the *claiming firm's* UEI and its provenance, and
receive a :class:`TierAssignment` with a full per-field audit trail. The caller
(baseline asset or audit claims loader) is responsible for deriving the firm UEI;
keeping that out of the classifier means the tier rules are trivially testable.

Tier precedence (strict, never upgraded on weak evidence):

    T4  no federal record               (audit mode only)
    T1  positive member confirmation, by EITHER authoritative UEI route:
          (a) Consortia=Yes + Primary Consortia Member UEI == firm UEI, or
          (b) order recipient UEI == firm UEI under a CMF-managed base OT,
        each also requiring PIID 9th position in {3, 9}
    T3  modification-based, member field unfillable by construction
    T2  rollup / residual unverifiable attribution

T1 is checked before T3 because a *populated and matching* member/recipient field
is positive confirmation that overrides the structural-invisibility heuristic.
Route (b) recovers awards where the order records the firm as its own recipient
even though the Consortia member field is blank — authoritative because the order
recipient UEI is the legal recipient of that order. The name-collision guard
lives in T1: a UEI that mismatches the firm never reaches T1 no matter how closely
the names resemble each other.

Assumptions (also documented in docs/ot-consortium/tiers.md):
  * ``Consortia`` and ``Primary Consortia Member UEI`` are ``None`` when not
    populated; ``None`` is treated as "unknown", never as "No".
  * The PIID 9th position (1-indexed) encodes the instrument type; ``3`` =
    research, ``9`` = prototype/production qualify for T1.
  * UEI comparison is exact after upper/strip normalization. Name similarity is
    never sufficient for T1.
"""

from __future__ import annotations

from .models import (
    FirmUEISource,
    OTAward,
    TierAssignment,
    TierEvidenceItem,
    VerificationTier,
)

#: PIID 9th-position codes that qualify an award as a Phase III research /
#: prototype-production transition for T1.
T1_PIID_TYPE_CODES = frozenset({"3", "9"})


def _norm_uei(uei: str | None) -> str:
    return (uei or "").strip().upper()


def piid_ninth_position(piid: str | None) -> str | None:
    """Return the 9th character (1-indexed) of a PIID, or None if too short."""
    if not piid:
        return None
    s = str(piid).strip()
    return s[8] if len(s) >= 9 else None


def assign_tier(
    award: OTAward,
    *,
    firm_uei: str | None,
    firm_uei_source: FirmUEISource,
    registry: object,
) -> TierAssignment:
    """Classify one OT award into exactly one verification tier.

    Args:
        award: The federal-record OT award to classify.
        firm_uei: The claiming firm's UEI (None if unresolved).
        firm_uei_source: Provenance of ``firm_uei`` (provided / name-resolved).
        registry: A :class:`~sbir_etl.ot_consortium.registry.CMFRegistry`.

    Returns:
        A :class:`TierAssignment` with the tier, evidence, and confidence note.
    """
    evidence: list[TierEvidenceItem] = []
    base = {
        "award_id": award.award_id,
        "piid": award.piid,
        "parent_piid": award.parent_piid,
        "firm_uei": firm_uei,
        "firm_uei_source": firm_uei_source,
        "obligation_amount": award.obligation_amount,
        "agency": award.agency,
        "fiscal_year": award.fiscal_year,
    }

    # ---- T4: no federal record (audit mode) --------------------------------
    if not award.found_in_federal_data:
        evidence.append(
            TierEvidenceItem(
                field="found_in_federal_data",
                value=False,
                rule="T4",
                note="Claimed award not located in USAspending/FPDS.",
            )
        )
        return TierAssignment(
            tier=VerificationTier.NO_FEDERAL_RECORD,
            evidence=evidence,
            confidence_note="No federal record found; attribution cannot be verified.",
            **base,
        )

    norm_firm = _norm_uei(firm_uei)
    norm_member = _norm_uei(award.primary_consortia_member_uei)
    ninth = piid_ninth_position(award.piid)

    # ---- T1: positive member confirmation ----------------------------------
    # Requires ALL of: Consortia=Yes, populated member UEI that equals the firm
    # UEI (exact, never name-only), and a qualifying PIID 9th-position code.
    consortia_yes = award.consortia_flag is True
    member_present = bool(norm_member)
    member_matches_firm = bool(norm_firm) and norm_member == norm_firm
    piid_qualifies = ninth in T1_PIID_TYPE_CODES

    if member_present:
        evidence.append(
            TierEvidenceItem(
                field="primary_consortia_member_uei",
                value=award.primary_consortia_member_uei,
                rule="T1",
                note=(
                    "Member UEI populated."
                    if member_matches_firm
                    else "Member UEI populated "
                    "but does NOT match the claiming firm UEI (name resemblance is irrelevant)."
                ),
            )
        )

    if consortia_yes and member_matches_firm and piid_qualifies:
        evidence.append(
            TierEvidenceItem(field="consortia_flag", value=True, rule="T1", note="Consortia = Yes.")
        )
        evidence.append(
            TierEvidenceItem(
                field="piid",
                value=award.piid,
                rule="T1",
                note=f"PIID 9th position {ninth!r} indicates research/prototype-production.",
            )
        )
        note = "Member-confirmed: Consortia=Yes and member UEI matches firm by UEI."
        if firm_uei_source == FirmUEISource.NAME_RESOLVED:
            note += (
                " NOTE: firm UEI was recovered by name resolution, so the federal-to-firm link is"
                " UEI-to-UEI but the firm anchor is weaker than a firm-provided UEI."
            )
        return TierAssignment(
            tier=VerificationTier.MEMBER_CONFIRMED,
            resolution_method="uei",
            evidence=evidence,
            confidence_note=note,
            **base,
        )

    # ---- T1 (alternative route): order-level recipient under a CMF base OT --
    # When the base/parent OT is held by a CMF and THIS order records the firm as
    # its own recipient (order recipient UEI == firm UEI), the federal record
    # authoritatively attributes the award to the firm — even with the Consortia
    # member field unpopulated. This is UEI-to-UEI attribution via a different
    # field than the Consortia member UEI, so it is recorded as a distinct route.
    norm_recipient = _norm_uei(award.recipient_uei)
    order_recipient_is_firm = bool(norm_firm) and norm_recipient == norm_firm
    base_match = _base_cmf_match(registry, award)
    if base_match is not None and order_recipient_is_firm and piid_qualifies:
        evidence.append(
            TierEvidenceItem(
                field="recipient_uei",
                value=award.recipient_uei,
                rule="T1",
                note="Order records the claiming firm as its own recipient (UEI match).",
            )
        )
        evidence.append(
            TierEvidenceItem(
                field="parent_piid",
                value=award.parent_piid,
                rule="T1",
                note=f"Base OT is managed by CMF {base_match.record.cmf_id} "
                f"(matched by {base_match.method}); order recipient is authoritative.",
            )
        )
        evidence.append(
            TierEvidenceItem(
                field="piid",
                value=award.piid,
                rule="T1",
                note=f"PIID 9th position {ninth!r} indicates research/prototype-production.",
            )
        )
        note = (
            "Member-confirmed via order-level recipient: this order records the firm as its own "
            f"recipient UEI under a CMF-managed base OT ({base_match.record.canonical_name}). "
            "Authoritative even though the Consortia member field is unpopulated."
        )
        if firm_uei_source == FirmUEISource.NAME_RESOLVED:
            note += (
                " NOTE: firm UEI was recovered by name resolution (still a UEI-to-UEI match, but a"
                " weaker firm anchor than a firm-provided UEI)."
            )
        return TierAssignment(
            tier=VerificationTier.MEMBER_CONFIRMED,
            resolution_method="order_recipient_uei",
            cmf_name=base_match.record.canonical_name,
            evidence=evidence,
            confidence_note=note,
            **base,
        )

    # Record why T1 was not reached (for the audit trail) before falling through.
    t1_block = _t1_block_reason(
        consortia_yes=consortia_yes,
        member_present=member_present,
        member_matches_firm=member_matches_firm,
        piid_qualifies=piid_qualifies,
        ninth=ninth,
        norm_firm=bool(norm_firm),
    )
    # If a populated member UEI mismatched the firm, surface it as a rejected
    # name-collision near-miss in resolution_method so a human can spot-check.
    rejected_method = "name_collision" if (member_present and not member_matches_firm) else None

    # ---- T3: structurally invisible (modification-based) -------------------
    if award.is_modification is True:
        evidence.append(
            TierEvidenceItem(
                field="is_modification",
                value=True,
                rule="T3",
                note="Modification to a base agreement; member field unfillable by construction.",
            )
        )
        if award.parent_piid:
            evidence.append(
                TierEvidenceItem(
                    field="parent_piid",
                    value=award.parent_piid,
                    rule="T3",
                    note="Order rolls up to a base OT; member identity not derivable.",
                )
            )
        return TierAssignment(
            tier=VerificationTier.STRUCTURALLY_INVISIBLE,
            resolution_method=rejected_method,
            cmf_name=_cmf_name(registry, award),
            evidence=evidence,
            confidence_note="Structurally invisible (modification-based OT). " + t1_block,
            **base,
        )

    # ---- T2: rollup-only / residual unverifiable ---------------------------
    match = _match(registry, award)
    if match is not None:
        evidence.append(
            TierEvidenceItem(
                field="recipient_name" if match.method == "name" else "recipient_uei",
                value=award.recipient_name if match.method == "name" else award.recipient_uei,
                rule="T2",
                note=f"Recorded vendor is CMF {match.record.cmf_id} (matched by {match.method}); "
                "obligation is a rollup across members, not attributable.",
            )
        )
        return TierAssignment(
            tier=VerificationTier.ROLLUP_ONLY,
            resolution_method=rejected_method,
            cmf_name=match.record.canonical_name,
            evidence=evidence,
            confidence_note="Rollup-only: CMF is the recorded vendor with no usable member UEI. "
            + t1_block,
            **base,
        )

    # Residual: consortium-linked but neither confirmable nor a recognized CMF
    # rollup nor a modification. Default to the conservative unverifiable floor.
    evidence.append(
        TierEvidenceItem(
            field="consortia_flag",
            value=award.consortia_flag,
            rule="T2",
            note="Consortium-linked but attribution not establishable from federal data.",
        )
    )
    return TierAssignment(
        tier=VerificationTier.ROLLUP_ONLY,
        resolution_method=rejected_method,
        cmf_name=_cmf_name(registry, award),
        evidence=evidence,
        confidence_note="Unverifiable attribution (residual). " + t1_block,
        **base,
    )


def _t1_block_reason(
    *,
    consortia_yes: bool,
    member_present: bool,
    member_matches_firm: bool,
    piid_qualifies: bool,
    ninth: str | None,
    norm_firm: bool,
) -> str:
    """Human-readable explanation of why T1 was not reached."""
    reasons: list[str] = []
    if not consortia_yes:
        reasons.append("Consortia flag not populated as Yes")
    if not member_present:
        reasons.append("Primary Consortia Member UEI not populated")
    elif not norm_firm:
        reasons.append("claiming firm UEI unavailable to match against member UEI")
    elif not member_matches_firm:
        reasons.append("member UEI does not match claiming firm (name-only matches rejected)")
    if not piid_qualifies:
        reasons.append(f"PIID 9th position {ninth!r} not in research/prototype codes")
    return "Not T1 because: " + "; ".join(reasons) + "." if reasons else ""


def _match(registry: object, award: OTAward):  # type: ignore[no-untyped-def]
    matcher = getattr(registry, "match", None)
    if matcher is None:
        return None
    return matcher(name=award.recipient_name, uei=award.recipient_uei)


def _base_cmf_match(registry: object, award: OTAward):  # type: ignore[no-untyped-def]
    """Match the base/parent OT recipient against the CMF registry, if known."""
    matcher = getattr(registry, "match", None)
    if matcher is None or not (award.base_recipient_name or award.base_recipient_uei):
        return None
    return matcher(name=award.base_recipient_name, uei=award.base_recipient_uei)


def _cmf_name(registry: object, award: OTAward) -> str | None:
    match = _match(registry, award)
    return match.record.canonical_name if match is not None else None
