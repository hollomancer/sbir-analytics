"""Neo4j client wrapper for batch loading and transaction management."""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from loguru import logger
from neo4j import Driver, GraphDatabase, Session, Transaction
from pydantic import BaseModel, Field


class Neo4jConfig(BaseModel):
    """Neo4j connection configuration."""

    uri: str
    username: str
    password: str
    database: str = "neo4j"
    batch_size: int = 5000  # Increased for UNWIND performance


class LoadMetrics(BaseModel):
    """Metrics for Neo4j loading operations."""

    # Use Field(default_factory=...) to avoid shared mutable defaults between instances.
    nodes_created: dict[str, int] = Field(default_factory=dict)
    nodes_updated: dict[str, int] = Field(default_factory=dict)
    relationships_created: dict[str, int] = Field(default_factory=dict)
    errors: int = 0
    duration_seconds: float = 0.0


class Neo4jClient:
    """Neo4j client with batch loading and transaction management capabilities."""

    def __init__(self, config: Neo4jConfig) -> None:
        """Initialize Neo4j client.

        Args:
            config: Neo4j connection configuration
        """
        self.config = config
        self._driver: Driver | None = None
        logger.info(f"Neo4j client initialized for {config.uri}")

    @property
    def driver(self) -> Driver:
        """Get or create Neo4j driver.

        Returns:
            Neo4j driver instance
        """
        if self._driver is None:
            self._driver = GraphDatabase.driver(
                self.config.uri,
                auth=(self.config.username, self.config.password),
            )
            logger.debug("Neo4j driver created")
        return self._driver

    def close(self) -> None:
        """Close Neo4j driver connection."""
        if self._driver is not None:
            self._driver.close()
            self._driver = None
            logger.debug("Neo4j driver closed")

    @contextmanager
    def session(self) -> Iterator[Session]:
        """Context manager for Neo4j session.

        Yields:
            Neo4j session instance
        """
        session = self.driver.session(database=self.config.database)
        try:
            yield session
        finally:
            session.close()

    def create_constraints(self) -> None:
        """Create unique constraints for entity primary keys."""
        constraints = [
            "CREATE CONSTRAINT company_uei IF NOT EXISTS FOR (c:Company) REQUIRE c.uei IS UNIQUE",
            "CREATE CONSTRAINT award_id IF NOT EXISTS FOR (a:Award) REQUIRE a.award_id IS UNIQUE",
            "CREATE CONSTRAINT researcher_id IF NOT EXISTS FOR (r:Researcher) REQUIRE r.researcher_id IS UNIQUE",
            "CREATE CONSTRAINT patent_id IF NOT EXISTS FOR (p:Patent) REQUIRE p.patent_id IS UNIQUE",
        ]

        with self.session() as session:
            for constraint in constraints:
                try:
                    session.run(constraint)
                    logger.info(f"Created constraint: {constraint}")
                except Exception as e:
                    logger.warning(f"Constraint may already exist: {e}")

    def create_indexes(self) -> None:
        """Create indexes for frequently queried properties."""
        indexes = [
            "CREATE INDEX company_name IF NOT EXISTS FOR (c:Company) ON (c.name)",
            "CREATE INDEX award_date IF NOT EXISTS FOR (a:Award) ON (a.award_date)",
            "CREATE INDEX researcher_name IF NOT EXISTS FOR (r:Researcher) ON (r.name)",
            "CREATE INDEX patent_number IF NOT EXISTS FOR (p:Patent) ON (p.patent_number)",
        ]

        with self.session() as session:
            for index in indexes:
                try:
                    session.run(index)
                    logger.info(f"Created index: {index}")
                except Exception as e:
                    logger.warning(f"Index may already exist: {e}")

    def upsert_node(
        self,
        tx: Transaction,
        label: str,
        key_property: str,
        key_value: Any,
        properties: dict[str, Any],
    ) -> dict[str, Any]:
        """Upsert a single node (create or update).

        Args:
            tx: Neo4j transaction
            label: Node label (e.g., "Company")
            key_property: Property name for matching (e.g., "uei")
            key_value: Value of the key property
            properties: All node properties to set

        Returns:
            Result summary with operation details
        """
        # Use ON CREATE to mark newly-created nodes with a temporary flag so we can
        # reliably distinguish create vs match. We then remove the temporary flag
        # in a cleanup step so we don't persist internal metadata.
        query = f"""
        MERGE (n:{label} {{{key_property}: $key_value}})
        ON CREATE SET n += $properties, n.__created_flag = true
        ON MATCH SET n += $properties
        RETURN n, CASE WHEN n.__created_flag IS NOT NULL THEN 'created' ELSE 'updated' END AS operation
        """

        result = tx.run(query, key_value=key_value, properties=properties)
        record = result.single()

        op = record["operation"] if record else "unknown"

        # Try to remove the internal flag to avoid leaving behind helper properties.
        # This is best-effort and non-fatal if it fails.
        try:
            if op == "created":
                tx.run(
                    f"MATCH (n:{label} {{{key_property}: $key_value}}) REMOVE n.__created_flag",
                    key_value=key_value,
                )
        except Exception:
            # Ignore cleanup errors - they are not critical for correctness of upsert.
            pass

        return {"operation": op}

    def batch_upsert_nodes(
        self,
        label: str,
        key_property: str,
        nodes: list[dict[str, Any]],
        metrics: LoadMetrics | None = None,
    ) -> LoadMetrics:
        """Batch upsert nodes with transaction management using UNWIND for performance.

        Args:
            label: Node label
            key_property: Property name for matching
            nodes: List of node property dictionaries
            metrics: Optional metrics object to update

        Returns:
            Load metrics with counts of created/updated nodes
        """
        if metrics is None:
            metrics = LoadMetrics()

        batch_size = self.config.batch_size
        total_batches = (len(nodes) + batch_size - 1) // batch_size

        logger.info(
            f"Upserting {len(nodes)} {label} nodes in {total_batches} batches " f"of {batch_size}"
        )

        with self.session() as session:
            for i in range(0, len(nodes), batch_size):
                batch = nodes[i : i + batch_size]
                batch_num = i // batch_size + 1

                # Filter out nodes missing the key property
                valid_batch = [n for n in batch if n.get(key_property) is not None]
                invalid_count = len(batch) - len(valid_batch)
                if invalid_count > 0:
                    logger.error(f"{invalid_count} nodes missing key property {key_property}")
                    metrics.errors += invalid_count

                if not valid_batch:
                    continue

                try:
                    # Use UNWIND to batch process all nodes in a single query
                    query = f"""
                    UNWIND $batch AS node
                    MERGE (n:{label} {{{key_property}: node.{key_property}}})
                    ON CREATE SET n = node, n.__created = true
                    ON MATCH SET n += node, n.__created = false
                    RETURN count(CASE WHEN n.__created THEN 1 END) as created_count,
                           count(CASE WHEN NOT n.__created THEN 1 END) as updated_count
                    """

                    result = session.run(query, batch=valid_batch)
                    record = result.single()

                    created = record["created_count"] if record else 0
                    updated = record["updated_count"] if record else 0

                    # Clean up temporary flags
                    cleanup_query = f"""
                    MATCH (n:{label})
                    WHERE n.__created IS NOT NULL
                    REMOVE n.__created
                    """
                    session.run(cleanup_query)

                    # Update metrics
                    metrics.nodes_created[label] = metrics.nodes_created.get(label, 0) + created
                    metrics.nodes_updated[label] = metrics.nodes_updated.get(label, 0) + updated

                    logger.debug(
                        f"Batch {batch_num}/{total_batches} committed "
                        f"({len(valid_batch)} {label} nodes: {created} created, {updated} updated)"
                    )

                except Exception as e:
                    metrics.errors += len(valid_batch)
                    logger.error(f"Error in batch {batch_num}/{total_batches} for {label}: {e}")

        logger.info(
            f"Completed {label} upsert: "
            f"{metrics.nodes_created.get(label, 0)} created, "
            f"{metrics.nodes_updated.get(label, 0)} updated, "
            f"{metrics.errors} errors"
        )

        return metrics

    def create_relationship(
        self,
        tx: Transaction,
        source_label: str,
        source_key: str,
        source_value: Any,
        target_label: str,
        target_key: str,
        target_value: Any,
        rel_type: str,
        properties: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a relationship between two nodes.

        Args:
            tx: Neo4j transaction
            source_label: Source node label
            source_key: Source node key property
            source_value: Source node key value
            target_label: Target node label
            target_key: Target node key property
            target_value: Target node key value
            rel_type: Relationship type
            properties: Optional relationship properties

        Returns:
            Result summary with operation status
        """
        properties = properties or {}

        query = f"""
        MATCH (source:{source_label} {{{source_key}: $source_value}})
        MATCH (target:{target_label} {{{target_key}: $target_value}})
        MERGE (source)-[r:{rel_type}]->(target)
        SET r += $properties
        RETURN r, source, target
        """

        result = tx.run(
            query,
            source_value=source_value,
            target_value=target_value,
            properties=properties,
        )

        record = result.single()
        if record is None:
            return {
                "status": "failed",
                "reason": "source or target node not found",
            }

        return {"status": "created"}

    def batch_create_relationships(
        self,
        relationships: list[tuple[str, str, Any, str, str, Any, str, dict[str, Any] | None]],
        metrics: LoadMetrics | None = None,
    ) -> LoadMetrics:
        """Batch create relationships with transaction management.

        Args:
            relationships: List of relationship tuples:
                (source_label, source_key, source_value,
                 target_label, target_key, target_value,
                 rel_type, properties)
            metrics: Optional metrics object to update

        Returns:
            Load metrics with counts of created relationships
        """
        if metrics is None:
            metrics = LoadMetrics()

        batch_size = self.config.batch_size
        total_batches = (len(relationships) + batch_size - 1) // batch_size

        logger.info(
            f"Creating {len(relationships)} relationships in {total_batches} batches "
            f"of {batch_size}"
        )

        with self.session() as session:
            for i in range(0, len(relationships), batch_size):
                batch = relationships[i : i + batch_size]
                batch_num = i // batch_size + 1

                try:
                    with session.begin_transaction() as tx:
                        for rel in batch:
                            (
                                source_label,
                                source_key,
                                source_value,
                                target_label,
                                target_key,
                                target_value,
                                rel_type,
                                properties,
                            ) = rel

                            result = self.create_relationship(
                                tx,
                                source_label,
                                source_key,
                                source_value,
                                target_label,
                                target_key,
                                target_value,
                                rel_type,
                                properties,
                            )

                            if result["status"] == "created":
                                metrics.relationships_created[rel_type] = (
                                    metrics.relationships_created.get(rel_type, 0) + 1
                                )
                            else:
                                metrics.errors += 1
                                logger.warning(
                                    f"Failed to create relationship {rel_type}: "
                                    f"{result.get('reason', 'unknown')}"
                                )

                        tx.commit()

                    logger.debug(
                        f"Batch {batch_num}/{total_batches} committed "
                        f"({len(batch)} relationships)"
                    )

                except Exception as e:
                    metrics.errors += 1
                    logger.error(f"Error in relationship batch {batch_num}/{total_batches}: {e}")

        total_created = sum(metrics.relationships_created.values())
        logger.info(
            f"Completed relationship creation: " f"{total_created} created, {metrics.errors} errors"
        )

        return metrics

    def __enter__(self) -> "Neo4jClient":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type: Any, exc_val, exc_tb: Any) -> None:
        """Context manager exit."""
        self.close()
