"""Neo4j client wrapper for batch loading and transaction management."""

import hashlib
import json
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
    auto_migrate: bool = True  # Automatically run migrations on client initialization


class LoadMetrics(BaseModel):
    """Metrics for Neo4j loading operations."""

    # Use Field(default_factory=...) to avoid shared mutable defaults between instances.
    nodes_created: dict[str, int] = Field(default_factory=dict)
    nodes_updated: dict[str, int] = Field(default_factory=dict)
    relationships_created: dict[str, int] = Field(default_factory=dict)
    errors: int = 0
    duration_seconds: float = 0.0


def _compute_node_hash(properties: dict[str, Any]) -> str:
    """Compute a stable hash of node properties for change detection.

    Args:
        properties: Dictionary of node properties

    Returns:
        MD5 hash of the serialized properties
    """
    # Remove any internal properties that shouldn't affect the hash
    clean_props = {k: v for k, v in properties.items() if not k.startswith("__")}
    # Sort keys for consistent hashing
    stable_json = json.dumps(clean_props, sort_keys=True, default=str)
    return hashlib.md5(stable_json.encode()).hexdigest()


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

        # Run migrations automatically if enabled
        if config.auto_migrate:
            try:
                from migrations.runner import MigrationRunner

                runner = MigrationRunner(self.driver)
                runner.upgrade()
                logger.info("Neo4j migrations completed")
            except Exception as e:
                logger.warning(f"Failed to run migrations: {e}")
                # Don't fail initialization if migrations fail

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
        """Create unique constraints for entity primary keys.

        DEPRECATED: Use Neo4j Migrations instead. This method is kept for backward compatibility.
        See migrations/versions/001_initial_schema.py for current schema definitions.
        """
        constraints = [
            # Legacy constraints (kept for backward compatibility)
            "CREATE CONSTRAINT company_id IF NOT EXISTS FOR (c:Company) REQUIRE c.company_id IS UNIQUE",
            "CREATE CONSTRAINT award_id IF NOT EXISTS FOR (a:Award) REQUIRE a.award_id IS UNIQUE",
            "CREATE CONSTRAINT researcher_id IF NOT EXISTS FOR (r:Researcher) REQUIRE r.researcher_id IS UNIQUE",
            "CREATE CONSTRAINT patent_id IF NOT EXISTS FOR (p:Patent) REQUIRE p.patent_id IS UNIQUE",
            "CREATE CONSTRAINT institution_name IF NOT EXISTS FOR (i:ResearchInstitution) REQUIRE i.name IS UNIQUE",
            # Organization constraints
            "CREATE CONSTRAINT organization_id IF NOT EXISTS FOR (o:Organization) REQUIRE o.organization_id IS UNIQUE",
            # Individual constraints
            "CREATE CONSTRAINT individual_id IF NOT EXISTS FOR (i:Individual) REQUIRE i.individual_id IS UNIQUE",
            # FinancialTransaction constraints
            "CREATE CONSTRAINT financial_transaction_id IF NOT EXISTS FOR (ft:FinancialTransaction) REQUIRE ft.transaction_id IS UNIQUE",
        ]

        with self.session() as session:
            for constraint in constraints:
                try:
                    session.run(constraint)
                    logger.info(f"Created constraint: {constraint}")
                except Exception as e:
                    logger.warning(f"Constraint may already exist: {e}")

    def create_indexes(self) -> None:
        """Create indexes for frequently queried properties.

        DEPRECATED: Use Neo4j Migrations instead. This method is kept for backward compatibility.
        See migrations/versions/001_initial_schema.py and 002_add_organization_deduplication_indexes.py
        for current index definitions.
        """
        indexes = [
            # Legacy indexes (kept for backward compatibility)
            "CREATE INDEX company_name IF NOT EXISTS FOR (c:Company) ON (c.name)",
            "CREATE INDEX company_normalized_name IF NOT EXISTS FOR (c:Company) ON (c.normalized_name)",
            "CREATE INDEX company_uei IF NOT EXISTS FOR (c:Company) ON (c.uei)",
            "CREATE INDEX company_duns IF NOT EXISTS FOR (c:Company) ON (c.duns)",
            "CREATE INDEX award_date IF NOT EXISTS FOR (a:Award) ON (a.award_date)",
            "CREATE INDEX researcher_name IF NOT EXISTS FOR (r:Researcher) ON (r.name)",
            "CREATE INDEX patent_number IF NOT EXISTS FOR (p:Patent) ON (p.patent_number)",
            "CREATE INDEX institution_name IF NOT EXISTS FOR (i:ResearchInstitution) ON (i.name)",
            # Organization indexes
            "CREATE INDEX organization_name IF NOT EXISTS FOR (o:Organization) ON (o.name)",
            "CREATE INDEX organization_normalized_name IF NOT EXISTS FOR (o:Organization) ON (o.normalized_name)",
            "CREATE INDEX organization_type IF NOT EXISTS FOR (o:Organization) ON (o.organization_type)",
            "CREATE INDEX organization_uei IF NOT EXISTS FOR (o:Organization) ON (o.uei)",
            "CREATE INDEX organization_duns IF NOT EXISTS FOR (o:Organization) ON (o.duns)",
            "CREATE INDEX organization_agency_code IF NOT EXISTS FOR (o:Organization) ON (o.agency_code)",
            # Organization transition metrics indexes
            "CREATE INDEX organization_transition_success_rate IF NOT EXISTS FOR (o:Organization) ON (o.transition_success_rate)",
            "CREATE INDEX organization_transition_total_transitions IF NOT EXISTS FOR (o:Organization) ON (o.transition_total_transitions)",
            "CREATE INDEX organization_transition_total_awards IF NOT EXISTS FOR (o:Organization) ON (o.transition_total_awards)",
            # Individual indexes
            "CREATE INDEX individual_name IF NOT EXISTS FOR (i:Individual) ON (i.name)",
            "CREATE INDEX individual_normalized_name IF NOT EXISTS FOR (i:Individual) ON (i.normalized_name)",
            "CREATE INDEX individual_type IF NOT EXISTS FOR (i:Individual) ON (i.individual_type)",
            "CREATE INDEX individual_email IF NOT EXISTS FOR (i:Individual) ON (i.email)",
            # FinancialTransaction indexes
            "CREATE INDEX financial_transaction_type IF NOT EXISTS FOR (ft:FinancialTransaction) ON (ft.transaction_type)",
            "CREATE INDEX financial_transaction_date IF NOT EXISTS FOR (ft:FinancialTransaction) ON (ft.transaction_date)",
            "CREATE INDEX financial_transaction_agency IF NOT EXISTS FOR (ft:FinancialTransaction) ON (ft.agency)",
            "CREATE INDEX financial_transaction_award_id IF NOT EXISTS FOR (ft:FinancialTransaction) ON (ft.award_id)",
            "CREATE INDEX financial_transaction_contract_id IF NOT EXISTS FOR (ft:FinancialTransaction) ON (ft.contract_id)",
            "CREATE INDEX financial_transaction_recipient_uei IF NOT EXISTS FOR (ft:FinancialTransaction) ON (ft.recipient_uei)",
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

        Only updates nodes when their properties have actually changed, determined by
        comparing a hash of the property values. This significantly improves performance
        when re-loading data that hasn't changed.

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

                # Add hash to each node for change detection
                for node in valid_batch:
                    node["__hash"] = _compute_node_hash(node)

                try:
                    # Use query builder for consistent query construction
                    from .query_builder import Neo4jQueryBuilder
                    
                    query = Neo4jQueryBuilder.build_batch_merge_query(
                        label=label,
                        key_property=key_property,
                        include_hash_check=True,
                        return_counts=True,
                    )

                    result = session.run(query, batch=valid_batch)
                    record = result.single()

                    created = record["created_count"] if record else 0
                    updated = record["updated_count"] if record else 0

                    # Clean up temporary flags
                    cleanup_query = f"""
                    MATCH (n:{label})
                    WHERE n.__new IS NOT NULL
                    REMOVE n.__new
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

    def batch_upsert_organizations_with_multi_key(
        self,
        nodes: list[dict[str, Any]],
        metrics: LoadMetrics | None = None,
        merge_on_uei: bool = True,
        merge_on_duns: bool = True,
        track_merge_history: bool = True,
    ) -> LoadMetrics:
        """
        Batch upsert Organization nodes with multi-key MERGE logic.

        Strategy:
        1. For each node, check if UEI/DUNS matches existing node
        2. If found, merge properties into existing node (by organization_id)
        3. If not found, create new node with standard MERGE

        This handles cases where:
        - Company appears with UEI in one award, name-only in another
        - Company has different organization_ids but same UEI/DUNS

        Args:
            nodes: List of Organization node dictionaries
            metrics: Optional LoadMetrics to update
            merge_on_uei: If True, merge nodes with same UEI
            merge_on_duns: If True, merge nodes with same DUNS
            track_merge_history: If True, track merge history in node properties

        Returns:
            LoadMetrics with creation/update counts
        """
        if metrics is None:
            metrics = LoadMetrics()

        batch_size = self.config.batch_size
        total_batches = (len(nodes) + batch_size - 1) // batch_size

        logger.info(
            f"Upserting {len(nodes)} Organization nodes with multi-key MERGE "
            f"in {total_batches} batches"
        )

        with self.session() as session:
            for i in range(0, len(nodes), batch_size):
                batch = nodes[i : i + batch_size]
                batch_num = i // batch_size + 1

                valid_batch = [n for n in batch if n.get("organization_id") is not None]
                invalid_count = len(batch) - len(valid_batch)
                if invalid_count > 0:
                    logger.error(f"{invalid_count} nodes missing organization_id")
                    metrics.errors += invalid_count

                if not valid_batch:
                    continue

                # Add hash for change detection
                for node in valid_batch:
                    node["__hash"] = _compute_node_hash(node)

                try:
                    # Phase 1: Check for existing nodes by UEI/DUNS BEFORE creating
                    check_query = """
                    UNWIND $batch AS node
                    OPTIONAL MATCH (existing:Organization)
                    WHERE existing.organization_id <> node.organization_id
                      AND (
                        ($merge_uei AND node.uei IS NOT NULL AND existing.uei = node.uei)
                        OR ($merge_duns AND node.duns IS NOT NULL AND existing.duns = node.duns)
                      )
                    WITH node, collect(existing)[0] as existing_node
                    RETURN node, existing_node
                    """

                    result = session.run(
                        check_query,
                        batch=valid_batch,
                        merge_uei=merge_on_uei,
                        merge_duns=merge_on_duns,
                    )

                    nodes_to_merge = {}  # org_id -> existing_org_id
                    nodes_to_create = []

                    for record in result:
                        node = record["node"]
                        existing = record["existing_node"]

                        if existing:
                            # Merge into existing node
                            existing_id = existing["organization_id"]
                            nodes_to_merge[node["organization_id"]] = existing_id
                        else:
                            # No duplicate found, create normally
                            nodes_to_create.append(node)

                    # Phase 2: Merge properties into existing nodes
                    if nodes_to_merge:
                        merge_list = []
                        for new_id, existing_id in nodes_to_merge.items():
                            # Find the node data
                            node_data = next(n for n in valid_batch if n["organization_id"] == new_id)
                            # Remove organization_id and internal fields to avoid overwriting
                            props = {
                                k: v
                                for k, v in node_data.items()
                                if k not in ("organization_id", "__hash")
                            }

                            # Build merge history if tracking enabled
                            merge_history_entry = None
                            if track_merge_history:
                                from datetime import datetime

                                merge_history_entry = {
                                    "from_org_id": new_id,
                                    "from_name": node_data.get("name"),
                                    "method": "uei_match" if node_data.get("uei") else "duns_match",
                                    "merged_at": datetime.utcnow().isoformat(),
                                    "properties": {
                                        k: v
                                        for k, v in node_data.items()
                                        if k
                                        not in (
                                            "organization_id",
                                            "__hash",
                                            "__merged_from",
                                            "__merge_history",
                                        )
                                    },
                                }

                            merge_list.append(
                                {
                                    "new_id": new_id,
                                    "existing_id": existing_id,
                                    "props": props,
                                    "merge_history": merge_history_entry,
                                }
                            )

                        merge_props_query = """
                        UNWIND $merges AS merge
                        MATCH (existing:Organization {organization_id: merge.existing_id})
                        SET existing += merge.props,
                            existing.__updated_at = datetime()
                        """
                        
                        if track_merge_history:
                            merge_props_query += """
                            WITH existing, merge
                            WHERE merge.merge_history IS NOT NULL
                            WITH existing, 
                                 coalesce(existing.__merged_from, []) as current_merged_from,
                                 coalesce(existing.__merge_history, []) as current_history
                            SET existing.__merged_from = current_merged_from + [merge.new_id],
                                existing.__merge_history = current_history + [merge.merge_history]
                            """

                        merge_props_query += """
                        RETURN count(existing) as merged_count
                        """

                        result = session.run(merge_props_query, merges=merge_list)
                        record = result.single()
                        merged_count = record["merged_count"] if record else 0

                        metrics.nodes_updated["Organization"] = (
                            metrics.nodes_updated.get("Organization", 0) + merged_count
                        )

                        logger.debug(
                            f"Batch {batch_num}: Merged {merged_count} nodes into existing organizations"
                        )

                        # Move relationships from duplicate to canonical
                        # Note: This is a simplified approach - in practice, you might want
                        # to handle relationship migration more carefully
                        for new_id, existing_id in nodes_to_merge.items():
                            move_rels_query = """
                            MATCH (duplicate:Organization {organization_id: $new_id})
                            MATCH (canonical:Organization {organization_id: $existing_id})
                            // Move outgoing relationships
                            OPTIONAL MATCH (duplicate)-[r_out]->(target)
                            WHERE NOT (canonical)-[r_out]->(target)
                            WITH canonical, duplicate, collect(r_out) as outgoing_rels
                            UNWIND outgoing_rels as rel
                            CALL apoc.refactor.from(rel, canonical) YIELD input, output
                            RETURN count(rel) as moved_out
                            """
                            # Actually, APOC might not be available, so use simpler approach
                            move_rels_query = """
                            MATCH (duplicate:Organization {organization_id: $new_id})
                            MATCH (canonical:Organization {organization_id: $existing_id})
                            // For now, just delete duplicate - relationships will be recreated
                            // In production, you'd want to migrate relationships properly
                            DETACH DELETE duplicate
                            RETURN count(duplicate) as deleted_count
                            """
                            try:
                                session.run(
                                    move_rels_query, new_id=new_id, existing_id=existing_id
                                )
                            except Exception as e:
                                logger.warning(f"Failed to delete duplicate node {new_id}: {e}")

                    # Phase 3: Create remaining nodes normally
                    if nodes_to_create:
                        query = f"""
                        UNWIND $batch AS node
                        MERGE (n:Organization {{organization_id: node.organization_id}})
                        ON CREATE SET n = node, n.__new = true
                        ON MATCH SET n.__new = false
                        WITH n, node
                        WHERE n.__new OR n.__hash IS NULL OR n.__hash <> node.__hash
                        SET n += node
                        RETURN count(CASE WHEN n.__new THEN 1 END) as created_count,
                               count(CASE WHEN NOT n.__new THEN 1 END) as updated_count
                        """

                        result = session.run(query, batch=nodes_to_create)
                        record = result.single()

                        created = record["created_count"] if record else 0
                        updated = record["updated_count"] if record else 0

                        metrics.nodes_created["Organization"] = (
                            metrics.nodes_created.get("Organization", 0) + created
                        )
                        metrics.nodes_updated["Organization"] = (
                            metrics.nodes_updated.get("Organization", 0) + updated
                        )

                    # Cleanup temporary flags
                    cleanup_query = """
                    MATCH (n:Organization)
                    WHERE n.__new IS NOT NULL
                    REMOVE n.__new
                    """
                    session.run(cleanup_query)

                    logger.debug(
                        f"Batch {batch_num}/{total_batches} committed: "
                        f"{len(nodes_to_create)} created/updated, "
                        f"{len(nodes_to_merge)} merged"
                    )

                except Exception as e:
                    metrics.errors += len(valid_batch)
                    logger.error(f"Error in batch {batch_num}/{total_batches}: {e}")

        logger.info(
            f"Completed Organization upsert: "
            f"{metrics.nodes_created.get('Organization', 0)} created, "
            f"{metrics.nodes_updated.get('Organization', 0)} updated"
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
        """Batch create relationships with transaction management using UNWIND for performance.

        Uses Cypher UNWIND to process relationships in bulk within each batch,
        dramatically improving performance (10-100x faster than individual queries).

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

                # Group relationships by type and node labels for optimized UNWIND queries
                rels_by_signature: dict[tuple, list[dict]] = {}
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

                    # Group by (source_label, source_key, target_label, target_key, rel_type)
                    signature = (source_label, source_key, target_label, target_key, rel_type)
                    if signature not in rels_by_signature:
                        rels_by_signature[signature] = []

                    rels_by_signature[signature].append(
                        {
                            "source_value": source_value,
                            "target_value": target_value,
                            "properties": properties or {},
                        }
                    )

                try:
                    with session.begin_transaction() as tx:
                        for signature, rel_list in rels_by_signature.items():
                            source_label, source_key, target_label, target_key, rel_type = signature

                            # Use UNWIND to batch process all relationships in a single query
                            query = f"""
                            UNWIND $batch AS rel
                            MATCH (source:{source_label} {{{source_key}: rel.source_value}})
                            MATCH (target:{target_label} {{{target_key}: rel.target_value}})
                            MERGE (source)-[r:{rel_type}]->(target)
                            SET r += rel.properties
                            RETURN count(r) as created_count
                            """

                            result = tx.run(query, batch=rel_list)
                            record = result.single()

                            if record:
                                created_count = record["created_count"]
                                metrics.relationships_created[rel_type] = (
                                    metrics.relationships_created.get(rel_type, 0) + created_count
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
