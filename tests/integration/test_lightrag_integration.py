"""Integration tests for LightRAG pipeline components.

Tests the Neo4j-dependent parts of the LightRAG integration:
- Config loading from PipelineConfig
- Document preparation and metadata handling
- Vector index creation (migration 004 schema)
- Entity cross-reference Cypher queries
- Community query patterns

These tests do NOT require an LLM API key — they validate the
Neo4j query/write paths independently of LightRAG's entity extraction.

Run with: docker compose --profile dev up neo4j -d
          pytest tests/integration/test_lightrag_integration.py -o "addopts=" -v
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from tests.conftest import neo4j_running as neo4j_available

from sbir_rag.config import LightRAGConfig
from sbir_rag.document_prep import prepare_award_document, prepare_solicitation_document

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not neo4j_available(), reason="Neo4j not running"),
]


# ---------------------------------------------------------------------------
# Config integration
# ---------------------------------------------------------------------------


class TestLightRAGConfigIntegration:
    """Test config loading against the real PipelineConfig."""

    def test_from_yaml_config_with_pipeline_config(self):
        """from_yaml_config accepts the real PipelineConfig from get_config()."""
        from sbir_etl.config.loader import get_config

        config = LightRAGConfig.from_yaml_config(get_config())
        assert isinstance(config, LightRAGConfig)
        # Default in base.yaml is disabled
        assert config.enabled is False
        assert config.workspace == "sbir"

    def test_from_yaml_config_with_dict(self):
        """from_yaml_config still works with a plain dict."""
        config = LightRAGConfig.from_yaml_config(
            {"lightrag": {"enabled": True, "workspace": "test"}}
        )
        assert config.enabled is True
        assert config.workspace == "test"

    def test_neo4j_env_var_resolution(self, monkeypatch):
        """NEO4J_DATABASE env var is picked up."""
        monkeypatch.setenv("NEO4J_DATABASE", "testdb")
        config = LightRAGConfig()
        assert config.neo4j_database == "testdb"


# ---------------------------------------------------------------------------
# Document preparation (no Neo4j needed, but grouped here for E2E coverage)
# ---------------------------------------------------------------------------


class TestDocumentPrepIntegration:
    """Test document prep handles real-world data edge cases."""

    def test_nan_values_become_none(self):
        """NaN values in award_id and topic_code should become None, not 'nan'."""
        row = pd.Series(
            {
                "award_id": float("nan"),
                "award_title": "Test Award",
                "abstract": "Test abstract",
                "agency": "DOD",
            }
        )
        doc = prepare_award_document(row)
        assert doc["metadata"]["award_id"] is None
        assert doc["metadata"]["award_id"] != "nan"

    def test_solicitation_nan_topic_code(self):
        """NaN topic_code in solicitations becomes None."""
        row = pd.Series(
            {
                "topic_code": float("nan"),
                "title": "Test Topic",
                "description": "Test description",
                "agency": "NSF",
            }
        )
        doc = prepare_solicitation_document(row)
        assert doc["metadata"]["topic_code"] is None

    def test_full_award_roundtrip(self):
        """Full award document has expected structure."""
        row = pd.Series(
            {
                "award_id": "SBIR-12345",
                "award_title": "Quantum Sensing for Navigation",
                "abstract": "This project develops quantum sensors for GPS-denied navigation.",
                "agency": "DOD",
                "phase": "Phase II",
                "keywords": "quantum, sensors, navigation",
                "award_year": 2024,
                "company_name": "QuantumTech Inc",
            }
        )
        doc = prepare_award_document(row)

        assert "Quantum Sensing" in doc["content"]
        assert "Agency: DOD" in doc["content"]
        assert doc["metadata"]["award_id"] == "SBIR-12345"
        assert doc["metadata"]["company_name"] == "QuantumTech Inc"
        assert doc["metadata"]["document_type"] == "award"


# ---------------------------------------------------------------------------
# Neo4j schema and query patterns
# ---------------------------------------------------------------------------


class TestLightRAGNeo4jSchema:
    """Test LightRAG Neo4j schema creation and query patterns."""

    def test_vector_index_creation(self, neo4j_client):
        """Migration 004 vector indexes can be created."""
        with neo4j_client.session() as session:
            # Create the vector index (idempotent)
            session.run(
                """
                CREATE VECTOR INDEX award_embedding_test IF NOT EXISTS
                FOR (a:TestAward) ON (a.embedding)
                OPTIONS {indexConfig: {
                    `vector.dimensions`: 768,
                    `vector.similarity_function`: 'cosine'
                }}
                """
            )

            # Verify index exists
            result = session.run("SHOW INDEXES WHERE name = 'award_embedding_test'")
            indexes = list(result)
            assert len(indexes) == 1

            # Cleanup
            session.run("DROP INDEX award_embedding_test IF EXISTS")

    def test_entity_cross_reference_query_pattern(self, neo4j_client):
        """Cross-reference Cypher pattern links entities to awards via chunks."""
        with neo4j_client.session() as session:
            # Set up test data: entity <- MENTIONS - chunk, award
            session.run(
                """
                CREATE (e:__entity__ {name: 'TestEntity', entity_type: 'TECHNOLOGY'})
                CREATE (c:__chunk__ {source_id: 'AWARD-TEST-001'})
                CREATE (a:TestAward {award_id: 'AWARD-TEST-001', award_title: 'Test'})
                CREATE (c)-[:MENTIONS]->(e)
                """
            )

            # Run the cross-reference query pattern
            result = session.run(
                """
                MATCH (e:__entity__)<-[:MENTIONS]-(c:__chunk__)
                WHERE c.source_id IS NOT NULL
                MATCH (a:TestAward {award_id: c.source_id})
                MERGE (e)-[:EXTRACTED_FROM]->(a)
                RETURN count(*) AS links_created
                """
            )
            record = result.single()
            assert record["links_created"] == 1

            # Verify the relationship was created
            result = session.run(
                """
                MATCH (e:__entity__ {name: 'TestEntity'})-[:EXTRACTED_FROM]->(a:TestAward)
                RETURN a.award_id AS award_id
                """
            )
            record = result.single()
            assert record["award_id"] == "AWARD-TEST-001"

            # Cleanup
            session.run("MATCH (n:__entity__) DETACH DELETE n")
            session.run("MATCH (n:__chunk__) DETACH DELETE n")
            session.run("MATCH (n:TestAward) DETACH DELETE n")

    def test_community_query_pattern(self, neo4j_client):
        """Community query returns expected structure."""
        with neo4j_client.session() as session:
            # Set up test community with members
            session.run(
                """
                CREATE (c:__community__ {id: 'test-comm-1', level: 0,
                        title: 'Quantum Tech', summary: 'Quantum technologies cluster'})
                CREATE (e1:__entity__ {name: 'quantum sensing', entity_type: 'TECHNOLOGY'})
                CREATE (e2:__entity__ {name: 'photonic systems', entity_type: 'TECHNOLOGY'})
                CREATE (a:TestAward {award_id: 'A001', agency: 'DOD'})
                CREATE (c)-[:HAS_MEMBER]->(e1)
                CREATE (c)-[:HAS_MEMBER]->(e2)
                CREATE (e1)-[:EXTRACTED_FROM]->(a)
                """
            )

            # Run the community extraction query pattern
            result = session.run(
                """
                MATCH (c:__community__)
                OPTIONAL MATCH (c)-[:HAS_MEMBER]->(e:__entity__)
                OPTIONAL MATCH (e)-[:EXTRACTED_FROM]->(a:TestAward)
                WITH c,
                     collect(DISTINCT e.name) AS entities,
                     collect(DISTINCT a.award_id) AS award_ids,
                     collect(DISTINCT a.agency) AS agencies
                RETURN
                    c.id AS community_id,
                    c.level AS level,
                    c.title AS title,
                    c.summary AS summary,
                    entities,
                    award_ids,
                    size(entities) AS num_entities,
                    size(award_ids) AS num_awards,
                    [a IN agencies WHERE a IS NOT NULL] AS agencies
                ORDER BY size(entities) DESC
                """
            )

            record = result.single()
            assert record["community_id"] == "test-comm-1"
            assert record["title"] == "Quantum Tech"
            assert set(record["entities"]) == {"quantum sensing", "photonic systems"}
            assert record["num_entities"] == 2
            assert record["award_ids"] == ["A001"]
            assert record["agencies"] == ["DOD"]

            # Cleanup
            session.run("MATCH (n:__community__) DETACH DELETE n")
            session.run("MATCH (n:__entity__) DETACH DELETE n")
            session.run("MATCH (n:TestAward) DETACH DELETE n")

    def test_company_matching_length_guard(self, neo4j_client):
        """Company matching query has length guards to prevent cartesian explosions."""
        with neo4j_client.session() as session:
            # Short name entity should NOT match via CONTAINS
            session.run(
                """
                CREATE (e1:__entity__ {name: 'MIT', entity_type: 'ORGANIZATION'})
                CREATE (e2:__entity__ {name: 'Raytheon Technologies', entity_type: 'ORGANIZATION'})
                CREATE (c1:TestCompany {name: 'MIT Lincoln Laboratory'})
                CREATE (c2:TestCompany {name: 'Raytheon Technologies Corp'})
                """
            )

            # Run the company matching query with length guards
            result = session.run(
                """
                MATCH (e:__entity__)
                WHERE e.entity_type = 'ORGANIZATION'
                  AND size(e.name) >= 4
                MATCH (c:TestCompany)
                WHERE toLower(c.name) = toLower(e.name)
                   OR (size(e.name) >= 8
                       AND (toLower(c.name) CONTAINS toLower(e.name)
                            OR toLower(e.name) CONTAINS toLower(c.name)))
                RETURN e.name AS entity_name, c.name AS company_name
                """
            )

            matches = [(r["entity_name"], r["company_name"]) for r in result]
            # "MIT" (3 chars) should be excluded by size >= 4 guard
            assert not any(m[0] == "MIT" for m in matches)
            # "Raytheon Technologies" (20 chars) should match via CONTAINS
            assert ("Raytheon Technologies", "Raytheon Technologies Corp") in matches

            # Cleanup
            session.run("MATCH (n:__entity__) DETACH DELETE n")
            session.run("MATCH (n:TestCompany) DETACH DELETE n")

    def test_cet_subcommunity_mapping_pattern(self, neo4j_client):
        """CET sub-community mapping query links CETAreas to communities."""
        with neo4j_client.session() as session:
            # Set up: CETArea <- CLASSIFIED_AS - Award -> entity -> community
            session.run(
                """
                CREATE (cet:CETArea {name: 'Quantum Information Science'})
                CREATE (a1:TestAward {award_id: 'QA1'})
                CREATE (a2:TestAward {award_id: 'QA2'})
                CREATE (a1)-[:CLASSIFIED_AS]->(cet)
                CREATE (a2)-[:CLASSIFIED_AS]->(cet)
                CREATE (e1:__entity__ {name: 'quantum entanglement'})
                CREATE (e2:__entity__ {name: 'quantum computing'})
                CREATE (e1)-[:EXTRACTED_FROM]->(a1)
                CREATE (e2)-[:EXTRACTED_FROM]->(a2)
                CREATE (c:__community__ {id: 'qc-comm', level: 0})
                CREATE (c)-[:HAS_MEMBER]->(e1)
                CREATE (c)-[:HAS_MEMBER]->(e2)
                """
            )

            # Run mapping query (threshold >= 2 awards overlap)
            result = session.run(
                """
                MATCH (cet:CETArea)<-[:CLASSIFIED_AS]-(a:TestAward)
                MATCH (e:__entity__)-[:EXTRACTED_FROM]->(a)
                MATCH (c:__community__)-[:HAS_MEMBER]->(e)
                WITH cet, c, count(DISTINCT a) AS overlap_count
                WHERE overlap_count >= 2
                MERGE (cet)-[r:HAS_SUBCOMMUNITY]->(c)
                SET r.overlap_count = overlap_count
                RETURN
                    count(*) AS rels_created,
                    count(DISTINCT cet) AS cets_mapped
                """
            )
            record = result.single()
            assert record["rels_created"] == 1
            assert record["cets_mapped"] == 1

            # Verify relationship properties
            result = session.run(
                """
                MATCH (cet:CETArea)-[r:HAS_SUBCOMMUNITY]->(c:__community__)
                RETURN cet.name AS cet_name, r.overlap_count AS overlap, c.id AS comm_id
                """
            )
            record = result.single()
            assert record["cet_name"] == "Quantum Information Science"
            assert record["overlap"] == 2
            assert record["comm_id"] == "qc-comm"

            # Cleanup
            session.run("MATCH (n:CETArea) DETACH DELETE n")
            session.run("MATCH (n:__community__) DETACH DELETE n")
            session.run("MATCH (n:__entity__) DETACH DELETE n")
            session.run("MATCH (n:TestAward) DETACH DELETE n")


# ---------------------------------------------------------------------------
# Embedding write path (batch UNWIND)
# ---------------------------------------------------------------------------


class TestVectorEmbeddingWrites:
    """Test the batch embedding write path to Neo4j."""

    def test_batch_unwind_embedding_write(self, neo4j_client):
        """Batch UNWIND writes embeddings to Award nodes."""
        with neo4j_client.session() as session:
            # Create test awards
            session.run(
                """
                UNWIND [{id: 'EMB-001', title: 'Award A'},
                        {id: 'EMB-002', title: 'Award B'}] AS a
                CREATE (:TestAward {award_id: a.id, award_title: a.title})
                """
            )

            # Batch write embeddings (simulating vector_index asset)
            embeddings = [
                {"award_id": "EMB-001", "embedding": np.random.randn(768).tolist()},
                {"award_id": "EMB-002", "embedding": np.random.randn(768).tolist()},
            ]

            session.run(
                """
                UNWIND $batch AS row
                MATCH (a:TestAward {award_id: row.award_id})
                SET a.embedding = row.embedding
                """,
                batch=embeddings,
            )

            # Verify embeddings were written
            result = session.run(
                """
                MATCH (a:TestAward)
                WHERE a.embedding IS NOT NULL
                RETURN count(a) AS count, size(a.embedding) AS dim
                LIMIT 1
                """
            )
            record = result.single()
            assert record["count"] == 2
            assert record["dim"] == 768

            # Cleanup
            session.run("MATCH (n:TestAward) DETACH DELETE n")
