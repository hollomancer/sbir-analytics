"""Tier classifier tests — one per tier plus the name-collision guard.

These are the acceptance fixtures called out in the spec:
  * clean member-confirmed order (T1)
  * CMF-as-vendor rollup (T2)
  * modification-based base OT (T3)
  * firm-claimed award absent from federal data (T4)
  * name-collision near-miss that must NOT reach T1
"""

import pytest

from sbir_etl.ot_consortium.classifier import assign_tier, piid_ninth_position
from sbir_etl.ot_consortium.models import FirmUEISource, OTAward, VerificationTier

from .conftest import FIRM_UEI, OTHER_FIRM_UEI

pytestmark = pytest.mark.fast

# A PIID whose 9th character (1-indexed) is "9" → prototype/production.
PIID_PROTOTYPE = "FA865023912340"
# A PIID whose 9th character is "C" → ordinary contract, not research/prototype.
PIID_CONTRACT = "FA86502C012340"


def _confirm(award: OTAward, firm_uei=FIRM_UEI, source=FirmUEISource.PROVIDED, registry=None):
    return assign_tier(award, firm_uei=firm_uei, firm_uei_source=source, registry=registry)


def test_piid_ninth_position():
    assert piid_ninth_position(PIID_PROTOTYPE) == "9"
    assert piid_ninth_position("SHORT") is None
    assert piid_ninth_position(None) is None


def test_t1_member_confirmed(registry):
    """Clean member-confirmed order: Consortia=Yes, member UEI matches, PIID ok."""
    award = OTAward(
        award_id="ORDER-1",
        piid=PIID_PROTOTYPE,
        parent_piid="BASE-1",
        recipient_name="Advanced Technology International",
        recipient_uei="CMFATI000001",
        consortia_flag=True,
        primary_consortia_member_uei=FIRM_UEI,
        obligation_amount=250_000.0,
        agency="Navy",
        fiscal_year=2023,
    )
    result = _confirm(award, registry=registry)
    assert result.tier == VerificationTier.MEMBER_CONFIRMED
    assert result.is_verifiable is True
    assert result.resolution_method == "uei"
    assert any(e.rule == "T1" for e in result.evidence)


def test_t1_requires_qualifying_piid(registry):
    """Member UEI matches but PIID 9th position is not research/prototype → not T1."""
    award = OTAward(
        award_id="ORDER-1b",
        piid=PIID_CONTRACT,
        consortia_flag=True,
        primary_consortia_member_uei=FIRM_UEI,
        recipient_name="Advanced Technology International",
    )
    result = _confirm(award, registry=registry)
    assert result.tier != VerificationTier.MEMBER_CONFIRMED
    assert "PIID 9th position" in result.confidence_note


def test_t1_requires_consortia_yes(registry):
    """Member UEI matches and PIID ok, but Consortia flag not populated → not T1."""
    award = OTAward(
        award_id="ORDER-1c",
        piid=PIID_PROTOTYPE,
        consortia_flag=None,
        primary_consortia_member_uei=FIRM_UEI,
        recipient_name="Advanced Technology International",
    )
    result = _confirm(award, registry=registry)
    assert result.tier != VerificationTier.MEMBER_CONFIRMED


def test_name_collision_must_not_reach_t1(registry):
    """Member UEI present and PIID ok, but member UEI != firm UEI despite similar
    names. Must NOT reach T1; the near-miss is flagged for human review."""
    award = OTAward(
        award_id="ORDER-2",
        piid=PIID_PROTOTYPE,
        consortia_flag=True,
        primary_consortia_member_uei=OTHER_FIRM_UEI,  # different firm
        recipient_name="Advanced Technology International",
    )
    result = _confirm(award, firm_uei=FIRM_UEI, registry=registry)
    assert result.tier != VerificationTier.MEMBER_CONFIRMED
    assert result.is_verifiable is False
    assert result.resolution_method == "name_collision"
    assert "name-only matches rejected" in result.confidence_note


def test_t2_rollup_cmf_vendor(registry):
    """CMF is the recorded vendor with no member UEI → rollup-only (T2)."""
    award = OTAward(
        award_id="ROLLUP-1",
        recipient_name="NSTXL",
        consortia_flag=None,
        primary_consortia_member_uei=None,
        obligation_amount=9_000_000.0,
    )
    result = _confirm(award, registry=registry)
    assert result.tier == VerificationTier.ROLLUP_ONLY
    assert result.cmf_name == "National Security Technology Accelerator"
    assert any(e.rule == "T2" for e in result.evidence)


def test_t2_rollup_matches_by_uei(registry):
    """Rollup detection prefers UEI: recorded vendor UEI is a known CMF."""
    award = OTAward(
        award_id="ROLLUP-2",
        recipient_uei="CMFATI000001",
        recipient_name="Some Reseller Name That Does Not Match",
        primary_consortia_member_uei=None,
    )
    result = _confirm(award, registry=registry)
    assert result.tier == VerificationTier.ROLLUP_ONLY
    assert result.cmf_name == "Advanced Technology International"


def test_t3_modification_based(registry):
    """Modification to a base agreement → structurally invisible (T3)."""
    award = OTAward(
        award_id="MOD-1",
        piid="W900W023P00001",
        parent_piid="BASE-OT-1",
        is_modification=True,
        recipient_name="SOSSEC",
        primary_consortia_member_uei=None,
    )
    result = _confirm(award, firm_uei=None, source=FirmUEISource.UNRESOLVED, registry=registry)
    assert result.tier == VerificationTier.STRUCTURALLY_INVISIBLE
    assert any(e.rule == "T3" for e in result.evidence)


def test_t1_beats_t3_when_member_confirmed(registry):
    """A modification row that still carries a matching member UEI is confirmable."""
    award = OTAward(
        award_id="MOD-2",
        piid=PIID_PROTOTYPE,
        is_modification=True,
        consortia_flag=True,
        primary_consortia_member_uei=FIRM_UEI,
        recipient_name="Advanced Technology International",
    )
    result = _confirm(award, registry=registry)
    assert result.tier == VerificationTier.MEMBER_CONFIRMED


def test_unresolved_firm_is_not_flagged_name_collision(registry):
    """Member UEI populated but the claiming firm UEI is unknown: no mismatch can
    be established, so the record must NOT be flagged as a name-collision."""
    award = OTAward(
        award_id="UNRES-1",
        piid=PIID_PROTOTYPE,
        consortia_flag=True,
        primary_consortia_member_uei="SOMEMEMBER01",
        recipient_name="NSTXL",
    )
    result = _confirm(award, firm_uei=None, source=FirmUEISource.UNRESOLVED, registry=registry)
    assert result.tier != VerificationTier.MEMBER_CONFIRMED
    assert result.resolution_method != "name_collision"
    assert result.resolution_method is None


def test_t4_no_federal_record(registry):
    """Claimed award absent from federal data → T4."""
    award = OTAward(award_id="GHOST-1", found_in_federal_data=False)
    result = _confirm(award, registry=registry)
    assert result.tier == VerificationTier.NO_FEDERAL_RECORD
    assert result.is_verifiable is False


def test_name_resolved_firm_can_reach_t1(registry):
    """A name-resolved firm UEI still permits T1 (link is UEI-to-UEI) but is noted."""
    award = OTAward(
        award_id="ORDER-3",
        piid=PIID_PROTOTYPE,
        consortia_flag=True,
        primary_consortia_member_uei=FIRM_UEI,
        recipient_name="Advanced Technology International",
    )
    result = _confirm(award, source=FirmUEISource.NAME_RESOLVED, registry=registry)
    assert result.tier == VerificationTier.MEMBER_CONFIRMED
    assert "name resolution" in result.confidence_note


def test_t1_via_order_recipient_under_cmf_base(registry):
    """Order records the firm as its own recipient under a CMF-managed base OT →
    authoritative T1 even with the Consortia member field blank."""
    award = OTAward(
        award_id="ORD-1",
        piid=PIID_PROTOTYPE,
        parent_piid="BASE-1",
        base_recipient_name="NSTXL",  # base OT held by a CMF
        recipient_uei=FIRM_UEI,  # this order's recipient is the firm
        recipient_name="Member Firm",
        consortia_flag=None,  # member field unpopulated
        primary_consortia_member_uei=None,
    )
    result = _confirm(award, firm_uei=FIRM_UEI, registry=registry)
    assert result.tier == VerificationTier.MEMBER_CONFIRMED
    assert result.resolution_method == "order_recipient_uei"
    assert result.cmf_name == "National Security Technology Accelerator"
    assert "order-level recipient" in result.confidence_note


def test_order_recipient_not_t1_when_base_not_cmf(registry):
    """Firm is the order recipient but the base is not a CMF → not a consortium
    confirmation, must not reach T1."""
    award = OTAward(
        award_id="ORD-2",
        piid=PIID_PROTOTYPE,
        parent_piid="BASE-2",
        base_recipient_name="Random Prime Inc",  # not in registry
        recipient_uei=FIRM_UEI,
    )
    result = _confirm(award, firm_uei=FIRM_UEI, registry=registry)
    assert result.tier != VerificationTier.MEMBER_CONFIRMED


def test_order_recipient_not_t1_when_recipient_differs(registry):
    """Base is a CMF but the order recipient is a different UEI → not this firm."""
    award = OTAward(
        award_id="ORD-3",
        piid=PIID_PROTOTYPE,
        parent_piid="BASE-3",
        base_recipient_name="NSTXL",
        recipient_uei="SOMEONEELSE1",
    )
    result = _confirm(award, firm_uei=FIRM_UEI, registry=registry)
    assert result.tier != VerificationTier.MEMBER_CONFIRMED


def test_order_recipient_requires_qualifying_piid(registry):
    """Order recipient under a CMF base but non-qualifying PIID → not T1."""
    award = OTAward(
        award_id="ORD-4",
        piid=PIID_CONTRACT,  # 9th position not in {3,9}
        parent_piid="BASE-4",
        base_recipient_name="NSTXL",
        recipient_uei=FIRM_UEI,
    )
    result = _confirm(award, firm_uei=FIRM_UEI, registry=registry)
    assert result.tier != VerificationTier.MEMBER_CONFIRMED


def test_residual_is_conservative_t2(registry):
    """Consortium-linked but unconfirmable and not a CMF/mod → conservative T2 floor."""
    award = OTAward(
        award_id="RESID-1",
        consortia_flag=True,
        primary_consortia_member_uei=None,
        recipient_name="Unknown Performer LLC",
    )
    result = _confirm(award, registry=registry)
    assert result.tier == VerificationTier.ROLLUP_ONLY
    assert result.is_verifiable is False
