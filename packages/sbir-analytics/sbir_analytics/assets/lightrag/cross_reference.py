"""Cross-reference LightRAG entities with existing structured graph nodes.

After LightRAG ingestion, ``__entity__`` nodes exist in Neo4j alongside the
structured Award / Company / Organization nodes.  This asset creates
``REFERS_TO`` relationships linking extracted entities back to their source
Award nodes using the award_id stored in chunk metadata.
"""

from __future__ import annotations

import time

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
    description="Link LightRAG entities to structured Award/Company nodes",
    group_name="lightrag",
    compute_kind="neo4j",
    deps=["lightrag_document_ingestion"],
)
def lightrag_entity_cross_references(context) -> Output[dict]:
    """Create cross-reference relationships between LightRAG and structured nodes.

    Links ``__entity__`` nodes extracted by LightRAG back to the Award nodes
    they were extracted from.  Also attempts name-based matching between
    extracted organization entities and existing Company nodes.

    Args:
        context: Dagster execution context.

    Returns:
        Summary dict with cross-reference metrics.
    """
    rag_config = LightRAGConfig.from_yaml_config(get_config())

    if not rag_config.enabled:
        context.log.info("LightRAG is disabled, skipping cross-references")
        return Output(
            value={"status": "skipped", "reason": "disabled"},
            metadata={"status": "skipped"},
        )

    client = _get_neo4j_client()
    if client is None:
        context.log.info("Neo4j unavailable, skipping cross-references")
        return Output(
            value={"status": "skipped", "reason": "neo4j_unavailable"},
            metadata={"status": "skipped"},
        )

    start = time.time()
    entity_links = 0
    company_links = 0

    try:
        # Link __entity__ nodes to Award nodes via chunk document IDs.
        # During ingestion, award_id is passed as the document ID to
        # rag.ainsert(ids=...), which LightRAG stores as full_doc_id on
        # __chunk__ nodes. Entities get source_id referencing chunk IDs,
        # so we traverse: entity → (source_id) → chunk → (full_doc_id) → Award.
        entity_to_award_query = """
        MATCH (e:__entity__)
        WHERE e.source_id IS NOT NULL
        WITH e, split(e.source_id, '<SEP>') AS chunk_ids
        UNWIND chunk_ids AS chunk_id
        MATCH (c:__chunk__)
        WHERE c.id = chunk_id AND c.full_doc_id IS NOT NULL
        MATCH (a:Award {award_id: c.full_doc_id})
        MERGE (e)-[:EXTRACTED_FROM]->(a)
        RETURN count(*) AS links_created
        """

        with client.session() as session:
            result = session.run(entity_to_award_query)
            record = result.single()
            entity_links = record["links_created"] if record else 0

        context.log.info(f"Created {entity_links} entity → Award links")

        # Match extracted organization entities to Company nodes by name.
        # Uses case-insensitive exact match first, then containment with a
        # minimum name length guard to avoid short-name cartesian explosions.
        company_match_query = """
        MATCH (e:__entity__)
        WHERE e.entity_type = 'ORGANIZATION'
          AND size(e.name) >= 4
        MATCH (c:Company)
        WHERE toLower(c.name) = toLower(e.name)
           OR (size(e.name) >= 8
               AND (toLower(c.name) CONTAINS toLower(e.name)
                    OR toLower(e.name) CONTAINS toLower(c.name)))
        MERGE (e)-[:REFERS_TO]->(c)
        RETURN count(*) AS links_created
        """

        with client.session() as session:
            result = session.run(company_match_query)
            record = result.single()
            company_links = record["links_created"] if record else 0

        context.log.info(f"Created {company_links} entity → Company links")

    except Exception as e:
        logger.error(f"Cross-reference creation failed: {e}")
        return Output(
            value={"status": "error", "error": str(e)},
            metadata={"error": str(e)},
        )
    finally:
        client.close()

    duration = time.time() - start
    result = {
        "status": "success",
        "entity_to_award_links": entity_links,
        "entity_to_company_links": company_links,
        "duration_seconds": round(duration, 2),
    }

    return Output(
        value=result,
        metadata={
            "entity_to_award_links": entity_links,
            "entity_to_company_links": company_links,
            "duration_seconds": round(duration, 2),
        },
    )
