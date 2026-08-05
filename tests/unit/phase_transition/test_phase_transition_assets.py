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
                "piid": "C_II_1",
                "generated_unique_award_id": "C_II_1",
                "transaction_unique_id": "TX-C_II_1",
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
                "generated_unique_award_id": "C_III_1",
                "transaction_unique_id": "TX-C_III_1",
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
                "piid": "C_II_2",
                "generated_unique_award_id": "C_II_2",
                "transaction_unique_id": "TX-C_II_2",
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
                "generated_unique_award_id": "C_NON_SBIR",
                "transaction_unique_id": "TX-C_NON_SBIR",
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
                "piid": "C_II_3",
                "generated_unique_award_id": "C_II_3",
                "transaction_unique_id": "TX-C_II_3",
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
                "generated_unique_award_id": "C_III_2",
                "transaction_unique_id": "TX-C_III_2",
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
                "piid": "C_II_4",
                "generated_unique_award_id": "C_II_4",
                "transaction_unique_id": "TX-C_II_4",
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
                "generated_unique_award_id": "C_III_3",
                "transaction_unique_id": "TX-C_III_3",
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
    assert foo["source_award_id"] == "C_II_1"
    assert foo["representative_transaction_id"] == "TX-C_II_1"
    assert foo["source_transaction_count"] == 1


@pytest.mark.parametrize(
    ("naics_column", "psc_column"),
    [
        ("naics_code", "psc_code"),
        ("naics", "product_or_service_code"),
    ],
)
def test_prepare_contract_rows_passes_through_taxonomy_aliases(naics_column, psc_column):
    from sbir_analytics.assets.phase_transition.phase_ii import _prepare_contract_rows

    row = {
        "contract_id": "C_II_TAXONOMY",
        "generated_unique_award_id": "GEN-TAXONOMY",
        "transaction_unique_id": "TX-TAXONOMY",
        "vendor_uei": "AAAAAAAAAAAA",
        "research": "SR2",
        naics_column: "541715",
        psc_column: "AC12",
    }

    result = _prepare_contract_rows(pd.DataFrame([row])).iloc[0]

    assert result["naics_code"] == "541715"
    assert result["psc_code"] == "AC12"


def test_prepare_phase_iii_rows_excludes_assistance_and_other_phases():
    from sbir_analytics.assets.phase_transition.phase_iii import _prepare_phase_iii_rows

    df = _prepare_phase_iii_rows(_contracts_fixture())
    assert set(df["contract_id"]) == {"C_III_1", "C_III_2", "C_III_3"}
    # action_date required — dtype should be python date, never null here.
    assert df["action_date"].notna().all()


@pytest.mark.parametrize(
    ("research", "expected"),
    [
        ("SMALL BUSINESS INNOVATION RESEARCH PROGRAM PHASE II ACTION", "II"),
        ("SMALL BUSINESS INNOVATION RESEARCH PROGRAM PHASE III ACTION", "III"),
        ("SMALL TECHNOLOGY TRANSFER RESEARCH PROGRAM PHASE II", "II"),
        ("SMALL TECHNOLOGY TRANSFER RESEARCH PROGRAM PHASE III", "III"),
    ],
)
def test_classify_contract_phase_accepts_award_archive_descriptions(research, expected):
    from sbir_analytics.assets.phase_transition.phase_ii import _classify_contract_phase

    assert _classify_contract_phase(pd.Series({"research": research})) == expected


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
                "naics": "541715",
                "product_or_service_code": "AC12",
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
    assert df.iloc[0]["naics_code"] == "541715"
    assert df.iloc[0]["psc_code"] == "AC12"


def test_prepare_sbir_gov_rows_resets_filtered_index_for_minimal_phase_ii_row():
    from sbir_analytics.assets.phase_transition.phase_ii import _prepare_sbir_gov_rows

    awards = pd.DataFrame(
        [
            {"award_id": "PHASE-I", "phase": "I"},
            {"award_id": "PHASE-II", "phase": "II"},
        ]
    )

    result = _prepare_sbir_gov_rows(awards)

    assert len(result) == 1
    assert result.iloc[0]["award_id"] == "PHASE-II"


def test_unify_fills_only_missing_federal_taxonomy_from_reconciled_duplicate():
    from sbir_analytics.assets.phase_transition.phase_ii import (
        _prepare_contract_rows,
        _prepare_sbir_gov_rows,
        _unify,
    )

    federal = _prepare_contract_rows(
        pd.DataFrame(
            [
                {
                    "contract_id": "SHARED-AWARD",
                    "piid": "SHARED-AWARD",
                    "generated_unique_award_id": "CONT_AWD_GENERATED_SHARED",
                    "transaction_unique_id": "TX-SHARED-AWARD",
                    "vendor_uei": "AAAAAAAAAAAA",
                    "research": "SR2",
                    "action_date": "2020-01-01",
                    "period_of_performance_current_end_date": "2022-01-01",
                    "naics_code": None,
                    "psc_code": "FEDERAL-PSC",
                }
            ]
        )
    )
    reconciled = _prepare_sbir_gov_rows(
        pd.DataFrame(
            [
                {
                    "award_id": "SHARED-AWARD",
                    "company_uei": "AAAAAAAAAAAA",
                    "phase": "II",
                    "naics_code": "541715",
                    "psc_code": " federal-psc ",
                }
            ]
        )
    )

    result = _unify(federal, reconciled).iloc[0]

    assert result["award_id"] == "CONT_AWD_GENERATED_SHARED"
    assert result["source_award_id"] == "SHARED-AWARD"
    assert result["source"] == "fpds_contract"
    assert result["period_of_performance_end"] == date(2022, 1, 1)
    assert result["naics_code"] == "541715"
    assert result["psc_code"] == "FEDERAL-PSC"


def test_prepare_contract_rows_uses_latest_snapshot_not_maximum_end_and_is_order_stable():
    from sbir_analytics.assets.phase_transition.phase_ii import _prepare_contract_rows

    rows = [
        {
            "contract_id": "SAME-PIID",
            "piid": "SAME-PIID",
            "generated_unique_award_id": " cont_awd_stable ",
            "transaction_unique_id": "TX-001",
            "vendor_uei": "AAAAAAAAAAAA",
            "awarding_toptier_agency_name": "DOD",
            "research": "SR2",
            "action_date": "2020-01-01",
            "period_of_performance_current_end_date": "2025-12-31",
            "naics_code": "OLD",
            "product_or_service_code": "OLD-PSC",
            "federal_action_obligation": 100,
        },
        {
            "contract_id": "SAME-PIID",
            "piid": "SAME-PIID",
            "generated_unique_award_id": "CONT_AWD_STABLE",
            "transaction_unique_id": "TX-002",
            "vendor_uei": "AAAAAAAAAAAA",
            "awarding_toptier_agency_name": "DOD",
            "research": "SR2",
            "action_date": "2022-01-01",
            "period_of_performance_current_end_date": "2024-12-31",
            "naics_code": "NEW",
            "product_or_service_code": "NEW-PSC",
            "federal_action_obligation": -10,
        },
    ]

    forward = _prepare_contract_rows(pd.DataFrame(rows))
    reverse = _prepare_contract_rows(pd.DataFrame(list(reversed(rows))))

    pd.testing.assert_frame_equal(forward, reverse)
    award = forward.iloc[0]
    assert award["award_id"] == "CONT_AWD_STABLE"
    assert award["representative_transaction_id"] == "TX-002"
    assert award["source_transaction_count"] == 2
    assert award["award_date"] == date(2020, 1, 1)
    assert award["period_of_performance_end"] == date(2024, 12, 31)
    assert award["naics_code"] == "NEW"
    assert award["psc_code"] == "NEW-PSC"
    assert award["award_amount"] == 90


def test_prepare_contract_rows_breaks_same_date_ties_by_transaction_id():
    from sbir_analytics.assets.phase_transition.phase_ii import _prepare_contract_rows

    rows = [
        {
            "contract_id": "SAME-PIID",
            "piid": "SAME-PIID",
            "generated_unique_award_id": "CONT_AWD_SAME_DATE",
            "transaction_unique_id": "tx-a",
            "vendor_uei": "AAAAAAAAAAAA",
            "research": "SR2",
            "action_date": "2022-01-01",
            "period_of_performance_current_end_date": "2025-01-01",
        },
        {
            "contract_id": "SAME-PIID",
            "piid": "SAME-PIID",
            "generated_unique_award_id": "CONT_AWD_SAME_DATE",
            "transaction_unique_id": "TX-Z",
            "vendor_uei": "AAAAAAAAAAAA",
            "research": "SR2",
            "action_date": "2022-01-01",
            "period_of_performance_current_end_date": "2024-01-01",
        },
    ]

    forward = _prepare_contract_rows(pd.DataFrame(rows))
    reverse = _prepare_contract_rows(pd.DataFrame(list(reversed(rows))))

    pd.testing.assert_frame_equal(forward, reverse)
    award = forward.iloc[0]
    assert award["representative_transaction_id"] == "TX-Z"
    assert award["period_of_performance_end"] == date(2024, 1, 1)


def test_prepare_contract_rows_never_substitutes_contract_id_for_missing_piid():
    from sbir_analytics.assets.phase_transition.phase_ii import (
        _prepare_contract_rows,
        _prepare_sbir_gov_rows,
        _unify,
    )

    federal = _prepare_contract_rows(
        pd.DataFrame(
            [
                {
                    "contract_id": "CONT_AWD_1",
                    "generated_unique_award_id": "CONT_AWD_1",
                    "transaction_unique_id": "TX-1",
                    "vendor_uei": "AAAAAAAAAAAA",
                    "research": "SR2",
                }
            ]
        )
    )

    result = federal.iloc[0]
    assert result["award_id"] == "CONT_AWD_1"
    assert pd.isna(result["source_award_id"])

    supplemental = _prepare_sbir_gov_rows(
        pd.DataFrame(
            [
                {
                    "award_id": "SBIR-1",
                    "contract": "CONT_AWD_1",
                    "phase": "II",
                }
            ]
        )
    )
    unified = _unify(federal, supplemental)

    assert set(unified["award_id"]) == {"CONT_AWD_1", "SBIR-1"}


def test_prepare_contract_rows_rejects_conflicting_transaction_payloads():
    from sbir_analytics.assets.phase_transition.phase_ii import (
        PhaseIIInputError,
        _prepare_contract_rows,
    )

    base = {
        "contract_id": "PIID-1",
        "piid": "PIID-1",
        "generated_unique_award_id": "CONT_AWD_1",
        "transaction_unique_id": "TX-1",
        "vendor_uei": "AAAAAAAAAAAA",
        "research": "SR2",
        "action_date": "2022-01-01",
    }
    rows = [
        {**base, "period_of_performance_current_end_date": "2024-01-01"},
        {**base, "period_of_performance_current_end_date": "2025-01-01"},
    ]

    with pytest.raises(PhaseIIInputError, match="conflicting source values.*TX-1"):
        _prepare_contract_rows(pd.DataFrame(rows))


def test_prepare_contract_rows_rejects_conflicting_phase_codes_for_one_transaction():
    from sbir_analytics.assets.phase_transition.phase_ii import (
        PhaseIIInputError,
        _prepare_contract_rows,
    )

    base = {
        "contract_id": "PIID-1",
        "piid": "PIID-1",
        "generated_unique_award_id": "CONT_AWD_1",
        "transaction_unique_id": "TX-1",
        "vendor_uei": "AAAAAAAAAAAA",
        "action_date": "2022-01-01",
    }

    with pytest.raises(PhaseIIInputError, match="conflicting source values.*TX-1"):
        _prepare_contract_rows(
            pd.DataFrame([{**base, "research": "SR2"}, {**base, "research": "ST2"}])
        )


@pytest.mark.parametrize("missing_key", ["generated_unique_award_id", "transaction_unique_id"])
def test_prepare_contract_rows_requires_stable_federal_keys(missing_key):
    from sbir_analytics.assets.phase_transition.phase_ii import (
        PhaseIIInputError,
        _prepare_contract_rows,
    )

    row = {
        "contract_id": "PIID-1",
        "generated_unique_award_id": "CONT_AWD_1",
        "transaction_unique_id": "TX-1",
        "vendor_uei": "AAAAAAAAAAAA",
        "research": "SR2",
    }
    row.pop(missing_key)

    with pytest.raises(PhaseIIInputError, match=missing_key):
        _prepare_contract_rows(pd.DataFrame([row]))


@pytest.mark.parametrize(
    ("contract", "agency_tracking_number", "expected"),
    [
        ("CONTRACT-ID", "TRACKING-ID", "CONTRACT-ID"),
        (r"\N", "TRACKING-ID", "TRACKING-ID"),
        (None, None, "SBIR-ID"),
    ],
)
def test_prepare_sbir_gov_rows_uses_frozen_source_id_priority(
    contract, agency_tracking_number, expected
):
    from sbir_analytics.assets.phase_transition.phase_ii import _prepare_sbir_gov_rows

    result = _prepare_sbir_gov_rows(
        pd.DataFrame(
            [
                {
                    "award_id": "SBIR-ID",
                    "contract": contract,
                    "agency_tracking_number": agency_tracking_number,
                    "phase": "II",
                }
            ]
        )
    ).iloc[0]

    assert result["source_award_id"] == expected


def test_unify_reconciles_only_exact_normalized_source_ids():
    from sbir_analytics.assets.phase_transition.phase_ii import (
        _prepare_contract_rows,
        _prepare_sbir_gov_rows,
        _unify,
    )

    federal = _prepare_contract_rows(
        pd.DataFrame(
            [
                {
                    "contract_id": "PIID-EXACT",
                    "piid": "PIID-EXACT",
                    "generated_unique_award_id": "CONT_AWD_EXACT",
                    "transaction_unique_id": "TX-EXACT",
                    "vendor_uei": "AAAAAAAAAAAA",
                    "research": "SR2",
                }
            ]
        )
    )
    supplemental = _prepare_sbir_gov_rows(
        pd.DataFrame(
            [
                {
                    "award_id": "SBIR-EXACT",
                    "contract": " piid-exact ",
                    "company_uei": "AAAAAAAAAAAA",
                    "phase": "II",
                },
                {
                    "award_id": "SBIR-NONMATCH",
                    "contract": "PIID-OTHER",
                    "company_uei": "AAAAAAAAAAAA",
                    "phase": "II",
                },
            ]
        )
    )

    result = _unify(federal, supplemental)

    assert set(result["award_id"]) == {"CONT_AWD_EXACT", "SBIR-NONMATCH"}
    assert result.loc[result["award_id"] == "CONT_AWD_EXACT", "source"].item() == "fpds_contract"


def test_unify_reconciles_multiple_agreeing_and_blank_supplementals_into_one_federal_row():
    from sbir_analytics.assets.phase_transition.phase_ii import (
        _prepare_contract_rows,
        _prepare_sbir_gov_rows,
        _unify,
    )

    federal = _prepare_contract_rows(
        pd.DataFrame(
            [
                {
                    "contract_id": "PIID-1",
                    "piid": "PIID-1",
                    "generated_unique_award_id": "CONT_AWD_1",
                    "transaction_unique_id": "TX-1",
                    "vendor_uei": "AAAAAAAAAAAA",
                    "research": "SR2",
                    "naics_code": None,
                    "psc_code": None,
                }
            ]
        )
    )
    supplemental = _prepare_sbir_gov_rows(
        pd.DataFrame(
            [
                {
                    "award_id": "SBIR-1",
                    "contract": "PIID-1",
                    "phase": "II",
                    "naics_code": " 541715 ",
                    "psc_code": None,
                },
                {
                    "award_id": "SBIR-2",
                    "contract": "PIID-1",
                    "phase": "II",
                    "naics_code": "541715",
                    "psc_code": " ac12 ",
                },
                {
                    "award_id": "SBIR-3",
                    "contract": "PIID-1",
                    "phase": "II",
                    "naics_code": None,
                    "psc_code": "AC12",
                },
            ]
        )
    )

    result = _unify(federal, supplemental)

    assert len(result) == 1
    assert result.iloc[0]["award_id"] == "CONT_AWD_1"
    assert result.iloc[0]["source"] == "fpds_contract"
    assert result.iloc[0]["naics_code"] == "541715"
    assert result.iloc[0]["psc_code"] == "AC12"


def test_unify_preserves_all_non_taxonomy_federal_fields_with_multiple_supplementals():
    from sbir_analytics.assets.phase_transition.phase_ii import (
        _prepare_contract_rows,
        _prepare_sbir_gov_rows,
        _unify,
    )

    federal = _prepare_contract_rows(
        pd.DataFrame(
            [
                {
                    "piid": "PIID-1",
                    "generated_unique_award_id": "CONT_AWD_1",
                    "transaction_unique_id": "TX-1",
                    "vendor_uei": "FEDERAL-UEI",
                    "vendor_duns": "123456789",
                    "vendor_name": "Federal Recipient",
                    "awarding_toptier_agency_name": "FEDERAL AGENCY",
                    "awarding_sub_tier_agency_name": "FEDERAL SUBAGENCY",
                    "research": "SR2",
                    "action_date": "2020-01-02",
                    "period_of_performance_start_date": "2020-02-03",
                    "period_of_performance_current_end_date": "2022-04-05",
                    "federal_action_obligation": 123_456,
                    "naics_code": None,
                    "psc_code": "AC12",
                }
            ]
        )
    )
    supplemental = _prepare_sbir_gov_rows(
        pd.DataFrame(
            [
                {
                    "award_id": "SBIR-1",
                    "contract": "PIID-1",
                    "company_uei": "SUPPLEMENTAL-UEI-1",
                    "company_name": "Supplemental Recipient One",
                    "agency": "SUPPLEMENTAL AGENCY ONE",
                    "branch": "SUPPLEMENTAL BRANCH ONE",
                    "phase": "II",
                    "award_amount": 1,
                    "award_date": "2018-01-01",
                    "contract_start_date": "2018-02-01",
                    "contract_end_date": "2019-01-01",
                    "naics_code": "541715",
                    "psc_code": "ac12",
                },
                {
                    "award_id": "SBIR-2",
                    "contract": "PIID-1",
                    "company_uei": "SUPPLEMENTAL-UEI-2",
                    "company_name": "Supplemental Recipient Two",
                    "agency": "SUPPLEMENTAL AGENCY TWO",
                    "branch": "SUPPLEMENTAL BRANCH TWO",
                    "phase": "II",
                    "award_amount": 2,
                    "award_date": "2017-01-01",
                    "contract_start_date": "2017-02-01",
                    "contract_end_date": "2023-01-01",
                    "naics_code": "541715",
                    "psc_code": None,
                },
            ]
        )
    )
    expected = federal.iloc[0].drop(labels=["naics_code", "psc_code"])

    result = _unify(federal, supplemental)

    pd.testing.assert_series_equal(result.iloc[0].drop(labels=["naics_code", "psc_code"]), expected)
    assert result.iloc[0]["naics_code"] == "541715"
    assert result.iloc[0]["psc_code"] == "AC12"


def test_unify_leaves_distinct_unmatched_supplemental_multiplicity_untouched():
    from sbir_analytics.assets.phase_transition.phase_ii import (
        PHASE_II_COLUMNS,
        _prepare_sbir_gov_rows,
        _unify,
    )

    supplemental = _prepare_sbir_gov_rows(
        pd.DataFrame(
            [
                {
                    "award_id": "SBIRGOV:UNMATCHED:" + "a" * 64,
                    "source_award_id": "UNMATCHED",
                    "source_row_sha256": "a" * 64,
                    "company_name": "Recipient One",
                    "phase": "II",
                },
                {
                    "award_id": "SBIRGOV:UNMATCHED:" + "b" * 64,
                    "source_award_id": "UNMATCHED",
                    "source_row_sha256": "b" * 64,
                    "company_name": "Recipient Two",
                    "phase": "II",
                },
            ]
        )
    )

    result = _unify(pd.DataFrame(columns=PHASE_II_COLUMNS), supplemental)

    assert len(result) == 2
    assert set(result["award_id"]) == {
        "SBIRGOV:UNMATCHED:" + "a" * 64,
        "SBIRGOV:UNMATCHED:" + "b" * 64,
    }
    assert set(result["recipient_name"]) == {"Recipient One", "Recipient Two"}


@pytest.mark.parametrize(
    ("taxonomy_column", "first_value", "second_value"),
    [
        ("naics_code", "541715", "541713"),
        ("psc_code", "AC12", "AC13"),
    ],
)
def test_unify_rejects_conflicting_multiple_supplemental_taxonomy(
    taxonomy_column, first_value, second_value
):
    from sbir_analytics.assets.phase_transition.phase_ii import (
        PhaseIIInputError,
        _prepare_contract_rows,
        _prepare_sbir_gov_rows,
        _unify,
    )

    federal = _prepare_contract_rows(
        pd.DataFrame(
            [
                {
                    "piid": "PIID-1",
                    "generated_unique_award_id": "CONT_AWD_1",
                    "transaction_unique_id": "TX-1",
                    "research": "SR2",
                }
            ]
        )
    )
    supplemental = _prepare_sbir_gov_rows(
        pd.DataFrame(
            [
                {
                    "award_id": "SBIR-1",
                    "contract": "PIID-1",
                    "phase": "II",
                    taxonomy_column: first_value,
                },
                {
                    "award_id": "SBIR-2",
                    "contract": "PIID-1",
                    "phase": "II",
                    taxonomy_column: second_value,
                },
            ]
        )
    )

    with pytest.raises(PhaseIIInputError, match=f"conflicting {taxonomy_column}"):
        _unify(federal, supplemental)


@pytest.mark.parametrize(
    ("taxonomy_column", "federal_value", "supplemental_value"),
    [
        ("naics_code", "541715", "541713"),
        ("psc_code", "AC12", "AC13"),
    ],
)
def test_unify_rejects_federal_supplemental_taxonomy_mismatch(
    taxonomy_column, federal_value, supplemental_value
):
    from sbir_analytics.assets.phase_transition.phase_ii import (
        PhaseIIInputError,
        _prepare_contract_rows,
        _prepare_sbir_gov_rows,
        _unify,
    )

    federal = _prepare_contract_rows(
        pd.DataFrame(
            [
                {
                    "piid": "PIID-1",
                    "generated_unique_award_id": "CONT_AWD_1",
                    "transaction_unique_id": "TX-1",
                    "vendor_uei": "AAAAAAAAAAAA",
                    "research": "SR2",
                    taxonomy_column: federal_value,
                }
            ]
        )
    )
    supplemental = _prepare_sbir_gov_rows(
        pd.DataFrame(
            [
                {
                    "award_id": "SBIR-1",
                    "contract": "PIID-1",
                    "phase": "II",
                    taxonomy_column: supplemental_value,
                }
            ]
        )
    )

    with pytest.raises(PhaseIIInputError, match=f"conflicting {taxonomy_column}"):
        _unify(federal, supplemental)


@pytest.mark.parametrize(
    ("taxonomy_column", "federal_value", "supplemental_value"),
    [
        ("naics_code", " 541715 ", "541715"),
        ("psc_code", " ac12 ", "AC12"),
    ],
)
def test_unify_preserves_federal_taxonomy_when_normalized_values_match(
    taxonomy_column, federal_value, supplemental_value
):
    from sbir_analytics.assets.phase_transition.phase_ii import (
        _prepare_contract_rows,
        _prepare_sbir_gov_rows,
        _unify,
    )

    federal = _prepare_contract_rows(
        pd.DataFrame(
            [
                {
                    "piid": "PIID-1",
                    "generated_unique_award_id": "CONT_AWD_1",
                    "transaction_unique_id": "TX-1",
                    "vendor_uei": "AAAAAAAAAAAA",
                    "research": "SR2",
                    taxonomy_column: federal_value,
                }
            ]
        )
    )
    supplemental = _prepare_sbir_gov_rows(
        pd.DataFrame(
            [
                {
                    "award_id": "SBIR-1",
                    "contract": "PIID-1",
                    "phase": "II",
                    taxonomy_column: supplemental_value,
                }
            ]
        )
    )

    result = _unify(federal, supplemental)

    assert len(result) == 1
    assert result.iloc[0]["source"] == "fpds_contract"
    assert result.iloc[0][taxonomy_column] == federal_value

    missing_federal = federal.copy()
    missing_federal.loc[:, taxonomy_column] = None
    filled = _unify(
        missing_federal,
        _prepare_sbir_gov_rows(
            pd.DataFrame(
                [
                    {
                        "award_id": "SBIR-1",
                        "contract": "PIID-1",
                        "phase": "II",
                        taxonomy_column: f" {supplemental_value.lower()} ",
                    }
                ]
            )
        ),
    )
    assert filled.iloc[0][taxonomy_column] == supplemental_value.strip().upper()


def test_unify_stops_on_cross_agency_piid_ambiguity():
    from sbir_analytics.assets.phase_transition.phase_ii import (
        PhaseIIInputError,
        _prepare_contract_rows,
        _prepare_sbir_gov_rows,
        _unify,
    )

    federal = _prepare_contract_rows(
        pd.DataFrame(
            [
                {
                    "contract_id": "DUPLICATE-PIID",
                    "piid": "DUPLICATE-PIID",
                    "generated_unique_award_id": "CONT_AWD_AGENCY_A",
                    "transaction_unique_id": "TX-A",
                    "vendor_uei": "AAAAAAAAAAAA",
                    "agency": "AGENCY A",
                    "research": "SR2",
                },
                {
                    "contract_id": "DUPLICATE-PIID",
                    "piid": "DUPLICATE-PIID",
                    "generated_unique_award_id": "CONT_AWD_AGENCY_B",
                    "transaction_unique_id": "TX-B",
                    "vendor_uei": "AAAAAAAAAAAA",
                    "agency": "AGENCY B",
                    "research": "SR2",
                },
            ]
        )
    )
    supplemental = _prepare_sbir_gov_rows(
        pd.DataFrame(
            [
                {
                    "award_id": "SBIR-1",
                    "contract": "DUPLICATE-PIID",
                    "company_uei": "AAAAAAAAAAAA",
                    "phase": "II",
                }
            ]
        )
    )

    with pytest.raises(PhaseIIInputError, match="requires exactly one federal match"):
        _unify(federal, supplemental)


def test_unify_multi_supplemental_reconciliation_is_order_independent():
    from sbir_analytics.assets.phase_transition.phase_ii import (
        _prepare_contract_rows,
        _prepare_sbir_gov_rows,
        _unify,
    )

    federal = _prepare_contract_rows(
        pd.DataFrame(
            [
                {
                    "piid": "SHARED-PIID",
                    "generated_unique_award_id": "CONT_AWD_SHARED",
                    "transaction_unique_id": "TX-SHARED",
                    "research": "SR2",
                }
            ]
        )
    )
    supplemental = _prepare_sbir_gov_rows(
        pd.DataFrame(
            [
                {
                    "award_id": "SBIRGOV:SHARED-PIID:" + "a" * 64,
                    "source_award_id": "SHARED-PIID",
                    "source_row_sha256": "a" * 64,
                    "phase": "II",
                    "naics_code": None,
                    "psc_code": "ac12",
                },
                {
                    "award_id": "SBIRGOV:SHARED-PIID:" + "b" * 64,
                    "source_award_id": "SHARED-PIID",
                    "source_row_sha256": "b" * 64,
                    "phase": "II",
                    "naics_code": "541715",
                    "psc_code": "AC12",
                },
            ]
        )
    )

    forward = _unify(federal, supplemental)
    reversed_result = _unify(federal, supplemental.iloc[::-1].reset_index(drop=True))

    pd.testing.assert_frame_equal(forward, reversed_result)
    assert len(forward) == 1
    assert forward.iloc[0]["naics_code"] == "541715"
    assert forward.iloc[0]["psc_code"] == "AC12"


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
    assert lookup["C_II_3"]["latency_days"] == (date(2023, 9, 1) - date(2024, 1, 1)).days
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
    assert s.loc["C_II_2", "time_days"] == (data_cut - date(2023, 6, 30)).days


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

    phase_ii = PhaseIIAward(
        award_id="SBIR-1",
        source_award_id="PIID-1",
        representative_transaction_id="TX-1",
        source_transaction_count=1,
        recipient_uei="AAAAAAAAAAAA",
        recipient_duns="123456789",
        recipient_name="Firm",
        agency="DOD",
        sub_agency="AF",
        naics_code="541715",
        psc_code="AC12",
        award_amount=500_000,
        award_date=date(2020, 1, 1),
        period_of_performance_start=date(2020, 1, 1),
        period_of_performance_end=date(2022, 1, 1),
        source="fpds_contract",
        phase_coding_reconciled=False,
    )
    assert phase_ii.naics_code == "541715"
    assert phase_ii.psc_code == "AC12"
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
    output_path = tmp_path / "data/processed/phase_ii_awards.parquet"
    assert output_path.exists()
    assert pd.read_parquet(output_path).empty
    checks_path = tmp_path / "data/processed/phase_ii_awards.checks.json"
    assert checks_path.exists()
    import json

    payload = json.loads(checks_path.read_text())
    assert payload["total_rows"] == 0
    assert payload["inputs"]["contracts_exists"] is False


def test_validated_phase_ii_awards_preserves_existing_output_when_write_fails(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    from dagster import build_asset_context

    from sbir_analytics.assets.phase_transition import validated_phase_ii_awards

    output_path = tmp_path / "data/processed/phase_ii_awards.parquet"
    output_path.parent.mkdir(parents=True)
    output_path.write_bytes(b"previous-complete-artifact")

    def fail_write(*_args, **_kwargs):
        raise RuntimeError("simulated parquet failure")

    monkeypatch.setattr(pd.DataFrame, "to_parquet", fail_write)
    with pytest.raises(RuntimeError, match="simulated parquet failure"):
        validated_phase_ii_awards(context=build_asset_context())

    assert output_path.read_bytes() == b"previous-complete-artifact"
    assert not list(output_path.parent.glob(".phase_ii_awards.parquet.*.tmp.parquet"))


def test_validated_phase_ii_awards_rejects_non_object_source_manifest(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from dagster import build_asset_context

    from sbir_analytics.assets.phase_transition.phase_ii import (
        PhaseIIInputError,
        validated_phase_ii_awards,
    )

    sbir_path = tmp_path / "data/processed/enriched_sbir_awards.parquet"
    sbir_path.parent.mkdir(parents=True)
    pd.DataFrame([{"award_id": "A", "phase": "II"}]).to_parquet(sbir_path, index=False)
    sbir_path.with_suffix(".checks.json").write_text("[]", encoding="utf-8")

    with pytest.raises(PhaseIIInputError, match="must be a JSON object"):
        validated_phase_ii_awards(context=build_asset_context())
