"""Dagster job for PaECTER embedding generation and similarity computation.

This job materializes:
  - paecter_embeddings_awards: Generate embeddings for SBIR awards
  - paecter_embeddings_patents: Generate embeddings for USPTO patents
  - paecter_award_patent_similarity: Compute similarity scores between awards and patents

Usage:
  - Import the job into your Dagster repository
  - Run the job with dagster CLI or from the Dagster UI
  - Requires validated_sbir_awards and transformed_patents assets to be materialized first
"""

from dagster import AssetSelection, build_assets_job


try:
    from src.assets.paecter.embeddings import (
        paecter_award_patent_similarity,
        paecter_embeddings_awards,
        paecter_embeddings_patents,
    )
except Exception:  # pragma: no cover
    paecter_embeddings_awards = None  # type: ignore
    paecter_embeddings_patents = None  # type: ignore
    paecter_award_patent_similarity = None  # type: ignore


if all(
    asset is not None
    for asset in [
        paecter_embeddings_awards,
        paecter_embeddings_patents,
        paecter_award_patent_similarity,
    ]
):
    paecter_job = build_assets_job(
        name="paecter_job",
        assets=[
            paecter_embeddings_awards,
            paecter_embeddings_patents,
            paecter_award_patent_similarity,
        ],
        selection=AssetSelection.keys(
            paecter_embeddings_awards.key,
            paecter_embeddings_patents.key,
            paecter_award_patent_similarity.key,
        ),
        description=(
            "Generate PaECTER embeddings for SBIR awards and USPTO patents, "
            "and compute similarity scores between them. "
            "Requires validated_sbir_awards and transformed_patents to be materialized first."
        ),
    )
else:
    paecter_job = build_assets_job(  # type: ignore[unreachable]
        name="paecter_job_placeholder",
        assets=[],
        description="Placeholder job (PaECTER assets unavailable at import time).",
    )


__all__ = ["paecter_job"]

