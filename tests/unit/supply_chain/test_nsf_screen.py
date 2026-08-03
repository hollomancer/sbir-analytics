import pandas as pd

from sbir_etl.supply_chain.nsf_screen import (
    aggregate_nsf_supplier_screen,
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
