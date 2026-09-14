"""Tests for the R16 permutation-separation machinery."""

from collections import Counter
from datetime import date

import pandas as pd
import pytest

from sbir_analytics.assets.phase_iii_census.criteria import (
    CORE_CLAUSES,
    METRIC_COLUMNS,
    CensusInputError,
    build_census_tables,
)
from sbir_analytics.assets.phase_iii_negative_controls import permutation as perm
from sbir_analytics.assets.phase_iii_negative_controls.placebo import (
    PLACEBO_SEED,
    build_placebo_assignment,
)

DATA_CUT = date(2026, 2, 6)


def _pair(
    prior: int, target: int, prior_end: object, *, firm: str, **over: object
) -> dict[str, object]:
    row: dict[str, object] = {
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
    row.update(over)
    return row


@pytest.fixture
def pairs() -> pd.DataFrame:
    """Enough structure that date and non-date clauses both bind."""

    return pd.DataFrame(
        [
            _pair(1, 1, "2018-01-31", firm="FIRM-A"),
            _pair(1, 2, "2018-01-31", firm="FIRM-A", target_action_date="2026-06-01"),
            _pair(2, 3, None, firm="FIRM-A"),
            _pair(3, 4, "2020-03-31", firm="FIRM-B", target_sbir_phase="PHASE II"),
            _pair(4, 5, "2025-12-31", firm="FIRM-B"),
            _pair(
                5,
                6,
                "2022-05-31",
                firm="FIRM-C",
                target_naics_code="999999",
                target_psc_code="ZZ99",
            ),
            _pair(
                6,
                7,
                "2023-06-30",
                firm="FIRM-D",
                target_agency="DEPARTMENT B",
                target_sub_agency="X",
            ),
            _pair(7, 8, "2010-01-01", firm="FIRM-E", target_action_date="2016-01-01"),
            _pair(8, 9, "2019-09-30", firm="FIRM-F", target_research="SR3"),
        ]
    )


def test_date_dependent_clause_ids_are_exactly_the_two_that_read_the_permuted_column() -> None:
    ids = {clause.clause_id for clause in CORE_CLAUSES}
    assert perm.DATE_DEPENDENT_CLAUSE_IDS <= ids
    assert perm.DATE_DEPENDENT_CLAUSE_IDS == {"prior_end_observable", "target_post_completion"}
    assert perm.R16_FINAL_CLAUSE_ID == "exact_naics_or_psc_lineage"


@pytest.mark.parametrize("seed", [PLACEBO_SEED, 20260802, 20260803, 20261301])
def test_final_stage_matches_the_shared_builder_for_any_seed(
    pairs: pd.DataFrame, seed: int
) -> None:
    """The fast path must equal the last dropoff row and the six cells of build_census_tables."""

    permuted = build_placebo_assignment(pairs, seed=seed).permuted_pairs
    expected_dropoff, expected_cells = build_census_tables(permuted, DATA_CUT)
    fixed = perm.date_independent_mask(pairs, DATA_CUT)

    summary, cells = perm.final_stage_and_cells(permuted, DATA_CUT, fixed_mask=fixed)

    last = expected_dropoff.iloc[-1]
    assert last["clause_id"] == perm.R16_FINAL_CLAUSE_ID
    for metric in METRIC_COLUMNS:
        assert summary[metric] == last[metric], metric
    pd.testing.assert_frame_equal(
        cells.reset_index(drop=True), expected_cells.reset_index(drop=True)
    )


def test_actual_frame_matches_the_shared_builder(pairs: pd.DataFrame) -> None:
    expected_dropoff, expected_cells = build_census_tables(pairs, DATA_CUT)
    draws = perm.run_permutation_draws(pairs, DATA_CUT, [20260802])
    for metric in METRIC_COLUMNS:
        assert draws.actual_final.iloc[0][metric] == expected_dropoff.iloc[-1][metric]
    pd.testing.assert_frame_equal(
        draws.actual_cells.drop(columns="seed").reset_index(drop=True),
        expected_cells.reset_index(drop=True),
    )


def test_fixed_mask_is_independent_of_the_permuted_date(pairs: pd.DataFrame) -> None:
    fixed = perm.date_independent_mask(pairs, DATA_CUT)
    permuted = build_placebo_assignment(pairs, seed=20260802).permuted_pairs
    pd.testing.assert_series_equal(fixed, perm.date_independent_mask(permuted, DATA_CUT))


def test_fixed_mask_index_mismatch_is_refused(pairs: pd.DataFrame) -> None:
    fixed = perm.date_independent_mask(pairs, DATA_CUT)
    with pytest.raises(CensusInputError, match="row index"):
        perm.final_stage_and_cells(pairs.iloc[:-1], DATA_CUT, fixed_mask=fixed)


def test_preregistered_seeds_start_after_the_r15_seed_and_are_consecutive() -> None:
    seeds = perm.preregistered_seeds()
    assert len(seeds) == perm.R16_DRAWS == 500
    assert seeds[0] == PLACEBO_SEED + 1
    assert PLACEBO_SEED not in seeds
    assert seeds == list(range(seeds[0], seeds[0] + 500))
    with pytest.raises(CensusInputError, match="exceed the R15 seed"):
        perm.preregistered_seeds(3, first_seed=PLACEBO_SEED)
    with pytest.raises(CensusInputError, match="at least one draw"):
        perm.preregistered_seeds(0)


def test_run_records_one_row_one_cell_table_and_one_digest_per_seed(pairs: pd.DataFrame) -> None:
    seeds = [20260802, 20260803, 20260804]
    seen: list[int] = []
    draws = perm.run_permutation_draws(pairs, DATA_CUT, seeds, on_draw=seen.append)

    assert seen == seeds
    assert draws.placebo_final["seed"].tolist() == seeds
    assert list(draws.placebo_final.columns) == list(perm.FINAL_STAGE_COLUMNS)
    assert Counter(draws.placebo_cells["seed"]) == dict.fromkeys(seeds, 6)
    assert draws.mapping_digests["mapping_sha256"].nunique() == 3
    assert (draws.placebo_final["stage"] == perm.R16_FINAL_CLAUSE_ID).all()


def test_run_refuses_duplicate_seeds(pairs: pd.DataFrame) -> None:
    with pytest.raises(CensusInputError, match="distinct"):
        perm.run_permutation_draws(pairs, DATA_CUT, [20260802, 20260802])


@pytest.mark.parametrize(
    ("successes", "trials", "low", "high"),
    [
        (200, 200, 0.98115, 1.0),
        (500, 500, 0.99238, 1.0),
        (485, 500, 0.95110, 0.98174),
        (0, 10, 0.0, 0.27753),
        (5, 10, 0.23659, 0.76341),
    ],
)
def test_wilson_interval_matches_reference_values(
    successes: int, trials: int, low: float, high: float
) -> None:
    got_low, got_high = perm.wilson_interval(successes, trials)
    assert got_low == pytest.approx(low, abs=5e-5)
    assert got_high == pytest.approx(high, abs=5e-5)


def test_wilson_interval_rejects_bad_inputs() -> None:
    with pytest.raises(CensusInputError):
        perm.wilson_interval(11, 10)
    with pytest.raises(CensusInputError):
        perm.wilson_interval(1, 0)
    with pytest.raises(CensusInputError):
        perm.wilson_interval(1, 10, confidence=1.0)


def test_exceedance_counts_strict_exceedances_and_reports_ties() -> None:
    summary = perm.exceedance(10.0, [9.0, 10.0, 11.0, 9.5], metric="m", stage_or_cell="s")
    assert summary.exceeded == 2
    assert summary.tied == 1
    assert summary.draws == 4
    assert summary.proportion == 0.5
    assert summary.interval_method == "wilson_95"


def test_primary_threshold_is_the_wilson_lower_bound_not_the_point_estimate() -> None:
    all_exceeded = perm.exceedance(1.0, [0.0] * 500, metric="m", stage_or_cell="s")
    assert perm.primary_threshold_met(all_exceeded)
    # 485/500 = 0.97 point estimate, lower bound 0.9511: met by the interval rule.
    fifteen_missed = perm.exceedance(1.0, [0.0] * 485 + [2.0] * 15, metric="m", stage_or_cell="s")
    assert fifteen_missed.proportion == pytest.approx(0.97)
    assert perm.primary_threshold_met(fifteen_missed)
    # 480/500 = 0.96 point estimate clears 0.95 but its lower bound (0.9390) does not.
    twenty_missed = perm.exceedance(1.0, [0.0] * 480 + [2.0] * 20, metric="m", stage_or_cell="s")
    assert twenty_missed.proportion == pytest.approx(0.96)
    assert not perm.primary_threshold_met(twenty_missed)


def test_exceedance_table_marks_exactly_one_primary_row(pairs: pd.DataFrame) -> None:
    draws = perm.run_permutation_draws(pairs, DATA_CUT, [20260802, 20260803])
    table = perm.exceedance_table(draws)
    primary = table.loc[table["primary"]]
    assert len(primary) == 1
    assert primary.iloc[0]["metric"] == perm.R16_PRIMARY_METRIC
    assert primary.iloc[0]["stage_or_cell"] == perm.R16_FINAL_CLAUSE_ID
    assert table["threshold_met"].notna().sum() == 1
    assert table.loc[table["metric"].eq("total_obligated_dollars"), "descriptive_only"].all()
    assert len(table) == len(METRIC_COLUMNS) * (1 + 6)


def test_run_validates_the_pair_frame_like_the_shared_builder(pairs: pd.DataFrame) -> None:
    """A malformed frame must fail closed here exactly as build_census_tables does."""

    malformed = pairs.copy()
    malformed.loc[malformed.index[0], "target_transaction_id"] = None

    with pytest.raises(CensusInputError):
        build_census_tables(malformed, DATA_CUT)
    with pytest.raises(CensusInputError):
        perm.run_permutation_draws(malformed, DATA_CUT, [20260802])


def test_permuted_frame_still_passes_pair_validation(pairs: pd.DataFrame) -> None:
    """One validation covers every draw because the placebo touches no key column."""

    from sbir_analytics.assets.phase_iii_census.criteria import validate_pair_frame

    permuted = build_placebo_assignment(pairs, seed=20260802).permuted_pairs
    validate_pair_frame(permuted)
