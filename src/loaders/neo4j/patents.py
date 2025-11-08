"""Patent Loader for Neo4j Graph Operations

This module provides the PatentLoader class for loading USPTO patent assignment data
into Neo4j. It implements a multi-phase loading strategy:

Phase 1: Load Patents and PatentAssignments
Phase 2: Load PatentEntity nodes (assignees and assignors)
Phase 3: Link assignments to entities (ASSIGNED_TO, ASSIGNED_FROM relationships)
Phase 4: SBIR integration (link to Company and Award nodes)
Phase 5: Compute metrics (assignment chains, entity statistics)

The loader is designed to work with transformed PatentAssignment models and uses
Neo4jClient for batch operations and transaction management.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import date
from typing import Any

from loguru import logger

from .client import LoadMetrics, Neo4jClient


@dataclass
class PatentLoaderConfig:
    """Configuration for patent loading operations."""

    batch_size: int = 1000
    create_indexes: bool = True
    create_constraints: bool = True
    link_to_sbir: bool = True


class PatentLoader:
    """Loads USPTO patent assignment data into Neo4j graph database.

    Implements a phased loading strategy for patents, assignments, entities,
    relationships, and SBIR integration.

    Attributes:
        client: Neo4jClient instance for graph operations
        config: PatentLoaderConfig with batch size and feature flags
    """

    def __init__(self, client: Neo4jClient, config: PatentLoaderConfig | None = None) -> None:
        """Initialize PatentLoader.

        Args:
            client: Neo4jClient instance for Neo4j operations
            config: Optional PatentLoaderConfig (uses defaults if not provided)
        """
        self.client = client
        self.config = config or PatentLoaderConfig()
        logger.info(
            f"PatentLoader initialized with batch_size={self.config.batch_size}, "
            f"create_indexes={self.config.create_indexes}, "
            f"create_constraints={self.config.create_constraints}"
        )

    def create_constraints(self) -> None:
        """Create unique constraints for patent entity primary keys."""
        constraints = [
            "CREATE CONSTRAINT patent_grant_doc_num IF NOT EXISTS "
            "FOR (p:Patent) REQUIRE p.grant_doc_num IS UNIQUE",
            "CREATE CONSTRAINT patent_assignment_rf_id IF NOT EXISTS "
            "FOR (a:PatentAssignment) REQUIRE a.rf_id IS UNIQUE",
            "CREATE CONSTRAINT patent_entity_id IF NOT EXISTS "
            "FOR (e:PatentEntity) REQUIRE e.entity_id IS UNIQUE",
        ]

        with self.client.session() as session:
            for constraint in constraints:
                try:
                    session.run(constraint)
                    logger.info(f"Created constraint: {constraint}")
                except Exception as e:
                    logger.warning(f"Constraint may already exist: {e}")

    def create_indexes(self) -> None:
        """Create indexes for frequently queried patent properties."""
        indexes = [
            # Tier 1: Essential indexes
            "CREATE INDEX patent_grant_doc_num_idx IF NOT EXISTS "
            "FOR (p:Patent) ON (p.grant_doc_num)",
            "CREATE INDEX patent_assignment_rf_id_idx IF NOT EXISTS "
            "FOR (a:PatentAssignment) ON (a.rf_id)",
            "CREATE INDEX patent_entity_normalized_name_idx IF NOT EXISTS "
            "FOR (e:PatentEntity) ON (e.normalized_name)",
            # Tier 2: High value indexes
            "CREATE INDEX patent_appno_date_idx IF NOT EXISTS " "FOR (p:Patent) ON (p.appno_date)",
            "CREATE INDEX patent_assignment_exec_date_idx IF NOT EXISTS "
            "FOR (a:PatentAssignment) ON (a.exec_date)",
            "CREATE INDEX patent_entity_type_idx IF NOT EXISTS "
            "FOR (e:PatentEntity) ON (e.entity_type)",
        ]

        with self.client.session() as session:
            for index in indexes:
                try:
                    session.run(index)
                    logger.info(f"Created index: {index}")
                except Exception as e:
                    logger.warning(f"Index may already exist: {e}")

    def load_patents(
        self, patents: list[dict[str, Any]], metrics: LoadMetrics | None = None
    ) -> LoadMetrics:
        """Load Patent nodes into Neo4j.

        Phase 1: Create Patent nodes from transformed patent documents.

        Args:
            patents: List of patent dictionaries with keys:
                - grant_doc_num (required, unique)
                - title
                - appno_date
                - grant_date
                - publication_date
                - filing_date
                - language
                - abstract
                - raw_metadata

            metrics: Optional LoadMetrics to accumulate results

        Returns:
            LoadMetrics with counts of created/updated Patent nodes
        """
        if metrics is None:
            metrics = LoadMetrics()

        if not patents:
            logger.info("No patents to load")
            return metrics

        logger.info(f"Loading {len(patents)} Patent nodes")
        start_time = time.time()

        # Extract and validate patent data
        patent_nodes = []
        for patent in patents:
            grant_doc_num = patent.get("grant_doc_num")
            if not grant_doc_num:
                logger.warning(f"Skipping patent with missing grant_doc_num: {patent}")
                metrics.errors += 1
                continue

            # Build node properties, converting dates to ISO format strings
            node_props = {
                "grant_doc_num": str(grant_doc_num).strip(),
                "title": patent.get("title"),
                "abstract": patent.get("abstract"),
                "language": patent.get("language", "en"),
            }

            # Add optional date fields (convert date objects to ISO strings)
            for date_field in ["appno_date", "grant_date", "publication_date", "filing_date"]:
                date_val = patent.get(date_field)
                if date_val:
                    if isinstance(date_val, date):
                        node_props[date_field] = date_val.isoformat()
                    else:
                        node_props[date_field] = date_val

            # Add metadata
            node_props["raw_metadata"] = str(patent.get("raw_metadata", {}))

            patent_nodes.append(node_props)

        # Use batch upsert to create/update Patent nodes
        metrics = self.client.batch_upsert_nodes(
            label="Patent",
            key_property="grant_doc_num",
            nodes=patent_nodes,
            metrics=metrics,
        )

        duration = time.time() - start_time
        logger.info(
            f"Patent loading completed in {duration:.2f}s: "
            f"{metrics.nodes_created.get('Patent', 0)} created, "
            f"{metrics.nodes_updated.get('Patent', 0)} updated"
        )

        return metrics

    def load_patent_assignments(
        self,
        assignments: list[dict[str, Any]],
        metrics: LoadMetrics | None = None,
    ) -> LoadMetrics:
        """Load PatentAssignment nodes into Neo4j.

        Phase 1: Create PatentAssignment nodes with temporal and conveyance metadata.

        Args:
            assignments: List of assignment dictionaries with keys:
                - rf_id (required, unique)
                - file_id
                - execution_date
                - recorded_date
                - conveyance_type
                - conveyance_description
                - employer_assign
                - grant_doc_num (links to Patent)

            metrics: Optional LoadMetrics to accumulate results

        Returns:
            LoadMetrics with counts of created/updated PatentAssignment nodes
        """
        if metrics is None:
            metrics = LoadMetrics()

        if not assignments:
            logger.info("No assignments to load")
            return metrics

        logger.info(f"Loading {len(assignments)} PatentAssignment nodes")
        start_time = time.time()

        # Extract and validate assignment data
        assignment_nodes = []
        for assignment in assignments:
            rf_id = assignment.get("rf_id")
            if not rf_id:
                logger.warning(f"Skipping assignment with missing rf_id: {assignment}")
                metrics.errors += 1
                continue

            # Build node properties
            node_props = {
                "rf_id": str(rf_id).strip(),
                "file_id": assignment.get("file_id"),
                "conveyance_type": assignment.get("conveyance_type", "assignment"),
                "conveyance_description": assignment.get("conveyance_description"),
                "employer_assign": bool(assignment.get("employer_assign", False)),
                "grant_doc_num": assignment.get("grant_doc_num"),
            }

            # Add temporal properties (convert date objects to ISO strings)
            for date_field in ["execution_date", "recorded_date"]:
                date_val = assignment.get(date_field)
                if date_val:
                    if isinstance(date_val, date):
                        node_props[date_field] = date_val.isoformat()
                    else:
                        node_props[date_field] = date_val

            assignment_nodes.append(node_props)

        # Use batch upsert to create/update PatentAssignment nodes
        metrics = self.client.batch_upsert_nodes(
            label="PatentAssignment",
            key_property="rf_id",
            nodes=assignment_nodes,
            metrics=metrics,
        )

        duration = time.time() - start_time
        logger.info(
            f"PatentAssignment loading completed in {duration:.2f}s: "
            f"{metrics.nodes_created.get('PatentAssignment', 0)} created, "
            f"{metrics.nodes_updated.get('PatentAssignment', 0)} updated"
        )

        return metrics

    def load_patent_entities(
        self,
        entities: list[dict[str, Any]],
        entity_type: str,
        metrics: LoadMetrics | None = None,
    ) -> LoadMetrics:
        """Load PatentEntity nodes (assignees and assignors) into Neo4j.

        Phase 2: Create PatentEntity nodes with address and identifier information.

        Args:
            entities: List of entity dictionaries with keys:
                - entity_id (required, unique)
                - name (required)
                - normalized_name
                - street
                - city
                - state
                - postal_code
                - country
                - uei
                - cage
                - duns
                - entity_type (ASSIGNEE or ASSIGNOR)

            entity_type: Type of entity (ASSIGNEE or ASSIGNOR) for filtering

            metrics: Optional LoadMetrics to accumulate results

        Returns:
            LoadMetrics with counts of created/updated PatentEntity nodes
        """
        if metrics is None:
            metrics = LoadMetrics()

        if not entities:
            logger.info(f"No {entity_type} entities to load")
            return metrics

        logger.info(f"Loading {len(entities)} PatentEntity nodes (type={entity_type})")
        start_time = time.time()

        # Extract and validate entity data
        entity_nodes = []
        for entity in entities:
            entity_id = entity.get("entity_id")
            name = entity.get("name")

            if not entity_id or not name:
                logger.warning(f"Skipping entity with missing entity_id or name: {entity}")
                metrics.errors += 1
                continue

            # Build node properties
            node_props = {
                "entity_id": str(entity_id).strip(),
                "name": str(name).strip(),
                "normalized_name": entity.get("normalized_name"),
                "entity_type": entity_type,
                "street": entity.get("street"),
                "city": entity.get("city"),
                "state": entity.get("state"),
                "postal_code": entity.get("postal_code"),
                "country": entity.get("country"),
                "uei": entity.get("uei"),
                "cage": entity.get("cage"),
                "duns": entity.get("duns"),
            }

            # Remove None values to keep Neo4j clean
            node_props = {k: v for k, v in node_props.items() if v is not None}

            entity_nodes.append(node_props)

        # Use batch upsert to create/update PatentEntity nodes
        metrics = self.client.batch_upsert_nodes(
            label="PatentEntity",
            key_property="entity_id",
            nodes=entity_nodes,
            metrics=metrics,
        )

        duration = time.time() - start_time
        logger.info(
            f"PatentEntity loading ({entity_type}) completed in {duration:.2f}s: "
            f"{metrics.nodes_created.get('PatentEntity', 0)} created, "
            f"{metrics.nodes_updated.get('PatentEntity', 0)} updated"
        )

        return metrics

    def create_assigned_via_relationships(
        self,
        assignments: list[dict[str, str]],
        metrics: LoadMetrics | None = None,
    ) -> LoadMetrics:
        """Create ASSIGNED_VIA relationships between Patents and PatentAssignments.

        Phase 1: Link Patent nodes to PatentAssignment nodes via ASSIGNED_VIA.

        Args:
            assignments: List of assignments with:
                - grant_doc_num: Patent key
                - rf_id: PatentAssignment key

            metrics: Optional LoadMetrics to accumulate results

        Returns:
            LoadMetrics with counts of created relationships
        """
        if metrics is None:
            metrics = LoadMetrics()

        if not assignments:
            logger.info("No ASSIGNED_VIA relationships to create")
            return metrics

        logger.info(f"Creating {len(assignments)} ASSIGNED_VIA relationships")
        start_time = time.time()

        relationships = []
        for assignment in assignments:
            grant_doc_num = assignment.get("grant_doc_num")
            rf_id = assignment.get("rf_id")

            if not grant_doc_num or not rf_id:
                logger.warning(
                    f"Skipping ASSIGNED_VIA relationship with missing keys: {assignment}"
                )
                metrics.errors += 1
                continue

            # Relationship tuple format for batch_create_relationships:
            # (source_label, source_key, source_value,
            #  target_label, target_key, target_value,
            #  rel_type, properties)
            relationships.append(
                (
                    "Patent",
                    "grant_doc_num",
                    str(grant_doc_num).strip(),
                    "PatentAssignment",
                    "rf_id",
                    str(rf_id).strip(),
                    "ASSIGNED_VIA",
                    {},
                )
            )

        metrics = self.client.batch_create_relationships(
            relationships=relationships, metrics=metrics
        )

        duration = time.time() - start_time
        logger.info(
            f"ASSIGNED_VIA relationship creation completed in {duration:.2f}s: "
            f"{metrics.relationships_created.get('ASSIGNED_VIA', 0)} created"
        )

        return metrics

    def create_assigned_from_relationships(
        self,
        assignments: list[dict[str, str]],
        metrics: LoadMetrics | None = None,
    ) -> LoadMetrics:
        """Create ASSIGNED_FROM relationships (PatentAssignment → PatentEntity).

        Phase 3: Link PatentAssignment nodes to PatentEntity (assignor) nodes.

        Args:
            assignments: List of assignments with:
                - rf_id: PatentAssignment key
                - assignor_entity_id: PatentEntity key for assignor
                - execution_date (optional): date of assignment

            metrics: Optional LoadMetrics to accumulate results

        Returns:
            LoadMetrics with counts of created relationships
        """
        if metrics is None:
            metrics = LoadMetrics()

        if not assignments:
            logger.info("No ASSIGNED_FROM relationships to create")
            return metrics

        logger.info(f"Creating {len(assignments)} ASSIGNED_FROM relationships")
        start_time = time.time()

        relationships = []
        for assignment in assignments:
            rf_id = assignment.get("rf_id")
            assignor_entity_id = assignment.get("assignor_entity_id")

            if not rf_id or not assignor_entity_id:
                logger.warning(
                    f"Skipping ASSIGNED_FROM relationship with missing keys: {assignment}"
                )
                metrics.errors += 1
                continue

            # Build relationship properties
            rel_props = {}
            if assignment.get("execution_date"):
                rel_props["execution_date"] = (
                    assignment["execution_date"].isoformat()
                    if isinstance(assignment["execution_date"], date)
                    else assignment["execution_date"]
                )

            relationships.append(
                (
                    "PatentAssignment",
                    "rf_id",
                    str(rf_id).strip(),
                    "PatentEntity",
                    "entity_id",
                    str(assignor_entity_id).strip(),
                    "ASSIGNED_FROM",
                    rel_props,
                )
            )

        metrics = self.client.batch_create_relationships(
            relationships=relationships, metrics=metrics
        )

        duration = time.time() - start_time
        logger.info(
            f"ASSIGNED_FROM relationship creation completed in {duration:.2f}s: "
            f"{metrics.relationships_created.get('ASSIGNED_FROM', 0)} created"
        )

        return metrics

    def create_assigned_to_relationships(
        self,
        assignments: list[dict[str, str]],
        metrics: LoadMetrics | None = None,
    ) -> LoadMetrics:
        """Create ASSIGNED_TO relationships (PatentAssignment → PatentEntity).

        Phase 3: Link PatentAssignment nodes to PatentEntity (assignee) nodes.

        Args:
            assignments: List of assignments with:
                - rf_id: PatentAssignment key
                - assignee_entity_id: PatentEntity key for assignee
                - recorded_date (optional): date of recording

            metrics: Optional LoadMetrics to accumulate results

        Returns:
            LoadMetrics with counts of created relationships
        """
        if metrics is None:
            metrics = LoadMetrics()

        if not assignments:
            logger.info("No ASSIGNED_TO relationships to create")
            return metrics

        logger.info(f"Creating {len(assignments)} ASSIGNED_TO relationships")
        start_time = time.time()

        relationships = []
        for assignment in assignments:
            rf_id = assignment.get("rf_id")
            assignee_entity_id = assignment.get("assignee_entity_id")

            if not rf_id or not assignee_entity_id:
                logger.warning(f"Skipping ASSIGNED_TO relationship with missing keys: {assignment}")
                metrics.errors += 1
                continue

            # Build relationship properties with temporal data
            rel_props = {}
            if assignment.get("recorded_date"):
                rel_props["recorded_date"] = (
                    assignment["recorded_date"].isoformat()
                    if isinstance(assignment["recorded_date"], date)
                    else assignment["recorded_date"]
                )

            relationships.append(
                (
                    "PatentAssignment",
                    "rf_id",
                    str(rf_id).strip(),
                    "PatentEntity",
                    "entity_id",
                    str(assignee_entity_id).strip(),
                    "ASSIGNED_TO",
                    rel_props,
                )
            )

        metrics = self.client.batch_create_relationships(
            relationships=relationships, metrics=metrics
        )

        duration = time.time() - start_time
        logger.info(
            f"ASSIGNED_TO relationship creation completed in {duration:.2f}s: "
            f"{metrics.relationships_created.get('ASSIGNED_TO', 0)} created"
        )

        return metrics

    def create_generated_from_relationships(
        self,
        patent_awards: list[dict[str, str]],
        metrics: LoadMetrics | None = None,
    ) -> LoadMetrics:
        """Create GENERATED_FROM relationships (Patent → Award).

        Phase 4: Link Patent nodes to Award nodes for SBIR-funded patents.

        Args:
            patent_awards: List of patent-award pairs with:
                - grant_doc_num: Patent key
                - award_id: Award key

            metrics: Optional LoadMetrics to accumulate results

        Returns:
            LoadMetrics with counts of created relationships
        """
        if metrics is None:
            metrics = LoadMetrics()

        if not patent_awards:
            logger.info("No GENERATED_FROM relationships to create")
            return metrics

        logger.info(f"Creating {len(patent_awards)} GENERATED_FROM relationships")
        start_time = time.time()

        relationships = []
        for pair in patent_awards:
            grant_doc_num = pair.get("grant_doc_num")
            award_id = pair.get("award_id")

            if not grant_doc_num or not award_id:
                logger.warning(f"Skipping GENERATED_FROM relationship with missing keys: {pair}")
                metrics.errors += 1
                continue

            relationships.append(
                (
                    "Patent",
                    "grant_doc_num",
                    str(grant_doc_num).strip(),
                    "Award",
                    "award_id",
                    str(award_id).strip(),
                    "GENERATED_FROM",
                    {},
                )
            )

        metrics = self.client.batch_create_relationships(
            relationships=relationships, metrics=metrics
        )

        duration = time.time() - start_time
        logger.info(
            f"GENERATED_FROM relationship creation completed in {duration:.2f}s: "
            f"{metrics.relationships_created.get('GENERATED_FROM', 0)} created"
        )

        return metrics

    def create_owns_relationships(
        self,
        company_patents: list[dict[str, str]],
        metrics: LoadMetrics | None = None,
    ) -> LoadMetrics:
        """Create OWNS relationships (Company → Patent).

        Phase 4: Link Company nodes to Patent nodes for current ownership.

        Args:
            company_patents: List of company-patent pairs with:
                - uei: Company key
                - grant_doc_num: Patent key

            metrics: Optional LoadMetrics to accumulate results

        Returns:
            LoadMetrics with counts of created relationships
        """
        if metrics is None:
            metrics = LoadMetrics()

        if not company_patents:
            logger.info("No OWNS relationships to create")
            return metrics

        logger.info(f"Creating {len(company_patents)} OWNS relationships")
        start_time = time.time()

        relationships = []
        for pair in company_patents:
            uei = pair.get("uei")
            grant_doc_num = pair.get("grant_doc_num")

            if not uei or not grant_doc_num:
                logger.warning(f"Skipping OWNS relationship with missing keys: {pair}")
                metrics.errors += 1
                continue

            relationships.append(
                (
                    "Company",
                    "uei",
                    str(uei).strip(),
                    "Patent",
                    "grant_doc_num",
                    str(grant_doc_num).strip(),
                    "OWNS",
                    {},
                )
            )

        metrics = self.client.batch_create_relationships(
            relationships=relationships, metrics=metrics
        )

        duration = time.time() - start_time
        logger.info(
            f"OWNS relationship creation completed in {duration:.2f}s: "
            f"{metrics.relationships_created.get('OWNS', 0)} created"
        )

        return metrics

    def create_chain_of_relationships(
        self,
        assignment_chains: list[dict[str, str]],
        metrics: LoadMetrics | None = None,
    ) -> LoadMetrics:
        """Create CHAIN_OF relationships between sequential assignments.

        Phase 5: Link PatentAssignment nodes to form ownership chains.

        Args:
            assignment_chains: List of assignment-pair records with:
                - current_rf_id: PatentAssignment key (later in time)
                - previous_rf_id: PatentAssignment key (earlier in time)

            metrics: Optional LoadMetrics to accumulate results

        Returns:
            LoadMetrics with counts of created relationships
        """
        if metrics is None:
            metrics = LoadMetrics()

        if not assignment_chains:
            logger.info("No CHAIN_OF relationships to create")
            return metrics

        logger.info(f"Creating {len(assignment_chains)} CHAIN_OF relationships")
        start_time = time.time()

        relationships = []
        for chain in assignment_chains:
            current_rf_id = chain.get("current_rf_id")
            previous_rf_id = chain.get("previous_rf_id")

            if not current_rf_id or not previous_rf_id:
                logger.warning(f"Skipping CHAIN_OF relationship with missing keys: {chain}")
                metrics.errors += 1
                continue

            relationships.append(
                (
                    "PatentAssignment",
                    "rf_id",
                    str(current_rf_id).strip(),
                    "PatentAssignment",
                    "rf_id",
                    str(previous_rf_id).strip(),
                    "CHAIN_OF",
                    {},
                )
            )

        metrics = self.client.batch_create_relationships(
            relationships=relationships, metrics=metrics
        )

        duration = time.time() - start_time
        logger.info(
            f"CHAIN_OF relationship creation completed in {duration:.2f}s: "
            f"{metrics.relationships_created.get('CHAIN_OF', 0)} created"
        )

        return metrics


__all__ = ["PatentLoader", "PatentLoaderConfig"]
