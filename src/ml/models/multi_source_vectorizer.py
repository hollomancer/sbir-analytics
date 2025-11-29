"""
Multi-source TF-IDF vectorizer for CET classification.

This module provides a vectorizer that combines multiple text sources
(abstract, keywords, title) with configurable weights to improve
classification accuracy, especially for short or vague abstracts.

Based on the sbir-cet-classifier multi-source approach, adapted for sbir-analytics.
"""

from __future__ import annotations

from typing import Any

from sklearn.feature_extraction.text import TfidfVectorizer


class MultiSourceCETVectorizer(TfidfVectorizer):
    """
    TF-IDF vectorizer that combines multiple text sources with configurable weights.

    This vectorizer extends the standard TfidfVectorizer to support weighted
    combination of multiple text fields (abstract, keywords, title). Each source
    is repeated proportionally to its configured weight before vectorization.

    Example:
        With weights abstract=0.5, keywords=0.3, title=0.2:
        - Abstract text repeated 5 times
        - Keywords text repeated 3 times
        - Title text repeated 2 times
        Then combined and vectorized together.

    This approach gives more importance to higher-weighted sources while
    maintaining a single coherent feature space.
    """

    def __init__(
        self,
        abstract_weight: float = 0.5,
        keywords_weight: float = 0.3,
        title_weight: float = 0.2,
        cet_keywords: dict[str, list[str]] | None = None,
        keyword_boost_factor: float = 2.0,
        **tfidf_params: Any,
    ):
        """
        Initialize multi-source CET vectorizer.

        Args:
            abstract_weight: Weight for abstract text (default: 0.5)
            keywords_weight: Weight for keywords text (default: 0.3)
            title_weight: Weight for title text (default: 0.2)
            cet_keywords: Dictionary mapping CET IDs to keyword lists (for boosting)
            keyword_boost_factor: Multiplier for CET keyword TF-IDF scores
            **tfidf_params: Additional parameters passed to TfidfVectorizer

        Raises:
            ValueError: If weights don't sum to 1.0
        """
        super().__init__(**tfidf_params)

        # Validate weights sum to 1.0
        total_weight = abstract_weight + keywords_weight + title_weight
        if abs(total_weight - 1.0) > 1e-6:
            raise ValueError(
                f"Weights must sum to 1.0, got {total_weight} "
                f"(abstract={abstract_weight}, keywords={keywords_weight}, title={title_weight})"
            )

        self.abstract_weight = abstract_weight
        self.keywords_weight = keywords_weight
        self.title_weight = title_weight

        # CET keyword boosting (optional, for compatibility with CETAwareTfidfVectorizer)
        self.cet_keywords = cet_keywords or {}
        self.keyword_boost_factor = keyword_boost_factor

        # Build flat keyword set for fast lookup
        self.keyword_set: set[str] = set()
        for keywords in self.cet_keywords.values():
            self.keyword_set.update(k.lower() for k in keywords)

    def _combine_sources(self, doc: dict[str, str]) -> str:
        """
        Combine multiple text sources with repetition-based weighting.

        Args:
            doc: Dictionary with keys: 'abstract', 'keywords', 'title'

        Returns:
            Combined text string with sources repeated according to weights
        """
        parts = []

        # Scale weights to integer repetitions (multiply by 10 for granularity)
        abstract_reps = int(self.abstract_weight * 10)
        keywords_reps = int(self.keywords_weight * 10)
        title_reps = int(self.title_weight * 10)

        # Repeat each source proportional to its weight
        abstract = doc.get("abstract", "").strip()
        if abstract:
            parts.extend([abstract] * abstract_reps)

        keywords = doc.get("keywords", "").strip()
        if keywords:
            parts.extend([keywords] * keywords_reps)

        title = doc.get("title", "").strip()
        if title:
            parts.extend([title] * title_reps)

        # Combine with spaces
        return " ".join(parts) if parts else ""

    def fit(self, raw_documents: list, y=None) -> MultiSourceCETVectorizer:
        """
        Fit vectorizer on documents.

        Args:
            raw_documents: List of dictionaries with 'abstract', 'keywords', 'title' keys,
                          or list of strings (for backward compatibility)
            y: Target labels (ignored, for sklearn compatibility)

        Returns:
            self
        """
        # Handle both dict format and string format
        if raw_documents and isinstance(raw_documents[0], dict):
            combined_texts = [self._combine_sources(doc) for doc in raw_documents]
        else:
            # Backward compatibility: treat as simple strings
            combined_texts = raw_documents

        return super().fit(combined_texts, y)

    def transform(self, raw_documents: list):
        """
        Transform documents to TF-IDF matrix.

        Args:
            raw_documents: List of dictionaries with 'abstract', 'keywords', 'title' keys,
                          or list of strings (for backward compatibility)

        Returns:
            Sparse TF-IDF matrix
        """
        # Handle both dict format and string format
        if raw_documents and isinstance(raw_documents[0], dict):
            combined_texts = [self._combine_sources(doc) for doc in raw_documents]
        else:
            # Backward compatibility: treat as simple strings
            combined_texts = raw_documents

        X = super().transform(combined_texts)

        # Apply keyword boosting if CET keywords provided
        if self.cet_keywords and hasattr(self, "vocabulary_"):
            X = self._apply_keyword_boost(X)

        return X

    def fit_transform(self, raw_documents: list, y=None):
        """
        Fit vectorizer and transform documents.

        Args:
            raw_documents: List of dictionaries with 'abstract', 'keywords', 'title' keys,
                          or list of strings (for backward compatibility)
            y: Target labels (ignored, for sklearn compatibility)

        Returns:
            Sparse TF-IDF matrix
        """
        # Handle both dict format and string format
        if raw_documents and isinstance(raw_documents[0], dict):
            combined_texts = [self._combine_sources(doc) for doc in raw_documents]
        else:
            # Backward compatibility: treat as simple strings
            combined_texts = raw_documents

        X = super().fit_transform(combined_texts, y)

        # Apply keyword boosting if CET keywords provided
        if self.cet_keywords and hasattr(self, "vocabulary_"):
            X = self._apply_keyword_boost(X)

        return X

    def _apply_keyword_boost(self, X):  # type: ignore[no-untyped-def]
        """
        Apply keyword boosting to TF-IDF matrix.

        Boosts features that match CET keywords by the configured boost factor.

        Args:
            X: TF-IDF matrix (sparse)

        Returns:
            Boosted TF-IDF matrix
        """
        if not hasattr(self, "vocabulary_"):
            return X

        # Find indices of keyword features
        keyword_indices = []
        for word, idx in self.vocabulary_.items():
            if word.lower() in self.keyword_set:
                keyword_indices.append(idx)

        if not keyword_indices:
            return X

        # Boost keyword features
        X_boosted = X.copy()
        X_boosted[:, keyword_indices] *= self.keyword_boost_factor

        return X_boosted


def create_multi_source_vectorizer(
    config: dict[str, Any],
    cet_keywords: dict[str, list[str]] | None = None,
) -> MultiSourceCETVectorizer:
    """
    Factory function to create a configured MultiSourceCETVectorizer.

    Args:
        config: Configuration dictionary from classification.yaml
        cet_keywords: Optional CET keyword mapping for boosting

    Returns:
        Configured MultiSourceCETVectorizer instance
    """
    tfidf_config = config.get("tfidf", {})
    multi_source_config = config.get("multi_source", {})

    # Get weights (with defaults)
    abstract_weight = multi_source_config.get("abstract_weight", 0.5)
    keywords_weight = multi_source_config.get("keywords_weight", 0.3)
    title_weight = multi_source_config.get("title_weight", 0.2)

    # Get TF-IDF parameters
    stop_words = tfidf_config.get("stop_words", None)

    return MultiSourceCETVectorizer(
        abstract_weight=abstract_weight,
        keywords_weight=keywords_weight,
        title_weight=title_weight,
        cet_keywords=cet_keywords,
        keyword_boost_factor=tfidf_config.get("keyword_boost_factor", 2.0),
        max_features=tfidf_config.get("max_features", 5000),
        min_df=tfidf_config.get("min_df", 2),
        max_df=tfidf_config.get("max_df", 0.95),
        ngram_range=tuple(tfidf_config.get("ngram_range", [1, 2])),
        sublinear_tf=tfidf_config.get("sublinear_tf", True),
        use_idf=tfidf_config.get("use_idf", True),
        smooth_idf=tfidf_config.get("smooth_idf", True),
        norm=tfidf_config.get("norm", "l2"),
        stop_words=stop_words,
    )
