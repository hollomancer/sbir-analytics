"""Dagster job for SPECTER2 embedding generation and similarity computation.

This job materializes:
  - specter2_embeddings_awards: Generate embeddings for SBIR awards
  - specter2_embeddings_patents: Generate embeddings for USPTO patents
  - specter2_award_patent_similarity: Compute similarity scores between awards and patents

Usage:
  - Import the job into your Dagster repository
  - Run the job with dagster CLI or from the Dagster UI
  - Requires validated_sbir_awards and transformed_patents assets to be materialized first
"""

from dagster import AssetSelection, define_asset_job


try:
    from src.assets.specter2.embeddings import (
        specter2_award_patent_similarity,
        specter2_embeddings_awards,
        specter2_embeddings_patents,
    )
except Exception:  # pragma: no cover
    specter2_embeddings_awards = None  # type: ignore
    specter2_embeddings_patents = None  # type: ignore
    specter2_award_patent_similarity = None  # type: ignore


if all(
    asset is not None
    for asset in [
        specter2_embeddings_awards,
        specter2_embeddings_patents,
        specter2_award_patent_similarity,
    ]
):
    specter2_job = define_asset_job(
        name="specter2_job",
        selection=AssetSelection.keys(
            specter2_embeddings_awards.key,
            specter2_embeddings_patents.key,
            specter2_award_patent_similarity.key,
        ),
        description=(
            "Generate SPECTER2 embeddings for SBIR awards and USPTO patents, "
            "and compute similarity scores between them. "
            "Requires validated_sbir_awards and transformed_patents to be materialized first."
        ),
    )
else:
    specter2_job = define_asset_job(  # type: ignore[unreachable]
        name="specter2_job_placeholder",
        selection=AssetSelection.keys(),
        description="Placeholder job (SPECTER2 assets unavailable at import time).",
    )


__all__ = ["specter2_job"]
