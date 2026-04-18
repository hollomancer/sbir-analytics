"""Unit tests for the phase_transition asset pipeline.

Covers the four asset functions and their helpers, using synthetic
in-memory frames — no Dagster runtime, no network, no filesystem reads
outside pytest's ``tmp_path``.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest


pytestmark = pytest.mark.fast


def _contracts_fixture() -> pd.DataFrame:
    """Synthetic FPDS/USAspending rows covering II, III, and noise."""

    return pd.DataFrame(
        [
            # Phase II contract (SR2)
            {
                "contract_id": "C_II_1",
                "vendor_uei": "AAAAAAAAAAAA",
                "vendor_duns": "123456789",
                "vendor_name": "Foo Inc",
                "awarding_agency_name": "DOD",
                "action_date": "2020-01-15",
                "period_of_performance_current_end_date": "2022-06-30",
                "research": "SR2",
                "federal_action_obligation": 750_000,
            },
            # Phase III contract (SR3)
            {
                "contract_id": "C_III_1",
                "vendor_uei": "AAAAAAAAAAAA",
                "vendor_duns": "123456789",
                "vendor_name": "Foo Inc",
                "awarding_agency_name": "DOD",
                "action_date": "2023-02-01",
                "period_of_performance_current_end_date": "2024-12-31",
                "research": "SR3",
                "federal_action_obligation": 5_000_000,
            },
            # Phase II contract for a different firm that never transitions (censored)
            {
                "contract_id": "C_II_2",
                "vendor_uei": "BBBBBBBBBBBB",
                "vendor_duns": "222333444",
                "vendor_name": "Bar LLC",
                "awarding_agency_name": "NASA",
                "action_date": "2021-05-01",
                "period_of_performance_current_end_date": "2023-06-30",
                "research": "SR2",
                "federal_action_obligation": 1_500_000,
            },
            # Unrelated contract (no SBIR flag) — must be ignored.
            {
                "contract_id": "C_NON_SBIR",
                "vendor_uei": "CCCCCCCCCCCC",
                "vendor_duns": "555666777",
                "vendor_name": "Baz Corp",
                "awarding_agency_name": "DOE",
                "action_date": "2022-04-01",
                "period_of_performance_current_end_date": "2024-04-01",
                "research": None,
                "federal_action_obligation": 300_000,
            },
            # Phase III that precedes Phase II end (negative latency case) — Phase II for
            # firm D ends 2024-01-01 but Phase III occurred 2023-09-01.
            {
                "contract_id": "C_II_3",
                "vendor_uei": "DDDDDDDDDDDD",
                "vendor_duns": "888999000",
                "vendor_name": "Qux Labs",
                "awarding_agency_name": "DOE",
                "action_date": "2022-01-15",
                "period_of_performance_current_end_date": "2024-01-01",
                "research": "SR2",
                "federal_action_obligation": 900_000,
            },
            {
                "contract_id": "C_III_2",
                "vendor_uei": "DDDDDDDDDDDD",
                "vendor_duns": "888999000",
                "vendor_name": "Qux Labs",
                "awarding_agency_name": "DOE",
                "action_date": "2023-09-01",
                "period_of_performance_current_end_date": "2025-09-01",
                "research": "SR3",
                "federal_action_obligation": 4_000_000,
            },
            # Phase III with only DUNS (no UEI) — exercises the DUNS-crosswalk fallback.
            {
                "contract_id": "C_II_4",
                "vendor_uei": "EEEEEEEEEEEE",
                "vendor_duns": "777666555",
                "vendor_name": "OldFirm",
                "awarding_agency_name": "HHS",
                "action_date": "2018-02-01",
                "period_of_performance_current_end_date": "2020-06-30",
                "research": "SR2",
                "federal_action_obligation": 1_000_000,
            },
            {
                "contract_id": "C_III_3",
                "vendor_uei": None,
                "vendor_duns": "777666555",
                "vendor_name": "OldFirm",
                "awarding_agency_name": "HHS",
                "action_date": "2021-12-01",
                "period_of_performance_current_end_date": "2023-12-01",
                "research": "SR3",
                "federal_action_obligation": 2_000_000,
            },
        ]
    )


# -- phase_ii / phase_iii helpers --------------------------------------------


def test_prepare_contract_rows_picks_only_phase_ii():
    from sbir_analytics.assets.phase_transition.phase_ii import _prepare_contract_rows

    df = _prepare_contract_rows(_contracts_fixture())
    assert set(df["award_id"]) == {"C_II_1", "C_II_2", "C_II_3", "C_II_4"}
    # Normalization: UEI uppercased/trimmed to 12 chars, DUNS 9 digits.
    foo = df.loc[df["award_id"] == "C_II_1"].iloc[0]
    assert foo["recipient_uei"] == "AAAAAAAAAAAA"
    assert foo["recipient_duns"] == "123456789"
    assert foo["source"] == "fpds_contract"
    assert bool(foo["phase_coding_reconciled"]) is False


def test_prepare_phase_iii_rows_excludes_assistance_and_other_phases():
    from sbir_analytics.assets.phase_transition.phase_iii import _prepare_phase_iii_rows

    df = _prepare_phase_iii_rows(_contracts_fixture())
    assert set(df["contract_id"]) == {"C_III_1", "C_III_2", "C_III_3"}
    # action_date required — dtype should be python date, never null here.
    assert df["action_date"].notna().all()


def test_is_assistance_row_recognizes_usaspending_type_and_award_type_code():
    """`type` is 'C'/'D' for assistance; `award_type_code` carries the numeric codes."""

    from sbir_analytics.assets.phase_transition.phase_ii import _is_assistance_row

    assert _is_assistance_row(pd.Series({"type": "C"}))
    assert _is_assistance_row(pd.Series({"type": "d"}))  # case-insensitive
    assert _is_assistance_row(pd.Series({"award_type_code": "04"}))
    assert _is_assistance_row(pd.Series({"cfda_number": "12.345"}))
    # Procurement rows (type A/B, no assistance markers) must NOT be flagged.
    assert not _is_assistance_row(pd.Series({"type": "A"}))
    assert not _is_assistance_row(pd.Series({"type": "B", "award_type_code": "C"}))


def test_sbir_gov_reconciliation_carries_reconciled_flag():
    from sbir_analytics.assets.phase_transition.phase_ii import _prepare_sbir_gov_rows

    awards = pd.DataFrame(
        [
            {
                "award_id": "SBIR-1",
                "company_uei": "FFFFFFFFFFFF",
                "company_duns": "123123123",
                "company_name": "GovReconFirm",
                "agency": "USDA",
                "branch": None,
                "award_amount": 100_000,
                "award_date": date(2021, 1, 1),
                "contract_start_date": date(2021, 2, 1),
                "contract_end_date": date(2023, 2, 1),
                "phase": "II",
            },
            # Phase I row should be excluded.
            {
                "award_id": "SBIR-2",
                "company_uei": None,
                "company_duns": None,
                "phase": "I",
            },
        ]
    )
    df = _prepare_sbir_gov_rows(awards)
    assert list(df["award_id"]) == ["SBIR-1"]
    assert bool(df.iloc[0]["phase_coding_reconciled"]) is True
    assert df.iloc[0]["source"] == "sbir_gov"


# -- pair + survival helpers --------------------------------------------------


def test_pairs_and_survival_end_to_end():
    from sbir_analytics.assets.phase_transition.pairs import _build_pairs, _build_survival
    from sbir_analytics.assets.phase_transition.phase_ii import _prepare_contract_rows
    from sbir_analytics.assets.phase_transition.phase_iii import _prepare_phase_iii_rows

    contracts = _contracts_fixture()
    phase_ii = _prepare_contract_rows(contracts)
    phase_iii = _prepare_phase_iii_rows(contracts)

    pairs = _build_pairs(phase_ii, phase_iii)

    # Three matches: C_II_1<->C_III_1 (UEI), C_II_3<->C_III_2 (UEI, negative),
    # C_II_4<->C_III_3 (DUNS crosswalk).
    assert len(pairs) == 3
    lookup = {row["phase_ii_award_id"]: row for _, row in pairs.iterrows()}

    assert lookup["C_II_1"]["identifier_basis"] == "uei"
    assert lookup["C_II_1"]["latency_days"] == (date(2023, 2, 1) - date(2022, 6, 30)).days
    assert bool(lookup["C_II_1"]["same_agency"]) is True

    # Negative latency must be preserved (not clipped).
    assert lookup["C_II_3"]["latency_days"] == (
        date(2023, 9, 1) - date(2024, 1, 1)
    ).days
    assert lookup["C_II_3"]["latency_days"] < 0

    # DUNS fallback path.
    assert lookup["C_II_4"]["identifier_basis"] == "duns_crosswalk"
    assert lookup["C_II_4"]["latency_days"] > 0

    # Survival: C_II_2 censors at the data cut; others are observed.
    data_cut = date(2026, 4, 17)
    survival = _build_survival(phase_ii, pairs, data_cut)
    assert len(survival) == 4
    s = survival.set_index("phase_ii_award_id")
    assert bool(s.loc["C_II_1", "event_observed"]) is True
    assert bool(s.loc["C_II_2", "event_observed"]) is False
    # Censored row's event_date equals the data-cut date.
    assert s.loc["C_II_2", "event_date"] == data_cut
    # time_days for censored row = data_cut - phase_ii_end_date.
    assert s.loc["C_II_2", "time_days"] == (
        data_cut - date(2023, 6, 30)
    ).days


def test_build_pairs_no_double_counting_on_duns_when_uei_already_matched():
    """A pair joined on UEI must not be re-emitted on DUNS."""

    from sbir_analytics.assets.phase_transition.pairs import _build_pairs

    phase_ii = pd.DataFrame(
        [
            {
                "award_id": "PII",
                "recipient_uei": "AAAAAAAAAAAA",
                "recipient_duns": "123456789",
                "recipient_name": "Firm",
                "agency": "DOD",
                "sub_agency": None,
                "award_amount": 1,
                "award_date": None,
                "period_of_performance_start": None,
                "period_of_performance_end": date(2022, 1, 1),
                "source": "fpds_contract",
                "phase_coding_reconciled": False,
            }
        ]
    )
    phase_iii = pd.DataFrame(
        [
            {
                "contract_id": "PIII",
                "recipient_uei": "AAAAAAAAAAAA",
                "recipient_duns": "123456789",
                "recipient_name": "Firm",
                "agency": "DOD",
                "sub_agency": None,
                "obligated_amount": 1,
                "action_date": date(2023, 1, 1),
                "period_of_performance_start": None,
                "period_of_performance_end": None,
            }
        ]
    )
    pairs = _build_pairs(phase_ii, phase_iii)
    assert len(pairs) == 1
    assert pairs.iloc[0]["identifier_basis"] == "uei"


def test_survival_respects_data_cut_from_env(monkeypatch):
    from sbir_analytics.assets.phase_transition.utils import parse_data_cut_date

    monkeypatch.setenv("SBIR_ETL__PHASE_TRANSITION__DATA_CUT_DATE", "2020-12-31")
    assert parse_data_cut_date() == date(2020, 12, 31)


# -- Pydantic contract smoke tests -------------------------------------------


def test_pydantic_contracts_round_trip_valid_rows():
    from sbir_etl.models.phase_transition import (
        PhaseIIAward,
        PhaseIIIContract,
        PhaseTransitionPair,
        PhaseTransitionSurvival,
    )

    PhaseIIAward(
        award_id="SBIR-1",
        recipient_uei="AAAAAAAAAAAA",
        recipient_duns="123456789",
        recipient_name="Firm",
        agency="DOD",
        sub_agency="AF",
        award_amount=500_000,
        award_date=date(2020, 1, 1),
        period_of_performance_start=date(2020, 1, 1),
        period_of_performance_end=date(2022, 1, 1),
        source="fpds_contract",
        phase_coding_reconciled=False,
    )
    PhaseIIIContract(
        contract_id="C_III",
        recipient_uei="AAAAAAAAAAAA",
        recipient_duns="123456789",
        recipient_name="Firm",
        agency="DOD",
        sub_agency="AF",
        obligated_amount=5_000_000,
        action_date=date(2023, 1, 1),
        period_of_performance_start=date(2023, 1, 1),
        period_of_performance_end=date(2025, 1, 1),
    )
    PhaseTransitionPair(
        recipient_uei="AAAAAAAAAAAA",
        recipient_duns=None,
        identifier_basis="uei",
        phase_ii_award_id="SBIR-1",
        phase_ii_source="fpds_contract",
        phase_ii_agency="DOD",
        phase_ii_end_date=date(2022, 1, 1),
        phase_iii_contract_id="C_III",
        phase_iii_agency="DOD",
        phase_iii_action_date=date(2023, 1, 1),
        latency_days=365,
        same_agency=True,
    )
    PhaseTransitionSurvival(
        phase_ii_award_id="SBIR-1",
        recipient_uei="AAAAAAAAAAAA",
        recipient_duns=None,
        phase_ii_agency="DOD",
        phase_ii_end_date=date(2022, 1, 1),
        event_observed=True,
        event_date=date(2023, 1, 1),
        time_days=365,
    )


def test_pydantic_contracts_reject_invalid_source():
    import pydantic
    from sbir_etl.models.phase_transition import PhaseIIAward

    with pytest.raises(pydantic.ValidationError):
        PhaseIIAward(
            award_id="x",
            source="not_a_real_source",
        )


# -- Asset wrapper smoke test (no Dagster, no real parquet data) -------------


def test_validated_phase_ii_awards_runs_on_empty_inputs(tmp_path, monkeypatch):
    """When upstream parquet files are absent, the asset should still run and
    emit an empty frame plus a checks JSON flagging missing inputs."""

    monkeypatch.chdir(tmp_path)
    from dagster import build_asset_context

    from sbir_analytics.assets.phase_transition import validated_phase_ii_awards

    out = validated_phase_ii_awards(context=build_asset_context())
    assert out.value.empty
    checks_path = tmp_path / "data/processed/phase_ii_awards.checks.json"
    assert checks_path.exists()
    import json

    payload = json.loads(checks_path.read_text())
    assert payload["total_rows"] == 0
    assert payload["inputs"]["contracts_exists"] is False
