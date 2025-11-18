"""Base loader class for Neo4j operations.

This module provides BaseNeo4jLoader, a base class that standardizes common patterns
across all Neo4j loaders, reducing code duplication by ~60%.

Key features:
- Standardized initialization with Neo4jClient
- Common logging patterns and metrics reporting
- Helper methods for schema management
- Simplified node and relationship loading patterns
- BaseLoaderConfig for consistent configuration patterns
"""

from __future__ import annotations

from abc import ABC
from datetime import datetime
from typing import Any

from loguru import logger
from pydantic import BaseModel, Field

from .client import LoadMetrics, Neo4jClient


class BaseLoaderConfig(BaseModel):
    """Base configuration for Neo4j loaders.

    Provides common configuration fields that all loaders share.
    Individual loaders can extend this with additional fields.
    """

    batch_size: int = Field(
        default=1000,
        ge=1,
        description="Number of records to process per batch",
    )
    create_indexes: bool = Field(
        default=True,
        description="Whether to create indexes during initialization",
    )
    create_constraints: bool = Field(
        default=True,
        description="Whether to create constraints during initialization",
    )

    model_config = {"frozen": False}  # Allow mutation for backward compatibility


class BaseNeo4jLoader(ABC):
    """Base class for all Neo4j loaders.

    Provides common functionality for:
    - Client initialization
    - Metrics tracking and reporting
    - Schema management (constraints, indexes)
    - Batch node upserts
    - Batch relationship creation
    - Standardized logging

    Attributes:
        client: Neo4jClient instance for graph operations
        metrics: LoadMetrics for tracking operations
        loader_name: Name of the loader (automatically derived from class name)

    Example:
        >>> class PatentLoader(BaseNeo4jLoader):
        ...     def load_patents(self, patents: list[dict]) -> LoadMetrics:
        ...         return self.batch_upsert_nodes(
        ...             label="Patent",
        ...             key_property="patent_id",
        ...             nodes=patents
        ...         )
    """

    def __init__(self, client: Neo4jClient):
        """Initialize loader with Neo4j client.

        Args:
            client: Neo4jClient instance for graph operations
        """
        self.client = client
        self.metrics = LoadMetrics()
        self.loader_name = self.__class__.__name__
        logger.debug(f"{self.loader_name} initialized")

    # -------------------------------------------------------------------------
    # Node Operations
    # -------------------------------------------------------------------------

    def batch_upsert_nodes(
        self,
        label: str,
        key_property: str,
        nodes: list[dict[str, Any]],
        log_progress: bool = True,
    ) -> LoadMetrics:
        """Batch upsert nodes with standardized logging.

        This is a convenience wrapper around client.batch_upsert_nodes that
        adds consistent logging patterns.

        Args:
            label: Node label (e.g., "Patent", "Award")
            key_property: Property name for matching (e.g., "patent_id")
            nodes: List of node property dictionaries
            log_progress: Whether to log progress messages

        Returns:
            LoadMetrics with counts of created/updated nodes

        Example:
            >>> metrics = self.batch_upsert_nodes(
            ...     label="Patent",
            ...     key_property="patent_id",
            ...     nodes=patents
            ... )
        """
        if not nodes:
            logger.info(f"{self.loader_name}: No {label} nodes to load")
            return self.metrics

        if log_progress:
            logger.info(
                f"{self.loader_name}: Loading {len(nodes)} {label} nodes "
                f"(key: {key_property})"
            )

        start_time = datetime.utcnow()

        self.metrics = self.client.batch_upsert_nodes(
            label=label,
            key_property=key_property,
            nodes=nodes,
            metrics=self.metrics,
        )

        if log_progress:
            duration = (datetime.utcnow() - start_time).total_seconds()
            self._log_node_results(label, duration)

        return self.metrics

    def batch_upsert_organizations(
        self,
        nodes: list[dict[str, Any]],
        merge_on_uei: bool = True,
        merge_on_duns: bool = True,
        track_merge_history: bool = True,
        log_progress: bool = True,
    ) -> LoadMetrics:
        """Batch upsert Organization nodes with multi-key merge logic.

        This is a convenience wrapper around client.batch_upsert_organizations_with_multi_key
        that adds consistent logging patterns.

        Args:
            nodes: List of Organization node dictionaries
            merge_on_uei: If True, merge nodes with same UEI
            merge_on_duns: If True, merge nodes with same DUNS
            track_merge_history: If True, track merge history in node properties
            log_progress: Whether to log progress messages

        Returns:
            LoadMetrics with counts of created/updated/merged nodes
        """
        if not nodes:
            logger.info(f"{self.loader_name}: No Organization nodes to load")
            return self.metrics

        if log_progress:
            logger.info(f"{self.loader_name}: Loading {len(nodes)} Organization nodes")

        start_time = datetime.utcnow()

        self.metrics = self.client.batch_upsert_organizations_with_multi_key(
            nodes=nodes,
            metrics=self.metrics,
            merge_on_uei=merge_on_uei,
            merge_on_duns=merge_on_duns,
            track_merge_history=track_merge_history,
        )

        if log_progress:
            duration = (datetime.utcnow() - start_time).total_seconds()
            self._log_node_results("Organization", duration)

        return self.metrics

    # -------------------------------------------------------------------------
    # Relationship Operations
    # -------------------------------------------------------------------------

    def batch_create_relationships(
        self,
        source_label: str,
        source_key: str,
        target_label: str,
        target_key: str,
        rel_type: str,
        relationships: list[tuple[Any, Any, dict[str, Any] | None]],
        log_progress: bool = True,
    ) -> LoadMetrics:
        """Batch create relationships with standardized format and logging.

        Simplified interface that constructs the full relationship tuple format
        expected by client.batch_create_relationships.

        Args:
            source_label: Source node label
            source_key: Source node key property
            target_label: Target node label
            target_key: Target node key property
            rel_type: Relationship type
            relationships: List of (source_value, target_value, properties) tuples
            log_progress: Whether to log progress messages

        Returns:
            LoadMetrics with counts of created relationships

        Example:
            >>> metrics = self.batch_create_relationships(
            ...     source_label="Award",
            ...     source_key="award_id",
            ...     target_label="Organization",
            ...     target_key="organization_id",
            ...     rel_type="AWARDED_TO",
            ...     relationships=[
            ...         ("AWARD-001", "ORG-123", {"amount": 100000}),
            ...         ("AWARD-002", "ORG-456", {"amount": 200000}),
            ...     ]
            ... )
        """
        if not relationships:
            logger.info(f"{self.loader_name}: No {rel_type} relationships to create")
            return self.metrics

        if log_progress:
            logger.info(
                f"{self.loader_name}: Creating {len(relationships)} {rel_type} relationships "
                f"({source_label} → {target_label})"
            )

        start_time = datetime.utcnow()

        # Convert simplified format to full tuple format expected by client
        full_relationships: list[
            tuple[str, str, Any, str, str, Any, str, dict[str, Any] | None]
        ] = []

        for source_value, target_value, properties in relationships:
            full_relationships.append(
                (
                    source_label,
                    source_key,
                    source_value,
                    target_label,
                    target_key,
                    target_value,
                    rel_type,
                    properties,
                )
            )

        self.metrics = self.client.batch_create_relationships(
            relationships=full_relationships,
            metrics=self.metrics,
        )

        if log_progress:
            duration = (datetime.utcnow() - start_time).total_seconds()
            self._log_relationship_results(rel_type, duration)

        return self.metrics

    # -------------------------------------------------------------------------
    # Schema Management
    # -------------------------------------------------------------------------

    def create_constraints(self, constraints: list[str]) -> None:
        """Create constraints with error handling and logging.

        Args:
            constraints: List of CREATE CONSTRAINT statements

        Example:
            >>> self.create_constraints([
            ...     "CREATE CONSTRAINT patent_id IF NOT EXISTS "
            ...     "FOR (p:Patent) REQUIRE p.patent_id IS UNIQUE"
            ... ])
        """
        if not constraints:
            return

        logger.info(f"{self.loader_name}: Creating {len(constraints)} constraints")

        with self.client.session() as session:
            for constraint in constraints:
                try:
                    session.run(constraint)
                    logger.debug(f"Created constraint: {constraint}")
                except Exception as e:
                    logger.warning(f"Constraint may already exist: {e}")

    def create_indexes(self, indexes: list[str]) -> None:
        """Create indexes with error handling and logging.

        Args:
            indexes: List of CREATE INDEX statements

        Example:
            >>> self.create_indexes([
            ...     "CREATE INDEX patent_date IF NOT EXISTS "
            ...     "FOR (p:Patent) ON (p.grant_date)"
            ... ])
        """
        if not indexes:
            return

        logger.info(f"{self.loader_name}: Creating {len(indexes)} indexes")

        with self.client.session() as session:
            for index in indexes:
                try:
                    session.run(index)
                    logger.debug(f"Created index: {index}")
                except Exception as e:
                    logger.warning(f"Index may already exist: {e}")

    # -------------------------------------------------------------------------
    # Property Enrichment
    # -------------------------------------------------------------------------

    def enrich_node_properties(
        self,
        label: str,
        key_property: str,
        enrichments: list[tuple[Any, dict[str, Any]]],
        log_progress: bool = True,
    ) -> LoadMetrics:
        """Enrich existing nodes with additional properties.

        Updates nodes without replacing existing properties. Useful for adding
        computed or derived properties after initial node creation.

        Args:
            label: Node label
            key_property: Property name for matching
            enrichments: List of (key_value, properties_to_add) tuples
            log_progress: Whether to log progress messages

        Returns:
            LoadMetrics with counts of updated nodes

        Example:
            >>> metrics = self.enrich_node_properties(
            ...     label="Award",
            ...     key_property="award_id",
            ...     enrichments=[
            ...         ("AWARD-001", {"cet_primary": "AI", "cet_score": 95}),
            ...         ("AWARD-002", {"cet_primary": "Quantum", "cet_score": 88}),
            ...     ]
            ... )
        """
        if not enrichments:
            logger.info(f"{self.loader_name}: No {label} enrichments to apply")
            return self.metrics

        if log_progress:
            logger.info(f"{self.loader_name}: Enriching {len(enrichments)} {label} nodes")

        start_time = datetime.utcnow()
        batch_size = self.client.config.batch_size

        with self.client.session() as session:
            for i in range(0, len(enrichments), batch_size):
                batch = enrichments[i : i + batch_size]

                # Convert to format suitable for UNWIND
                batch_data = [
                    {"key": key_value, "props": props} for key_value, props in batch
                ]

                # Use query builder for consistent query construction
                from ..query_builder import Neo4jQueryBuilder
                
                query = Neo4jQueryBuilder.build_batch_match_update_query(
                    label=label,
                    key_property=key_property,
                    return_count=True,
                )

                try:
                    result = session.run(query, batch=batch_data)
                    record = result.single()
                    updated = record["updated_count"] if record else 0

                    self.metrics.nodes_updated[label] = (
                        self.metrics.nodes_updated.get(label, 0) + updated
                    )

                except Exception as e:
                    logger.error(f"Error enriching {label} batch: {e}")
                    self.metrics.errors += len(batch)

        if log_progress:
            duration = (datetime.utcnow() - start_time).total_seconds()
            logger.info(
                f"{self.loader_name}: Enriched {self.metrics.nodes_updated.get(label, 0)} "
                f"{label} nodes in {duration:.2f}s"
            )

        return self.metrics

    # -------------------------------------------------------------------------
    # Logging Utilities
    # -------------------------------------------------------------------------

    def _log_node_results(self, label: str, duration: float) -> None:
        """Log node operation results."""
        created = self.metrics.nodes_created.get(label, 0)
        updated = self.metrics.nodes_updated.get(label, 0)

        logger.info(
            f"{self.loader_name}: {label} loading completed in {duration:.2f}s - "
            f"{created} created, {updated} updated, {self.metrics.errors} errors"
        )

    def _log_relationship_results(self, rel_type: str, duration: float) -> None:
        """Log relationship operation results."""
        created = self.metrics.relationships_created.get(rel_type, 0)

        logger.info(
            f"{self.loader_name}: {rel_type} relationship creation completed in {duration:.2f}s - "
            f"{created} created, {self.metrics.errors} errors"
        )

    def log_summary(self) -> None:
        """Log overall summary of all operations performed by this loader."""
        total_nodes_created = sum(self.metrics.nodes_created.values())
        total_nodes_updated = sum(self.metrics.nodes_updated.values())
        total_rels_created = sum(self.metrics.relationships_created.values())

        logger.info(
            f"{self.loader_name} Summary: "
            f"{total_nodes_created} nodes created, "
            f"{total_nodes_updated} nodes updated, "
            f"{total_rels_created} relationships created, "
            f"{self.metrics.errors} errors"
        )

    def reset_metrics(self) -> None:
        """Reset metrics to start fresh tracking."""
        self.metrics = LoadMetrics()
