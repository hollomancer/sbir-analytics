"""Dagster assets for PaECTER embedding generation and similarity computation."""

from .embeddings import (
    paecter_embeddings_awards,
    paecter_embeddings_patents,
    paecter_award_patent_similarity,
)

__all__ = [
    "paecter_embeddings_awards",
    "paecter_embeddings_patents",
    "paecter_award_patent_similarity",
]

