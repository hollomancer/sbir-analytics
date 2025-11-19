#!/usr/bin/env python3
"""CET smoke test - validates constraints, nodes, enrichments, relationships, and assertions."""
import os
from src.loaders.neo4j_client import Neo4jClient, Neo4jConfig
from src.loaders.cet_loader import CETLoader, CETLoaderConfig


def main():
    """Run CET smoke test."""
    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    user = os.environ.get("NEO4J_USERNAME", "neo4j")
    pwd = os.environ.get("NEO4J_PASSWORD", "password")

    client = Neo4jClient(Neo4jConfig(uri=uri, username=user, password=pwd))
    loader = CETLoader(client, CETLoaderConfig(batch_size=50))

    # Ensure constraints and indexes
    loader.create_constraints()
    loader.create_indexes()

    # Upsert CETArea node
    areas = [{
        "cet_id": "artificial_intelligence",
        "name": "Artificial Intelligence",
        "taxonomy_version": "TEST-2025Q1",
        "keywords": ["machine learning", "neural network"],
    }]
    m_areas = loader.load_cet_areas(areas)
    assert (m_areas.errors or 0) == 0, f"Errors loading CET areas: {m_areas.errors}"

    # Upsert Award enrichment (creates Award node if absent)
    enrich_award = [{
        "award_id": "smoke_award_001",
        "cet_primary_id": "artificial_intelligence",
        "cet_primary_score": 92.5,
        "cet_supporting_ids": [],
        "cet_taxonomy_version": "TEST-2025Q1",
        "cet_model_version": "vtest",
    }]
    m_award = loader.upsert_award_cet_enrichment(enrich_award)
    assert (m_award.errors or 0) == 0, f"Errors upserting award enrichment: {m_award.errors}"

    # Create Award -> CETArea relationship
    rel_rows = [{
        "award_id": "smoke_award_001",
        "primary_cet": "artificial_intelligence",
        "primary_score": 92.5,
        "classified_at": "2025-01-01T00:00:00Z",
        "taxonomy_version": "TEST-2025Q1",
    }]
    m_rel = loader.create_award_cet_relationships(rel_rows)
    assert (m_rel.errors or 0) == 0, f"Errors creating Award->CET relationships: {m_rel.errors}"

    # Upsert Company enrichment and create Company -> CET relationship
    enrich_company = [{
        "uei": "UEI-SMOKE",
        "cet_dominant_id": "artificial_intelligence",
        "cet_dominant_score": 88.0,
        "cet_specialization_score": 0.9,
        "cet_areas": ["artificial_intelligence"],
        "cet_taxonomy_version": "TEST-2025Q1",
    }]
    m_company = loader.upsert_company_cet_enrichment(enrich_company, key_property="uei")
    assert (m_company.errors or 0) == 0, f"Errors upserting company enrichment: {m_company.errors}"

    comp_rel_rows = [{
        "uei": "UEI-SMOKE",
        "cet_dominant_id": "artificial_intelligence",
        "cet_dominant_score": 88.0,
        "cet_specialization_score": 0.9,
        "cet_taxonomy_version": "TEST-2025Q1",
    }]
    m_comp_rel = loader.create_company_cet_relationships(
        comp_rel_rows, rel_type="SPECIALIZES_IN", key_property="uei"
    )
    assert (m_comp_rel.errors or 0) == 0, f"Errors creating Company->CET relationships: {m_comp_rel.errors}"

    # Assertions via cypher
    with client.session() as session:
        # Award enrichment presence
        rec = session.run(
            "MATCH (a:Award {award_id:$aid}) RETURN a.cet_primary_id AS pid, a.cet_taxonomy_version AS v",
            aid="smoke_award_001",
        ).single()
        assert rec and rec["pid"] == "artificial_intelligence", "Award enrichment missing or incorrect"

        # Award -> CET relationship exists
        rel_count = session.run(
            "MATCH (:Award {award_id:$aid})-[:APPLICABLE_TO]->(:CETArea {cet_id:$cid}) RETURN count(*) AS c",
            aid="smoke_award_001", cid="artificial_intelligence"
        ).single()["c"]
        assert rel_count == 1, f"Expected 1 APPLICABLE_TO, found {rel_count}"

        # Company -> CET relationship exists
        comp_rel_count = session.run(
            "MATCH (:Company {uei:$uei})-[:SPECIALIZES_IN]->(:CETArea {cet_id:$cid}) RETURN count(*) AS c",
            uei="UEI-SMOKE", cid="artificial_intelligence"
        ).single()["c"]
        assert comp_rel_count == 1, f"Expected 1 SPECIALIZES_IN, found {comp_rel_count}"

    print("CET smoke completed successfully.")
    client.close()


if __name__ == '__main__':
    main()

