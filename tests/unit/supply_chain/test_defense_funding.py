"""Tests for NSF-awardee DoD funding normalization and evidence gates."""

from __future__ import annotations

import json

import pandas as pd
import pytest

from sbir_etl.supply_chain.defense_funding import (
    build_defense_funding_summary,
    build_nsf_award_defense_evidence,
    build_nsf_identity_registry,
    combine_prime_transactions,
    evaluate_defense_funding_quality,
    normalize_prime_api_transactions,
    normalize_prime_archive_transactions,
    normalize_subaward_transactions,
)


@pytest.fixture
def awardees() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "nsf_organization_id": "uei:ABCDEFGHIJKL",
                "nsf_awardee_name": "Alpha Technologies, Inc.",
                "nsf_awardee_legal_business_name": "Alpha Technologies, Inc.",
                "nsf_awardee_uei": "ABCDEFGHIJKL",
                "organization_resolution_method": "direct_nsf_uei",
                "organization_resolution_confidence": "verified_identifier",
                "nsf_awardee_status": "current",
            },
            {
                "nsf_organization_id": "duns:123456789",
                "nsf_awardee_name": "Beta Materials LLC",
                "nsf_awardee_uei": None,
                "organization_resolution_method": "sbir_gov_legacy_duns",
                "organization_resolution_confidence": "verified_legacy_identifier",
                "nsf_awardee_status": "former",
            },
        ]
    )


@pytest.fixture
def reconciliation() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "nsf_organization_id": "uei:ABCDEFGHIJKL",
                "nsf_awardee_uei": "ABCDEFGHIJKL",
                "sbir_gov_uei": "ABCDEFGHIJKL",
                "sbir_gov_duns": "987654321",
                "nsf_awardee_name": "Alpha Technologies Inc",
                "sbir_gov_company_name": "ALPHA TECHNOLOGIES, INC.",
            },
            {
                "nsf_organization_id": "duns:123456789",
                "nsf_awardee_uei": None,
                "sbir_gov_uei": None,
                "sbir_gov_duns": "123-456-789",
                "nsf_awardee_name": "Beta Materials LLC",
                "sbir_gov_company_name": "Beta Materials, L.L.C.",
            },
        ]
    )


@pytest.fixture
def registry(awardees: pd.DataFrame, reconciliation: pd.DataFrame) -> pd.DataFrame:
    return build_nsf_identity_registry(awardees, reconciliation)


def test_identity_registry_preserves_exact_aliases_and_status(registry: pd.DataFrame) -> None:
    alpha = registry.set_index("nsf_organization_id").loc["uei:ABCDEFGHIJKL"]

    assert json.loads(alpha["recipient_uei_aliases"]) == ["ABCDEFGHIJKL"]
    assert json.loads(alpha["recipient_duns_aliases"]) == ["987654321"]
    assert alpha["nsf_awardee_status"] == "current"
    assert alpha["identity_name_count"] == 1


def test_identity_registry_fails_closed_on_shared_exact_identifier(
    awardees: pd.DataFrame, reconciliation: pd.DataFrame
) -> None:
    collision = reconciliation.copy()
    collision.loc[1, "sbir_gov_uei"] = "ABCDEFGHIJKL"

    with pytest.raises(ValueError, match="multiple organizations"):
        build_nsf_identity_registry(awardees, collision)


def _archive_rows() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "transaction_unique_id": "CONT_TX_1",
                "generated_unique_award_id": "CONT_AWD_P1_9700",
                "piid": "P1",
                "agency": "Department of Defense",
                "sub_agency": "Department of the Air Force",
                "vendor_name": "Alpha Technologies Inc",
                "vendor_uei": "ABCDEFGHIJKL",
                "vendor_duns": None,
                "action_date": "2023-09-30",
                "start_date": "2023-01-01",
                "end_date": "2024-01-01",
                "obligation_amount": 100.0,
                "contract_award_type": "A",
                "description": "sensor production",
                "naics_code": "334511",
                "product_or_service_code": "5998",
                "metadata": {"funding_agency": "Department of Defense"},
            },
            {
                "transaction_unique_id": "CONT_TX_2",
                "generated_unique_award_id": "CONT_AWD_OT1_9700",
                "piid": "OT1",
                "agency": None,
                "sub_agency": "Defense Advanced Research Projects Agency",
                "vendor_name": "Beta Materials LLC",
                "vendor_uei": None,
                "vendor_duns": "123456789",
                "action_date": "2023-10-01",
                "start_date": "2023-10-01",
                "end_date": "2025-01-01",
                "obligation_amount": -20.0,
                "contract_award_type": "R",
                "description": "prototype agreement",
                "metadata": {"funding_agency": "Department of Defense"},
            },
            {
                "transaction_unique_id": "CONT_TX_3",
                "generated_unique_award_id": "CONT_AWD_OT2_9700",
                "piid": "OT2",
                "agency": "Department of Defense",
                "vendor_name": "Beta Materials, Incorporated",
                "vendor_uei": None,
                "vendor_duns": None,
                "action_date": "2024-02-01",
                "obligation_amount": 0.0,
                "contract_award_type": "O",
                "description": "research agreement",
                "metadata": {},
            },
            {
                "transaction_unique_id": "CONT_TX_OTHER",
                "generated_unique_award_id": "CONT_AWD_OTHER_7500",
                "piid": "OTHER",
                "agency": "Department of Health and Human Services",
                "vendor_name": "Alpha Technologies Inc",
                "vendor_uei": "ABCDEFGHIJKL",
                "vendor_duns": None,
                "action_date": "2024-01-01",
                "obligation_amount": 999.0,
                "contract_award_type": "A",
                "description": "not DoD",
                "metadata": {},
            },
        ]
    )


def test_archive_prime_normalization_preserves_signed_grain_and_dod_filter(
    registry: pd.DataFrame,
) -> None:
    transactions = normalize_prime_archive_transactions(
        _archive_rows(),
        registry,
        source_path="FY2024_DoD_Contracts_Full.zip",
        source_sha256="abc123",
    )

    assert transactions["prime_transaction_id"].tolist() == [
        "CONT_TX_1",
        "CONT_TX_2",
        "CONT_TX_3",
    ]
    assert transactions["signed_obligation_amount"].tolist() == [100.0, -20.0, 0.0]
    assert transactions["fiscal_year"].tolist() == [2023, 2024, 2024]
    assert transactions["instrument_group"].tolist() == [
        "prime_procurement",
        "prime_other_transaction",
        "prime_other_transaction",
    ]
    assert transactions["recipient_match_confidence"].tolist() == [
        "verified_identifier",
        "verified_legacy_identifier",
        "candidate_name",
    ]
    assert transactions.loc[1, "is_deobligation"]
    assert transactions.loc[2, "is_zero_obligation"]
    assert transactions["source_transaction_sha256"].eq("abc123").all()


def test_archive_ot_only_excludes_procurement(registry: pd.DataFrame) -> None:
    transactions = normalize_prime_archive_transactions(_archive_rows(), registry, ot_only=True)

    assert set(transactions["prime_transaction_id"]) == {"CONT_TX_2", "CONT_TX_3"}
    assert transactions["instrument_group"].eq("prime_other_transaction").all()


def test_api_prime_normalization_recomputes_fiscal_year_and_signed_flags() -> None:
    transactions = normalize_prime_api_transactions(
        pd.DataFrame(
            [
                {
                    "prime_transaction_id": "API_TX_1",
                    "dod_award_generated_id": "CONT_AWD_1_9700",
                    "dod_award_id": "P1",
                    "nsf_organization_id": "uei:ABCDEFGHIJKL",
                    "recipient_match_method": "exact_uei",
                    "recipient_match_confidence": "verified_identifier",
                    "instrument_group": "prime_procurement",
                    "signed_obligation_amount": 50,
                    "action_date": "2022-09-30",
                    "source_system": "USAspending API",
                },
                {
                    "prime_transaction_id": "API_TX_2",
                    "dod_award_generated_id": "ASST_NON_1_9700",
                    "dod_award_id": "G1",
                    "nsf_organization_id": "uei:ABCDEFGHIJKL",
                    "recipient_match_method": "exact_uei",
                    "recipient_match_confidence": "verified_identifier",
                    "instrument_group": "prime_assistance",
                    "signed_obligation_amount": -10,
                    "action_date": "2022-10-01",
                    "source_system": "USAspending API",
                },
            ]
        )
    )

    assert transactions["fiscal_year"].tolist() == [2022, 2023]
    assert transactions["is_deobligation"].tolist() == [False, True]


def _subaward_facts() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "subaward_fact_id": "composite:1",
                "sbir_organization_id": "uei:ABCDEFGHIJKL",
                "match_method": "exact_uei",
                "evidence_grade": "verified_identifier",
                "prime_award_unique_key": "CONT_AWD_P2_9700",
                "prime_award_piid": "P2",
                "prime_name": "Large Prime Inc",
                "prime_uei": "MNOPQRSTUVWX",
                "prime_parent_name": None,
                "prime_naics_code": "334511",
                "prime_award_description": "aircraft system",
                "subaward_number": "S1",
                "subaward_sam_report_id": "R1",
                "subaward_amount": 25.0,
                "subaward_action_date": "2023-10-02",
                "subawardee_uei": "ABCDEFGHIJKL",
                "subawardee_duns": None,
                "subawardee_name": "Alpha Technologies Inc",
                "subaward_description": "sensor component",
                "source_url": "https://www.usaspending.gov/award/P2",
                "source_last_modified": "2024-01-01",
                "source_input_path": "dod_contract_subawards_fy2024.zip",
                "source_input_sha256": "def456",
                "source_system": "USAspending.gov subaward data (SAM.gov/FSRS)",
            },
            {
                "subaward_fact_id": "composite:2",
                "sbir_organization_id": "duns:123456789",
                "match_method": "exact_normalized_name",
                "evidence_grade": "candidate_name",
                "prime_award_unique_key": "ASST_NON_G2_9700",
                "prime_award_piid": "G2",
                "prime_name": "Research University",
                "subaward_number": "S2",
                "subaward_sam_report_id": "R2",
                "subaward_amount": -5.0,
                "subaward_action_date": "2024-03-01",
                "subawardee_name": "Beta Materials LLC",
                "subaward_description": "material testing",
                "source_system": "USAspending.gov subaward data (SAM.gov/FSRS)",
            },
        ]
    )


def test_subaward_normalization_keeps_contract_assistance_and_candidates_separate() -> None:
    transactions = normalize_subaward_transactions(_subaward_facts())

    assert transactions["instrument_group"].tolist() == [
        "contract_subaward",
        "assistance_subaward",
    ]
    assert transactions["funding_mode"].eq("reported_subaward").all()
    assert transactions.loc[0, "source_transaction_path"] == ("dod_contract_subawards_fy2024.zip")
    assert transactions.loc[1, "recipient_match_confidence"] == "candidate_name"


def test_summary_evidence_and_quality_exclude_weak_names(
    registry: pd.DataFrame,
) -> None:
    prime = normalize_prime_archive_transactions(_archive_rows(), registry)
    subawards = normalize_subaward_transactions(_subaward_facts())
    summary = build_defense_funding_summary(prime, subawards)
    direct = pd.DataFrame(
        [
            {
                "nsf_award_id": "1234567",
                "nsf_organization_id": "uei:ABCDEFGHIJKL",
                "nsf_program": "SBIR",
                "nsf_phase": "II",
                "nsf_award_title": "Advanced sensor",
                "nsf_start_date": "2023-01-01",
                "nsf_end_date": "2024-12-31",
                "nsf_award_performance_status": "active",
                "source_url": "https://api.nsf.gov/1234567",
                "source_path": "1234567.json",
                "source_record_sha256": "nsfhash",
            },
            {
                "nsf_award_id": "7654321",
                "nsf_organization_id": "duns:123456789",
                "nsf_program": "SBIR",
                "nsf_phase": "I",
                "nsf_award_title": "Novel material",
                "nsf_start_date": "2019-01-01",
                "nsf_end_date": "2020-01-01",
                "nsf_award_performance_status": "expired",
                "source_url": "https://api.nsf.gov/7654321",
                "source_path": "7654321.json",
                "source_record_sha256": "nsfhash2",
            },
        ]
    )
    evidence = build_nsf_award_defense_evidence(direct, prime, subawards)
    quality = evaluate_defense_funding_quality(prime, subawards, summary, evidence)

    assert summary["signed_obligation_total"].sum() == 105.0
    assert summary["source_transaction_count"].sum() == 3
    assert (
        summary["recipient_match_confidences"]
        .map(lambda value: "candidate_name" not in json.loads(value))
        .all()
    )
    assert evidence["specific_award_usage_status"].eq("not_established").all()
    assert evidence["critical_supply_chain_status"].eq("not_assessed").all()
    assert not evidence["temporal_association_is_causal_evidence"].any()
    assert quality["quality_gates_passed"]


def test_combined_prime_sources_refuse_duplicate_transaction_ids(
    registry: pd.DataFrame,
) -> None:
    prime = normalize_prime_archive_transactions(_archive_rows().iloc[:1], registry)

    with pytest.raises(ValueError, match="overlap"):
        combine_prime_transactions(prime, prime.copy())
