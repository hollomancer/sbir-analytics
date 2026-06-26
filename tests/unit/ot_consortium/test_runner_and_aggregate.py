"""End-to-end mode tests: baseline classification, audit classification, report."""

import pandas as pd
import pytest

from sbir_etl.ot_consortium.aggregate import build_magnitude_report
from sbir_etl.ot_consortium.claims_loader import load_claims
from sbir_etl.ot_consortium.models import UNVERIFIABLE_TIERS, VerificationTier
from sbir_etl.ot_consortium.runner import (
    assignments_to_records,
    classify_baseline,
    classify_claims,
)

from .conftest import FIRM_UEI

pytestmark = pytest.mark.fast

PIID_PROTOTYPE = "FA865023912340"  # 9th char "9"


def test_classify_baseline_filters_and_classifies(registry):
    detections = pd.DataFrame(
        [
            {"award_id": "award_0", "contract_id": "C-OT-1"},  # OT consortium → classified
            {"award_id": "award_1", "contract_id": "C-PLAIN"},  # not OT → skipped
        ]
    )
    contracts = pd.DataFrame(
        [
            {
                "contract_id": "C-OT-1",
                "piid": PIID_PROTOTYPE,
                "vendor_name": "Advanced Technology International",
                "award_type": "Other Transaction Agreement",
                "Consortia": "Y",
                "Primary Consortia Member UEI": FIRM_UEI,
                "obligated_amount": 250000,
                "awarding_agency_name": "Navy",
                "fiscal_year": 2023,
            },
            {
                "contract_id": "C-PLAIN",
                "piid": "FA86502C012340",
                "vendor_name": "Some Vendor",
                "award_type": "Definitive Contract",
            },
        ]
    )
    awards = pd.DataFrame(
        [
            {"award_id": "award_0", "Company": "Member Firm", "UEI": FIRM_UEI},
            {"award_id": "award_1", "Company": "Other Firm", "UEI": "ZZZ"},
        ]
    )
    assignments = classify_baseline(detections, contracts, awards, registry)
    assert len(assignments) == 1  # plain contract filtered out
    assert assignments[0].tier == VerificationTier.MEMBER_CONFIRMED
    assert assignments[0].firm_uei == FIRM_UEI


def test_classify_baseline_empty():
    assert classify_baseline(pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), None) == []


def test_baseline_t1_via_order_recipient_base_lookup(registry):
    """Order recipient is the firm; base OT (looked up by parent_piid) is a CMF →
    authoritative T1 via the order-level recipient route, Consortia field blank."""
    detections = pd.DataFrame([{"award_id": "award_0", "contract_id": "ORDER-1"}])
    contracts = pd.DataFrame(
        [
            {
                "contract_id": "ORDER-1",
                "piid": PIID_PROTOTYPE,
                "parent_piid": "BASE-1",
                "vendor_name": "Member Firm",
                "vendor_uei": FIRM_UEI,  # order recipient is the firm
                "award_type": "Other Transaction",
                "obligated_amount": 100,
                "fiscal_year": 2023,
            },
            {  # the base OT, held by a CMF — only present for lookup
                "contract_id": "BASE-1",
                "piid": "BASE-1",
                "vendor_name": "NSTXL",
                "award_type": "Other Transaction",
            },
        ]
    )
    awards = pd.DataFrame([{"award_id": "award_0", "Company": "Member Firm", "UEI": FIRM_UEI}])
    assignments = classify_baseline(detections, contracts, awards, registry)
    assert len(assignments) == 1
    assert assignments[0].tier == VerificationTier.MEMBER_CONFIRMED
    assert assignments[0].resolution_method == "order_recipient_uei"


def test_classify_claims_t4_when_absent(registry):
    claims = load_claims(
        [{"company": "Ghost Co", "piid": "NOPE-1", "uei": "GHOST0000001", "obligation": "100"}]
    )
    assignments, non_attr = classify_claims(claims, registry, federal_records=None)
    assert len(assignments) == 1
    assert assignments[0].tier == VerificationTier.NO_FEDERAL_RECORD
    assert non_attr == []


def test_classify_claims_locates_federal_record(registry):
    claims = load_claims(
        [{"company": "Member Firm", "piid": PIID_PROTOTYPE, "uei": FIRM_UEI, "obligation": "5000"}]
    )
    federal = pd.DataFrame(
        [
            {
                "piid": PIID_PROTOTYPE,
                "vendor_name": "Advanced Technology International",
                "award_type": "Other Transaction",
                "Consortia": "Y",
                "Primary Consortia Member UEI": FIRM_UEI,
                "obligated_amount": 5000,
            }
        ]
    )
    assignments, non_attr = classify_claims(claims, registry, federal_records=federal)
    assert assignments[0].tier == VerificationTier.MEMBER_CONFIRMED


def test_classify_claims_separates_non_attributable(registry):
    claims = load_claims(
        [
            {"company": "Agg Co", "covered_sales": "9999999"},  # aggregate, no award handle
        ]
    )
    assignments, non_attr = classify_claims(claims, registry)
    assert assignments == []
    assert len(non_attr) == 1


def test_assignments_to_records_carries_audit_trail(registry):
    claims = load_claims([{"company": "Ghost", "piid": "X", "uei": "U", "obligation": "1"}])
    assignments, _ = classify_claims(claims, registry)
    records = assignments_to_records(assignments)
    assert records[0]["tier"] == str(VerificationTier.NO_FEDERAL_RECORD)
    assert isinstance(records[0]["evidence"], list)
    assert records[0]["evidence"]  # non-empty audit trail


def test_magnitude_report_unverifiable_is_first_class(registry):
    """The unverifiable share must be reported separately, never folded into verified."""
    detections = pd.DataFrame(
        [
            {"award_id": "award_0", "contract_id": "T1"},
            {"award_id": "award_1", "contract_id": "T2"},
            {"award_id": "award_2", "contract_id": "T3"},
        ]
    )
    contracts = pd.DataFrame(
        [
            {
                "contract_id": "T1",
                "piid": PIID_PROTOTYPE,
                "vendor_name": "Advanced Technology International",
                "award_type": "Other Transaction",
                "Consortia": "Y",
                "Primary Consortia Member UEI": FIRM_UEI,
                "obligated_amount": 100,
                "fiscal_year": 2023,
            },
            {
                "contract_id": "T2",
                "vendor_name": "NSTXL",
                "award_type": "Other Transaction",
                "obligated_amount": 9000,
                "fiscal_year": 2023,
            },
            {
                "contract_id": "T3",
                "piid": "W900W023P00001",
                "vendor_name": "SOSSEC",
                "award_type": "Other Transaction",
                "modification_number": "P00002",
                "obligated_amount": 500,
                "fiscal_year": 2022,
            },
        ]
    )
    awards = pd.DataFrame([{"award_id": "award_0", "Company": "Member Firm", "UEI": FIRM_UEI}])
    assignments = classify_baseline(detections, contracts, awards, registry)
    report = build_magnitude_report(assignments, mode="baseline")

    assert report.total_count == 3
    assert report.verified_count == 1
    assert report.verified_obligated_usd == 100
    assert report.unverifiable_count == 2
    assert report.unverifiable_obligated_usd == 9500
    # Verified and unverifiable partition the total — never double-counted.
    assert report.verified_count + report.unverifiable_count == report.total_count
    assert round(report.unverifiable_share, 4) == round(2 / 3, 4)
    assert "90-day" in report.fpds_lag_note or "~90" in report.fpds_lag_note


def test_magnitude_report_breakdowns_and_non_attributable(registry):
    claims = load_claims(
        [
            {
                "company": "Ghost",
                "piid": "NOPE",
                "uei": "U",
                "obligation": "100",
                "agency": "Army",
                "fy": "2023",
            },
            {"company": "Agg", "covered_sales": "5000"},  # non-attributable
        ]
    )
    assignments, non_attr = classify_claims(claims, registry)
    report = build_magnitude_report(assignments, mode="audit", non_attributable=non_attr)
    assert report.mode == "audit"
    assert report.non_attributable_count == 1
    assert report.non_attributable_obligated_usd == 5000
    assert "by_agency" in report.breakdowns
    # Every tier appears in by_tier for a stable shape.
    tiers_present = {b.tier for b in report.by_tier}
    assert set(VerificationTier) == tiers_present


def test_unverifiable_tiers_constant():
    assert VerificationTier.MEMBER_CONFIRMED not in UNVERIFIABLE_TIERS
    assert VerificationTier.ROLLUP_ONLY in UNVERIFIABLE_TIERS
    assert len(UNVERIFIABLE_TIERS) == 3
