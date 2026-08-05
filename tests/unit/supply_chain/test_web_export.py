import pandas as pd

from sbir_etl.supply_chain.web_export import (
    build_nsf_defense_lineage_payload,
    build_web_graph_payload,
)


def _edges() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "sbir_organization_id": "uei:SUPPLIER1",
                "prime_organization_id": "uei:PRIME1",
                "sbir_awardee_name": "Supplier One",
                "prime_name": "Prime One LLC",
                "prime_family_id": "uei:FAMILY1",
                "prime_family_name": "Prime One Holdings",
                "reported_subaward_amount": 100.0,
                "reported_subaward_count": 2,
                "prime_award_count": 1,
                "observed_fiscal_year_count": 2,
                "first_observed_date": "2023-01-02",
                "last_observed_date": "2024-01-03",
                "identifier_verified_facts": 2,
            },
            {
                "sbir_organization_id": "uei:SUPPLIER1",
                "prime_organization_id": "uei:PRIME1-SUB",
                "sbir_awardee_name": "Supplier One",
                "prime_name": "Prime One Division",
                "prime_family_id": "uei:FAMILY1",
                "prime_family_name": "Prime One Family",
                "reported_subaward_amount": 25.0,
                "reported_subaward_count": 1,
                "prime_award_count": 1,
                "observed_fiscal_year_count": 1,
                "first_observed_date": "2024-04-01",
                "last_observed_date": "2024-04-01",
                "identifier_verified_facts": 1,
            },
            {
                "sbir_organization_id": "uei:SUPPLIER2",
                "prime_organization_id": "uei:PRIME1",
                "sbir_awardee_name": "Supplier Two",
                "prime_name": "Prime One LLC",
                "prime_family_id": "uei:FAMILY1",
                "prime_family_name": "Prime One Family",
                "reported_subaward_amount": 50.0,
                "reported_subaward_count": 1,
                "prime_award_count": 1,
                "observed_fiscal_year_count": 1,
                "first_observed_date": "2024-02-01",
                "last_observed_date": "2024-02-01",
                "identifier_verified_facts": 1,
            },
        ]
    )


def _exposure() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "sbir_organization_id": "uei:SUPPLIER1",
                "screening_status": "single_observed_prime",
                "observed_customer_hhi": 1.0,
                "top_observed_prime_share": 1.0,
                "nsf_sbir_awardee": True,
                "nsf_sbir_award_count": 3,
                "nsf_sbir_topic_codes": "AM|MM",
                "nsf_sbir_first_award_year": 2019,
                "nsf_sbir_latest_award_year": 2024,
                "nsf_sbir_award_amount": 1_750_000,
                "nsf_review_priority": "persistent_relationship",
                "critical_supply_chain_review_candidate": True,
                "critical_supply_chain_candidate_award_count": 2,
                "primary_cets": "advanced_manufacturing|microelectronics",
                "dod_supply_chain_categories": "manufacturing|microelectronics",
                "cet_classifier_version": "CET-RULES-2026Q3",
                "defense_crosswalk_version": "DOD-CROSSWALK-2026Q3",
            }
        ]
    )


def test_web_export_rolls_legal_entities_up_to_prime_family() -> None:
    payload = build_web_graph_payload(
        _edges(),
        _exposure(),
        metadata={"generated_at_utc": "2026-01-01T00:00:00+00:00"},
    )

    assert payload["scope"] == {
        "supplier_tier": "tier_2",
        "customer_tier": "tier_1_prime",
        "evidence_grade": "verified_identifier",
        "input_legal_entity_edge_count": 3,
        "display_prime_family_edge_count": 2,
        "supplier_count": 2,
        "prime_family_count": 1,
        "nsf_sbir_supplier_count": 1,
        "nsf_sbir_prime_family_edge_count": 1,
        "critical_supply_chain_review_candidate_supplier_count": 1,
        "critical_supply_chain_review_candidate_edge_count": 1,
    }
    assert len(payload["nodes"]) == 3
    assert len({node["id"] for node in payload["nodes"]}) == 3
    supplier_edge = next(
        edge for edge in payload["edges"] if edge["source"] == "supplier:uei:SUPPLIER1"
    )
    assert supplier_edge["target"] == "prime:uei:FAMILY1"
    assert supplier_edge["reported_subaward_amount"] == 125.0
    assert supplier_edge["prime_legal_entity_count"] == 2
    assert supplier_edge["evidence_grade"] == "verified_identifier"


def test_web_export_preserves_supplier_screen_without_claiming_dependency() -> None:
    payload = build_web_graph_payload(_edges(), _exposure())

    supplier = next(node for node in payload["nodes"] if node["id"] == "supplier:uei:SUPPLIER1")
    assert supplier["screening_status"] == "single_observed_prime"
    assert supplier["observed_customer_hhi"] == 1.0
    assert supplier["dependency_status"] == "not_established"
    assert supplier["nsf_sbir_awardee"]
    assert supplier["nsf_sbir_award_count"] == 3
    assert supplier["nsf_sbir_topic_codes"] == "AM|MM"
    assert supplier["nsf_review_priority"] == "persistent_relationship"
    assert supplier["critical_supply_chain_review_candidate"]
    assert supplier["critical_supply_chain_candidate_award_count"] == 2
    assert supplier["dod_supply_chain_categories"] == "manufacturing|microelectronics"
    assert all(edge["dependency_status"] == "not_established" for edge in payload["edges"])
    assert sum(edge["nsf_supply_chain_review_candidate"] for edge in payload["edges"]) == 1
    assert sum(edge["critical_supply_chain_review_candidate"] for edge in payload["edges"]) == 1


def test_web_export_rejects_incomplete_edge_schema() -> None:
    incomplete = _edges().drop(columns=["prime_name"])

    try:
        build_web_graph_payload(incomplete, _exposure())
    except ValueError as exc:
        assert "prime_name" in str(exc)
    else:
        raise AssertionError("missing required edge columns should fail")


def test_lineage_export_builds_distinct_traceable_node_and_edge_types() -> None:
    direct = pd.DataFrame(
        [
            {
                "nsf_award_id": "1234567",
                "nsf_organization_id": "uei:SUPPLIER1",
                "nsf_award_title": "Additive manufacturing sensor",
                "nsf_award_abstract": "Advanced manufacturing",
                "nsf_program": "SBIR",
                "nsf_phase": "II",
                "nsf_start_date": "2023-01-01",
                "nsf_end_date": "2025-01-01",
                "nsf_award_performance_status": "expired",
                "nsf_estimated_total_amount": 900000,
                "source_url": "https://api.nsf.gov/1234567",
                "source_path": "snapshot/1234567.json",
                "source_record_sha256": "nsfhash",
            }
        ]
    )
    awardees = pd.DataFrame(
        [
            {
                "nsf_organization_id": "uei:SUPPLIER1",
                "nsf_awardee_name": "Supplier One",
                "nsf_awardee_legal_business_name": "Supplier One Inc",
                "nsf_awardee_status": "former",
                "organization_resolution_method": "direct_nsf_uei",
                "organization_resolution_confidence": "verified_identifier",
            }
        ]
    )
    prime = pd.DataFrame(
        [
            {
                "prime_transaction_id": "CONT_TX_1",
                "nsf_organization_id": "uei:SUPPLIER1",
                "dod_award_generated_id": "CONT_AWD_P1_9700",
                "dod_award_id": "P1",
                "funding_mode": "prime",
                "instrument_group": "prime_procurement",
                "signed_obligation_amount": 100,
                "action_date": pd.Timestamp("2024-01-01", tz="UTC"),
                "fiscal_year": 2024,
                "recipient_match_method": "exact_uei",
                "recipient_match_confidence": "verified_identifier",
                "source_system": "USAspending API",
                "source_transaction_path": "transactions/P1.json",
                "source_transaction_sha256": "primehash",
                "source_url": "https://www.usaspending.gov/award/P1",
                "award_description": "sensor procurement",
            },
            {
                "prime_transaction_id": "CONT_TX_2",
                "nsf_organization_id": "uei:SUPPLIER1",
                "dod_award_generated_id": "CONT_AWD_P1_9700",
                "dod_award_id": "P1",
                "funding_mode": "prime",
                "instrument_group": "prime_procurement",
                "signed_obligation_amount": -10,
                "action_date": pd.Timestamp("2024-10-01", tz="UTC"),
                "fiscal_year": 2025,
                "recipient_match_method": "exact_uei",
                "recipient_match_confidence": "verified_identifier",
                "source_system": "USAspending API",
                "source_transaction_path": "transactions/P1.json",
                "source_transaction_sha256": "primehash",
                "source_url": "https://www.usaspending.gov/award/P1",
                "award_description": "sensor procurement",
            },
        ]
    )
    subawards = pd.DataFrame(
        columns=[
            "subaward_transaction_id",
            "nsf_organization_id",
            "dod_award_generated_id",
            "funding_mode",
            "instrument_group",
            "signed_obligation_amount",
            "action_date",
            "fiscal_year",
            "recipient_match_method",
            "recipient_match_confidence",
            "source_system",
        ]
    )
    screen = pd.DataFrame(
        [
            {
                "nsf_award_id": "1234567",
                "nsf_organization_id": "uei:SUPPLIER1",
                "primary_cet": "advanced_manufacturing",
                "primary_cet_score": 0.8,
                "cet_taxonomy_version": "NSTC-CET-2024",
                "cet_classifier_version": "CET-RULES-2026Q3",
                "critical_supply_chain_review_candidate": True,
                "defense_policy_mapping_status": (
                    "deferred_no_authoritative_dod14_or_ndis8_mapping"
                ),
            }
        ]
    )
    evidence = pd.DataFrame(
        [
            {
                "evidence_assertion_id": "evidence:1",
                "nsf_award_id": "1234567",
                "nsf_organization_id": "uei:SUPPLIER1",
                "_dod_award_key": "CONT_AWD_P1_9700",
                "dod_award_generated_id": "CONT_AWD_P1_9700",
                "funding_mode": "prime",
                "instrument_group": "prime_procurement",
                "signed_obligation_total": 90,
                "temporal_association": "overlaps_nsf_performance_period",
                "source_transaction_ids": '["CONT_TX_1","CONT_TX_2"]',
                "source_paths": '["transactions/P1.json"]',
                "source_sha256s": '["primehash"]',
            }
        ]
    )

    payload = build_nsf_defense_lineage_payload(
        direct,
        awardees,
        prime,
        subawards,
        screen,
        evidence,
        metadata={"analysis_date": "2026-08-03", "quality_gates_passed": True},
        downloads={"evidence": "data/nsf_award_defense_evidence.csv"},
    )

    assert payload["schema_version"] == "2.0"
    assert {node["kind"] for node in payload["nodes"]} == {
        "agency",
        "dod_award",
        "legal_entity",
        "nsf_award",
        "technology",
    }
    assert payload["scope"]["verified_funding_edge_count"] == 1
    assert payload["scope"]["candidate_edge_count"] == 2
    entity = next(node for node in payload["nodes"] if node["kind"] == "legal_entity")
    assert entity["nsf_awardee_status"] == "former"
    assert entity["signed_dod_funding_total"] == 90
    funding = next(
        edge
        for edge in payload["edges"]
        if edge["relationship_type"] == "received_dod_prime_funding"
    )
    assert funding["signed_obligation_total"] == 90
    assert funding["source_record_ids"] == ["CONT_TX_1", "CONT_TX_2"]
    assert funding["match_method"] == "exact_uei"
    association = next(
        edge
        for edge in payload["edges"]
        if edge["relationship_type"] == "candidate_temporal_association"
    )
    assert association["specific_award_usage_status"] == "not_established"
    assert association["temporal_association_is_causal_evidence"] is False
    node_ids = {node["id"] for node in payload["nodes"]}
    assert all(
        edge["source"] in node_ids and edge["target"] in node_ids for edge in payload["edges"]
    )
