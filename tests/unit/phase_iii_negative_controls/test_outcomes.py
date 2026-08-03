"""Tests for the frozen Phase 2 firm-outcome grain."""

import inspect
from datetime import date

import pandas as pd
import pytest

from sbir_analytics.assets.phase_iii_census.criteria import CORE_CLAUSES, CensusInputError
from sbir_analytics.assets.phase_iii_negative_controls import (
    build_control_pseudo_priors,
    build_uei_firm_mapping,
    compare_firm_outcomes,
    evaluate_firm_outcomes,
)


pytestmark = pytest.mark.fast

CUT = date(2025, 12, 31)
UEI_A = "AAAAAAAAAAAA"
UEI_B = "BBBBBBBBBBBB"
UEI_C = "CCCCCCCCCCCC"


def _pair(row_id: int, uei: str, **overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "prior_award_id": f"PRIOR-{row_id}",
        "prior_recipient_uei": uei,
        "prior_agency": "DEPARTMENT A",
        "prior_sub_agency": "COMPONENT A",
        "prior_naics_code": "541715",
        "prior_psc_code": "AC13",
        "prior_period_of_performance_end": "2020-12-31",
        "target_id": f"PIID-{row_id}",
        "target_recipient_uei": uei,
        "target_agency": "DEPARTMENT A",
        "target_sub_agency": "COMPONENT A",
        "target_naics_code": "541715",
        "target_psc_code": "AC13",
        "target_action_date": "2021-01-01",
        "target_competition_type": "FULL AND OPEN COMPETITION",
        "target_obligated_amount": 100,
        "target_research": None,
        "target_sbir_phase": None,
        "target_transaction_id": f"TRANSACTION-{row_id}",
        "target_contract_key": f"CONTRACT-{row_id}",
        "agency_match_level": "office",
    }
    row.update(overrides)
    return row


def _mapping(*rows: tuple[str, str]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["exact_uei", "firm_id"])


def _evaluate(pairs: list[dict[str, object]], mapping: pd.DataFrame, risk_set: list[str]):
    return evaluate_firm_outcomes(pd.DataFrame(pairs), mapping, risk_set, CUT)


def test_evaluator_retains_zero_outcome_firms_at_every_stage() -> None:
    outcomes = _evaluate(
        [_pair(1, UEI_A)],
        _mapping((UEI_A, "FIRM-A"), (UEI_B, "FIRM-B")),
        ["FIRM-A", "FIRM-B"],
    )

    assert len(outcomes.firm_counts) == 2 * (len(CORE_CLAUSES) + 1)
    zero_rows = outcomes.firm_counts.loc[outcomes.firm_counts["firm_id"].eq("FIRM-B")]
    assert (
        zero_rows[["surviving_pairs", "distinct_transactions", "distinct_contracts"]]
        .eq(0)
        .all(axis=None)
    )
    assert outcomes.frequency_distribution.groupby("clause_id")["firms"].sum().eq(2).all()
    assert (
        outcomes.frequency_distribution.groupby("clause_id")["firm_proportion"].sum().eq(1.0).all()
    )


def test_evaluator_collapses_pair_and_transaction_fanout_to_distinct_contracts() -> None:
    outcomes = _evaluate(
        [
            _pair(
                1,
                UEI_A,
                target_id="PIID-1",
                target_transaction_id="TX-1",
                target_contract_key="CONTRACT-1",
            ),
            _pair(
                2,
                UEI_A,
                target_id="PIID-1",
                target_transaction_id="TX-1",
                target_contract_key="CONTRACT-1",
            ),
            _pair(3, UEI_A, target_transaction_id="TX-2", target_contract_key="CONTRACT-1"),
        ],
        _mapping((UEI_A, "FIRM-A")),
        ["FIRM-A"],
    )

    inherited = outcomes.firm_counts.loc[
        outcomes.firm_counts["clause_id"].eq("all_exact_uei_pairs")
    ].iloc[0]
    assert inherited[
        ["surviving_pairs", "distinct_transactions", "distinct_contracts"]
    ].tolist() == [3, 2, 1]


def test_evaluator_aggregates_every_exact_uei_in_a_firm_envelope() -> None:
    outcomes = _evaluate(
        [_pair(1, UEI_A), _pair(2, UEI_B)],
        _mapping((UEI_A, "ENVELOPE-1"), (UEI_B, "ENVELOPE-1")),
        ["ENVELOPE-1"],
    )

    assert outcomes.firm_counts.loc[
        outcomes.firm_counts["clause_id"].eq("all_exact_uei_pairs"),
        ["surviving_pairs", "distinct_transactions", "distinct_contracts"],
    ].iloc[0].tolist() == [2, 2, 2]


def test_comparison_reports_final_overlap_clearing_counts_and_directed_risk_ratio() -> None:
    sbir = _evaluate(
        [
            _pair(1, UEI_A),
            _pair(2, UEI_A),
            _pair(3, UEI_B),
        ],
        _mapping((UEI_A, "S1"), (UEI_B, "S2"), (UEI_C, "S3")),
        ["S1", "S2", "S3"],
    )
    control = _evaluate(
        [_pair(4, UEI_A), _pair(5, UEI_B)],
        _mapping((UEI_A, "C1"), (UEI_B, "C2"), (UEI_C, "C3")),
        ["C1", "C2", "C3"],
    )

    compared = compare_firm_outcomes(sbir, control)
    final = compared.final_comparison.iloc[0]

    assert set(compared.firm_counts["arm"]) == {"sbir", "control"}
    assert set(compared.frequency_distribution["arm"]) == {"sbir", "control"}
    assert final["overlap_coefficient"] == pytest.approx(2 / 3)
    assert final[
        [
            "sbir_clearing_numerator",
            "sbir_clearing_denominator",
            "control_clearing_numerator",
            "control_clearing_denominator",
        ]
    ].tolist() == [2, 3, 2, 3]
    assert final["sbir_control_risk_ratio"] == pytest.approx(1.0)


def test_comparison_records_null_ratio_when_control_clearing_proportion_is_zero() -> None:
    sbir = _evaluate(
        [_pair(1, UEI_A)],
        _mapping((UEI_A, "S1")),
        ["S1"],
    )
    control = _evaluate(
        [_pair(2, UEI_B, target_naics_code="999999", target_psc_code="ZZ99")],
        _mapping((UEI_B, "C1")),
        ["C1"],
    )

    final = compare_firm_outcomes(sbir, control).final_comparison.iloc[0]

    assert final["control_clearing_proportion"] == 0.0
    assert final["sbir_clearing_proportion"] == 1.0
    assert final["sbir_control_risk_ratio"] is None


def test_evaluator_rejects_nonunique_mapping_and_inexact_risk_set() -> None:
    pairs = pd.DataFrame([_pair(1, UEI_A)])

    with pytest.raises(CensusInputError, match="each exact UEI exactly once"):
        evaluate_firm_outcomes(
            pairs,
            _mapping((UEI_A, "FIRM-A"), (UEI_A, "FIRM-B")),
            ["FIRM-A", "FIRM-B"],
            CUT,
        )
    with pytest.raises(CensusInputError, match="complete firm risk set"):
        evaluate_firm_outcomes(
            pairs,
            _mapping((UEI_A, "FIRM-A")),
            ["FIRM-A", "FIRM-B"],
            CUT,
        )
    with pytest.raises(CensusInputError, match="absent from the UEI-to-firm mapping"):
        evaluate_firm_outcomes(
            pairs,
            _mapping((UEI_B, "FIRM-B")),
            ["FIRM-B"],
            CUT,
        )


def test_evaluator_signature_and_source_are_blind_to_study_labels() -> None:
    assert list(inspect.signature(evaluate_firm_outcomes).parameters) == [
        "pair_frame",
        "uei_to_firm",
        "firm_risk_set",
        "data_cut_date",
    ]
    source = inspect.getsource(evaluate_firm_outcomes).lower()
    for forbidden in ("arm", "control", "sbir", "treated", "treatment", "placebo"):
        assert forbidden not in source


def test_build_uei_firm_mapping_expands_envelopes_and_rejects_overlap() -> None:
    covariates = pd.DataFrame(
        [
            {"firm_id": "FIRM-A", "firm_ueis": (UEI_A, UEI_B)},
            {"firm_id": "FIRM-C", "firm_ueis": (UEI_C,)},
        ]
    )

    assert build_uei_firm_mapping(covariates, ["FIRM-A"]).to_dict(orient="records") == [
        {"exact_uei": UEI_A, "firm_id": "FIRM-A"},
        {"exact_uei": UEI_B, "firm_id": "FIRM-A"},
    ]

    overlapping = pd.concat(
        [
            covariates,
            pd.DataFrame([{"firm_id": "FIRM-D", "firm_ueis": (UEI_A,)}]),
        ],
        ignore_index=True,
    )
    with pytest.raises(CensusInputError, match="multiple firm envelopes"):
        build_uei_firm_mapping(overlapping, ["FIRM-A", "FIRM-D"])


def test_build_uei_firm_mapping_ignores_unmatched_envelopes() -> None:
    covariates = pd.DataFrame(
        [
            {"firm_id": "FIRM-A", "firm_ueis": (UEI_A,)},
            {"firm_id": "UNMATCHED", "firm_ueis": ()},
        ]
    )

    assert build_uei_firm_mapping(covariates, ["FIRM-A"]).to_dict(orient="records") == [
        {"exact_uei": UEI_A, "firm_id": "FIRM-A"}
    ]


def test_control_pseudo_priors_copy_all_prior_fields_and_expand_multi_uei_envelope() -> None:
    treated_uei = "TREAT0000001"
    control_uei_1 = "CTRL00000001"
    control_uei_2 = "CTRL00000002"
    phase_ii = pd.DataFrame(
        [
            {
                "award_id": "AWARD-1",
                "recipient_uei": treated_uei,
                "agency": "DOD",
                "naics_code": "541715",
                "period_of_performance_end": "2020-01-01",
            },
            {
                "award_id": "AWARD-2",
                "recipient_uei": treated_uei,
                "agency": "DOD",
                "naics_code": "334511",
                "period_of_performance_end": "2021-01-01",
            },
        ]
    )
    matches = pd.DataFrame(
        [{"treated_firm_id": treated_uei, "control_firm_id": "CONTROL-ENVELOPE"}]
    )
    controls = pd.DataFrame(
        [
            {
                "firm_id": "CONTROL-ENVELOPE",
                "firm_ueis": (control_uei_1, control_uei_2),
            }
        ]
    )

    pseudo = build_control_pseudo_priors(phase_ii, matches, controls)

    assert len(pseudo) == 4
    assert set(pseudo["recipient_uei"]) == {control_uei_1, control_uei_2}
    expected_non_uei = pd.concat([phase_ii.drop(columns="recipient_uei")] * 2, ignore_index=True)
    pd.testing.assert_frame_equal(
        pseudo.drop(columns="recipient_uei").sort_values("award_id").reset_index(drop=True),
        expected_non_uei.sort_values("award_id").reset_index(drop=True),
    )
