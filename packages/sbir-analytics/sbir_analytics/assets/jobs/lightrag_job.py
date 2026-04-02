"""Dagster job for LightRAG knowledge graph ingestion and community detection.

This job materializes the full LightRAG pipeline:
  - lightrag_document_ingestion: Ingest SBIR awards into LightRAG
  - extracted_solicitation_topics: Extract solicitation topics from SBIR.gov
  - lightrag_solicitation_ingestion: Ingest solicitation topics
  - neo4j_award_embeddings: Write embeddings to Neo4j vector index
  - lightrag_entity_cross_references: Link entities to structured nodes
  - lightrag_topic_communities: Extract Leiden communities
  - cet_subcommunity_mapping: Map communities to CET areas

Usage:
  - Run with: dagster job execute -j lightrag_ingestion_job
  - Requires validated_sbir_awards and paecter_embeddings_awards to be materialized first
  - LightRAG must be enabled in config (lightrag.enabled: true)
"""

from dagster import AssetSelection, define_asset_job

lightrag_ingestion_job = define_asset_job(
    name="lightrag_ingestion_job",
    selection=AssetSelection.groups("lightrag"),
    description=(
        "Ingest SBIR awards and solicitation topics into LightRAG, "
        "build Leiden communities, write embeddings to Neo4j vector index, "
        "and create cross-references between extracted entities and structured nodes."
    ),
)

__all__ = ["lightrag_ingestion_job"]
