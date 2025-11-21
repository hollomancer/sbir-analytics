"""Integration test fixtures."""

import pytest

# Import shared fixtures
from tests.conftest_shared import Neo4jTestHelper, neo4j_client, neo4j_config, neo4j_helper


@pytest.fixture(autouse=True)
def cleanup_test_data(neo4j_client):
    """Clean up test data before and after each test (autouse for integration tests)."""
    # Clean before test
    try:
        with neo4j_client.session() as session:
            session.run("MATCH (n:TestCompany) DETACH DELETE n")
            session.run("MATCH (n:TestAward) DETACH DELETE n")
    except Exception:
        pass  # Skip cleanup if Neo4j not available

    yield

    # Clean after test
    try:
        with neo4j_client.session() as session:
            session.run("MATCH (n:TestCompany) DETACH DELETE n")
            session.run("MATCH (n:TestAward) DETACH DELETE n")
    except Exception:
        pass  # Skip cleanup if Neo4j not available


# Re-export for pytest discovery
__all__ = [
    "neo4j_config",
    "neo4j_client",
    "cleanup_test_data",
    "Neo4jTestHelper",
    "neo4j_helper",
]
