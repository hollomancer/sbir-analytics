"""Neo4j vector index asset for award embeddings.

Writes pre-computed ModernBERT-Embed embeddings from the ``paecter_embeddings_awards``
asset into Award nodes in Neo4j, making them queryable via the ``award_embedding``
vector index created in migration 004.
"""

from __future__ import annotations

import time

import pandas as pd
from dagster import Output, asset
from loguru import logger

from sbir_etl.config.loader import get_config

try:
    from sbir_graph.loaders.neo4j import Neo4jClient, Neo4jConfig
except ImportError:
    Neo4jClient = None  # type: ignore[assignment, misc]
    Neo4jConfig = None  # type: ignore[assignment, misc]


def _get_neo4j_client() -> Neo4jClient | None:
    """Get Neo4j client, or None if unavailable."""
    import os

    if Neo4jClient is None:
        logger.warning("sbir_graph not installed, skipping Neo4j operations")
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
    description="Write award embeddings to Neo4j vector index",
    group_name="lightrag",
    compute_kind="neo4j",
)
def neo4j_award_embeddings(
    context,
    paecter_embeddings_awards: pd.DataFrame,
) -> Output[dict]:
    """Write pre-computed embeddings into Award nodes for vector search.

    Uses batch UNWIND to set ``embedding`` property on Award nodes,
    enabling k-NN queries via the ``award_embedding`` vector index.

    Args:
        context: Dagster execution context.
        paecter_embeddings_awards: DataFrame with ``award_id`` and ``embedding`` columns.

    Returns:
        Summary dict with write metrics.
    """
    client = _get_neo4j_client()
    if client is None:
        context.log.info("Neo4j unavailable, skipping embedding write")
        return Output(
            value={"status": "skipped", "reason": "neo4j_unavailable"},
            metadata={"status": "skipped"},
        )

    start = time.time()
    batch_size = 500
    updated = 0
    errors = 0

    try:
        for i in range(0, len(paecter_embeddings_awards), batch_size):
            batch_df = paecter_embeddings_awards.iloc[i : i + batch_size]
            batch = [
                {
                    "award_id": str(row["award_id"]),
                    "embedding": row["embedding"],
                }
                for _, row in batch_df.iterrows()
            ]

            query = """
            UNWIND $batch AS item
            MATCH (a:Award {award_id: item.award_id})
            SET a.embedding = item.embedding
            RETURN count(a) AS updated
            """

            with client.session() as session:
                result = session.run(query, batch=batch)
                record = result.single()
                updated += record["updated"] if record else 0

            if updated % 2000 == 0 and updated > 0:
                context.log.info(
                    f"Updated {updated}/{len(paecter_embeddings_awards)} award embeddings"
                )

    except Exception as e:
        logger.error(f"Error writing embeddings: {e}")
        errors += 1
    finally:
        client.close()

    duration = time.time() - start
    context.log.info(
        f"Award embedding write complete: {updated} updated in {duration:.1f}s"
    )

    result = {
        "status": "success" if errors == 0 else "partial",
        "embeddings_updated": updated,
        "total_embeddings": len(paecter_embeddings_awards),
        "errors": errors,
        "duration_seconds": round(duration, 2),
    }

    return Output(
        value=result,
        metadata={
            "embeddings_updated": updated,
            "total_embeddings": len(paecter_embeddings_awards),
            "errors": errors,
            "duration_seconds": round(duration, 2),
        },
    )
