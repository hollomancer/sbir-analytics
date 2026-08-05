"""Sparse lexical award↔target text similarity.

Ported from the transition-ranker scoring core (`2bc346a6`,
``specs/phase3-match-benchmark/transition-ranker.md``): on this domain's
jargon-heavy text, corpus-fitted word-level TF-IDF cosine beats dense
embeddings, BM25, and cross-encoders (0.751 vs 0.653/0.643/0.669 on the frozen
Phase III benchmark) — the connective signal is exact-lexical jargon, which
mean-pooled embeddings blur. Char-n-grams help only as a separate fusion
feature, not blended into the text score (rich-subset AUC: word 0.710 vs
0.6/0.4 blend 0.684).
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


def _clean(texts: Sequence[str]) -> list[str]:
    return ["" if text is None else str(text) for text in texts]


def _fit_corpus(queries: list[str], targets: list[str], analyzer: str):
    """Fit one TF-IDF space over queries + targets; None when the corpus is empty."""

    ngram = (1, 2) if analyzer == "word" else (3, 5)
    stop = {"stop_words": "english"} if analyzer == "word" else {}
    vectorizer = TfidfVectorizer(analyzer=analyzer, ngram_range=ngram, min_df=1, **stop)
    try:
        return vectorizer.fit_transform(queries + targets)
    except ValueError:  # corpus reduces to nothing but stopwords
        return None


def tfidf_cosine_matrix(
    query_texts: Sequence[str],
    target_texts: Sequence[str],
    *,
    analyzer: str = "word",
) -> np.ndarray:
    """Query×target TF-IDF cosine matrix, fitted on the union corpus.

    ``word`` uses (1,2)-grams with English stopwords; ``char_wb`` uses
    (3,5)-grams. Empty inputs yield a zero matrix of the right shape.

    This materializes a dense ``len(queries) × len(targets)`` matrix — for
    row-aligned pair scoring use :func:`paired_tfidf_cosine`, which never
    forms the cross product.
    """

    queries = _clean(query_texts)
    targets = _clean(target_texts)
    if not queries or not targets or not any(queries) or not any(targets):
        return np.zeros((len(queries), len(targets)))
    matrix = _fit_corpus(queries, targets, analyzer)
    if matrix is None:
        return np.zeros((len(queries), len(targets)))
    return cosine_similarity(matrix[: len(queries)], matrix[len(queries) :])


def paired_tfidf_cosine(
    query_texts: Sequence[str],
    target_texts: Sequence[str],
    *,
    analyzer: str = "word",
) -> np.ndarray:
    """Row-aligned TF-IDF cosine for (query[i], target[i]) pairs.

    The vectorizer is fitted over the full corpus (all queries + all targets),
    so idf reflects the run, but only the aligned pairings are scored. The
    paired cosines are read straight off the sparse rows — the dense ``N × N``
    cross-product is never built, so memory stays linear in the pair count.
    """

    if len(query_texts) != len(target_texts):
        raise ValueError("query_texts and target_texts must be the same length")
    if not query_texts:
        return np.zeros(0)
    queries = _clean(query_texts)
    targets = _clean(target_texts)
    if not any(queries) or not any(targets):
        return np.zeros(len(queries))
    matrix = _fit_corpus(queries, targets, analyzer)
    if matrix is None:
        return np.zeros(len(queries))
    count = len(queries)
    # TfidfVectorizer L2-normalizes each row, so the row-wise dot product of a
    # query row with its target row is exactly that pair's cosine similarity.
    paired = matrix[:count].multiply(matrix[count:]).sum(axis=1)
    return np.asarray(paired).ravel()


__all__ = ["paired_tfidf_cosine", "tfidf_cosine_matrix"]
