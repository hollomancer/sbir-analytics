"""Tests for normalize_contract_columns — the extractor→sample column bridge.

The extractor writes the FLAT ``transition_models.FederalContract`` schema, so the
bridge is a set of flat renames (obligation_amount -> obligated_amount, start_date ->
action_date, agency -> awarding_agency_name); vendor_uei/duns/name already match.
"""

import datetime

import pandas as pd

from sbir_analytics.assets.transition.contracts import normalize_contract_columns


def test_normalizes_real_extractor_model_dump():
    """A real transition_models.FederalContract dump normalizes to the sample schema."""
    from sbir_etl.models.transition_models import FederalContract

    contract = FederalContract(
        contract_id="W911NF20C0001",
        vendor_uei="ABC123DEF456",
        vendor_duns="123456789",
        vendor_name="Acme Robotics",
        obligation_amount=500000.0,
        start_date=datetime.date(2023, 8, 1),
        agency="Department of Defense",
    )

    out = normalize_contract_columns(pd.DataFrame([contract.model_dump()]))
    r = out.iloc[0]

    # Already-flat fields pass through.
    assert r["vendor_uei"] == "ABC123DEF456"
    assert r["vendor_duns"] == "123456789"
    assert r["vendor_name"] == "Acme Robotics"
    assert r["contract_id"] == "W911NF20C0001"
    # Renamed fields are populated from their extractor sources.
    assert r["obligated_amount"] == 500000.0  # <- obligation_amount
    assert str(r["action_date"]) == "2023-08-01"  # <- start_date
    assert r["awarding_agency_name"] == "Department of Defense"  # <- agency


def test_canonical_seed_passes_through_unchanged():
    """A seed already using canonical names is not overwritten by a source column."""
    df = pd.DataFrame(
        [
            {
                "contract_id": "C1",
                "vendor_uei": "UEI000000001",
                "obligated_amount": 100.0,  # canonical already present
                "obligation_amount": 999.0,  # source must NOT clobber it
                "action_date": "2022-01-01",
            }
        ]
    )
    out = normalize_contract_columns(df)
    assert out.iloc[0]["obligated_amount"] == 100.0  # unchanged


def test_empty_frame_is_noop():
    assert normalize_contract_columns(pd.DataFrame()).empty


def test_raw_usaspending_style_names_still_aliased():
    """Defensive raw aliases (uei/federal_action_obligation) still work for seeds."""
    df = pd.DataFrame([{"uei": "UEI1", "federal_action_obligation": 7.0}])
    out = normalize_contract_columns(df)
    assert out.iloc[0]["vendor_uei"] == "UEI1"
    assert out.iloc[0]["obligated_amount"] == 7.0
