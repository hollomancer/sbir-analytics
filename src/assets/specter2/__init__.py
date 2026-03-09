"""Dagster assets for SPECTER2 embedding generation and similarity computation."""

from .embeddings import (
    specter2_award_patent_similarity,
    specter2_embeddings_awards,
    specter2_embeddings_patents,
)


__all__ = [
    "specter2_embeddings_awards",
    "specter2_embeddings_patents",
    "specter2_award_patent_similarity",
]
