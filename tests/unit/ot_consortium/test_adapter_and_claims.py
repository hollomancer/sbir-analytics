"""Tests for the USAspending→OTAward adapter and the claims loader."""

import pandas as pd
import pytest

from sbir_etl.ot_consortium.claims_loader import load_claims
from sbir_etl.ot_consortium.usaspending_ot import (
    build_ot_award,
    detect_modification,
    is_ot_record,
    parse_consortia_flag,
)

pytestmark = pytest.mark.fast


@pytest.mark.parametrize(
    "value,expected",
    [
        ("Y", True),
        ("yes", True),
        ("N", False),
        ("no", False),
        ("", None),
        (None, None),
        ("maybe", None),  # unknown is never silently "No"
    ],
)
def test_parse_consortia_flag(value, expected):
    assert parse_consortia_flag(value) is expected


def test_detect_modification():
    assert detect_modification({"modification_number": "P00003"}) is True
    assert detect_modification({"modification_number": "0"}) is False
    assert detect_modification({"award_type": "Modification to OT"}) is True
    assert detect_modification({"award_type": "Definitive Contract"}) is None


def test_is_ot_record():
    assert is_ot_record({"award_type": "Other Transaction Agreement"}) is True
    assert is_ot_record({"Consortia": "Y"}) is True
    assert is_ot_record({"award_type": "Purchase Order"}) is False


def test_build_ot_award_field_mapping():
    row = {
        "contract_id": "FA8650-23-9-1234",
        "parent_idv_piid": "BASE-1",
        "vendor_uei": "CMF000000001",
        "vendor_name": "Advanced Technology International",
        "Consortia": "Y",
        "Primary Consortia Member UEI": "MEMBER0000001",
        "obligated_amount": "1,234,567",
        "awarding_agency_name": "Navy",
        "fiscal_year": "2023",
        "modification_number": "0",
    }
    award = build_ot_award(row)
    assert award.award_id == "FA8650-23-9-1234"
    assert award.parent_piid == "BASE-1"
    assert award.recipient_uei == "CMF000000001"
    assert award.consortia_flag is True
    assert award.primary_consortia_member_uei == "MEMBER0000001"
    assert award.obligation_amount == 1234567.0
    assert award.fiscal_year == 2023
    assert award.is_modification is False
    assert award.found_in_federal_data is True


def test_load_claims_alias_mapping_and_attributability():
    df = pd.DataFrame(
        [
            # Attributable: has a PIID.
            {
                "company": "Acme Inc",
                "uei": "ACME00000001",
                "piid": "FA8650-23-9-0001",
                "covered_sales": "500000",
                "fy": "2023",
            },
            # Non-attributable: aggregate total, no award handle.
            {
                "company": "Beta LLC",
                "covered_sales": "2000000",
            },
            # Attributable via firm-internal ref only.
            {
                "company": "Gamma Co",
                "internal_ref": "PROJ-42",
                "covered_sales": "100000",
            },
        ]
    )
    claims = load_claims(df)
    assert len(claims) == 3
    acme, beta, gamma = claims
    assert acme.firm_uei == "ACME00000001"
    assert acme.claimed_award_piid == "FA8650-23-9-0001"
    assert acme.is_attributable is True
    assert beta.is_attributable is False  # aggregate
    assert gamma.firm_internal_ref == "PROJ-42"
    assert gamma.is_attributable is True


def test_load_claims_from_list_of_dicts():
    claims = load_claims([{"company": "Solo", "piid": "X-23-3-0001", "obligation": "1"}])
    assert claims[0].firm_name == "Solo"
    assert claims[0].claimed_award_piid == "X-23-3-0001"


def test_load_claims_preserves_unknown_columns_in_metadata():
    claims = load_claims([{"company": "Solo", "piid": "P", "weird_extra": "keepme"}])
    assert claims[0].metadata.get("weird_extra") == "keepme"
