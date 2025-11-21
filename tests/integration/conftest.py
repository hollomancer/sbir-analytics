"""Integration test fixtures."""

import os
import pytest
from src.loaders.neo4j.client import Neo4jClient, Neo4jConfig


@pytest.fixture(scope="module")
def neo4j_config():
    """Create Neo4j configuration for testing."""
    return Neo4jConfig(
        uri=os.getenv("NEO4J_URI", "bolt://localhost:7687"),
        username=os.getenv("NEO4J_USERNAME", "neo4j"),
        password=os.getenv("NEO4J_PASSWORD", "password123"),
        database=os.getenv("NEO4J_DATABASE", "neo4j"),
        batch_size=10,
    )


@pytest.fixture(scope="module")
def neo4j_client(neo4j_config):
    """Create Neo4j client for testing."""
    client = Neo4jClient(neo4j_config)
    yield client
    client.close()


@pytest.fixture(autouse=True)
def cleanup_test_data(neo4j_client):
    """Clean up test data before and after each test."""
    # Clean before test
    with neo4j_client.session() as session:
        session.run("MATCH (n:TestCompany) DETACH DELETE n")
        session.run("MATCH (n:TestAward) DETACH DELETE n")

    yield

    # Clean after test
    with neo4j_client.session() as session:
        session.run("MATCH (n:TestCompany) DETACH DELETE n")
        session.run("MATCH (n:TestAward) DETACH DELETE n")


class Neo4jTestHelper:
    """Helper class for Neo4j integration tests."""

    def __init__(self, client: Neo4jClient):
        self.client = client

    def create_company(self, uei: str, name: str = "Test Company", **kwargs):
        """Create a TestCompany node."""
        props = {"uei": uei, "name": name, **kwargs}
        query = "CREATE (c:TestCompany $props)"
        with self.client.session() as session:
            session.run(query, props=props)

    def create_award(self, award_id: str, **kwargs):
        """Create a TestAward node."""
        props = {"award_id": award_id, **kwargs}
        query = "CREATE (a:TestAward $props)"
        with self.client.session() as session:
            session.run(query, props=props)

    def create_relationship(
        self,
        source_label: str,
        source_key: str,
        source_val: str,
        target_label: str,
        target_key: str,
        target_val: str,
        rel_type: str,
        props: dict = None,
    ):
        """Create a relationship between two nodes."""
        props = props or {}
        query = f"""
        MATCH (s:{source_label} {{{source_key}: $source_val}})
        MATCH (t:{target_label} {{{target_key}: $target_val}})
        CREATE (s)-[r:{rel_type} $props]->(t)
        RETURN r
        """
        with self.client.session() as session:
            session.run(
                query,
                source_val=source_val,
                target_val=target_val,
                props=props,
            )


@pytest.fixture
def neo4j_helper(neo4j_client):
    """Fixture providing Neo4jTestHelper."""
    return Neo4jTestHelper(neo4j_client)
