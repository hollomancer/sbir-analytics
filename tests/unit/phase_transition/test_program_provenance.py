"""Program provenance through the phase-transition contracts.

The Phase III mart could not be filtered to STTR because ``Program`` was
dropped before the outcome tables: ``_classify_contract_phase`` maps both
``SR3`` and ``ST3`` to the phase ``"III"``, which discarded the one field that
distinguishes the two programs. These tests pin the restored path end to end —
Phase III, Phase II, pairs, survival — and pin what must stay null.

Synthetic in-memory frames only: no Dagster runtime, no network, no
filesystem reads.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from sbir_etl.models.phase_transition import PhaseIIIContract


pytestmark = pytest.mark.fast


def _phase_iii_row(**overrides) -> dict:
    """A minimal directly-identified Phase III contract transaction."""

    row = {
        "contract_id": "C_III",
        "generated_unique_award_id": "C_III",
        "transaction_unique_id": "TX-C_III",
        "vendor_uei": "AAAAAAAAAAAA",
        "vendor_duns": "123456789",
        "vendor_name": "Foo Inc",
        "awarding_agency_name": "DOD",
        "action_date": "2023-02-01",
        "period_of_performance_current_end_date": "2024-12-31",
        "federal_action_obligation": 5_000_000,
    }
    row.update(overrides)
    return row


# --- Phase III: the coded path carries the program -------------------------


def test_sr3_row_is_labelled_sbir_with_10q_evidence():
    from sbir_analytics.assets.phase_transition.phase_iii import _prepare_phase_iii_rows

    out = _prepare_phase_iii_rows(pd.DataFrame([_phase_iii_row(research="SR3")]))

    assert len(out) == 1
    assert out.loc[0, "program"] == "SBIR"
    assert out.loc[0, "program_evidence"] == "direct_10q"
    assert out.loc[0, "phase_iii_evidence"] == "direct_10q"


def test_st3_row_is_labelled_sttr_and_not_collapsed_into_sbir():
    """The regression this PR exists to prevent: ST3 must survive as STTR."""

    from sbir_analytics.assets.phase_transition.phase_iii import _prepare_phase_iii_rows

    out = _prepare_phase_iii_rows(pd.DataFrame([_phase_iii_row(research="ST3")]))

    assert len(out) == 1
    assert out.loc[0, "program"] == "STTR"
    assert out.loc[0, "program_evidence"] == "direct_10q"


def test_both_codes_in_one_frame_keep_their_own_programs():
    from sbir_analytics.assets.phase_transition.phase_iii import _prepare_phase_iii_rows

    out = _prepare_phase_iii_rows(
        pd.DataFrame(
            [
                _phase_iii_row(contract_id="C_SBIR", research="SR3"),
                _phase_iii_row(contract_id="C_STTR", research="ST3"),
            ]
        )
    )

    assert dict(zip(out["contract_id"], out["program"], strict=True)) == {
        "C_SBIR": "SBIR",
        "C_STTR": "STTR",
    }


# --- Phase III: every uncoded path stays null ------------------------------


@pytest.mark.parametrize(
    ("overrides", "expected_phase_evidence"),
    [
        # Explicit sbir_phase column, no 10Q code.
        ({"sbir_phase": "Phase III"}, "direct_sbir_phase"),
        # Descriptive phase string in `research` itself.
        ({"research": "PHASE III"}, "direct_research"),
        # Both a descriptive research string and an sbir_phase label.
        ({"research": "PHASE 3", "sbir_phase": "Phase III"}, "direct_sbir_phase"),
    ],
)
def test_uncoded_identification_paths_carry_no_program(overrides, expected_phase_evidence):
    from sbir_analytics.assets.phase_transition.phase_iii import _prepare_phase_iii_rows

    out = _prepare_phase_iii_rows(pd.DataFrame([_phase_iii_row(**overrides)]))

    assert len(out) == 1
    assert out.loc[0, "phase_iii_evidence"] == expected_phase_evidence
    assert out.loc[0, "program"] is None
    assert out.loc[0, "program_evidence"] is None


def test_description_mentioning_sttr_does_not_set_program():
    """A free-text mention is not a program code, even when it names STTR."""

    from sbir_analytics.assets.phase_transition.phase_iii import _prepare_phase_iii_rows

    out = _prepare_phase_iii_rows(
        pd.DataFrame(
            [
                _phase_iii_row(
                    sbir_phase="Phase III",
                    description="STTR PHASE III PRODUCTION FOLLOW-ON",
                )
            ]
        )
    )

    assert len(out) == 1
    assert out.loc[0, "program"] is None


# --- Phase III: the inheritance decision -----------------------------------


def _declared_parent_frame(parent_research: str) -> pd.DataFrame:
    """An ST3/SR3-coded IDV plus one task order that inherits Phase III."""

    return pd.DataFrame(
        [
            {
                "contract_id": "IDV_1",
                "piid": "IDV_1",
                "generated_unique_award_id": "IDV_1",
                "transaction_unique_id": "TX-IDV_1",
                "contract_award_type": "IDV_IDC",
                "awarding_agency_name": "DOD",
                "action_date": "2021-01-01",
                "research": parent_research,
                "vendor_uei": "AAAAAAAAAAAA",
                "vendor_name": "Foo Inc",
            },
            {
                "contract_id": "ORDER_1",
                "piid": "ORDER_1",
                "generated_unique_award_id": "ORDER_1",
                "transaction_unique_id": "TX-ORDER_1",
                "contract_award_type": "DO",
                "parent_contract_id": "IDV_1",
                "awarding_agency_name": "DOD",
                "action_date": "2023-03-01",
                "vendor_uei": "AAAAAAAAAAAA",
                "vendor_name": "Foo Inc",
                "federal_action_obligation": 2_000_000,
            },
        ]
    )


@pytest.mark.parametrize("parent_research", ["SR3", "ST3"])
def test_program_is_not_inherited_from_a_declared_parent_idv(parent_research):
    """Decision: task-order inheritance confers the phase, never the program.

    An IDV is a contract vehicle rather than a program membership, and taking
    the program from a different award record is the same imputation the
    unknown-program policy forbids elsewhere. Parametrized over both codes so
    the rule cannot be satisfied by accident for one of them.
    """

    from sbir_analytics.assets.phase_transition.phase_iii import _prepare_phase_iii_rows

    out = _prepare_phase_iii_rows(_declared_parent_frame(parent_research))
    order = out.loc[out["contract_id"] == "ORDER_1"].reset_index(drop=True)

    assert len(order) == 1
    assert bool(order.loc[0, "phase_iii_inherited"]) is True
    assert order.loc[0, "phase_iii_evidence"] == "parent_declared"
    assert order.loc[0, "program"] is None
    assert order.loc[0, "program_evidence"] is None


def test_the_coded_parent_itself_still_carries_its_own_program():
    """Not inheriting downward must not strip the parent's own direct evidence."""

    from sbir_analytics.assets.phase_transition.phase_iii import _prepare_phase_iii_rows

    out = _prepare_phase_iii_rows(_declared_parent_frame("ST3"))
    parent = out.loc[out["contract_id"] == "IDV_1"].reset_index(drop=True)

    assert len(parent) == 1
    assert parent.loc[0, "program"] == "STTR"
    assert parent.loc[0, "program_evidence"] == "direct_10q"


# --- the row contract enforces evidence/claim agreement --------------------


def test_contract_rejects_a_program_without_evidence():
    with pytest.raises(ValueError, match="program_evidence"):
        PhaseIIIContract(
            contract_id="C",
            phase_iii_evidence="direct_10q",
            phase_iii_inherited=False,
            program="STTR",
            program_evidence=None,
            action_date=date(2023, 1, 1),
        )


def test_contract_rejects_evidence_without_a_program():
    with pytest.raises(ValueError, match="program_evidence"):
        PhaseIIIContract(
            contract_id="C",
            phase_iii_evidence="direct_10q",
            phase_iii_inherited=False,
            program=None,
            program_evidence="direct_10q",
            action_date=date(2023, 1, 1),
        )


def test_contract_accepts_an_inherited_row_with_no_program():
    row = PhaseIIIContract(
        contract_id="ORDER_1",
        parent_contract_id="IDV_1",
        phase_iii_evidence="parent_declared",
        phase_iii_inherited=True,
        action_date=date(2023, 3, 1),
    )

    assert row.program is None
    assert row.program_evidence is None


# --- Phase II: the canonical SBIR.gov Program column -----------------------


def test_sbir_gov_rows_carry_the_canonical_program_column():
    from sbir_analytics.assets.phase_transition.phase_ii import _prepare_sbir_gov_rows

    out = _prepare_sbir_gov_rows(
        pd.DataFrame(
            [
                {
                    "award_id": "G1",
                    "phase": "Phase II",
                    "program": "STTR",
                    "company_uei": "AAAAAAAAAAAA",
                    "company_name": "Foo Inc",
                    "agency": "DOD",
                    "contract_end_date": "2022-06-30",
                },
                {
                    "award_id": "G2",
                    "phase": "Phase II",
                    "program": "SBIR",
                    "company_uei": "BBBBBBBBBBBB",
                    "company_name": "Bar LLC",
                    "agency": "NASA",
                    "contract_end_date": "2022-09-30",
                },
                {
                    "award_id": "G3",
                    "phase": "Phase II",
                    "program": None,
                    "company_uei": "CCCCCCCCCCCC",
                    "company_name": "Baz Corp",
                    "agency": "NIH",
                    "contract_end_date": "2022-12-31",
                },
            ]
        )
    )

    assert dict(zip(out["award_id"], out["program"], strict=True)) == {
        "G1": "STTR",
        "G2": "SBIR",
        "G3": None,
    }


def test_phase_ii_contract_rows_take_program_from_the_10q_code():
    from sbir_analytics.assets.phase_transition.phase_ii import _prepare_contract_rows

    out = _prepare_contract_rows(
        pd.DataFrame(
            [
                {
                    "contract_id": "C_II_SBIR",
                    "piid": "C_II_SBIR",
                    "generated_unique_award_id": "C_II_SBIR",
                    "transaction_unique_id": "TX1",
                    "research": "SR2",
                    "awarding_agency_name": "DOD",
                    "action_date": "2020-01-15",
                    "period_of_performance_current_end_date": "2022-06-30",
                },
                {
                    "contract_id": "C_II_STTR",
                    "piid": "C_II_STTR",
                    "generated_unique_award_id": "C_II_STTR",
                    "transaction_unique_id": "TX2",
                    "research": "ST2",
                    "awarding_agency_name": "DOD",
                    "action_date": "2020-02-15",
                    "period_of_performance_current_end_date": "2022-07-31",
                },
                {
                    "contract_id": "C_II_UNCODED",
                    "piid": "C_II_UNCODED",
                    "generated_unique_award_id": "C_II_UNCODED",
                    "transaction_unique_id": "TX3",
                    "sbir_phase": "Phase II",
                    "awarding_agency_name": "DOD",
                    "action_date": "2020-03-15",
                    "period_of_performance_current_end_date": "2022-08-31",
                },
            ]
        )
    )

    assert dict(zip(out["award_id"], out["program"], strict=True)) == {
        "C_II_SBIR": "SBIR",
        "C_II_STTR": "STTR",
        "C_II_UNCODED": None,
    }


# --- pairs and survival carry both sides -----------------------------------


def _phase_ii_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "award_id": "P2_STTR",
                "source": "sbir_gov",
                "agency": "DOD",
                "program": "STTR",
                "period_of_performance_end": date(2022, 6, 30),
                "recipient_uei": "AAAAAAAAAAAA",
                "recipient_duns": "123456789",
            },
            {
                "award_id": "P2_UNKNOWN",
                "source": "fpds_contract",
                "agency": "DOD",
                "program": None,
                "period_of_performance_end": date(2022, 6, 30),
                "recipient_uei": "BBBBBBBBBBBB",
                "recipient_duns": "222333444",
            },
        ]
    )


def _phase_iii_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "contract_id": "P3_STTR",
                "agency": "DOD",
                "program": "STTR",
                "action_date": date(2023, 2, 1),
                "recipient_uei": "AAAAAAAAAAAA",
                "recipient_duns": "123456789",
            },
            {
                "contract_id": "P3_UNKNOWN",
                "agency": "DOD",
                "program": None,
                "action_date": date(2023, 5, 1),
                "recipient_uei": "BBBBBBBBBBBB",
                "recipient_duns": "222333444",
            },
        ]
    )


def test_pairs_carry_both_programs_independently():
    from sbir_analytics.assets.phase_transition.pairs import _build_pairs

    pairs = _build_pairs(_phase_ii_frame(), _phase_iii_frame())
    by_pair = {
        (r.phase_ii_award_id, r.phase_iii_contract_id): (
            r.phase_ii_program,
            r.phase_iii_program,
        )
        for r in pairs.itertuples()
    }

    assert by_pair[("P2_STTR", "P3_STTR")] == ("STTR", "STTR")
    assert by_pair[("P2_UNKNOWN", "P3_UNKNOWN")] == (None, None)


def test_a_known_phase_ii_program_does_not_fill_an_unknown_phase_iii_program():
    """The two sides are never reconciled against each other."""

    from sbir_analytics.assets.phase_transition.pairs import _build_pairs

    phase_iii = _phase_iii_frame()
    phase_iii.loc[phase_iii["contract_id"] == "P3_STTR", "program"] = None

    pairs = _build_pairs(_phase_ii_frame(), phase_iii)
    row = pairs.loc[pairs["phase_iii_contract_id"] == "P3_STTR"].reset_index(drop=True)

    assert len(row) == 1
    assert row.loc[0, "phase_ii_program"] == "STTR"
    assert row.loc[0, "phase_iii_program"] is None


def test_survival_frame_carries_phase_ii_program():
    from sbir_analytics.assets.phase_transition.pairs import (
        _build_pairs,
        _build_survival,
    )

    phase_ii = _phase_ii_frame()
    pairs = _build_pairs(phase_ii, _phase_iii_frame())
    survival = _build_survival(phase_ii, pairs, date(2025, 12, 31))

    assert dict(zip(survival["phase_ii_award_id"], survival["phase_ii_program"], strict=True)) == {
        "P2_STTR": "STTR",
        "P2_UNKNOWN": None,
    }


def test_pairs_tolerate_a_stale_upstream_frame_without_a_program_column():
    """A mart written before this change yields nulls, not a KeyError."""

    from sbir_analytics.assets.phase_transition.pairs import _build_pairs

    phase_ii = _phase_ii_frame().drop(columns=["program"])
    phase_iii = _phase_iii_frame().drop(columns=["program"])

    pairs = _build_pairs(phase_ii, phase_iii)

    assert len(pairs) == 2
    assert pairs["phase_ii_program"].isna().all()
    assert pairs["phase_iii_program"].isna().all()


# --- the exclusion policy applied to a real survival frame -----------------


def test_unknown_program_rows_leave_a_program_specific_survival_measure():
    """End-to-end: the unknown-program row is in neither numerator nor denominator.

    Both firms have an observed Phase III event, so a leak would be visible in
    the STTR rate rather than hidden by a zero.
    """

    from sbir_analytics.assets.phase_transition.pairs import (
        _build_pairs,
        _build_survival,
    )
    from sbir_etl.models.sbir_program import program_specific_measure

    phase_ii = _phase_ii_frame()
    pairs = _build_pairs(phase_ii, _phase_iii_frame())
    survival = _build_survival(phase_ii, pairs, date(2025, 12, 31))

    assert bool(survival["event_observed"].all()) is True

    measure = program_specific_measure(
        survival.itertuples(),
        "STTR",
        program_of=lambda r: r.phase_ii_program,
        event_of=lambda r: bool(r.event_observed),
    )

    assert measure.total == 2
    assert measure.denominator == 1
    assert measure.numerator == 1
    assert measure.unknown_program == 1
    assert measure.program_coverage == pytest.approx(0.5)
