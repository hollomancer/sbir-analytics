"""Regression tests for the PIID-grain bug class in Product 1's pair filter.

FPDS PIID is not a key: order numbers ("0001") recur across parent IDVs, PIIDs recur across
mods, legacy PIIDs collide across agencies. These tests pin the fixes:
  - award-grade compound target_id (never bare PIID),
  - award-grain coded-status (coded if ANY transaction carries SR3/ST3),
  - loud failure when the frame has only a bare PIID or no coding column.
"""

import pandas as pd
import pytest

from sbir_analytics.assets.phase_iii_candidates.pairing import (
    _prepare_contracts,
    award_key_series,
)


def _two_0001_orders_under_different_parents() -> pd.DataFrame:
    """Two order-"0001" contracts under DIFFERENT parent IDVs for the same firm.

    Award A (parent W1) has an SR3 transaction plus a non-coded mod -> the whole award is coded.
    Award B (parent W2) is uncoded -> a genuine candidate. A bare-PIID key collapses A and B
    into one "0001"; the compound key keeps them distinct.
    """
    return pd.DataFrame(
        [
            {"piid": "0001", "agencyID": "2100", "referenced_idv_piid": "W1", "research": "SR3",
             "vendor_uei": "UEIFIRMB00001", "awarding_agency_name": "ARMY",
             "action_date": "2022-01-01", "description": "coded phase iii base"},
            {"piid": "0001", "agencyID": "2100", "referenced_idv_piid": "W1", "research": None,
             "vendor_uei": "UEIFIRMB00001", "awarding_agency_name": "ARMY",
             "action_date": "2022-06-01", "description": "mod to the coded award"},
            {"piid": "0001", "agencyID": "2100", "referenced_idv_piid": "W2", "research": None,
             "vendor_uei": "UEIFIRMB00001", "awarding_agency_name": "ARMY",
             "action_date": "2023-01-01", "description": "uncoded follow-on under a different IDV"},
        ]
    )


def test_compound_key_keeps_distinct_parent_idv_orders_and_award_grain_coding():
    targets = _prepare_contracts(_two_0001_orders_under_different_parents())
    # Award A (SR3 anywhere) is fully excluded; award B survives as exactly one award-grade row.
    assert len(targets) == 1
    target_id = targets["target_id"].iloc[0]
    # A bare-PIID join would have produced target_id == "0001" and dropped/merged award B.
    assert target_id != "0001"
    assert "W2" in target_id  # the surviving award is the one under parent W2


def test_bare_piid_only_frame_fails_loud():
    with pytest.raises(ValueError, match="not an award key"):
        _prepare_contracts(pd.DataFrame([{"piid": "0001", "research": None, "vendor_uei": "U"}]))


def test_missing_coding_column_fails_loud():
    # No 'research' / 'sbir_phase' -> the already-coded exclusion cannot fire; must not pass silently.
    with pytest.raises(ValueError, match="no Phase III coding column"):
        _prepare_contracts(pd.DataFrame([{"piid": "0001", "agencyID": "2100", "vendor_uei": "U"}]))


def test_award_key_series_prefers_precomputed_unique_key():
    df = pd.DataFrame([{"contract_id": "C-1", "piid": "0001", "agencyID": "2100"}])
    assert list(award_key_series(df)) == ["C-1"]
