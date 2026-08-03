"""Tests for the fixed, cross-firm Phase III placebo."""

from datetime import date

import pandas as pd
import pytest

from sbir_analytics.assets.phase_iii_census.criteria import (
    build_dropoff_ladder,
    build_sensitivity_grid,
)
from sbir_analytics.assets.phase_iii_negative_controls import placebo as placebo_module
from sbir_analytics.assets.phase_iii_negative_controls.placebo import (
    PLACEBO_SEED,
    PlaceboInputError,
    build_placebo_census_tables,
    permute_prior_end_dates_across_firms,
)


pytestmark = pytest.mark.fast
DATA_CUT = date(2025, 12, 31)


def _pair(prior: int, target: int, prior_end: object, *, firm: str) -> dict[str, object]:
    return {
        "prior_award_id": f"PRIOR-{prior}",
        "prior_recipient_uei": firm,
        "prior_agency": "DEPARTMENT A",
        "prior_sub_agency": "COMPONENT A",
        "prior_naics_code": "541715",
        "prior_psc_code": "AC13",
        "prior_period_of_performance_end": prior_end,
        "target_id": f"TARGET-{target}",
        "target_recipient_uei": firm,
        "target_agency": "DEPARTMENT A",
        "target_sub_agency": "COMPONENT A",
        "target_naics_code": "541715",
        "target_psc_code": "AC13",
        "target_action_date": "2024-01-15",
        "target_competition_type": "FULL AND OPEN COMPETITION",
        "target_obligated_amount": 100.0,
        "target_research": None,
        "target_sbir_phase": None,
        "target_transaction_id": f"TRANSACTION-{target}",
        "target_contract_key": f"CONTRACT-{target}",
        "agency_match_level": "office",
    }


@pytest.fixture
def pairs() -> pd.DataFrame:
    return pd.DataFrame(
        [
            _pair(1, 1, "2018-01-31", firm="FIRM-A"),
            _pair(1, 2, "2018-01-31", firm="FIRM-A"),
            _pair(2, 3, "2019-02-28", firm="FIRM-A"),
            _pair(3, 4, "2020-03-31", firm="FIRM-B"),
            _pair(4, 5, "2021-04-30", firm="FIRM-B"),
            _pair(5, 6, "2022-05-31", firm="FIRM-C"),
            _pair(6, 7, "2023-06-30", firm="FIRM-D"),
        ]
    )


def _award_dates(frame: pd.DataFrame) -> pd.DataFrame:
    return (
        frame.drop_duplicates("prior_award_id")
        .assign(
            prior_period_of_performance_end=lambda value: pd.to_datetime(
                value["prior_period_of_performance_end"]
            )
        )
        .loc[
            :,
            ["prior_award_id", "prior_recipient_uei", "prior_period_of_performance_end"],
        ]
    )


def test_placebo_is_fixed_cross_firm_and_preserves_fanout(pairs: pd.DataFrame) -> None:
    assert PLACEBO_SEED == 20260801

    first = permute_prior_end_dates_across_firms(pairs)
    second = permute_prior_end_dates_across_firms(pairs)

    pd.testing.assert_frame_equal(first, second)
    pd.testing.assert_frame_equal(
        first.drop(columns="prior_period_of_performance_end"),
        pairs.drop(columns="prior_period_of_performance_end"),
    )
    assert first.groupby("prior_award_id")["prior_period_of_performance_end"].nunique().eq(1).all()

    before = _award_dates(pairs)
    after = _award_dates(first)
    pd.testing.assert_series_equal(
        after["prior_period_of_performance_end"].sort_values().reset_index(drop=True),
        before["prior_period_of_performance_end"].sort_values().reset_index(drop=True),
        check_names=False,
    )
    before_by_firm = before.groupby("prior_recipient_uei")["prior_period_of_performance_end"].agg(
        set
    )
    for row in after.itertuples(index=False):
        assert row.prior_period_of_performance_end not in before_by_firm[row.prior_recipient_uei]


def test_placebo_mapping_is_independent_of_pair_row_order(pairs: pd.DataFrame) -> None:
    baseline = permute_prior_end_dates_across_firms(pairs).set_index("target_transaction_id")
    reordered = pairs.sample(frac=1, random_state=17)
    permuted = permute_prior_end_dates_across_firms(reordered).set_index("target_transaction_id")

    pd.testing.assert_series_equal(
        baseline["prior_period_of_performance_end"].sort_index(),
        permuted["prior_period_of_performance_end"].sort_index(),
    )


@pytest.mark.parametrize(
    ("column", "value", "message"),
    [
        ("prior_award_id", " ", "must have a prior_award_id"),
        ("prior_recipient_uei", " ", "must have a prior_recipient_uei"),
        (
            "prior_period_of_performance_end",
            "not-a-date",
            "unparsable nonblank value",
        ),
    ],
)
def test_placebo_rejects_invalid_keys_and_dates(
    pairs: pd.DataFrame,
    column: str,
    value: str,
    message: str,
) -> None:
    invalid = pairs.copy()
    invalid.loc[0, column] = value

    with pytest.raises(PlaceboInputError, match=message):
        permute_prior_end_dates_across_firms(invalid)


def test_placebo_rejects_conflicting_dates_within_prior_award(pairs: pd.DataFrame) -> None:
    invalid = pairs.copy()
    invalid.loc[1, "prior_period_of_performance_end"] = "2022-01-01"

    with pytest.raises(PlaceboInputError, match="map to exactly one prior_period"):
        permute_prior_end_dates_across_firms(invalid)


def test_placebo_rejects_conflicting_firms_within_prior_award(pairs: pd.DataFrame) -> None:
    invalid = pairs.copy()
    invalid.loc[1, "prior_recipient_uei"] = "FIRM-Z"

    with pytest.raises(PlaceboInputError, match="map to exactly one firm"):
        permute_prior_end_dates_across_firms(invalid)


@pytest.mark.parametrize(
    "firm_values",
    [
        ["FIRM-A", "FIRM-A"],
        ["FIRM-A", "FIRM-A", "FIRM-A", "FIRM-B"],
    ],
)
def test_placebo_fails_when_cross_firm_derangement_is_impossible(firm_values) -> None:
    impossible = pd.DataFrame(
        [
            _pair(index, index, f"202{index}-01-01", firm=firm)
            for index, firm in enumerate(firm_values, start=1)
        ]
    )

    with pytest.raises(PlaceboInputError, match="cross-firm placebo permutation is impossible"):
        permute_prior_end_dates_across_firms(impossible)


def test_empty_frame_is_preserved() -> None:
    empty = pd.DataFrame(
        columns=[
            "prior_award_id",
            "prior_recipient_uei",
            "prior_period_of_performance_end",
        ]
    )

    result = permute_prior_end_dates_across_firms(empty)

    pd.testing.assert_frame_equal(result, empty)


def test_placebo_census_tables_delegate_to_existing_frozen_helpers(
    pairs: pd.DataFrame,
) -> None:
    permuted = permute_prior_end_dates_across_firms(pairs)
    expected_dropoff = build_dropoff_ladder(permuted, DATA_CUT)
    expected_sensitivity = build_sensitivity_grid(permuted, DATA_CUT)

    actual_dropoff, actual_sensitivity = build_placebo_census_tables(pairs, DATA_CUT)

    pd.testing.assert_frame_equal(actual_dropoff, expected_dropoff)
    pd.testing.assert_frame_equal(actual_sensitivity, expected_sensitivity)


def test_placebo_census_tables_permute_once_and_share_one_frame(
    pairs: pd.DataFrame,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    permuted = permute_prior_end_dates_across_firms(pairs)
    permutation_calls: list[pd.DataFrame] = []
    helper_inputs: list[pd.DataFrame] = []

    def fake_permutation(frame: pd.DataFrame) -> pd.DataFrame:
        permutation_calls.append(frame)
        return permuted

    def fake_dropoff(frame: pd.DataFrame, data_cut_date: date) -> pd.DataFrame:
        assert data_cut_date == DATA_CUT
        helper_inputs.append(frame)
        return pd.DataFrame({"table": ["dropoff"]})

    def fake_sensitivity(frame: pd.DataFrame, data_cut_date: date) -> pd.DataFrame:
        assert data_cut_date == DATA_CUT
        helper_inputs.append(frame)
        return pd.DataFrame({"table": ["sensitivity"]})

    monkeypatch.setattr(
        placebo_module,
        "permute_prior_end_dates_across_firms",
        fake_permutation,
    )
    monkeypatch.setattr(placebo_module, "build_dropoff_ladder", fake_dropoff)
    monkeypatch.setattr(placebo_module, "build_sensitivity_grid", fake_sensitivity)

    dropoff, sensitivity = build_placebo_census_tables(pairs, DATA_CUT)

    assert len(permutation_calls) == 1
    assert permutation_calls[0] is pairs
    assert len(helper_inputs) == 2
    assert helper_inputs[0] is permuted
    assert helper_inputs[1] is permuted
    assert dropoff.loc[0, "table"] == "dropoff"
    assert sensitivity.loc[0, "table"] == "sensitivity"
