"""Regression tests for contract-award identity and dataset grain."""

import pandas as pd
import pytest

from sbir_etl.utils.award_identity import (
    AwardIdentityError,
    award_key_series,
    collapse_transactions_to_award_grain,
)


pytestmark = [pytest.mark.fast, pytest.mark.unit]


def test_complete_precomputed_award_key_is_preferred():
    frame = pd.DataFrame(
        {
            "contract_award_unique_key": ["CONT_AWD_1", " cont_awd_2 "],
            "contract_id": ["0001", "0001"],
        }
    )

    assert award_key_series(frame).tolist() == ["CONT_AWD_1", "CONT_AWD_2"]


def test_partial_precomputed_key_fails_instead_of_emitting_blank_identity():
    frame = pd.DataFrame(
        {
            "contract_award_unique_key": ["CONT_AWD_1", None],
            "piid": ["0001", "0002"],
            "agencyID": ["2100", "2100"],
            "referenced_idv_piid": ["W1", "W2"],
        }
    )

    with pytest.raises(AwardIdentityError, match="is partial"):
        award_key_series(frame)


def test_conflicting_complete_precomputed_key_aliases_fail():
    frame = pd.DataFrame(
        {
            "contract_award_unique_key": ["CONT_AWD_1", "CONT_AWD_2"],
            "generated_unique_award_id": ["cont_awd_1", "CONT_AWD_DIFFERENT"],
        }
    )

    with pytest.raises(AwardIdentityError, match="conflicting precomputed award key aliases"):
        award_key_series(frame)


def test_matching_complete_precomputed_key_aliases_are_accepted():
    frame = pd.DataFrame(
        {
            "contract_award_unique_key": ["CONT_AWD_1", " CONT_AWD_2 "],
            "generated_unique_award_id": ["cont_awd_1", "cont_awd_2"],
        }
    )

    assert award_key_series(frame).tolist() == ["CONT_AWD_1", "CONT_AWD_2"]


def test_compound_key_distinguishes_repeated_order_piid_across_parent_idvs():
    frame = pd.DataFrame(
        {
            "piid": ["0001", "0001"],
            "agencyID": ["2100", "2100"],
            "referenced_idv_piid": ["W1", "W2"],
        }
    )

    assert award_key_series(frame).tolist() == ["2100|W1|0001", "2100|W2|0001"]


@pytest.mark.parametrize(
    ("frame", "message"),
    [
        (pd.DataFrame([{"piid": "0001", "agencyID": "2100"}]), "parent IDV"),
        (
            pd.DataFrame(
                [
                    {
                        "piid": "0001",
                        "agencyID": "2100",
                        "referenced_idv_piid": None,
                    }
                ]
            ),
            "missing parent IDV",
        ),
        (
            pd.DataFrame([{"contract_id": "0001", "piid": "0001", "agencyID": "2100"}]),
            "parent IDV",
        ),
    ],
)
def test_bare_or_partial_compound_keys_fail(frame, message):
    with pytest.raises(AwardIdentityError, match=message):
        award_key_series(frame)


def test_conflicting_alias_values_fail():
    frame = pd.DataFrame(
        [
            {
                "piid": "0001",
                "PIID": "0002",
                "agencyID": "2100",
                "referenced_idv_piid": "W1",
            }
        ]
    )

    with pytest.raises(AwardIdentityError, match="conflicting PIID aliases"):
        award_key_series(frame)


def test_transaction_collapse_selects_latest_row_per_award():
    frame = pd.DataFrame(
        [
            {"contract_award_unique_key": "A", "action_date": "2023-01-01", "value": 1},
            {"contract_award_unique_key": "A", "action_date": "2023-06-01", "value": 2},
            {"contract_award_unique_key": "B", "action_date": "2023-02-01", "value": 3},
        ]
    )

    collapsed = collapse_transactions_to_award_grain(frame)

    assert collapsed["_award_key"].tolist() == ["B", "A"]
    assert dict(zip(collapsed["_award_key"], collapsed["value"], strict=True)) == {
        "A": 2,
        "B": 3,
    }
