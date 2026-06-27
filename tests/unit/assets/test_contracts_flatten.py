"""Tests for flatten_contract_records — the extractor→sample schema bridge.

The nested key names (vendor.uei, vendor.duns_number, vendor.cage_code,
value.obligated_amount, period.effective_date/signed_date) were verified against
sbir_etl.models.contract_models (FederalContract / ContractParty / ContractValue /
ContractPeriod).
"""

import pandas as pd

from sbir_analytics.assets.transition.contracts import flatten_contract_records


def _nested_row(**overrides):
    """A row shaped like FederalContract.model_dump()."""
    row = {
        "contract_id": "W911NF20C0001",
        "piid": "W911NF20C0001",
        "agency_code": "9700",
        "agency_name": "DOD",
        "vendor": {
            "uei": "ABC123DEF456",
            "duns_number": "123456789",
            "name": "Acme Robotics",
            "cage_code": "1ABC1",
        },
        "value": {"obligated_amount": 500000.0},
        "period": {"effective_date": "2023-08-01", "signed_date": "2023-07-15"},
    }
    row.update(overrides)
    return row


def test_flattens_nested_vendor_value_period():
    out = flatten_contract_records(pd.DataFrame([_nested_row()]))
    r = out.iloc[0]
    assert r["vendor_uei"] == "ABC123DEF456"
    assert r["vendor_duns"] == "123456789"
    assert r["vendor_name"] == "Acme Robotics"
    assert r["vendor_cage"] == "1ABC1"
    assert r["obligated_amount"] == 500000.0
    assert r["action_date"] == "2023-08-01"
    # agency_code is renamed to the expected awarding_agency_code
    assert r["awarding_agency_code"] == "9700"
    assert r["awarding_agency_name"] == "DOD"


def test_action_date_falls_back_to_signed_date():
    row = _nested_row(period={"effective_date": None, "signed_date": "2023-07-15"})
    out = flatten_contract_records(pd.DataFrame([row]))
    assert out.iloc[0]["action_date"] == "2023-07-15"


def test_flat_seed_passes_through_unchanged():
    """An already-flat seeded sample (no nested cols) is left as-is."""
    flat = pd.DataFrame(
        [
            {
                "contract_id": "C1",
                "vendor_uei": "UEI000000001",
                "obligated_amount": 100.0,
                "action_date": "2022-01-01",
            }
        ]
    )
    out = flatten_contract_records(flat)
    assert out.iloc[0]["vendor_uei"] == "UEI000000001"
    assert out.iloc[0]["obligated_amount"] == 100.0
    assert "vendor" not in out.columns  # nothing invented


def test_does_not_clobber_existing_flat_columns():
    """If a flat target already exists, the nested value does not overwrite it."""
    row = _nested_row(vendor_uei="PRESET_UEI00")
    out = flatten_contract_records(pd.DataFrame([row]))
    assert out.iloc[0]["vendor_uei"] == "PRESET_UEI00"


def test_empty_frame_is_noop():
    empty = pd.DataFrame()
    out = flatten_contract_records(empty)
    assert out.empty


def test_flattens_real_federal_contract_model_dump():
    """Pin the bridge to the real model: a FederalContract.model_dump() must flatten.

    Guards against the nested model field names drifting out from under the bridge.
    """
    from sbir_etl.models.contract_models import (
        ContractDescription,
        ContractParty,
        ContractPeriod,
        ContractValue,
        FederalContract,
    )

    contract = FederalContract(
        contract_id="W911NF20C0001",
        piid="W911NF20C0001",
        agency_code="9700",
        agency_name="DOD",
        vendor=ContractParty(
            name="Acme", uei="ABC123DEF456", duns_number="123456789", cage_code="1ABC1"
        ),
        value=ContractValue(obligated_amount=500000.0),
        period=ContractPeriod(effective_date="2023-08-01"),
        description_info=ContractDescription(),
    )

    out = flatten_contract_records(pd.DataFrame([contract.model_dump()]))
    r = out.iloc[0]
    assert r["vendor_uei"] == "ABC123DEF456"
    assert r["vendor_duns"] == "123456789"
    assert r["obligated_amount"] == 500000.0
    # model_dump yields a date object for effective_date; the pipeline's
    # pd.to_datetime handles it. Compare on the ISO string.
    assert str(r["action_date"]) == "2023-08-01"
    assert r["awarding_agency_code"] == "9700"
