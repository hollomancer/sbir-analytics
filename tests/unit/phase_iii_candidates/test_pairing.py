from __future__ import annotations

import pandas as pd

from sbir_analytics.assets import phase_iii_candidates as candidates_package
from sbir_analytics.assets.phase_iii_candidates.pairing import (
    PAIR_COLUMNS,
    PAIR_S1_COLUMNS,
    build_uei_pairs,
    pair_filter_s1,
)


def test_package_retains_current_public_exports_without_eager_loading() -> None:
    expected = {
        "CANDIDATES_OUTPUT_PATH",
        "candidates_path_for",
        "combine_candidate_outputs",
        "enrich_prior_awards",
        "phase_iii_directed_candidates",
        "phase_iii_followon_candidates",
    }

    assert expected.issubset(candidates_package.__all__)
    assert expected.issubset(dir(candidates_package))


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
    if "generated_unique_award_id" not in overrides:
        row["generated_unique_award_id"] = f"CONT_AWD_{row['contract_id']}"
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
                generated_unique_award_id="GEN-METADATA",
                transaction_unique_id=pd.NA,
                transaction_id="NULL",
                metadata={"transaction_id": "TX-METADATA", "award_id": "GEN-METADATA"},
            ),
            _contract(
                contract_id="LEGACY-NO-TRANSACTION-ID",
                piid="PIID-NO-TRANSACTION-ID",
                generated_unique_award_id="GEN-NO-TRANSACTION-ID",
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
    assert pd.isna(pairs.loc["LEGACY-NO-TRANSACTION-ID", "target_transaction_id"])
    assert pairs.loc["LEGACY-NO-TRANSACTION-ID", "target_contract_key"] == ("GEN-NO-TRANSACTION-ID")


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
    assert pairs["target_id"].tolist() == ["CONT_AWD_KEEP", "CONT_AWD_OFFICE-ONLY-MATCH"]
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


def test_postgres_copy_null_uei_never_enters_the_pair_universe() -> None:
    priors = pd.DataFrame([_prior(recipient_uei=r"\N")])
    contracts = pd.DataFrame([_contract(vendor_uei=r"\N")])

    pairs = build_uei_pairs(priors, contracts)

    assert pairs.empty


def test_build_uei_pairs_retains_every_transaction_and_authoritative_coding() -> None:
    contracts = pd.DataFrame(
        [
            _contract(
                contract_id="ORDER-1",
                generated_unique_award_id="CONT_AWD_ORDER-1",
                transaction_unique_id="TX-EARLY",
                action_date="2022-01-01",
                research="SR3",
                sbir_phase=None,
            ),
            _contract(
                contract_id="ORDER-1",
                generated_unique_award_id="CONT_AWD_ORDER-1",
                transaction_unique_id="TX-LATE",
                action_date="2022-06-01",
                research=None,
                sbir_phase="Phase 2",
            ),
        ]
    )

    pairs = build_uei_pairs(pd.DataFrame([_prior()]), contracts)

    assert pairs["target_transaction_id"].tolist() == ["TX-EARLY", "TX-LATE"]
    assert pairs["target_contract_key"].tolist() == [
        "CONT_AWD_ORDER-1",
        "CONT_AWD_ORDER-1",
    ]
    assert pairs["target_research"].tolist()[0] == "SR3"
    assert pairs["target_sbir_phase"].tolist()[1] == "Phase 2"


def test_optional_phase_is_not_synthesized_from_authoritative_research() -> None:
    contracts = pd.DataFrame([_contract(research="SR2")]).drop(columns="sbir_phase")

    pair = build_uei_pairs(pd.DataFrame([_prior()]), contracts).iloc[0]

    assert pair["target_research"] == "SR2"
    assert pd.isna(pair["target_sbir_phase"])


def test_pair_filter_s1_excludes_whole_coded_award_and_selects_latest_transaction() -> None:
    contracts = pd.DataFrame(
        [
            _contract(
                contract_id="CODED",
                generated_unique_award_id="CONT_AWD_CODED",
                transaction_unique_id="TX-CODED-EARLY",
                action_date="2022-01-01",
                research="SR3",
            ),
            _contract(
                contract_id="CODED",
                generated_unique_award_id="CONT_AWD_CODED",
                transaction_unique_id="TX-CODED-LATE",
                action_date="2022-06-01",
                research=None,
                transaction_description="A later uncoded modification",
            ),
            _contract(
                contract_id="KEEP",
                generated_unique_award_id="CONT_AWD_KEEP",
                transaction_unique_id="TX-KEEP-EARLY",
                action_date="2022-02-01",
                transaction_description="Earlier transaction",
            ),
            _contract(
                contract_id="KEEP",
                generated_unique_award_id="CONT_AWD_KEEP",
                transaction_unique_id="TX-KEEP-LATE",
                action_date="2022-08-01",
                transaction_description="Latest transaction",
            ),
        ]
    )

    pairs = pair_filter_s1(pd.DataFrame([_prior()]), contracts)

    assert list(pairs.columns) == PAIR_S1_COLUMNS
    assert pairs["target_id"].tolist() == ["CONT_AWD_KEEP"]
    assert pairs["target_action_date"].tolist() == ["2022-08-01"]
    assert pairs["target_description"].tolist() == ["Latest transaction"]


def test_s1_award_gate_sees_unpaired_transactions_before_uei_filtering() -> None:
    contracts = pd.DataFrame(
        [
            # A coded modification with no match still makes the entire award
            # already-coded under current S1's award-grain disposition.
            _contract(
                contract_id="CODED-ORDER",
                generated_unique_award_id="CONT_AWD_CODED-ORDER",
                transaction_unique_id="TX-CODED",
                vendor_uei="UNRELATED-UEI",
                action_date="2022-01-01",
                research="SR3",
            ),
            _contract(
                contract_id="CODED-ORDER",
                generated_unique_award_id="CONT_AWD_CODED-ORDER",
                transaction_unique_id="TX-UNCODED",
                action_date="2022-06-01",
                research=None,
            ),
            # The legacy path selects the latest transaction before its UEI
            # filter. A latest blank-UEI modification therefore drops the award
            # rather than falling back to the earlier matching transaction.
            _contract(
                contract_id="BLANK-LATEST",
                generated_unique_award_id="CONT_AWD_BLANK-LATEST",
                transaction_unique_id="TX-MATCHING-EARLY",
                action_date="2022-02-01",
            ),
            _contract(
                contract_id="BLANK-LATEST",
                generated_unique_award_id="CONT_AWD_BLANK-LATEST",
                transaction_unique_id="TX-BLANK-LATE",
                vendor_uei=" ",
                action_date="2022-08-01",
            ),
        ]
    )

    assert pair_filter_s1(pd.DataFrame([_prior()]), contracts).empty


def test_legacy_s1_collapses_duplicate_target_rows_but_shared_pairs_do_not() -> None:
    duplicate = _contract(
        contract_id="DUPLICATE",
        generated_unique_award_id="CONT_AWD_DUPLICATE",
        transaction_unique_id="TX-DUPLICATE",
        action_date="2022-08-01",
    )
    contracts = pd.DataFrame([duplicate, duplicate])
    priors = pd.DataFrame([_prior()])

    shared = build_uei_pairs(priors, contracts)
    legacy = pair_filter_s1(priors, contracts)

    assert len(shared) == 2
    assert len(legacy) == 1
    assert legacy.loc[0, "target_id"] == "CONT_AWD_DUPLICATE"
