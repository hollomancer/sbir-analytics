"""Dagster assets for ModernBert embedding generation and similarity computation.

Epistemic tier: exploratory. Neural embedding similarity used as transition
evidence has no validated contract, so similarity outputs are non-citable.
"""

from .embeddings import (
    modernbert_award_patent_similarity,
    modernbert_embeddings_awards,
    modernbert_embeddings_patents,
)


EPISTEMIC_TIER = "exploratory"


__all__ = [
    "modernbert_embeddings_awards",
    "modernbert_embeddings_patents",
    "modernbert_award_patent_similarity",
]
