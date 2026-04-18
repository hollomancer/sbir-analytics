"""Solicitation topic extraction and LightRAG ingestion assets.

Two assets:
1. ``extracted_solicitation_topics`` — pulls topic descriptions from SBIR.gov
2. ``lightrag_solicitation_ingestion`` — feeds topics into LightRAG for entity extraction

Solicitation descriptions are 500-3000 words of dense technical prose and are
the highest-value text source for LightRAG entity extraction.
"""

from __future__ import annotations

import time

import pandas as pd
from dagster import Output, asset

from sbir_etl.config.loader import get_config
from sbir_rag.config import LightRAGConfig
from sbir_rag.document_prep import classify_description, prepare_solicitation_document


@asset(
    description="Extract solicitation topics from SBIR.gov",
    group_name="lightrag",
    compute_kind="extraction",
)
def extracted_solicitation_topics(context) -> Output[pd.DataFrame]:
    """Extract solicitation topic descriptions from SBIR.gov API.

    Pulls full topic text (title + description) for all agencies,
    deduplicates by (topic_code, solicitation_number), and returns
    a DataFrame ready for LightRAG ingestion.

    Args:
        context: Dagster execution context.

    Returns:
        DataFrame with topic_code, solicitation_number, title, description, etc.
    """
    rag_config = LightRAGConfig.from_yaml_config(get_config())

    if not rag_config.enabled:
        context.log.info("LightRAG is disabled, skipping solicitation extraction")
        return Output(
            value=pd.DataFrame(),
            metadata={"status": "skipped"},
        )

    from sbir_etl.extractors.solicitation import SolicitationExtractor

    extractor = SolicitationExtractor()

    try:
        topics_df = extractor.extract_topics()
        topics_df = extractor.deduplicate_topics(topics_df)
    finally:
        extractor.close()

    # Count topics with descriptions (the valuable ones)
    has_description = (
        (topics_df["description"].notna() & (topics_df["description"].str.strip() != "")).sum()
        if len(topics_df) > 0
        else 0
    )

    context.log.info(
        f"Extracted {len(topics_df)} solicitation topics ({has_description} with descriptions)"
    )

    return Output(
        value=topics_df,
        metadata={
            "topic_count": len(topics_df),
            "with_description": int(has_description),
            "agencies": (topics_df["agency"].nunique() if len(topics_df) > 0 else 0),
        },
    )


@asset(
    description="Ingest solicitation topics into LightRAG knowledge graph",
    group_name="lightrag",
    compute_kind="llm",
)
async def lightrag_solicitation_ingestion(
    context,
    extracted_solicitation_topics: pd.DataFrame,
) -> Output[dict]:
    """Ingest solicitation topics into LightRAG for entity extraction.

    Converts each topic row into a structured document and inserts it
    into LightRAG. Only topics with non-empty descriptions are ingested,
    since topics without descriptions provide minimal extraction value.

    Args:
        context: Dagster execution context.
        extracted_solicitation_topics: Solicitation topics DataFrame.

    Returns:
        Summary dict with ingestion metrics.
    """
    config = LightRAGConfig.from_yaml_config(get_config())

    if not config.enabled:
        context.log.info("LightRAG is disabled, skipping solicitation ingestion")
        return Output(
            value={"status": "skipped", "reason": "disabled"},
            metadata={"status": "skipped"},
        )

    if extracted_solicitation_topics.empty:
        context.log.info("No solicitation topics to ingest")
        return Output(
            value={"status": "skipped", "reason": "no_topics"},
            metadata={"status": "skipped"},
        )

    from sbir_rag.factory import create_lightrag_instance

    rag = await create_lightrag_instance(config)

    # Classify and prepare documents using tiered description filtering
    documents = []
    tier_counts = {"stub": 0, "summary": 0, "full": 0}

    for _, row in extracted_solicitation_topics.iterrows():
        tier = classify_description(
            row,
            min_length=config.min_description_length,
            full_threshold=config.full_description_threshold,
        )
        tier_counts[tier] += 1

        if tier == "stub":
            continue  # Skip stubs — no LLM extraction value

        doc = prepare_solicitation_document(row)
        if doc["content"].strip():
            documents.append(doc)

    context.log.info(
        f"Description tiers: {tier_counts['full']} full, "
        f"{tier_counts['summary']} summary, {tier_counts['stub']} stubs skipped"
    )

    # Batch insert
    batch_size = 100
    ingested = 0
    start = time.time()

    for i in range(0, len(documents), batch_size):
        batch = documents[i : i + batch_size]
        # Pass topic_code as document IDs so LightRAG stores them on __chunk__
        # nodes (as full_doc_id), enabling cross-reference queries later.
        batch_ids = [doc["metadata"].get("topic_code") for doc in batch]
        await rag.ainsert([doc["content"] for doc in batch], ids=batch_ids)
        ingested += len(batch)
        if ingested % 500 == 0:
            context.log.info(f"Ingested {ingested}/{len(documents)} solicitations")

    duration = time.time() - start
    context.log.info(f"Solicitation ingestion complete: {ingested} documents in {duration:.1f}s")

    result = {
        "status": "success",
        "topics_ingested": ingested,
        "stubs_skipped": tier_counts["stub"],
        "summaries_ingested": tier_counts["summary"],
        "full_descriptions_ingested": tier_counts["full"],
        "duration_seconds": round(duration, 2),
    }

    return Output(
        value=result,
        metadata={
            "topics_ingested": ingested,
            "stubs_skipped": tier_counts["stub"],
            "summaries_ingested": tier_counts["summary"],
            "full_descriptions_ingested": tier_counts["full"],
            "duration_seconds": round(duration, 2),
        },
    )
