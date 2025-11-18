"""Neo4j query builder utilities for common patterns.

This module provides utilities for constructing common Neo4j Cypher queries,
reducing duplication across loaders and standardizing query patterns.
"""

from typing import Any


class Neo4jQueryBuilder:
    """Builder for common Neo4j Cypher query patterns."""

    @staticmethod
    def build_batch_merge_query(
        label: str,
        key_property: str,
        include_hash_check: bool = False,
        return_counts: bool = True,
    ) -> str:
        """Build a batch MERGE query using UNWIND.
        
        Args:
            label: Node label (e.g., "Company", "Award")
            key_property: Property name for matching (e.g., "uei", "award_id")
            include_hash_check: If True, only update nodes when hash changes
            return_counts: If True, return created_count and updated_count
            
        Returns:
            Cypher query string using UNWIND $batch pattern
        """
        if include_hash_check:
            # Query with hash-based change detection
            query = f"""
            UNWIND $batch AS node
            MERGE (n:{label} {{{key_property}: node.{key_property}}})
            ON CREATE SET n = node, n.__new = true
            ON MATCH SET n.__new = false
            WITH n, node,
                CASE WHEN NOT n.__new AND (n.__hash IS NULL OR n.__hash <> node.__hash)
                     THEN true ELSE false END AS needs_update
            FOREACH (x IN CASE WHEN needs_update THEN [1] ELSE [] END |
                SET n += node
            )
            """
            if return_counts:
                query += """
            RETURN count(CASE WHEN n.__new THEN 1 END) as created_count,
                   count(CASE WHEN needs_update THEN 1 END) as updated_count
            """
            else:
                query += "RETURN count(n) as total_count"
        else:
            # Simple MERGE without hash checking
            query = f"""
            UNWIND $batch AS node
            MERGE (n:{label} {{{key_property}: node.{key_property}}})
            SET n += node
            """
            if return_counts:
                query += "RETURN count(n) as updated_count"
            else:
                query += "RETURN count(n) as total_count"
        
        return query.strip()

    @staticmethod
    def build_batch_match_update_query(
        label: str,
        key_property: str,
        return_count: bool = True,
    ) -> str:
        """Build a batch MATCH + SET query (only updates existing nodes).
        
        Args:
            label: Node label
            key_property: Property name for matching
            return_count: If True, return updated_count
            
        Returns:
            Cypher query string
        """
        query = f"""
        UNWIND $batch AS item
        MATCH (n:{label} {{{key_property}: item.key}})
        SET n += item.props
        """
        if return_count:
            query += "RETURN count(n) as updated_count"
        else:
            query += "RETURN count(n) as total_count"
        
        return query.strip()

    @staticmethod
    def build_relationship_merge_query(
        source_label: str,
        source_key: str,
        rel_type: str,
        target_label: str,
        target_key: str,
        rel_properties: dict[str, Any] | None = None,
    ) -> str:
        """Build a relationship MERGE query.
        
        Args:
            source_label: Source node label
            source_key: Source node key property name
            rel_type: Relationship type (e.g., "AWARDED_TO", "TRANSITIONED_TO")
            target_label: Target node label
            target_key: Target node key property name
            rel_properties: Optional relationship properties to set
            
        Returns:
            Cypher query string
        """
        # Build relationship property SET clause
        if rel_properties:
            props_str = ", ".join(f"r.{k} = rel.{k}" for k in rel_properties.keys())
            set_clause = f"SET {props_str}"
        else:
            set_clause = ""
        
        query = f"""
        UNWIND $batch AS rel
        MATCH (source:{source_label} {{{source_key}: rel.source_key}})
        MATCH (target:{target_label} {{{target_key}: rel.target_key}})
        MERGE (source)-[r:{rel_type}]->(target)
        {set_clause}
        RETURN count(r) as relationship_count
        """
        
        return query.strip()

    @staticmethod
    def build_batch_create_query(
        label: str,
        return_count: bool = True,
    ) -> str:
        """Build a batch CREATE query (creates new nodes, no merge).
        
        Args:
            label: Node label
            return_count: If True, return created_count
            
        Returns:
            Cypher query string
        """
        query = f"""
        UNWIND $batch AS node
        CREATE (n:{label})
        SET n = node
        """
        if return_count:
            query += "RETURN count(n) as created_count"
        else:
            query += "RETURN count(n) as total_count"
        
        return query.strip()

    @staticmethod
    def build_single_merge_query(
        label: str,
        key_property: str,
        return_operation: bool = False,
    ) -> str:
        """Build a single-node MERGE query (not batched).
        
        Args:
            label: Node label
            key_property: Property name for matching
            return_operation: If True, return 'created' or 'updated'
            
        Returns:
            Cypher query string
        """
        query = f"""
        MERGE (n:{label} {{{key_property}: $key_value}})
        ON CREATE SET n += $properties, n.__created_flag = true
        ON MATCH SET n += $properties
        """
        if return_operation:
            query += "RETURN n, CASE WHEN n.__created_flag IS NOT NULL THEN 'created' ELSE 'updated' END AS operation"
        else:
            query += "RETURN n"
        
        return query.strip()

