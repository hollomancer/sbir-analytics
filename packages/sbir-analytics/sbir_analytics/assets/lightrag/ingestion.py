"""LightRAG document ingestion asset.

Converts validated SBIR awards into LightRAG documents and inserts them
into the LightRAG knowledge graph for entity extraction and community
detection.
"""

from __future__ import annotations

import time

import pandas as pd
from dagster import Output, asset
from loguru import logger

from sbir_etl.config.loader import get_config
from sbir_rag.config import LightRAGConfig
from sbir_rag.document_prep import prepare_award_document


@asset(
    description="Ingest SBIR awards into LightRAG knowledge graph",
    group_name="lightrag",
    compute_kind="llm",
)
async def lightrag_document_ingestion(
    context,
    validated_sbir_awards: pd.DataFrame,
) -> Output[dict]:
    """Ingest SBIR awards into LightRAG for entity extraction.

    Converts each award row into a structured document and inserts it
    into LightRAG, which performs LLM-based entity/relationship extraction
    and stores results as ``__entity__`` / ``__relationship__`` nodes in Neo4j.

    Args:
        context: Dagster execution context.
        validated_sbir_awards: Validated SBIR awards DataFrame.

    Returns:
        Summary dict with ingestion metrics.
    """
    config = LightRAGConfig.from_yaml_config(get_config())

    if not config.enabled:
        context.log.info("LightRAG is disabled in config, skipping ingestion")
        return Output(
            value={"status": "skipped", "reason": "disabled"},
            metadata={"status": "skipped"},
        )

    from sbir_rag.factory import create_lightrag_instance

    rag = await create_lightrag_instance(config)

    # Prepare documents
    documents = []
    skipped = 0
    for _, row in validated_sbir_awards.iterrows():
        doc = prepare_award_document(row)
        if doc["content"].strip():
            documents.append(doc)
        else:
            skipped += 1

    context.log.info(
        f"Prepared {len(documents)} documents ({skipped} skipped, empty content)"
    )

    # Batch insert
    batch_size = 100
    ingested = 0
    start = time.time()

    for i in range(0, len(documents), batch_size):
        batch = documents[i : i + batch_size]
        await rag.ainsert([doc["content"] for doc in batch])
        ingested += len(batch)
        if ingested % 500 == 0:
            context.log.info(f"Ingested {ingested}/{len(documents)} documents")

    duration = time.time() - start
    context.log.info(
        f"LightRAG ingestion complete: {ingested} documents in {duration:.1f}s"
    )

    result = {
        "status": "success",
        "documents_ingested": ingested,
        "documents_skipped": skipped,
        "duration_seconds": round(duration, 2),
    }

    return Output(
        value=result,
        metadata={
            "documents_ingested": ingested,
            "documents_skipped": skipped,
            "duration_seconds": round(duration, 2),
        },
    )
