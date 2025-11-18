"""Unit tests for Neo4j query builder."""

from src.loaders.neo4j.query_builder import Neo4jQueryBuilder


def test_build_batch_merge_query_simple():
    """Test building a simple batch MERGE query."""
    query = Neo4jQueryBuilder.build_batch_merge_query(
        label="Company",
        key_property="uei",
        include_hash_check=False,
        return_counts=True,
    )
    
    assert "UNWIND $batch AS node" in query
    assert "MERGE (n:Company {uei: node.uei})" in query
    assert "SET n += node" in query
    assert "updated_count" in query


def test_build_batch_merge_query_with_hash():
    """Test building a batch MERGE query with hash checking."""
    query = Neo4jQueryBuilder.build_batch_merge_query(
        label="Award",
        key_property="award_id",
        include_hash_check=True,
        return_counts=True,
    )
    
    assert "UNWIND $batch AS node" in query
    assert "MERGE (n:Award {award_id: node.award_id})" in query
    assert "__hash" in query
    assert "created_count" in query
    assert "updated_count" in query


def test_build_batch_match_update_query():
    """Test building a batch MATCH + SET query."""
    query = Neo4jQueryBuilder.build_batch_match_update_query(
        label="Company",
        key_property="uei",
        return_count=True,
    )
    
    assert "UNWIND $batch AS item" in query
    assert "MATCH (n:Company {uei: item.key})" in query
    assert "SET n += item.props" in query
    assert "updated_count" in query


def test_build_relationship_merge_query():
    """Test building a relationship MERGE query."""
    query = Neo4jQueryBuilder.build_relationship_merge_query(
        source_label="Award",
        source_key="award_id",
        rel_type="AWARDED_TO",
        target_label="Company",
        target_key="uei",
    )
    
    assert "UNWIND $batch AS rel" in query
    assert "MATCH (source:Award {award_id: rel.source_key})" in query
    assert "MATCH (target:Company {uei: rel.target_key})" in query
    assert "MERGE (source)-[r:AWARDED_TO]->(target)" in query


def test_build_relationship_merge_query_with_properties():
    """Test building a relationship MERGE query with properties."""
    query = Neo4jQueryBuilder.build_relationship_merge_query(
        source_label="Award",
        source_key="award_id",
        rel_type="TRANSITIONED_TO",
        target_label="Transition",
        target_key="transition_id",
        rel_properties={"score": "rel.score", "confidence": "rel.confidence"},
    )
    
    assert "SET r.score = rel.score" in query
    assert "SET r.confidence = rel.confidence" in query


def test_build_batch_create_query():
    """Test building a batch CREATE query."""
    query = Neo4jQueryBuilder.build_batch_create_query(
        label="Patent",
        return_count=True,
    )
    
    assert "UNWIND $batch AS node" in query
    assert "CREATE (n:Patent)" in query
    assert "SET n = node" in query
    assert "created_count" in query


def test_build_single_merge_query():
    """Test building a single-node MERGE query."""
    query = Neo4jQueryBuilder.build_single_merge_query(
        label="Company",
        key_property="uei",
        return_operation=True,
    )
    
    assert "MERGE (n:Company {uei: $key_value})" in query
    assert "ON CREATE SET n += $properties" in query
    assert "ON MATCH SET n += $properties" in query
    assert "operation" in query

