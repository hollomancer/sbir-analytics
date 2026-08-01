from datetime import date

import pandas as pd
import pytest

from sbir_analytics.assets.phase_iii_census.criteria import (
    CensusInputError,
    SensitivityReviewRequired,
    apply_core_clauses,
    build_dropoff_ladder,
    build_sensitivity_grid,
    criterion_exact_taxonomy_lineage,
    criterion_not_phase_i_or_ii_coded,
    criterion_not_phase_iii_coded,
    criterion_prior_end_observable,
    criterion_target_post_completion,
    enforce_sensitivity_checkpoint,
    sensitivity_review_reasons,
    validate_pair_frame,
    validate_source_columns,
)


pytestmark = pytest.mark.fast

CUT = date(2025, 12, 31)


def _pair(row_id: int = 1, **overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "prior_award_id": f"PRIOR-{row_id}",
        "prior_recipient_uei": f"UEI-{row_id}",
        "prior_agency": "DEPARTMENT A",
        "prior_sub_agency": "COMPONENT A",
        "prior_naics_code": "541715",
        "prior_psc_code": "AC13",
        "prior_period_of_performance_end": "2020-12-31",
        "target_recipient_uei": f"UEI-{row_id}",
        "target_id": f"PIID-{row_id}",
        "target_agency": "DEPARTMENT A",
        "target_sub_agency": "COMPONENT A",
        "target_naics_code": "541715",
        "target_psc_code": "AC13",
        "target_action_date": "2021-01-01",
        "target_obligated_amount": 100,
        "target_research": None,
        "target_sbir_phase": None,
        "target_transaction_id": f"TRANSACTION-{row_id}",
        "target_contract_key": f"GENERATED-AWARD-{row_id}",
        "target_competition_type": "FULL AND OPEN COMPETITION",
        "agency_match_level": "office",
    }
    row.update(overrides)
    return row


def _prior_source(**overrides: object) -> pd.DataFrame:
    row: dict[str, object] = {
        "award_id": "PRIOR-1",
        "recipient_uei": "UEI-1",
        "agency": "DEPARTMENT A",
        "sub_agency": "COMPONENT A",
        "naics_code": "541715",
        "psc_code": "AC13",
        "period_of_performance_end": "2020-12-31",
    }
    row.update(overrides)
    return pd.DataFrame([row])


def _contract_source(**overrides: object) -> pd.DataFrame:
    row: dict[str, object] = {
        "research": None,
        "sbir_phase": None,
        "naics_code": "541715",
        "psc_code": "AC13",
    }
    row.update(overrides)
    return pd.DataFrame([row])


def test_prior_end_clause_requires_parseable_date_at_or_before_cut() -> None:
    pairs = pd.DataFrame(
        [
            _pair(1, prior_period_of_performance_end="2025-12-31"),
            _pair(2, prior_period_of_performance_end="2026-01-01"),
            _pair(3, prior_period_of_performance_end="not-a-date"),
            _pair(4, prior_period_of_performance_end=None),
        ]
    )

    assert criterion_prior_end_observable(pairs, CUT).tolist() == [True, False, False, False]


def test_post_completion_clause_is_strict_and_respects_data_cut() -> None:
    pairs = pd.DataFrame(
        [
            _pair(1, target_action_date="2020-12-31"),
            _pair(2, target_action_date="2021-01-01"),
            _pair(3, target_action_date="2026-01-01"),
            _pair(4, target_action_date="not-a-date"),
        ]
    )

    assert criterion_target_post_completion(pairs, CUT).tolist() == [False, True, False, False]


@pytest.mark.parametrize(
    ("research", "phase", "expected"),
    [
        (" sr1 ", None, False),
        ("ST2", None, False),
        (None, " phase i ", False),
        (None, "II", False),
        ("SR3", "Phase III", True),
        (None, None, True),
    ],
)
def test_phase_i_or_ii_code_clause_is_affirmative_only(
    research: object, phase: object, expected: bool
) -> None:
    pairs = pd.DataFrame([_pair(target_research=research, target_sbir_phase=phase)])

    assert bool(criterion_not_phase_i_or_ii_coded(pairs, CUT).iloc[0]) is expected


@pytest.mark.parametrize(
    ("research", "phase", "expected"),
    [
        (" sr3 ", None, False),
        ("ST3", None, False),
        (None, " phase iii ", False),
        (None, "3", False),
        ("SR2", "Phase II", True),
        (None, None, True),
    ],
)
def test_phase_iii_code_clause_is_affirmative_only(
    research: object, phase: object, expected: bool
) -> None:
    pairs = pd.DataFrame([_pair(target_research=research, target_sbir_phase=phase)])

    assert bool(criterion_not_phase_iii_coded(pairs, CUT).iloc[0]) is expected


def test_null_code_values_pass_but_absent_source_columns_fail() -> None:
    pairs = pd.DataFrame([_pair(target_research=None, target_sbir_phase=pd.NA)])
    contracts = _contract_source(research=None, sbir_phase=pd.NA)

    validate_source_columns(_prior_source(), contracts)
    assert criterion_not_phase_i_or_ii_coded(pairs, CUT).all()
    assert criterion_not_phase_iii_coded(pairs, CUT).all()

    for missing_column in ("research", "sbir_phase"):
        with pytest.raises(CensusInputError, match="missing required coding columns"):
            validate_source_columns(_prior_source(), contracts.drop(columns=missing_column))


@pytest.mark.parametrize(
    ("prior_naics", "target_naics", "prior_psc", "target_psc", "expected"),
    [
        ("541715", 541715, "AC13", "ZZZZ", True),
        ("541715", "999999", " ac13 ", "AC13", True),
        ("5417", "541715", "AC", "AC13", False),
        (None, None, None, None, False),
        ("541715", "541714", "AC13", "AC14", False),
    ],
)
def test_taxonomy_clause_requires_exact_full_naics_or_psc(
    prior_naics: object,
    target_naics: object,
    prior_psc: object,
    target_psc: object,
    expected: bool,
) -> None:
    pairs = pd.DataFrame(
        [
            _pair(
                prior_naics_code=prior_naics,
                target_naics_code=target_naics,
                prior_psc_code=prior_psc,
                target_psc_code=target_psc,
            )
        ]
    )

    assert bool(criterion_exact_taxonomy_lineage(pairs, CUT).iloc[0]) is expected


def test_competition_type_is_audit_only_and_never_filters() -> None:
    pairs = pd.DataFrame(
        [
            _pair(1, target_competition_type="FULL AND OPEN COMPETITION"),
            _pair(2, target_competition_type="NOT COMPETED"),
        ]
    )

    survivors = apply_core_clauses(pairs, CUT)[-1][2]

    assert survivors["target_competition_type"].tolist() == [
        "FULL AND OPEN COMPETITION",
        "NOT COMPETED",
    ]


def test_dropoff_ladder_applies_the_frozen_clauses_cumulatively_in_order() -> None:
    pairs = pd.DataFrame(
        [
            _pair(1, prior_period_of_performance_end=None),
            _pair(2, target_action_date="2020-12-31"),
            _pair(3, target_research="SR2"),
            _pair(4, target_research="SR3"),
            _pair(5, target_naics_code="999999", target_psc_code="ZZZZ"),
            _pair(6),
        ]
    )

    ladder = build_dropoff_ladder(pairs, CUT)

    assert ladder["step_order"].tolist() == list(range(6))
    assert ladder["clause_id"].tolist() == [
        "all_exact_uei_pairs",
        "prior_end_observable",
        "target_post_completion",
        "not_phase_i_or_ii_coded",
        "not_phase_iii_coded",
        "exact_naics_or_psc_lineage",
    ]
    assert ladder["surviving_pairs"].tolist() == [6, 5, 4, 3, 2, 1]


def test_metrics_keep_signed_obligations_and_dedupe_transaction_pair_fanout() -> None:
    pairs = pd.DataFrame(
        [
            _pair(
                1,
                prior_recipient_uei="UEI-ONE",
                target_recipient_uei="UEI-ONE",
                target_id="PIID-ONE",
                target_transaction_id="TX-NEGATIVE",
                target_contract_key="AWARD-ONE",
                target_obligated_amount=-40,
            ),
            _pair(
                2,
                prior_recipient_uei="UEI-ONE",
                target_recipient_uei="UEI-ONE",
                target_id="PIID-ONE",
                target_transaction_id="TX-NEGATIVE",
                target_contract_key="AWARD-ONE",
                target_obligated_amount=-40,
            ),
            _pair(
                3,
                prior_recipient_uei="UEI-ONE",
                target_recipient_uei="UEI-ONE",
                target_id="PIID-ONE",
                target_transaction_id="TX-POSITIVE",
                target_contract_key="AWARD-ONE",
                target_obligated_amount=100,
            ),
        ]
    )

    final = build_dropoff_ladder(pairs, CUT).iloc[-1]

    assert final["surviving_pairs"] == 3
    assert final["distinct_firms"] == 1
    assert final["distinct_contracts"] == 1
    assert final["total_obligated_dollars"] == 60


@pytest.mark.parametrize("missing_column", ["target_transaction_id", "target_contract_key"])
def test_pair_validation_rejects_missing_stable_key_columns(missing_column: str) -> None:
    pairs = pd.DataFrame([_pair()]).drop(columns=missing_column)

    with pytest.raises(CensusInputError, match="missing required columns"):
        validate_pair_frame(pairs)


@pytest.mark.parametrize("key_column", ["target_transaction_id", "target_contract_key"])
def test_pair_validation_rejects_blank_stable_keys_even_when_piid_is_present(
    key_column: str,
) -> None:
    pairs = pd.DataFrame([_pair(**{key_column: "", "target_id": "PIID-IS-NOT-A-KEY"})])

    with pytest.raises(CensusInputError, match="stable transaction|generated award key"):
        validate_pair_frame(pairs)


def test_pair_validation_rejects_duplicate_prior_transaction_composite() -> None:
    pair = _pair()
    pairs = pd.DataFrame([pair, pair])

    with pytest.raises(CensusInputError, match="pair-table grain"):
        validate_pair_frame(pairs)


@pytest.mark.parametrize(
    "overrides",
    [
        {"prior_naics_code": None, "prior_psc_code": None},
        {"target_naics_code": None, "target_psc_code": None},
    ],
)
def test_pair_validation_rejects_an_all_missing_taxonomy_side(
    overrides: dict[str, object],
) -> None:
    pairs = pd.DataFrame([_pair(**overrides)])

    with pytest.raises(CensusInputError, match="no usable prior or target NAICS/PSC"):
        validate_pair_frame(pairs)


@pytest.mark.parametrize("obligation", [None, "", "not-a-dollar-value"])
def test_pair_validation_rejects_missing_or_malformed_obligations(obligation: object) -> None:
    pairs = pd.DataFrame([_pair(target_obligated_amount=obligation)])

    with pytest.raises(CensusInputError, match="numeric signed obligated amount"):
        validate_pair_frame(pairs)


def test_sensitivity_grid_has_all_six_cells_and_uses_exact_agency_predicates() -> None:
    pairs = pd.DataFrame(
        [
            _pair(
                1,
                prior_agency=" Department A ",
                target_agency="department a",
                prior_sub_agency=" Component A ",
                target_sub_agency="component a",
                agency_match_level=None,
            ),
            _pair(
                2,
                prior_agency="DEPARTMENT A",
                target_agency="DEPARTMENT A",
                prior_sub_agency="COMPONENT A",
                target_sub_agency="COMPONENT B",
                agency_match_level="agency",
            ),
            _pair(
                3,
                prior_agency="DEPARTMENT A",
                target_agency="DEPARTMENT B",
                prior_sub_agency="SHARED COMPONENT",
                target_sub_agency="SHARED COMPONENT",
                agency_match_level="sub_tier",
            ),
            _pair(
                4,
                prior_agency="DEPARTMENT A",
                target_agency="DEPARTMENT A",
                prior_sub_agency=None,
                target_sub_agency=None,
                agency_match_level="agency",
            ),
        ]
    )

    grid = build_sensitivity_grid(pairs, CUT)

    assert grid["cell_id"].tolist() == [
        "none__same_agency",
        "none__same_department",
        "5y__same_agency",
        "5y__same_department",
        "10y__same_agency",
        "10y__same_department",
    ]
    assert grid["surviving_pairs"].tolist() == [1, 3, 1, 3, 1, 3]
    assert grid["distinct_firms"].tolist() == [1, 3, 1, 3, 1, 3]
    assert grid["distinct_contracts"].tolist() == [1, 3, 1, 3, 1, 3]


def test_calendar_windows_are_inclusive_at_five_and_ten_year_leap_day_endpoints() -> None:
    common = {
        "prior_period_of_performance_end": "2020-02-29",
        "prior_agency": "DEPARTMENT A",
        "target_agency": "DEPARTMENT A",
        "prior_sub_agency": "COMPONENT A",
        "target_sub_agency": "COMPONENT A",
    }
    pairs = pd.DataFrame(
        [
            _pair(1, target_action_date="2025-02-28", **common),
            _pair(2, target_action_date="2025-03-01", **common),
            _pair(3, target_action_date="2030-02-28", **common),
            _pair(4, target_action_date="2030-03-01", **common),
        ]
    )

    grid = build_sensitivity_grid(pairs, date(2031, 1, 1)).set_index("cell_id")

    assert grid.loc["none__same_agency", "surviving_pairs"] == 4
    assert grid.loc["5y__same_agency", "surviving_pairs"] == 1
    assert grid.loc["10y__same_agency", "surviving_pairs"] == 3
    assert grid.loc["5y__same_department", "surviving_pairs"] == 1
    assert grid.loc["10y__same_department", "surviving_pairs"] == 3


def _checkpoint_grid(values: list[int]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "cell_id": [f"cell-{index}" for index in range(len(values))],
            "distinct_firms": values,
            "distinct_contracts": values,
            "total_obligated_dollars": [value * 10 for value in values],
        }
    )


def test_sensitivity_checkpoint_allows_exactly_threefold_span() -> None:
    grid = _checkpoint_grid([1, 3, 2, 2, 2, 2])

    assert sensitivity_review_reasons(grid) == []
    enforce_sensitivity_checkpoint(grid)


@pytest.mark.parametrize("values", [[1, 4, 2, 2, 2, 2], [0, 1, 1, 1, 1, 1]])
def test_sensitivity_checkpoint_stops_on_over_threefold_or_zero_nonzero_split(
    values: list[int],
) -> None:
    grid = _checkpoint_grid(values)

    with pytest.raises(SensitivityReviewRequired) as exc_info:
        enforce_sensitivity_checkpoint(grid)

    pd.testing.assert_frame_equal(exc_info.value.grid, grid)
    assert exc_info.value.reasons
