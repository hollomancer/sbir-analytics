"""Tests for deterministic Phase III negative-control exact matching."""

import pandas as pd
import pytest

from sbir_analytics.assets.phase_iii_negative_controls import (
    CovariateInputError,
    build_balance_table,
    exact_match_controls,
    require_covariate_balance,
    summarize_matching,
)


def _row(firm_id: str, *, stratum: int = 1, eligible: bool = True) -> dict[str, object]:
    return {
        "firm_id": firm_id,
        "firm_ueis": (firm_id,),
        "primary_naics": "541715" if stratum == 1 else "334511",
        "first_contract_business_size": "small_business",
        "state": "VA" if stratum == 1 else "MD",
        "first_contract_year": 2010 if stratum == 1 else 2011,
        "psc_family": "A" if stratum == 1 else "R",
        "match_eligible": eligible,
    }


def test_exact_matching_maximizes_one_control_before_extra_controls() -> None:
    treated = pd.DataFrame([_row("T1"), _row("T2")])
    controls = pd.DataFrame([_row(f"C{value}") for value in range(1, 5)])

    pairs = exact_match_controls(treated, controls)

    assert pairs[["treated_firm_id", "control_firm_id", "control_slot"]].to_dict(
        orient="records"
    ) == [
        {"treated_firm_id": "T1", "control_firm_id": "C1", "control_slot": 1},
        {"treated_firm_id": "T1", "control_firm_id": "C3", "control_slot": 2},
        {"treated_firm_id": "T2", "control_firm_id": "C2", "control_slot": 1},
        {"treated_firm_id": "T2", "control_firm_id": "C4", "control_slot": 2},
    ]
    assert pairs["control_firm_id"].is_unique


def test_exact_matching_never_crosses_a_covariate_stratum() -> None:
    treated = pd.DataFrame([_row("T1", stratum=1), _row("T2", stratum=2)])
    controls = pd.DataFrame([_row("C1", stratum=1), _row("C2", stratum=1)])

    pairs = exact_match_controls(treated, controls)
    summary = summarize_matching(treated, pairs)

    assert set(pairs["treated_firm_id"]) == {"T1"}
    assert summary.to_dict(orient="records") == [
        {"matched_control_count": 0, "treated_firms": 1},
        {"matched_control_count": 1, "treated_firms": 0},
        {"matched_control_count": 2, "treated_firms": 1},
        {"matched_control_count": 3, "treated_firms": 0},
    ]


def test_ineligible_rows_never_enter_matching() -> None:
    treated = pd.DataFrame([_row("T1"), _row("T2", eligible=False)])
    controls = pd.DataFrame([_row("C1"), _row("C2", eligible=False)])

    pairs = exact_match_controls(treated, controls)

    assert pairs[["treated_firm_id", "control_firm_id"]].to_dict(orient="records") == [
        {"treated_firm_id": "T1", "control_firm_id": "C1"}
    ]


def test_exact_pairs_produce_an_unflagged_smd_for_every_covariate() -> None:
    treated = pd.DataFrame([_row("T1"), _row("T2", stratum=2)])
    controls = pd.DataFrame([_row("C1"), _row("C2", stratum=2)])

    balance = build_balance_table(exact_match_controls(treated, controls))

    assert set(balance["covariate"]) == {
        "primary_naics",
        "first_contract_business_size",
        "state",
        "first_contract_year",
        "psc_family",
    }
    assert balance["absolute_smd"].eq(0.0).all()
    assert not balance["flagged_above_0_1"].any()
    require_covariate_balance(balance)


def test_empty_balance_cannot_authorize_outcomes() -> None:
    empty_controls = pd.DataFrame([_row("C1")]).iloc[0:0]
    balance = build_balance_table(exact_match_controls(pd.DataFrame([_row("T1")]), empty_controls))

    with pytest.raises(CovariateInputError, match="no matched pairs"):
        require_covariate_balance(balance)
