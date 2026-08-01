"""Phase III pairing regressions for award identity and transaction grain."""

import pandas as pd
import pytest

from sbir_analytics.assets.phase_iii_candidates.pairing import _prepare_contracts


pytestmark = [pytest.mark.fast, pytest.mark.unit]


def _repeated_order_rows() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "piid": "0001",
                "agencyID": "2100",
                "referenced_idv_piid": "W1",
                "research": "SR3",
                "vendor_uei": "UEI1",
                "awarding_agency_name": "ARMY",
                "action_date": "2022-01-01",
            },
            {
                "piid": "0001",
                "agencyID": "2100",
                "referenced_idv_piid": "W1",
                "research": None,
                "vendor_uei": "UEI1",
                "awarding_agency_name": "ARMY",
                "action_date": "2022-06-01",
            },
            {
                "piid": "0001",
                "agencyID": "2100",
                "referenced_idv_piid": "W2",
                "research": None,
                "vendor_uei": "UEI1",
                "awarding_agency_name": "ARMY",
                "action_date": "2023-01-01",
            },
            {
                "piid": "0001",
                "agencyID": "2100",
                "referenced_idv_piid": "W2",
                "research": None,
                "vendor_uei": "UEI1",
                "awarding_agency_name": "ARMY",
                "action_date": "2023-06-01",
            },
        ]
    )


def test_coded_status_and_collapse_are_applied_at_award_grain():
    targets = _prepare_contracts(_repeated_order_rows())

    assert len(targets) == 1
    assert targets.iloc[0]["target_id"] == "2100|W2|0001"
    assert targets.iloc[0]["target_action_date"] == "2023-06-01"


def test_missing_coding_column_fails_loudly():
    frame = pd.DataFrame([{"contract_award_unique_key": "A", "vendor_uei": "UEI1"}])

    with pytest.raises(ValueError, match="no Phase III coding column"):
        _prepare_contracts(frame)


def test_contract_id_is_not_treated_as_precomputed_unique_key():
    frame = pd.DataFrame(
        [{"contract_id": "0001", "piid": "0001", "agencyID": "2100", "research": None}]
    )

    with pytest.raises(ValueError, match="parent IDV"):
        _prepare_contracts(frame)
