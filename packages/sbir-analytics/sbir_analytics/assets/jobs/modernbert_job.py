"""Dagster job for ModernBert embedding generation and similarity computation.

This job materializes:
  - modernbert_embeddings_awards: Generate embeddings for SBIR awards
  - modernbert_embeddings_patents: Generate embeddings for USPTO patents
  - modernbert_award_patent_similarity: Compute similarity scores between awards and patents

Usage:
  - Import the job into your Dagster repository
  - Run the job with dagster CLI or from the Dagster UI
  - Requires validated_sbir_awards and transformed_patents assets to be materialized first

Epistemic tier: exploratory. This job wires the exploratory embedding and
similarity assets; outputs are non-citable.
"""

from dagster import AssetSelection, define_asset_job

from sbir_analytics.assets.modernbert.embeddings import (
    modernbert_award_patent_similarity,
    modernbert_embeddings_awards,
    modernbert_embeddings_patents,
)


EPISTEMIC_TIER = "exploratory"


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


__all__ = ["modernbert_job"]
