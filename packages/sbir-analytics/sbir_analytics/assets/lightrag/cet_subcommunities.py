"""Map Leiden sub-communities within CET taxonomy areas.

For each of the 21 CETArea nodes, finds LightRAG communities whose member
entities overlap with awards classified in that CET area.  Creates
``(:CETArea)-[:HAS_SUBCOMMUNITY]->(:__community__)`` relationships,
giving fine-grained thematic breakdown within each CET.
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
    description="Map Leiden sub-communities within CET taxonomy areas",
    group_name="lightrag",
    compute_kind="neo4j",
    deps=["lightrag_topic_communities"],
)
def cet_subcommunity_mapping(context) -> Output[dict]:
    """Link CETArea nodes to LightRAG communities via award overlap.

    For each CETArea, finds communities whose extracted entities were
    sourced from awards classified under that CET.  Creates
    ``HAS_SUBCOMMUNITY`` relationships with an ``overlap_count`` property
    indicating how many awards bridge the CET and community.

    Args:
        context: Dagster execution context.

    Returns:
        Summary dict with mapping metrics.
    """
    rag_config = LightRAGConfig.from_yaml_config(get_config())

    if not rag_config.enabled:
        context.log.info("LightRAG is disabled, skipping CET sub-community mapping")
        return Output(
            value={"status": "skipped", "reason": "disabled"},
            metadata={"status": "skipped"},
        )

    client = _get_neo4j_client()
    if client is None:
        context.log.info("Neo4j unavailable, skipping CET sub-community mapping")
        return Output(
            value={"status": "skipped", "reason": "neo4j_unavailable"},
            metadata={"status": "skipped"},
        )

    start = time.time()
    relationships_created = 0
    cet_areas_mapped = 0

    try:
        # Find communities that share awards with each CETArea.
        # Awards are linked to CETAreas via CLASSIFIED_AS relationships
        # and to communities via entity EXTRACTED_FROM paths.
        mapping_query = """
        MATCH (cet:CETArea)<-[:CLASSIFIED_AS]-(a:Award)
        MATCH (e:__entity__)-[:EXTRACTED_FROM]->(a)
        MATCH (c:__community__)-[:HAS_MEMBER]->(e)
        WITH cet, c, count(DISTINCT a) AS overlap_count
        WHERE overlap_count >= 2
        MERGE (cet)-[r:HAS_SUBCOMMUNITY]->(c)
        SET r.overlap_count = overlap_count
        RETURN
            count(*) AS rels_created,
            count(DISTINCT cet) AS cets_mapped
        """

        with client.session() as session:
            result = session.run(mapping_query)
            record = result.single()
            if record:
                relationships_created = record["rels_created"]
                cet_areas_mapped = record["cets_mapped"]

        context.log.info(
            f"Mapped {relationships_created} sub-community relationships "
            f"across {cet_areas_mapped} CET areas"
        )

    except Exception as e:
        logger.error(f"CET sub-community mapping failed: {e}")
        return Output(
            value={"status": "error", "error": str(e)},
            metadata={"error": str(e)},
        )
    finally:
        client.close()

    duration = time.time() - start
    result = {
        "status": "success",
        "relationships_created": relationships_created,
        "cet_areas_mapped": cet_areas_mapped,
        "duration_seconds": round(duration, 2),
    }

    return Output(
        value=result,
        metadata={
            "relationships_created": relationships_created,
            "cet_areas_mapped": cet_areas_mapped,
            "duration_seconds": round(duration, 2),
        },
    )
