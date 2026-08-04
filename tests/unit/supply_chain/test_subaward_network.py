import pandas as pd

from sbir_etl.supply_chain.subaward_network import (
    aggregate_supplier_prime_edges,
    build_nsf_sbir_award_candidates,
    build_sbir_awardee_registry,
    build_supplier_customer_exposure,
    build_subaward_facts,
    network_metadata,
)


def _awards() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "company_name": "Acme Technologies, Inc.",
                "company_uei": "ABCDEFGHIJKL",
                "company_duns": "123456789",
                "agency": "NSF",
                "program": "SBIR",
                "topic_code": "AI",
                "award_year": "2022",
                "award_amount": "250000",
            },
            {
                "company_name": "Acme Technologies Inc",
                "company_uei": "ABCDEFGHIJKL",
                "company_duns": "123456789",
                "agency": "DOD",
                "program": "SBIR",
            },
            {
                "company_name": "Name Match Labs LLC",
                "company_uei": None,
                "company_duns": None,
                "agency": "NSF",
                "program": "STTR",
            },
        ]
    )


def _subawards() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "prime_award_unique_key": "PRIME-1",
                "prime_award_piid": "W1",
                "prime_awardee_uei": "PRIMEUEI0001",
                "prime_awardee_name": "Major Prime Corp",
                "subaward_number": "SUB-1",
                "subaward_sam_report_id": "REPORT-1",
                "subaward_amount": 100_000,
                "subaward_action_date": "2025-01-15",
                "subawardee_uei": "ABCDEFGHIJKL",
                "subawardee_duns": "123456789",
                "subawardee_name": "Acme Tech",
            },
            {
                "prime_award_unique_key": "PRIME-1",
                "prime_award_piid": "W1",
                "prime_awardee_uei": "PRIMEUEI0001",
                "prime_awardee_name": "Major Prime Corp",
                "subaward_number": "SUB-2",
                "subaward_sam_report_id": "REPORT-2",
                "subaward_amount": 50_000,
                "subaward_action_date": "2025-02-15",
                "subawardee_name": "Name Match Labs",
            },
            {
                "prime_award_unique_key": "PRIME-2",
                "prime_award_piid": "W2",
                "prime_awardee_uei": "OTHERPRIME01",
                "prime_awardee_name": "Other Prime Corp",
                "subaward_number": "SUB-3",
                "subaward_sam_report_id": "REPORT-3",
                "subaward_amount": 25_000,
                "subaward_action_date": "2025-03-15",
                "subawardee_name": "Not an SBIR Firm",
            },
        ]
    )


def test_build_registry_counts_awards_and_prefers_uei_identity() -> None:
    registry = build_sbir_awardee_registry(_awards())

    acme = registry.loc[registry["sbir_uei"] == "ABCDEFGHIJKL"].iloc[0]
    assert acme["sbir_organization_id"] == "uei:ABCDEFGHIJKL"
    assert acme["sbir_award_count"] == 2
    assert acme["nsf_sbir_awardee"]
    assert acme["nsf_sbir_award_count"] == 1
    assert len(registry) == 2


def test_registry_reads_raw_sbir_gov_nsf_fields() -> None:
    awards = pd.DataFrame(
        [
            {
                "Company": "Critical Materials Lab",
                "UEI": "MATERIALS001",
                "Duns": "012345678",
                "Agency": "National Science Foundation",
                "Program": "SBIR",
                "Topic Code": "MM",
                "Award Year": "2022",
                "Award Amount": "275000",
            },
            {
                "Company": "Critical Materials Lab",
                "UEI": "MATERIALS001",
                "Duns": "012345678",
                "Agency": "NSF",
                "Program": "SBIR",
                "Topic Code": "AM",
                "Award Year": "2024",
                "Award Amount": "1000000",
            },
            {
                "Company": "Critical Materials Lab",
                "UEI": "MATERIALS001",
                "Duns": "012345678",
                "Agency": "NSF",
                "Program": "STTR",
                "Topic Code": "STTR",
                "Award Year": "2024",
                "Award Amount": "500000",
            },
        ]
    )

    awardee = build_sbir_awardee_registry(awards).iloc[0]

    assert awardee["nsf_sbir_awardee"]
    assert awardee["nsf_sbir_award_count"] == 2
    assert awardee["nsf_sttr_award_count"] == 1
    assert awardee["nsf_sbir_topic_codes"] == "AM|MM"
    assert awardee["nsf_sbir_first_award_year"] == 2022
    assert awardee["nsf_sbir_latest_award_year"] == 2024
    assert awardee["nsf_sbir_award_amount"] == 1_275_000


def test_build_subaward_facts_separates_verified_and_candidate_matches() -> None:
    registry = build_sbir_awardee_registry(_awards())
    facts = build_subaward_facts(registry, _subawards())

    assert len(facts) == 2
    verified = facts.loc[facts["subaward_number"] == "SUB-1"].iloc[0]
    candidate = facts.loc[facts["subaward_number"] == "SUB-2"].iloc[0]
    assert verified["match_method"] == "exact_uei"
    assert verified["subaward_fact_id"].startswith("composite:")
    assert verified["source_report_version_count"] == 1
    assert verified["evidence_grade"] == "verified_identifier"
    assert candidate["match_method"] == "exact_normalized_name"
    assert candidate["evidence_grade"] == "candidate_name"
    assert facts["dib_supplier_tier"].eq("tier_2").all()
    assert not facts["absence_is_negative_evidence"].any()


def test_name_candidates_can_be_excluded() -> None:
    registry = build_sbir_awardee_registry(_awards())
    facts = build_subaward_facts(registry, _subawards(), include_name_candidates=False)

    assert facts["subaward_number"].tolist() == ["SUB-1"]


def test_specific_nsf_sbir_awards_are_candidates_not_confirmed_usage() -> None:
    awards = _awards().copy()
    awards.loc[0, "award_title"] = "Resilient advanced material production"
    awards.loc[0, "phase"] = "Phase II"
    registry = build_sbir_awardee_registry(awards)
    facts = build_subaward_facts(registry, _subawards())
    edges = aggregate_supplier_prime_edges(
        facts.loc[facts["evidence_grade"] == "verified_identifier"]
    )
    exposure = build_supplier_customer_exposure(edges)

    candidates = build_nsf_sbir_award_candidates(awards, registry, exposure)

    assert len(candidates) == 1
    candidate = candidates.iloc[0]
    assert candidate["nsf_sbir_award_title"] == "Resilient advanced material production"
    assert candidate["awardee_association_method"] == "exact_uei"
    assert candidate["supplier_relationship_evidence"] == "verified_identifier"
    assert candidate["specific_award_usage_status"] == "not_established"
    assert candidate["critical_supply_chain_status"] == "not_assessed"


def test_duns_is_verified_when_uei_is_unavailable() -> None:
    registry = build_sbir_awardee_registry(_awards())
    subaward = _subawards().iloc[[0]].copy()
    subaward["subawardee_uei"] = None

    facts = build_subaward_facts(registry, subaward)

    assert facts.iloc[0]["match_method"] == "exact_duns"
    assert facts.iloc[0]["evidence_grade"] == "verified_identifier"


def test_placeholder_identifiers_cannot_create_verified_edges() -> None:
    awards = pd.DataFrame(
        [
            {
                "company_name": "Placeholder Identifier Labs LLC",
                "company_uei": "N/A",
                "company_duns": "NONE",
                "agency": "NSF",
                "program": "SBIR",
            },
            {
                "company_name": "Zero Identifier Systems Inc",
                "company_uei": "UNAVAILABLE",
                "company_duns": "000000000",
                "agency": "NSF",
                "program": "SBIR",
            },
        ]
    )
    subawards = pd.DataFrame(
        [
            {
                "prime_award_unique_key": "PRIME-PLACEHOLDER",
                "prime_award_piid": "W-PLACEHOLDER",
                "prime_awardee_name": "Major Prime Corp",
                "subaward_number": "SUB-PLACEHOLDER",
                "subaward_amount": 10_000,
                "subaward_action_date": "2025-01-15",
                "subawardee_uei": "N/A",
                "subawardee_duns": "NONE",
                "subawardee_name": "Placeholder Identifier Labs",
            },
            {
                "prime_award_unique_key": "PRIME-ZERO",
                "prime_award_piid": "W-ZERO",
                "prime_awardee_name": "Major Prime Corp",
                "subaward_number": "SUB-ZERO",
                "subaward_amount": 20_000,
                "subaward_action_date": "2025-01-16",
                "subawardee_uei": "UNAVAILABLE",
                "subawardee_duns": "000000000",
                "subawardee_name": "Zero Identifier Systems",
            },
        ]
    )

    registry = build_sbir_awardee_registry(awards)
    candidate_facts = build_subaward_facts(registry, subawards)
    verified_facts = build_subaward_facts(
        registry,
        subawards,
        include_name_candidates=False,
    )

    assert registry["sbir_uei"].isna().all()
    assert registry["sbir_duns"].isna().all()
    assert candidate_facts["subawardee_uei"].isna().all()
    assert candidate_facts["subawardee_duns"].isna().all()
    assert candidate_facts["match_method"].eq("exact_normalized_name").all()
    assert candidate_facts["evidence_grade"].eq("candidate_name").all()
    assert verified_facts.empty


def test_identical_source_rows_collapse_before_edge_amount_sum() -> None:
    registry = build_sbir_awardee_registry(_awards())
    source_row = _subawards().iloc[[0]].copy()

    facts = build_subaward_facts(
        registry,
        pd.concat([source_row, source_row], ignore_index=True),
    )
    edges = aggregate_supplier_prime_edges(facts)

    assert len(facts) == 1
    assert facts.iloc[0]["source_report_version_count"] == 2
    assert edges.iloc[0]["reported_subaward_amount"] == 100_000


def test_corrected_report_replaces_superseded_amount() -> None:
    registry = build_sbir_awardee_registry(_awards())
    first = _subawards().iloc[[0]].copy()
    first["subaward_sam_report_last_modified_date"] = "2025-02-01"
    revised = first.copy()
    revised["subaward_sam_report_id"] = "REPORT-1-REVISION"
    revised["subaward_amount"] = 125_000
    revised["subaward_sam_report_last_modified_date"] = "2025-03-01"

    facts = build_subaward_facts(registry, pd.concat([revised, first], ignore_index=True))
    edges = aggregate_supplier_prime_edges(facts)

    assert len(facts) == 1
    assert facts.iloc[0]["subaward_sam_report_id"] == "REPORT-1-REVISION"
    assert facts.iloc[0]["subaward_amount"] == 125_000
    assert facts.iloc[0]["subaward_action_date"] == pd.Timestamp("2025-01-15")
    assert facts.iloc[0]["source_report_version_count"] == 2
    assert edges.iloc[0]["reported_subaward_amount"] == 125_000


def test_equal_report_timestamps_use_report_id_tiebreaker() -> None:
    registry = build_sbir_awardee_registry(_awards())
    first = _subawards().iloc[[0]].copy()
    first["subaward_action_date"] = "2025-01-15T18:00:00"
    first["subaward_sam_report_last_modified_date"] = "2025-02-01"
    revised = first.copy()
    revised["subaward_sam_report_id"] = "REPORT-2"
    revised["subaward_amount"] = 125_000
    revised["subaward_action_date"] = "2025-01-15T08:00:00"

    facts = build_subaward_facts(registry, pd.concat([revised, first], ignore_index=True))

    assert len(facts) == 1
    assert facts.iloc[0]["subaward_sam_report_id"] == "REPORT-2"
    assert facts.iloc[0]["subaward_amount"] == 125_000
    assert facts.iloc[0]["subaward_action_date"] == pd.Timestamp("2025-01-15T08:00:00")
    assert facts.iloc[0]["source_report_version_count"] == 2


def test_equal_report_metadata_uses_order_independent_row_hash_tiebreaker() -> None:
    registry = build_sbir_awardee_registry(_awards())
    first = _subawards().iloc[[0]].copy()
    first["subaward_sam_report_last_modified_date"] = "2025-02-01"
    corrected = first.copy()
    corrected["subaward_amount"] = 125_000
    corrected["subaward_description"] = "Corrected report content"

    first_order = build_subaward_facts(
        registry,
        pd.concat([first, corrected], ignore_index=True),
    )
    reversed_order = build_subaward_facts(
        registry,
        pd.concat([corrected, first], ignore_index=True),
    )

    pd.testing.assert_frame_equal(first_order, reversed_order)
    assert first_order.iloc[0]["source_report_version_count"] == 2


def test_distinct_action_dates_remain_separate_economic_facts() -> None:
    registry = build_sbir_awardee_registry(_awards())
    first = _subawards().iloc[[0]].copy()
    later_action = first.copy()
    later_action["subaward_sam_report_id"] = "REPORT-1-LATER-ACTION"
    later_action["subaward_amount"] = 25_000
    later_action["subaward_action_date"] = "2025-01-20"

    facts = build_subaward_facts(
        registry,
        pd.concat([first, later_action], ignore_index=True),
    )
    edges = aggregate_supplier_prime_edges(facts)

    assert len(facts) == 2
    assert facts["source_report_version_count"].eq(1).all()
    assert edges.iloc[0]["reported_subaward_amount"] == 125_000


def test_aggregate_edges_preserves_amount_and_dependency_guardrail() -> None:
    registry = build_sbir_awardee_registry(_awards())
    facts = build_subaward_facts(registry, _subawards())
    verified = facts[facts["evidence_grade"] == "verified_identifier"]
    candidates = facts[facts["evidence_grade"] == "candidate_name"]
    edges = aggregate_supplier_prime_edges(verified)
    candidate_edges = aggregate_supplier_prime_edges(candidates)
    exposure = build_supplier_customer_exposure(edges)
    metadata = network_metadata(
        verified,
        edges,
        candidate_facts=candidates,
        candidate_edges=candidate_edges,
    )

    assert len(edges) == 1
    assert edges["reported_subaward_amount"].sum() == 100_000
    assert edges.iloc[0]["observed_fiscal_year_count"] == 1
    assert edges["dependency_status"].eq("not_established").all()
    assert edges.iloc[0]["nsf_supply_chain_review_candidate"]
    assert exposure.iloc[0]["observed_prime_family_count"] == 1
    assert exposure.iloc[0]["screening_status"] == "single_observed_prime"
    assert exposure.iloc[0]["dependency_status"] == "not_established"
    assert exposure.iloc[0]["nsf_review_priority"] == "observed_relationship"
    assert metadata["identifier_verified_subaward_facts"] == 1
    assert metadata["name_candidate_subaward_facts"] == 1
    assert metadata["tier_semantics"]["tier_3_plus"].startswith("not observable")


def test_customer_concentration_excludes_nonpositive_edges() -> None:
    edges = pd.DataFrame(
        [
            {
                "sbir_organization_id": "uei:SUPPLIER",
                "sbir_awardee_name": "Supplier Inc",
                "prime_organization_id": "uei:PRIME1",
                "prime_name": "Prime One",
                "prime_family_id": "uei:FAMILY1",
                "prime_family_name": "Prime Family One",
                "reported_subaward_amount": 100.0,
                "reported_subaward_count": 1,
                "prime_award_count": 1,
                "observed_fiscal_year_count": 1,
            },
            {
                "sbir_organization_id": "uei:SUPPLIER",
                "sbir_awardee_name": "Supplier Inc",
                "prime_organization_id": "uei:PRIME2",
                "prime_name": "Prime Two",
                "prime_family_id": "uei:FAMILY2",
                "prime_family_name": "Prime Family Two",
                "reported_subaward_amount": -50.0,
                "reported_subaward_count": 1,
                "prime_award_count": 1,
                "observed_fiscal_year_count": 1,
            },
        ]
    )

    exposure = build_supplier_customer_exposure(edges).iloc[0]

    assert exposure["reported_subaward_amount"] == 50.0
    assert exposure["concentration_basis_amount"] == 100.0
    assert exposure["nonpositive_edge_count"] == 1
    assert exposure["observed_customer_hhi"] == 1.0
