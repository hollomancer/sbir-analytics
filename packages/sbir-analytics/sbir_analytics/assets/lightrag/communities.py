"""Community detection asset: extract Leiden communities from LightRAG.

LightRAG builds communities during document insertion via the Leiden algorithm.
This asset queries the ``__community__`` nodes from Neo4j and produces a
DataFrame of community metadata for downstream consumption (CET sub-community
mapping, topic analysis, portfolio views).
"""

from __future__ import annotations

import time

import pandas as pd
from dagster import Output, asset
from loguru import logger

from sbir_etl.config.loader import get_config
from sbir_rag.config import LightRAGConfig

try:
    from sbir_graph.loaders.neo4j import Neo4jClient, Neo4jConfig
except ImportError:
    Neo4jClient = None  # type: ignore[assignment, misc]
    Neo4jConfig = None  # type: ignore[assignment, misc]


def _get_neo4j_client() -> Neo4jClient | None:
    """Get Neo4j client, or None if unavailable."""
    import os

    if Neo4jClient is None:
        return None

    try:
        config = get_config()
        neo4j_config = config.neo4j

        client_config = Neo4jConfig(
            uri=neo4j_config.uri,
            username=neo4j_config.username,
            password=neo4j_config.password,
            database=neo4j_config.database,
            batch_size=neo4j_config.batch_size,
        )

        client = Neo4jClient(client_config)
        with client.session() as session:
            session.run("RETURN 1")
        return client
    except Exception as e:
        skip = os.getenv("SKIP_NEO4J_LOADING", "false").lower() in ("true", "1", "yes")
        if skip:
            logger.warning(f"Neo4j unavailable but skipping: {e}")
            return None
        raise RuntimeError(
            f"Neo4j connection failed: {e}. Set SKIP_NEO4J_LOADING=true to skip."
        ) from e


@asset(
    description="Extract Leiden topic communities from LightRAG knowledge graph",
    group_name="lightrag",
    compute_kind="graph",
    deps=["lightrag_document_ingestion"],
)
def lightrag_topic_communities(context) -> Output[pd.DataFrame]:
    """Query LightRAG ``__community__`` nodes and build a communities DataFrame.

    Each community includes its member entities, the awards those entities
    were extracted from, and the agencies involved — providing a
    graph-based alternative to embedding-only clustering.

    Args:
        context: Dagster execution context.

    Returns:
        DataFrame with community_id, level, title, entities, award_ids, agencies.
    """
    rag_config = LightRAGConfig.from_yaml_config(get_config())

    if not rag_config.enabled:
        context.log.info("LightRAG is disabled, skipping community extraction")
        return Output(
            value=pd.DataFrame(),
            metadata={"status": "skipped"},
        )

    client = _get_neo4j_client()
    if client is None:
        context.log.info("Neo4j unavailable, skipping community extraction")
        return Output(
            value=pd.DataFrame(),
            metadata={"status": "skipped"},
        )

    start = time.time()

    try:
        # Query communities with their member entities and linked awards
        query = """
        MATCH (c:__community__)
        OPTIONAL MATCH (c)-[:HAS_MEMBER]->(e:__entity__)
        OPTIONAL MATCH (e)-[:EXTRACTED_FROM]->(a:Award)
        WITH c,
             collect(DISTINCT e.name) AS entities,
             collect(DISTINCT a.award_id) AS award_ids,
             collect(DISTINCT a.agency) AS agencies
        RETURN
            c.id AS community_id,
            c.level AS level,
            c.title AS title,
            c.summary AS summary,
            entities,
            award_ids,
            size(entities) AS num_entities,
            size(award_ids) AS num_awards,
            [a IN agencies WHERE a IS NOT NULL] AS agencies
        ORDER BY size(entities) DESC
        """

        rows = []
        with client.session() as session:
            result = session.run(query)
            for record in result:
                rows.append({
                    "community_id": record["community_id"],
                    "level": record["level"],
                    "title": record["title"],
                    "summary": record["summary"],
                    "entities": record["entities"],
                    "award_ids": record["award_ids"],
                    "num_entities": record["num_entities"],
                    "num_awards": record["num_awards"],
                    "agencies": record["agencies"],
                })

        communities_df = pd.DataFrame(rows) if rows else pd.DataFrame(columns=[
            "community_id", "level", "title", "summary", "entities",
            "award_ids", "num_entities", "num_awards", "agencies",
        ])

    except Exception as e:
        logger.error(f"Community extraction failed: {e}")
        return Output(
            value=pd.DataFrame(),
            metadata={"status": "error", "error": str(e)},
        )
    finally:
        client.close()

    duration = time.time() - start
    context.log.info(
        f"Extracted {len(communities_df)} communities in {duration:.1f}s"
    )

    return Output(
        value=communities_df,
        metadata={
            "num_communities": len(communities_df),
            "total_entities": int(communities_df["num_entities"].sum()) if len(communities_df) > 0 else 0,
            "total_awards_covered": int(communities_df["num_awards"].sum()) if len(communities_df) > 0 else 0,
            "duration_seconds": round(duration, 2),
        },
    )
