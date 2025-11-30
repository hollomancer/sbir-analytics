"""Integration test fixtures."""

import pytest

# Import shared fixtures
from tests.conftest_shared import Neo4jTestHelper, neo4j_client, neo4j_config, neo4j_helper


@pytest.fixture(autouse=True)
def cleanup_test_data(request):
    """Clean up test data before and after each test (autouse for integration tests).

    Only runs cleanup if the test actually uses neo4j_client fixture.
    """
    # Check if test uses neo4j_client
    if "neo4j_client" not in request.fixturenames:
        yield
        return

    # Get neo4j_client if available
    try:
        client = request.getfixturevalue("neo4j_client")
    except Exception:
        yield
        return

    # Clean before test
    try:
        with client.session() as session:
            session.run("MATCH (n:TestCompany) DETACH DELETE n")
            session.run("MATCH (n:TestAward) DETACH DELETE n")
    except Exception:
        pass  # Skip cleanup if Neo4j not available

    yield

    # Clean after test
    try:
        with client.session() as session:
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
