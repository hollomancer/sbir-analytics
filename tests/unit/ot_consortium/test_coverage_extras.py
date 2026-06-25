"""Targeted tests for adapter/runner edge paths (coercion, resolver, filters)."""

from dataclasses import dataclass

import pandas as pd
import pytest

from sbir_etl.ot_consortium.models import FirmUEISource, VerificationTier
from sbir_etl.ot_consortium.runner import classify_baseline, classify_claims
from sbir_etl.ot_consortium.usaspending_ot import build_ot_awards, is_ot_record
from sbir_etl.ot_consortium.claims_loader import load_claims

pytestmark = pytest.mark.fast

PIID_PROTOTYPE = "FA865023912340"


# --- usaspending_ot adapter ------------------------------------------------
def test_build_ot_awards_filters_non_ot():
    df = pd.DataFrame(
        [
            {"contract_id": "A", "award_type": "Other Transaction"},
            {"contract_id": "B", "award_type": "Purchase Order"},
        ]
    )
    awards = build_ot_awards(df, ot_only=True)
    assert [a.award_id for a in awards] == ["A"]
    # ot_only=False keeps everything.
    assert len(build_ot_awards(df, ot_only=False)) == 2


def test_build_ot_awards_empty():
    assert build_ot_awards(pd.DataFrame()) == []


def test_is_ot_via_idv_type_and_indicator():
    assert is_ot_record({"idv_type": "OT Agreement"}) is True
    assert is_ot_record({"ot_indicator": "Y"}) is True
    assert is_ot_record({"ot_indicator": "N"}) is False


def test_coercion_handles_bad_numbers():
    row = {"contract_id": "X", "obligated_amount": "not-a-number", "fiscal_year": "bad"}
    award = build_ot_awards(pd.DataFrame([row]), ot_only=False)[0]
    assert award.obligation_amount is None
    assert award.fiscal_year is None


# --- runner: registry-name linkage and award_id fallback -------------------
def test_baseline_links_via_registry_name(registry):
    """A contract that isn't flagged OT but whose vendor is a CMF is still in scope."""
    detections = pd.DataFrame([{"award_id": "award_0", "contract_id": "C1"}])
    contracts = pd.DataFrame(
        [{"contract_id": "C1", "vendor_name": "NSTXL", "award_type": "Definitive Contract"}]
    )
    awards = pd.DataFrame([{"award_id": "award_0", "Company": "X", "UEI": "U"}])
    assignments = classify_baseline(detections, contracts, awards, registry)
    assert len(assignments) == 1
    assert assignments[0].tier == VerificationTier.ROLLUP_ONLY


def test_baseline_synthesizes_award_ids(registry):
    """Awards without an award_id column get synthetic award_N ids matching scoring."""
    detections = pd.DataFrame([{"award_id": "award_0", "contract_id": "C1"}])
    contracts = pd.DataFrame(
        [
            {
                "contract_id": "C1",
                "piid": PIID_PROTOTYPE,
                "vendor_name": "NSTXL",
                "award_type": "Other Transaction",
                "Consortia": "Y",
                "Primary Consortia Member UEI": "FIRMUEI000001",
            }
        ]
    )
    awards = pd.DataFrame([{"Company": "Member Firm", "UEI": "FIRMUEI000001"}])  # no award_id
    assignments = classify_baseline(detections, contracts, awards, registry)
    assert assignments[0].firm_uei == "FIRMUEI000001"
    assert assignments[0].tier == VerificationTier.MEMBER_CONFIRMED


# --- runner: firm name resolution in audit mode ----------------------------
@dataclass
class _Rec:
    uei: str


@dataclass
class _Match:
    record: object
    method: str


class _StubResolver:
    """Minimal VendorResolver-shaped stub for name→UEI resolution."""

    def __init__(self, uei: str, method: str = "name_exact"):
        self._uei = uei
        self._method = method

    def resolve(self, *, name=None, **_):
        return _Match(record=_Rec(uei=self._uei), method=self._method)


def test_claims_name_resolved_firm_reaches_t1(registry):
    """A claim with no UEI but a resolvable name reaches T1 (UEI-to-UEI), flagged."""
    claims = load_claims([{"company": "Member Firm", "piid": PIID_PROTOTYPE, "obligation": "1000"}])
    assert claims[0].firm_uei is None
    federal = pd.DataFrame(
        [
            {
                "piid": PIID_PROTOTYPE,
                "vendor_name": "Advanced Technology International",
                "award_type": "Other Transaction",
                "Consortia": "Y",
                "Primary Consortia Member UEI": "FIRMUEI000001",
            }
        ]
    )
    resolver = _StubResolver("FIRMUEI000001")
    assignments, _ = classify_claims(claims, registry, federal_records=federal, resolver=resolver)
    assert assignments[0].tier == VerificationTier.MEMBER_CONFIRMED
    assert assignments[0].firm_uei_source == FirmUEISource.NAME_RESOLVED


def test_claims_name_resolution_via_fuzzy_method(registry):
    """A fuzzy (name_fuzzy) resolver match is still accepted as name-resolved."""
    claims = load_claims([{"company": "Membr Frm", "piid": PIID_PROTOTYPE, "obligation": "1"}])
    federal = pd.DataFrame(
        [
            {
                "piid": PIID_PROTOTYPE,
                "Consortia": "Y",
                "Primary Consortia Member UEI": "FIRMUEI000001",
                "award_type": "Other Transaction",
            }
        ]
    )
    resolver = _StubResolver("FIRMUEI000001", method="name_fuzzy")
    assignments, _ = classify_claims(claims, registry, federal_records=federal, resolver=resolver)
    assert assignments[0].firm_uei_source == FirmUEISource.NAME_RESOLVED
