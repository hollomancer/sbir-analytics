"""Interactive similarity search using Neo4j vector indexes.

Provides real-time k-NN search over Award embeddings stored in Neo4j,
bypassing LightRAG for simple similarity queries.  Uses the ``award_embedding``
vector index created in migration 004.

The batch ``paecter_award_patent_similarity`` asset is kept for the transition
detection pipeline (must maintain >=85% precision).  This module provides an
interactive alternative for ad-hoc similarity queries.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from loguru import logger

if TYPE_CHECKING:
    from sbir_rag.config import LightRAGConfig


async def find_similar_awards(
    query_text: str,
    config: LightRAGConfig,
    *,
    top_k: int = 10,
) -> list[dict[str, Any]]:
    """Real-time similarity search using Neo4j vector index.

    Generates an embedding for the query text via ModernBERT-Embed, then
    uses Neo4j's ``db.index.vector.queryNodes`` to find the nearest Award
    nodes by cosine similarity.

    Args:
        query_text: Natural language query to find similar awards.
        config: LightRAG configuration (for Neo4j and embedding settings).
        top_k: Number of nearest neighbors to return.

    Returns:
        List of dicts with award_id, title, abstract, score, agency.
    """
    import asyncio

    from sbir_rag.embedding_adapter import create_embedding_func

    # Generate query embedding
    embed_func = await create_embedding_func(config)
    query_embedding = await embed_func([query_text])
    embedding_list = query_embedding[0].tolist()

    # Query Neo4j vector index
    try:
        from sbir_graph.loaders.neo4j import Neo4jClient, Neo4jConfig
    except ImportError:
        logger.error("sbir_graph not installed, cannot perform similarity search")
        return []

    from sbir_etl.config.loader import get_config

    app_config = get_config()
    neo4j_config = app_config.neo4j

    client = Neo4jClient(Neo4jConfig(
        uri=neo4j_config.uri,
        username=neo4j_config.username,
        password=neo4j_config.password,
        database=neo4j_config.database,
    ))

    try:
        query = """
        CALL db.index.vector.queryNodes('award_embedding', $k, $embedding)
        YIELD node, score
        RETURN
            node.award_id AS award_id,
            node.award_title AS title,
            node.abstract AS abstract,
            node.agency AS agency,
            node.phase AS phase,
            node.company_name AS company,
            score
        ORDER BY score DESC
        """

        results = []
        with client.session() as session:
            records = session.run(query, k=top_k, embedding=embedding_list)
            for record in records:
                results.append({
                    "award_id": record["award_id"],
                    "title": record["title"],
                    "abstract": record["abstract"],
                    "agency": record["agency"],
                    "phase": record["phase"],
                    "company": record["company"],
                    "score": float(record["score"]),
                })

        logger.info(f"Found {len(results)} similar awards for: {query_text[:80]}")
        return results

    except Exception as e:
        logger.error(f"Similarity search failed: {e}")
        return []
    finally:
        client.close()
