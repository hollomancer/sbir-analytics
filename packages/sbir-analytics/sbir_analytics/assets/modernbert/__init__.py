"""Dagster assets for ModernBert embedding generation and similarity computation."""

from .embeddings import (
    modernbert_award_patent_similarity,
    modernbert_embeddings_awards,
    modernbert_embeddings_patents,
)


__all__ = [
    "modernbert_embeddings_awards",
    "modernbert_embeddings_patents",
    "modernbert_award_patent_similarity",
]
