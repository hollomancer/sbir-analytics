import pandas as pd

from sbir_etl.supply_chain.nsf_screen import (
    aggregate_nsf_supplier_screen,
    screen_direct_nsf_awards,
    screen_nsf_sbir_award_candidates,
)


def test_screen_combines_observed_relationship_with_auditable_cet_mapping() -> None:
    candidates = pd.DataFrame(
        [
            {
                "sbir_organization_id": "uei:SUPPLIER",
                "nsf_sbir_award_candidate_id": "nsf-sbir:manufacturing",
                "nsf_sbir_award_title": "Additive manufacturing for titanium castings",
                "nsf_sbir_topic_code": "AM",
                "nsf_sbir_abstract": "A digital manufacturing process for advanced machining.",
            },
            {
                "sbir_organization_id": "uei:SUPPLIER",
                "nsf_sbir_award_candidate_id": "nsf-sbir:unclassified",
                "nsf_sbir_award_title": "Study of local markets",
                "nsf_sbir_topic_code": "",
                "nsf_sbir_abstract": "A general study with no technical scope.",
            },
        ]
    )

    screened = screen_nsf_sbir_award_candidates(candidates).set_index("nsf_sbir_award_candidate_id")

    manufacturing = screened.loc["nsf-sbir:manufacturing"]
    assert manufacturing["primary_cet"] == "advanced_manufacturing"
    assert "manufacturing" in manufacturing["dod_supply_chain_categories"].split("|")
    assert manufacturing["critical_supply_chain_review_candidate"]
    assert manufacturing["critical_supply_chain_status"] == "not_assessed"
    assert manufacturing["cet_classifier_version"] == "CET-RULES-2026Q3"

    unclassified = screened.loc["nsf-sbir:unclassified"]
    assert pd.isna(unclassified["primary_cet"])
    assert not unclassified["critical_supply_chain_review_candidate"]
    assert unclassified["critical_supply_chain_screen_basis"] == (
        "observed_supplier_relationship_only"
    )

    supplier_screen = aggregate_nsf_supplier_screen(screened.reset_index())
    assert supplier_screen["nsf_specific_award_candidate_count"].sum() == 2
    assert supplier_screen["cet_classified_nsf_award_count"].sum() == 1
    assert supplier_screen["critical_supply_chain_candidate_award_count"].sum() == 1
    assert supplier_screen.iloc[0]["primary_cets"] == "advanced_manufacturing"


def test_direct_award_screen_uses_cet_and_funding_without_policy_mapping() -> None:
    awards = pd.DataFrame(
        [
            {
                "nsf_award_id": "1234567",
                "nsf_organization_id": "uei:SUPPLIER",
                "nsf_program": "SBIR",
                "nsf_phase": "II",
                "nsf_award_title": "Additive manufacturing for titanium castings",
                "nsf_award_abstract": "A digital manufacturing process for advanced machining.",
                "nsf_award_performance_status": "active",
            },
            {
                "nsf_award_id": "7654321",
                "nsf_organization_id": "uei:OTHER",
                "nsf_program": "SBIR",
                "nsf_phase": "I",
                "nsf_award_title": "Study of local markets",
                "nsf_award_abstract": "A general study with no technical scope.",
                "nsf_award_performance_status": "expired",
            },
            {
                "nsf_award_id": "1122334",
                "nsf_organization_id": "uei:TOPIC",
                "nsf_program": "SBIR",
                "nsf_phase": "I",
                "nsf_award_title": "Specialized device research",
                "nsf_award_abstract": "A general technical feasibility study.",
                "nsf_fund_program_name": "SBIR semiconductor manufacturing",
                "nsf_award_performance_status": "active",
            },
        ]
    )

    screened = screen_direct_nsf_awards(
        awards, funded_organization_ids={"uei:SUPPLIER", "uei:TOPIC"}
    ).set_index("nsf_award_id")

    assert screened.loc["1234567", "primary_cet"] == "advanced_manufacturing"
    assert screened.loc["1234567", "critical_supply_chain_review_candidate"]
    assert screened.loc["1234567", "critical_supply_chain_status"] == "not_assessed"
    assert screened.loc["1234567", "specific_award_usage_status"] == "not_established"
    assert screened.loc["1234567", "defense_policy_mapping_status"] == (
        "deferred_no_authoritative_dod14_or_ndis8_mapping"
    )
    assert pd.isna(screened.loc["1234567", "defense_policy_mapping_version"])
    assert screened["cet_classifier_version"].notna().all()
    assert screened["cet_taxonomy_version"].notna().all()
    assert not screened.loc["7654321", "critical_supply_chain_review_candidate"]
    assert screened.loc["1122334", "primary_cet"] == "semiconductors_and_microelectronics"
    assert screened.loc["1122334", "critical_supply_chain_review_candidate"]
