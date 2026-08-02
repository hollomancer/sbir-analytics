from datetime import date

import pandas as pd
import pytest

from sbir_analytics.assets.phase_iii_census.criteria import (
    build_dropoff_ladder,
    build_sensitivity_grid,
)
from sbir_analytics.assets.phase_iii_negative_controls import methods as methods_module
from sbir_analytics.assets.phase_iii_negative_controls.methods import (
    CONTROL_STATUS_LABEL,
    EXACT_DUNS_EXCLUSION_REASON,
    EXACT_UEI_EXCLUSION_REASON,
    PLACEBO_SEED,
    NegativeControlInputError,
    audit_exact_identifier_eligibility,
    build_placebo_census_tables,
    flag_identifier_free_name_stress_set,
    permute_prior_end_dates,
)


pytestmark = pytest.mark.fast
DATA_CUT = date(2025, 12, 31)


@pytest.fixture
def complete_award_history() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "award_id": "AWARD-UEI",
                "uei": "UEI000000001",
                "duns": None,
                "company_name": "UEI Recipient LLC",
            },
            {
                "award_id": "AWARD-DUNS",
                "uei": None,
                "duns": "123456789",
                "company_name": "DUNS Recipient LLC",
            },
            {
                "award_id": "AWARD-BOTH",
                "uei": "UEI000000003",
                "duns": "333333333",
                "company_name": "Both Recipient LLC",
            },
            {
                "award_id": "AWARD-NAME-ONLY",
                "uei": None,
                "duns": None,
                "company_name": "Acme Incorporated",
            },
            {
                "award_id": "AWARD-NAME-WITH-ID",
                "uei": "UEI000000005",
                "duns": None,
                "company_name": "Identifier Backed LLC",
            },
        ]
    )


@pytest.fixture
def candidate_entities() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "entity_id": "ENTITY-UEI",
                "uei": " uei-000-000-001 ",
                "duns": None,
                "entity_name": "UEI Recipient LLC",
            },
            {
                "entity_id": "ENTITY-DUNS",
                "uei": None,
                "duns": "123-456-789",
                "entity_name": "DUNS Recipient LLC",
            },
            {
                "entity_id": "ENTITY-BOTH",
                "uei": "UEI000000003",
                "duns": "33-333-3333",
                "entity_name": "Both Recipient LLC",
            },
            {
                "entity_id": "ENTITY-NAME-STRESS",
                "uei": None,
                "duns": None,
                "entity_name": "Acme, Inc.",
            },
            {
                "entity_id": "ENTITY-ID-BACKED-NAME",
                "uei": "malformed",
                "duns": "12",
                "entity_name": "Identifier Backed LLC",
            },
        ]
    )


def _pair(prior: int, target: int, prior_end: object) -> dict[str, object]:
    uei = f"UEI-{prior}"
    return {
        "prior_award_id": f"PRIOR-{prior}",
        "prior_recipient_uei": uei,
        "prior_agency": "DEPARTMENT A",
        "prior_sub_agency": "COMPONENT A",
        "prior_naics_code": "541715",
        "prior_psc_code": "AC13",
        "prior_period_of_performance_end": prior_end,
        "target_id": f"TARGET-{target}",
        "target_recipient_uei": uei,
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
def fanout_pairs() -> pd.DataFrame:
    return pd.DataFrame(
        [
            _pair(1, 1, "2018-01-31"),
            _pair(1, 2, "2018-01-31"),
            _pair(1, 3, "2018-01-31"),
            _pair(2, 4, "2019-02-28"),
            _pair(3, 5, "2020-03-31"),
            _pair(3, 6, "2020-03-31"),
            _pair(4, 7, "2021-04-30"),
        ]
    )


def test_exact_identifier_audit_labels_retained_rows_and_records_every_reason(
    candidate_entities: pd.DataFrame,
    complete_award_history: pd.DataFrame,
) -> None:
    audit = audit_exact_identifier_eligibility(candidate_entities, complete_award_history)
    by_id = audit.set_index("entity_id")

    assert by_id.loc["ENTITY-UEI", "exclusion_reason"] == EXACT_UEI_EXCLUSION_REASON
    assert by_id.loc["ENTITY-DUNS", "exclusion_reason"] == EXACT_DUNS_EXCLUSION_REASON
    assert by_id.loc["ENTITY-BOTH", "exclusion_reason"] == (
        f"{EXACT_UEI_EXCLUSION_REASON};{EXACT_DUNS_EXCLUSION_REASON}"
    )
    assert not bool(by_id.loc["ENTITY-BOTH", "passes_exact_identifier_screen"])

    for entity_id in ("ENTITY-NAME-STRESS", "ENTITY-ID-BACKED-NAME"):
        assert bool(by_id.loc[entity_id, "passes_exact_identifier_screen"])
        assert by_id.loc[entity_id, "control_status_label"] == CONTROL_STATUS_LABEL
        assert pd.isna(by_id.loc[entity_id, "exclusion_reason"])

    assert pd.isna(by_id.loc["ENTITY-UEI", "control_status_label"])
    assert pd.isna(by_id.loc["ENTITY-ID-BACKED-NAME", "normalized_uei"])
    assert pd.isna(by_id.loc["ENTITY-ID-BACKED-NAME", "normalized_duns"])


def test_exact_identifier_audit_fails_closed_on_empty_history(
    candidate_entities: pd.DataFrame,
) -> None:
    empty_history = pd.DataFrame(columns=["uei", "duns"])

    with pytest.raises(NegativeControlInputError, match="cannot be screened against empty"):
        audit_exact_identifier_eligibility(candidate_entities, empty_history)


def test_exact_identifier_audit_requires_unique_nonblank_entity_keys(
    candidate_entities: pd.DataFrame,
    complete_award_history: pd.DataFrame,
) -> None:
    invalid = candidate_entities.iloc[[0, 0]].copy()
    invalid.loc[invalid.index[1], "entity_id"] = " entity-uei "

    with pytest.raises(NegativeControlInputError, match="must be unique"):
        audit_exact_identifier_eligibility(invalid, complete_award_history)


def test_identifier_free_name_match_is_only_a_reporting_flag(
    candidate_entities: pd.DataFrame,
    complete_award_history: pd.DataFrame,
) -> None:
    audit = audit_exact_identifier_eligibility(candidate_entities, complete_award_history)
    original_screen = audit["passes_exact_identifier_screen"].copy()

    flagged = flag_identifier_free_name_stress_set(audit, complete_award_history)
    by_id = flagged.set_index("entity_id")

    assert bool(by_id.loc["ENTITY-NAME-STRESS", "identifier_free_award_exact_name_match"])
    assert not bool(by_id.loc["ENTITY-ID-BACKED-NAME", "identifier_free_award_exact_name_match"])
    assert by_id.loc["ENTITY-NAME-STRESS", "normalized_entity_name"] == "acme inc"
    pd.testing.assert_series_equal(
        flagged["passes_exact_identifier_screen"],
        original_screen,
    )


def test_placebo_is_fixed_at_unique_prior_award_grain_and_preserves_fanout(
    fanout_pairs: pd.DataFrame,
) -> None:
    assert PLACEBO_SEED == 20260801

    first = permute_prior_end_dates(fanout_pairs)
    second = permute_prior_end_dates(fanout_pairs)

    pd.testing.assert_frame_equal(first, second)
    assert not first["prior_period_of_performance_end"].equals(
        pd.to_datetime(fanout_pairs["prior_period_of_performance_end"])
    )
    assert first.groupby("prior_award_id")["prior_period_of_performance_end"].nunique().eq(1).all()

    before = (
        fanout_pairs.drop_duplicates("prior_award_id")["prior_period_of_performance_end"]
        .pipe(pd.to_datetime)
        .sort_values()
        .reset_index(drop=True)
    )
    after = (
        first.drop_duplicates("prior_award_id")["prior_period_of_performance_end"]
        .sort_values()
        .reset_index(drop=True)
    )
    pd.testing.assert_series_equal(after, before, check_names=False)
    pd.testing.assert_frame_equal(
        first.drop(columns="prior_period_of_performance_end"),
        fanout_pairs.drop(columns="prior_period_of_performance_end"),
    )


def test_placebo_mapping_is_independent_of_pair_row_order(fanout_pairs: pd.DataFrame) -> None:
    baseline = permute_prior_end_dates(fanout_pairs).set_index("target_transaction_id")
    reordered = fanout_pairs.sample(frac=1, random_state=17)
    permuted_reordered = permute_prior_end_dates(reordered).set_index("target_transaction_id")

    pd.testing.assert_series_equal(
        baseline["prior_period_of_performance_end"].sort_index(),
        permuted_reordered["prior_period_of_performance_end"].sort_index(),
    )


@pytest.mark.parametrize(
    ("column", "value", "message"),
    [
        ("prior_award_id", " ", "must have a prior_award_id"),
        (
            "prior_period_of_performance_end",
            "not-a-date",
            "unparsable nonblank value",
        ),
    ],
)
def test_placebo_rejects_invalid_award_keys_and_dates(
    fanout_pairs: pd.DataFrame,
    column: str,
    value: str,
    message: str,
) -> None:
    invalid = fanout_pairs.copy()
    invalid.loc[0, column] = value

    with pytest.raises(NegativeControlInputError, match=message):
        permute_prior_end_dates(invalid)


def test_placebo_rejects_conflicting_dates_within_prior_award(
    fanout_pairs: pd.DataFrame,
) -> None:
    invalid = fanout_pairs.copy()
    invalid.loc[1, "prior_period_of_performance_end"] = "2022-01-01"

    with pytest.raises(NegativeControlInputError, match="map to exactly one"):
        permute_prior_end_dates(invalid)


def test_placebo_census_tables_delegate_to_both_existing_frozen_helpers(
    fanout_pairs: pd.DataFrame,
) -> None:
    permuted = permute_prior_end_dates(fanout_pairs)
    expected_dropoff = build_dropoff_ladder(permuted, DATA_CUT)
    expected_sensitivity = build_sensitivity_grid(permuted, DATA_CUT)

    actual_dropoff, actual_sensitivity = build_placebo_census_tables(fanout_pairs, DATA_CUT)

    pd.testing.assert_frame_equal(actual_dropoff, expected_dropoff)
    pd.testing.assert_frame_equal(actual_sensitivity, expected_sensitivity)


def test_placebo_census_tables_permute_once_and_share_one_frame(
    fanout_pairs: pd.DataFrame,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    permuted = permute_prior_end_dates(fanout_pairs)
    permute_calls: list[pd.DataFrame] = []
    helper_inputs: list[pd.DataFrame] = []

    def fake_permute(pairs: pd.DataFrame) -> pd.DataFrame:
        permute_calls.append(pairs)
        return permuted

    def fake_dropoff(pairs: pd.DataFrame, data_cut_date: date) -> pd.DataFrame:
        assert data_cut_date == DATA_CUT
        helper_inputs.append(pairs)
        return pd.DataFrame({"table": ["dropoff"]})

    def fake_sensitivity(pairs: pd.DataFrame, data_cut_date: date) -> pd.DataFrame:
        assert data_cut_date == DATA_CUT
        helper_inputs.append(pairs)
        return pd.DataFrame({"table": ["sensitivity"]})

    monkeypatch.setattr(methods_module, "permute_prior_end_dates", fake_permute)
    monkeypatch.setattr(methods_module, "build_dropoff_ladder", fake_dropoff)
    monkeypatch.setattr(methods_module, "build_sensitivity_grid", fake_sensitivity)

    dropoff, sensitivity = build_placebo_census_tables(fanout_pairs, DATA_CUT)

    assert len(permute_calls) == 1
    assert permute_calls[0] is fanout_pairs
    assert helper_inputs[0] is permuted
    assert helper_inputs[1] is permuted
    assert dropoff.loc[0, "table"] == "dropoff"
    assert sensitivity.loc[0, "table"] == "sensitivity"
