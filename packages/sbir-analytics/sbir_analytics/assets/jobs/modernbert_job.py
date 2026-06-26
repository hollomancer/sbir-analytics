"""Dagster job for ModernBert embedding generation and similarity computation.

This job materializes:
  - modernbert_embeddings_awards: Generate embeddings for SBIR awards
  - modernbert_embeddings_patents: Generate embeddings for USPTO patents
  - modernbert_award_patent_similarity: Compute similarity scores between awards and patents

Usage:
  - Import the job into your Dagster repository
  - Run the job with dagster CLI or from the Dagster UI
  - Requires validated_sbir_awards and transformed_patents assets to be materialized first
"""

from dagster import AssetSelection, define_asset_job


try:
    from sbir_analytics.assets.modernbert.embeddings import (
        modernbert_award_patent_similarity,
        modernbert_embeddings_awards,
        modernbert_embeddings_patents,
    )
except Exception:  # pragma: no cover
    modernbert_embeddings_awards = None  # type: ignore
    modernbert_embeddings_patents = None  # type: ignore
    modernbert_award_patent_similarity = None  # type: ignore


if all(
    asset is not None
    for asset in [
        modernbert_embeddings_awards,
        modernbert_embeddings_patents,
        modernbert_award_patent_similarity,
    ]
):
    modernbert_job = define_asset_job(
        name="modernbert_job",
        selection=AssetSelection.keys(
            modernbert_embeddings_awards.key,
            modernbert_embeddings_patents.key,
            modernbert_award_patent_similarity.key,
        ),
        description=(
            "Generate ModernBert embeddings for SBIR awards and USPTO patents, "
            "and compute similarity scores between them. "
            "Requires validated_sbir_awards and transformed_patents to be materialized first."
        ),
    )
else:
    modernbert_job = define_asset_job(  # type: ignore[unreachable]
        name="modernbert_job_placeholder",
        selection=AssetSelection.keys(),
        description="Placeholder job (ModernBert assets unavailable at import time).",
    )


__all__ = ["modernbert_job"]
