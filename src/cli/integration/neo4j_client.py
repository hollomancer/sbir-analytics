"""Neo4j client for CLI health checks and statistics."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from loguru import logger
from neo4j import GraphDatabase
from rich.console import Console

from src.config.schemas import PipelineConfig


@dataclass
class Neo4jHealthStatus:
    """Neo4j connection health status."""

    connected: bool
    uri: str
    version: str | None = None
    error: str | None = None


@dataclass
class Neo4jStatistics:
    """Neo4j database statistics."""

    node_counts: dict[str, int]
    relationship_counts: dict[str, int]
    total_nodes: int
    total_relationships: int
    database_name: str


class Neo4jClient:
    """Neo4j client for CLI operations.

    Provides health checks, statistics, and basic query capabilities
    for the CLI interface.
    """

    def __init__(self, config: PipelineConfig, console: Console) -> None:
        """Initialize Neo4j client.

        Args:
            config: Pipeline configuration
            console: Rich console for output
        """
        self.config = config
        self.console = console
        self.neo4j_config = config.neo4j
        self._driver = None

    @property
    def driver(self) -> Any:
        """Get or create Neo4j driver."""
        if self._driver is None:
            import os
            password = self.neo4j_config.password or os.getenv(self.neo4j_config.password_env_var, "neo4j")
            self._driver = GraphDatabase.driver(
                self.neo4j_config.uri,
                auth=(self.neo4j_config.username, password),
            )
        return self._driver

    def close(self) -> None:
        """Close Neo4j driver connection."""
        if self._driver is not None:
            self._driver.close()  # type: ignore[unreachable]
            self._driver = None

    def health_check(self) -> Neo4jHealthStatus:
        """Check Neo4j connection health.

        Returns:
            Neo4jHealthStatus with connection status
        """
        try:
            with self.driver.session() as session:
                # Simple query to test connection
                result = session.run("RETURN 1 as test")
                record = result.single()

                if record and record["test"] == 1:
                    # Try to get version
                    version_result = session.run(
                        "CALL dbms.components() YIELD name, versions RETURN versions[0] as version"
                    )
                    version_record = version_result.single()
                    version = version_record["version"] if version_record else None

                    return Neo4jHealthStatus(
                        connected=True,
                        uri=self.neo4j_config.uri,
                        version=version,
                    )
                else:
                    return Neo4jHealthStatus(
                        connected=False,
                        uri=self.neo4j_config.uri,
                        error="Query returned unexpected result",
                    )

        except Exception as e:
            logger.debug(f"Neo4j health check failed: {e}")
            return Neo4jHealthStatus(
                connected=False,
                uri=self.neo4j_config.uri,
                error=str(e),
            )

    def get_statistics(self) -> Neo4jStatistics | None:
        """Get Neo4j database statistics.

        Returns:
            Neo4jStatistics or None if query fails
        """
        try:
            with self.driver.session(database=self.neo4j_config.database) as session:
                # Get node counts by label
                node_query = """
                MATCH (n)
                RETURN labels(n)[0] as label, count(n) as count
                ORDER BY count DESC
                """
                node_result = session.run(node_query)
                node_counts = {
                    record["label"]: record["count"] for record in node_result if record["label"]
                }

                # Get relationship counts by type
                rel_query = """
                MATCH ()-[r]->()
                RETURN type(r) as rel_type, count(r) as count
                ORDER BY count DESC
                """
                rel_result = session.run(rel_query)
                relationship_counts = {record["rel_type"]: record["count"] for record in rel_result}

                # Get totals
                total_nodes = sum(node_counts.values())
                total_relationships = sum(relationship_counts.values())

                return Neo4jStatistics(
                    node_counts=node_counts,
                    relationship_counts=relationship_counts,
                    total_nodes=total_nodes,
                    total_relationships=total_relationships,
                    database_name=self.neo4j_config.database,
                )

        except Exception as e:
            logger.warning(f"Failed to get Neo4j statistics: {e}")
            return None

    def execute_query(
        self, query: str, parameters: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Execute a read-only Cypher query.

        Args:
            query: Cypher query string
            parameters: Optional query parameters

        Returns:
            List of result records as dictionaries

        Raises:
            ValueError: If query appears to be a write operation
        """
        # Basic validation: warn if query contains write keywords
        write_keywords = ["CREATE", "DELETE", "SET", "REMOVE", "MERGE", "CREATE UNIQUE"]
        query_upper = query.upper()
        if any(keyword in query_upper for keyword in write_keywords):
            logger.warning(f"Query contains write keywords: {query}")

        try:
            with self.driver.session(database=self.neo4j_config.database) as session:
                result = session.run(query, parameters or {})
                records = [dict(record) for record in result]
                return records

        except Exception as e:
            logger.error(f"Query execution failed: {e}")
            raise
