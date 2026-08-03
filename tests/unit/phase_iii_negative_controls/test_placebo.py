"""Tests for the frozen full-census, cross-firm Phase III placebo."""

from collections import Counter
from datetime import date

import pandas as pd
import pytest

from sbir_analytics.assets.phase_iii_census.criteria import build_census_tables
from sbir_analytics.assets.phase_iii_negative_controls import placebo as placebo_module
from sbir_analytics.assets.phase_iii_negative_controls.placebo import (
    ASSIGNMENT_AUDIT_COLUMNS,
    PLACEBO_SEED,
    PlaceboAssignment,
    PlaceboInputError,
    build_placebo_assignment,
    build_placebo_census_tables,
    build_placebo_study_tables,
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
            _pair(2, 3, None, firm="FIRM-A"),
            _pair(3, 4, "2020-03-31", firm="FIRM-B"),
            _pair(4, 5, None, firm="FIRM-B"),
            _pair(5, 6, "2022-05-31", firm="FIRM-C"),
            _pair(6, 7, "2023-06-30", firm="FIRM-D"),
        ]
    )


def _date_multiset(values: pd.Series) -> Counter[object]:
    parsed = pd.to_datetime(values, errors="coerce")
    return Counter(None if pd.isna(value) else value.date() for value in parsed)


def test_assignment_is_fixed_cross_firm_and_preserves_pairs(pairs: pd.DataFrame) -> None:
    assert PLACEBO_SEED == 20260801

    first = build_placebo_assignment(pairs)
    second = build_placebo_assignment(pairs)

    assert first.mapping_sha256 == second.mapping_sha256
    assert len(first.mapping_sha256) == 64
    assert first.audit.columns.tolist() == list(ASSIGNMENT_AUDIT_COLUMNS)
    pd.testing.assert_frame_equal(first.audit, second.audit)
    pd.testing.assert_frame_equal(first.permuted_pairs, second.permuted_pairs)
    assert first.audit["seed"].eq(PLACEBO_SEED).all()
    assert first.audit["mapping_sha256"].eq(first.mapping_sha256).all()
    assert first.audit["recipient_firm_uei"].ne(first.audit["donor_firm_uei"]).all()
    pd.testing.assert_frame_equal(
        first.permuted_pairs.drop(columns="prior_period_of_performance_end"),
        pairs.drop(columns="prior_period_of_performance_end"),
    )
    assert first.permuted_pairs.index.equals(pairs.index)
    assert first.permuted_pairs["prior_award_id"].value_counts().to_dict() == (
        pairs["prior_award_id"].value_counts().to_dict()
    )
    assert _date_multiset(first.audit["permuted_prior_end"]) == _date_multiset(
        first.audit["original_prior_end"]
    )


def test_identical_cross_firm_dates_are_valid_and_reported_unchanged() -> None:
    identical = pd.DataFrame(
        [
            _pair(1, 1, "2020-01-01", firm="FIRM-A"),
            _pair(2, 2, "2020-01-01", firm="FIRM-A"),
            _pair(3, 3, "2020-01-01", firm="FIRM-B"),
            _pair(4, 4, "2020-01-01", firm="FIRM-B"),
        ]
    )

    assignment = build_placebo_assignment(identical)

    assert assignment.audit["recipient_firm_uei"].ne(assignment.audit["donor_firm_uei"]).all()
    expected_changed = ~(
        assignment.audit["original_prior_end"].eq(assignment.audit["permuted_prior_end"])
        | (
            assignment.audit["original_prior_end"].isna()
            & assignment.audit["permuted_prior_end"].isna()
        )
    )
    pd.testing.assert_series_equal(
        assignment.audit["date_value_changed"], expected_changed, check_names=False
    )
    assert (~assignment.audit["date_value_changed"]).any()
    assert _date_multiset(assignment.audit["permuted_prior_end"]) == _date_multiset(
        assignment.audit["original_prior_end"]
    )


def test_mapping_is_independent_of_pair_row_order(pairs: pd.DataFrame) -> None:
    baseline = build_placebo_assignment(pairs)
    reordered = build_placebo_assignment(pairs.sample(frac=1, random_state=17))

    assert reordered.mapping_sha256 == baseline.mapping_sha256
    pd.testing.assert_frame_equal(reordered.audit, baseline.audit)


@pytest.mark.parametrize(
    ("column", "value", "message"),
    [
        ("prior_award_id", " ", "must have a prior_award_id"),
        ("prior_recipient_uei", " ", "must have a prior_recipient_uei"),
        ("prior_period_of_performance_end", "not-a-date", "unparsable nonblank value"),
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
        build_placebo_assignment(invalid)


def test_placebo_rejects_conflicting_award_values(pairs: pd.DataFrame) -> None:
    conflicting_date = pairs.copy()
    conflicting_date.loc[1, "prior_period_of_performance_end"] = "2022-01-01"
    with pytest.raises(PlaceboInputError, match="map to exactly one prior_period"):
        build_placebo_assignment(conflicting_date)

    conflicting_firm = pairs.copy()
    conflicting_firm.loc[1, "prior_recipient_uei"] = "FIRM-Z"
    with pytest.raises(PlaceboInputError, match="map to exactly one firm"):
        build_placebo_assignment(conflicting_firm)


@pytest.mark.parametrize(
    "firm_values",
    [
        [],
        ["FIRM-A", "FIRM-A"],
        ["FIRM-A", "FIRM-A", "FIRM-A", "FIRM-B"],
    ],
)
def test_placebo_fails_when_cross_firm_derangement_is_impossible(firm_values) -> None:
    impossible = pd.DataFrame(
        [_pair(index, index, "2020-01-01", firm=firm) for index, firm in enumerate(firm_values, 1)],
        columns=list(_pair(1, 1, "2020-01-01", firm="FIRM-A")),
    )

    with pytest.raises(PlaceboInputError, match="requires at least two|permutation is impossible"):
        build_placebo_assignment(impossible)


def test_compatibility_permutation_returns_assignment_frame(pairs: pd.DataFrame) -> None:
    expected = build_placebo_assignment(pairs).permuted_pairs
    actual = permute_prior_end_dates_across_firms(pairs)
    pd.testing.assert_frame_equal(actual, expected)


def test_placebo_tables_use_one_memory_safe_census_call(
    pairs: pd.DataFrame,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assignment = build_placebo_assignment(pairs)
    calls: list[tuple[pd.DataFrame, date]] = []

    def fake_assignment(frame: pd.DataFrame) -> PlaceboAssignment:
        assert frame is pairs
        return assignment

    def fake_tables(frame: pd.DataFrame, data_cut: date) -> tuple[pd.DataFrame, pd.DataFrame]:
        calls.append((frame, data_cut))
        return pd.DataFrame({"kind": ["dropoff"]}), pd.DataFrame({"kind": ["sensitivity"]})

    monkeypatch.setattr(placebo_module, "build_placebo_assignment", fake_assignment)
    monkeypatch.setattr(placebo_module, "build_census_tables", fake_tables)

    study = build_placebo_study_tables(pairs, DATA_CUT)

    assert len(calls) == 1
    assert calls[0][0] is assignment.permuted_pairs
    assert calls[0][1] == DATA_CUT
    assert study.assignment is assignment
    assert study.dropoff.loc[0, "kind"] == "dropoff"
    assert study.sensitivity.loc[0, "kind"] == "sensitivity"


def test_placebo_census_tables_match_shared_builder(pairs: pd.DataFrame) -> None:
    permuted = build_placebo_assignment(pairs).permuted_pairs
    expected_dropoff, expected_sensitivity = build_census_tables(permuted, DATA_CUT)

    actual_dropoff, actual_sensitivity = build_placebo_census_tables(pairs, DATA_CUT)

    pd.testing.assert_frame_equal(actual_dropoff, expected_dropoff)
    pd.testing.assert_frame_equal(actual_sensitivity, expected_sensitivity)
