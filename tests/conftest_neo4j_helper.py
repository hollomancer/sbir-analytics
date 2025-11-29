"""Helper for Neo4j test availability checking."""


def neo4j_available() -> bool:
    """Check if Neo4j is available for testing."""
    try:
        from neo4j import GraphDatabase

        driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "test"))
        driver.verify_connectivity()
        driver.close()
        return True
    except Exception:
        return False
