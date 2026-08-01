from __future__ import annotations

import pandas as pd

from sbir_analytics.assets.phase_iii_candidates.pairing import (
    PAIR_COLUMNS,
    PAIR_S1_COLUMNS,
    build_uei_pairs,
    pair_filter_s1,
)


def _prior(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "award_id": "P-1",
        "recipient_uei": " UEI-ONE ",
        "agency": "DEPARTMENT OF DEFENSE",
        "sub_agency": "DEPARTMENT OF THE NAVY",
        "office": "NAVAIR",
        "naics_code": "541715",
        "psc_code": "AC13",
        "title": "Prior title",
        "abstract": "Prior abstract",
        "period_of_performance_end": "2020-12-31",
        "cet": "ADVANCED COMPUTING",
    }
    row.update(overrides)
    return row


def _contract(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "contract_id": "PIID-1",
        "vendor_uei": "uei-one",
        "awarding_agency_name": "DEPARTMENT OF DEFENSE",
        "awarding_sub_tier_agency_name": "DEPARTMENT OF THE NAVY",
        "awarding_office_name": "NAVAIR",
        "naics_code": "541715",
        "psc_code": "AC13",
        "transaction_description": "Target description",
        "action_date": "2022-01-15",
        "extent_competed": "FULL",
        "federal_action_obligation": 100.0,
        "research": None,
        "sbir_phase": None,
        "transaction_unique_id": "TX-1",
        "generated_unique_award_id": "CONT_AWD_GEN-1",
    }
    row.update(overrides)
    return row


def test_build_uei_pairs_is_only_a_normalized_nonblank_uei_gate() -> None:
    priors = pd.DataFrame(
        [
            _prior(),
            _prior(award_id="P-BLANK", recipient_uei="  "),
            _prior(award_id="P-NONE", recipient_uei=None),
            _prior(award_id="P-OTHER", recipient_uei="OTHER-UEI"),
        ]
    )
    contracts = pd.DataFrame(
        [
            _contract(contract_id="CODED", research="SR3"),
            _contract(
                contract_id="CROSS-AGENCY",
                awarding_agency_name="NATIONAL AERONAUTICS AND SPACE ADMINISTRATION",
                awarding_sub_tier_agency_name="NASA",
                awarding_office_name="AMES RESEARCH CENTER",
                transaction_unique_id="TX-2",
                generated_unique_award_id="CONT_AWD_GEN-2",
            ),
            _contract(
                contract_id="NO-UEI-MATCH",
                vendor_uei="UNRELATED",
                transaction_unique_id="TX-3",
                generated_unique_award_id="CONT_AWD_GEN-3",
            ),
            _contract(
                contract_id="BLANK-UEI",
                vendor_uei=" ",
                transaction_unique_id="TX-4",
                generated_unique_award_id="CONT_AWD_GEN-4",
            ),
        ]
    )

    pairs = build_uei_pairs(priors, contracts)

    assert list(pairs.columns) == PAIR_COLUMNS
    assert pairs["target_id"].tolist() == ["CODED", "CROSS-AGENCY"]
    assert pairs.loc[0, "target_research"] == "SR3"
    assert pd.isna(pairs.loc[1, "target_research"])
    assert pairs.loc[0, "agency_match_level"] == "office"
    assert pd.isna(pairs.loc[1, "agency_match_level"])


def test_build_uei_pairs_projects_stable_ids_with_documented_precedence() -> None:
    priors = pd.DataFrame([_prior()])
    contracts = pd.DataFrame(
        [
            _contract(
                contract_id="LEGACY-ID",
                piid="PIID-DIRECT",
                generated_unique_award_id="GEN-DIRECT",
                transaction_unique_id="TX-DIRECT",
                transaction_id="TX-SECONDARY",
                metadata={"transaction_id": "TX-METADATA", "award_id": "GEN-METADATA"},
            ),
            _contract(
                contract_id="LEGACY-METADATA",
                piid="PIID-METADATA",
                generated_unique_award_id=pd.NA,
                transaction_unique_id=pd.NA,
                transaction_id="NULL",
                metadata={"transaction_id": "TX-METADATA", "award_id": "GEN-METADATA"},
            ),
            _contract(
                contract_id="LEGACY-NO-GENERATED-KEY",
                piid="PIID-MUST-NOT-BE-USED",
                generated_unique_award_id=None,
                transaction_unique_id=None,
                transaction_id=None,
                metadata={},
            ),
        ]
    )

    pairs = build_uei_pairs(priors, contracts).set_index("target_id")

    # target_id is the unchanged scoring-path identifier; the new keys carry
    # transaction and award grain explicitly.
    assert pairs.loc["LEGACY-ID", "target_transaction_id"] == "TX-DIRECT"
    assert pairs.loc["LEGACY-ID", "target_contract_key"] == "GEN-DIRECT"
    assert pairs.loc["LEGACY-METADATA", "target_transaction_id"] == "TX-METADATA"
    assert pairs.loc["LEGACY-METADATA", "target_contract_key"] == "GEN-METADATA"
    assert pd.isna(pairs.loc["LEGACY-NO-GENERATED-KEY", "target_transaction_id"])
    assert pd.isna(pairs.loc["LEGACY-NO-GENERATED-KEY", "target_contract_key"])


def test_pair_filter_s1_preserves_legacy_coded_and_agency_gates_and_schema() -> None:
    priors = pd.DataFrame([_prior()])
    contracts = pd.DataFrame(
        [
            _contract(contract_id="KEEP", transaction_unique_id="TX-KEEP"),
            _contract(contract_id="CODED-RESEARCH", research=" st3 "),
            _contract(contract_id="CODED-LABEL", sbir_phase="Phase 3"),
            _contract(
                contract_id="NO-AGENCY-MATCH",
                awarding_agency_name="NATIONAL SCIENCE FOUNDATION",
                awarding_sub_tier_agency_name="NSF",
                awarding_office_name="OFFICE OF THE DIRECTOR",
            ),
            # Legacy S1 picks the finest observed hierarchy match without
            # requiring its parents to match.  Preserve that behavior exactly.
            _contract(
                contract_id="OFFICE-ONLY-MATCH",
                awarding_agency_name="NATIONAL SCIENCE FOUNDATION",
                awarding_sub_tier_agency_name="NSF",
                awarding_office_name="NAVAIR",
            ),
        ]
    )

    pairs = pair_filter_s1(priors, contracts)

    assert list(pairs.columns) == PAIR_S1_COLUMNS
    assert pairs["target_id"].tolist() == ["KEEP", "OFFICE-ONLY-MATCH"]
    assert pairs["agency_match_level"].tolist() == ["office", "office"]
    assert not {
        "target_research",
        "target_sbir_phase",
        "target_transaction_id",
        "target_contract_key",
    }.intersection(pairs.columns)


def test_pair_builders_return_their_declared_empty_schemas() -> None:
    empty = pd.DataFrame()

    assert list(build_uei_pairs(empty, empty).columns) == PAIR_COLUMNS
    assert list(pair_filter_s1(empty, empty).columns) == PAIR_S1_COLUMNS
