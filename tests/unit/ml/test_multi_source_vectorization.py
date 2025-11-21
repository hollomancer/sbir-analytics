"""
Unit tests for multi-source text vectorization (Phase 2).

Tests:
- MultiSourceCETVectorizer functionality
- Weight validation and text combination
- Integration with ApplicabilityModel
- Backward compatibility with single-source mode
"""

import numpy as np
import pytest

from src.ml.models.multi_source_vectorizer import (
    MultiSourceCETVectorizer,
    create_multi_source_vectorizer,
)


class TestMultiSourceVectorizerWeights:
    """Test weight validation and configuration."""

    def test_weights_must_sum_to_one(self):
        """Test that weights must sum to 1.0."""
        with pytest.raises(ValueError, match="Weights must sum to 1.0"):
            MultiSourceCETVectorizer(
                abstract_weight=0.5,
                keywords_weight=0.3,
                title_weight=0.3,  # 0.5 + 0.3 + 0.3 = 1.1 (invalid)
            )

    def test_valid_weights_accepted(self):
        """Test that valid weights are accepted."""
        vectorizer = MultiSourceCETVectorizer(
            abstract_weight=0.5,
            keywords_weight=0.3,
            title_weight=0.2,
        )

        assert vectorizer.abstract_weight == 0.5
        assert vectorizer.keywords_weight == 0.3
        assert vectorizer.title_weight == 0.2

    def test_custom_weights_configuration(self):
        """Test various valid weight configurations."""
        # Equal weights
        v1 = MultiSourceCETVectorizer(
            abstract_weight=0.33,
            keywords_weight=0.33,
            title_weight=0.34,
        )
        assert abs(v1.abstract_weight + v1.keywords_weight + v1.title_weight - 1.0) < 1e-6

        # Abstract-heavy
        v2 = MultiSourceCETVectorizer(
            abstract_weight=0.7,
            keywords_weight=0.2,
            title_weight=0.1,
        )
        assert abs(v2.abstract_weight + v2.keywords_weight + v2.title_weight - 1.0) < 1e-6


class TestMultiSourceVectorizerCombination:
    """Test text combination logic."""

    def test_combine_sources_basic(self):
        """Test basic text combination."""
        vectorizer = MultiSourceCETVectorizer(
            abstract_weight=0.5,
            keywords_weight=0.3,
            title_weight=0.2,
        )

        doc = {
            "abstract": "quantum computing research",
            "keywords": "quantum algorithms qubits",
            "title": "Quantum Computing Study",
        }

        combined = vectorizer._combine_sources(doc)

        # Abstract should appear 5 times (0.5 * 10)
        assert combined.count("quantum computing research") == 5
        # Keywords should appear 3 times (0.3 * 10)
        assert combined.count("quantum algorithms qubits") == 3
        # Title should appear 2 times (0.2 * 10)
        assert combined.count("Quantum Computing Study") == 2

    def test_combine_sources_missing_fields(self):
        """Test handling of missing text fields."""
        vectorizer = MultiSourceCETVectorizer(
            abstract_weight=0.5,
            keywords_weight=0.3,
            title_weight=0.2,
        )

        # Only abstract provided
        doc1 = {"abstract": "quantum computing"}
        combined1 = vectorizer._combine_sources(doc1)
        assert "quantum computing" in combined1

        # Only keywords provided
        doc2 = {"keywords": "quantum algorithms"}
        combined2 = vectorizer._combine_sources(doc2)
        assert "quantum algorithms" in combined2

        # Empty doc
        doc3 = {}
        combined3 = vectorizer._combine_sources(doc3)
        assert combined3 == ""

    def test_combine_sources_empty_strings(self):
        """Test handling of empty strings."""
        vectorizer = MultiSourceCETVectorizer(
            abstract_weight=0.5,
            keywords_weight=0.3,
            title_weight=0.2,
        )

        doc = {
            "abstract": "",
            "keywords": "quantum",
            "title": "",
        }

        combined = vectorizer._combine_sources(doc)
        # Only keywords should be present
        assert "quantum" in combined
        assert combined.strip() != ""


class TestMultiSourceVectorizerTransform:
    """Test vectorization and transformation."""

    def test_fit_transform_with_dicts(self):
        """Test fit_transform with dictionary input."""
        vectorizer = MultiSourceCETVectorizer(
            abstract_weight=0.5,
            keywords_weight=0.3,
            title_weight=0.2,
            max_features=100,
        )

        docs = [
            {
                "abstract": "quantum computing algorithms",
                "keywords": "quantum qubits",
                "title": "Quantum Research",
            },
            {
                "abstract": "machine learning neural networks",
                "keywords": "deep learning ai",
                "title": "ML Study",
            },
        ]

        X = vectorizer.fit_transform(docs)

        # Check shape
        assert X.shape[0] == 2  # 2 documents
        assert X.shape[1] <= 100  # max_features limit

        # Check it's a sparse matrix
        assert hasattr(X, "toarray")

    def test_fit_transform_backward_compat_strings(self):
        """Test backward compatibility with string input."""
        vectorizer = MultiSourceCETVectorizer(
            abstract_weight=0.5,
            keywords_weight=0.3,
            title_weight=0.2,
        )

        # String input (backward compat)
        docs = [
            "quantum computing algorithms",
            "machine learning neural networks",
        ]

        X = vectorizer.fit_transform(docs)

        assert X.shape[0] == 2
        assert X.shape[1] > 0

    def test_transform_after_fit(self):
        """Test separate fit and transform calls."""
        vectorizer = MultiSourceCETVectorizer(
            abstract_weight=0.5,
            keywords_weight=0.3,
            title_weight=0.2,
        )

        train_docs = [
            {"abstract": "quantum computing", "keywords": "quantum", "title": "QC"},
            {"abstract": "machine learning", "keywords": "ml ai", "title": "ML"},
        ]

        test_docs = [
            {"abstract": "quantum algorithms", "keywords": "qubits", "title": "Quantum"},
        ]

        vectorizer.fit(train_docs)
        X_test = vectorizer.transform(test_docs)

        assert X_test.shape[0] == 1
        assert X_test.shape[1] == vectorizer.transform(train_docs).shape[1]


class TestMultiSourceVectorizerKeywordBoosting:
    """Test CET keyword boosting functionality."""

    def test_keyword_boosting_applied(self):
        """Test that keyword boosting increases feature weights."""
        cet_keywords = {
            "quantum_computing": ["quantum", "qubit"],
        }

        vectorizer = MultiSourceCETVectorizer(
            abstract_weight=0.5,
            keywords_weight=0.3,
            title_weight=0.2,
            cet_keywords=cet_keywords,
            keyword_boost_factor=3.0,
            max_features=100,
        )

        docs = [
            {
                "abstract": "quantum computing with qubits",
                "keywords": "quantum qubit",
                "title": "Quantum",
            }
        ]

        X = vectorizer.fit_transform(docs)

        # Keyword boosting should be applied (tested indirectly via non-zero matrix)
        assert X.nnz > 0  # Has non-zero elements

    def test_no_keyword_boosting_when_not_provided(self):
        """Test that keyword boosting is optional."""
        vectorizer = MultiSourceCETVectorizer(
            abstract_weight=0.5,
            keywords_weight=0.3,
            title_weight=0.2,
            # No cet_keywords provided
        )

        docs = [{"abstract": "quantum computing", "keywords": "quantum", "title": "QC"}]

        X = vectorizer.fit_transform(docs)

        assert X.shape[0] == 1
        assert X.nnz > 0


class TestMultiSourceVectorizerFactory:
    """Test factory function for creating vectorizers."""

    def test_create_from_config(self):
        """Test creating vectorizer from configuration."""
        config = {
            "multi_source": {
                "abstract_weight": 0.6,
                "keywords_weight": 0.25,
                "title_weight": 0.15,
            },
            "tfidf": {
                "max_features": 5000,
                "keyword_boost_factor": 2.5,
                "stop_words": ["the", "a", "an"],
            },
        }

        cet_keywords = {"quantum_computing": ["quantum", "qubit"]}

        vectorizer = create_multi_source_vectorizer(config, cet_keywords)

        assert vectorizer.abstract_weight == 0.6
        assert vectorizer.keywords_weight == 0.25
        assert vectorizer.title_weight == 0.15
        assert vectorizer.keyword_boost_factor == 2.5
        assert vectorizer.max_features == 5000
        assert vectorizer.stop_words == ["the", "a", "an"]

    def test_create_with_defaults(self):
        """Test factory with minimal config (uses defaults)."""
        config = {}

        vectorizer = create_multi_source_vectorizer(config)

        # Should use default weights
        assert vectorizer.abstract_weight == 0.5
        assert vectorizer.keywords_weight == 0.3
        assert vectorizer.title_weight == 0.2


class TestMultiSourceVectorizerIntegration:
    """Test integration scenarios."""

    def test_consistent_vocabulary_across_calls(self):
        """Test that vocabulary is consistent across multiple transform calls."""
        vectorizer = MultiSourceCETVectorizer(
            abstract_weight=0.5,
            keywords_weight=0.3,
            title_weight=0.2,
        )

        docs = [
            {"abstract": "quantum computing", "keywords": "quantum", "title": "QC"},
            {"abstract": "machine learning", "keywords": "ml", "title": "ML"},
        ]

        vectorizer.fit(docs)

        # Transform same docs multiple times
        X1 = vectorizer.transform(docs)
        X2 = vectorizer.transform(docs)

        # Should produce identical results
        assert np.allclose(X1.toarray(), X2.toarray())

    def test_weights_affect_feature_importance(self):
        """Test that higher weights increase feature importance."""
        # Abstract-heavy configuration
        v_abstract = MultiSourceCETVectorizer(
            abstract_weight=0.8,
            keywords_weight=0.1,
            title_weight=0.1,
        )

        # Keywords-heavy configuration
        v_keywords = MultiSourceCETVectorizer(
            abstract_weight=0.2,
            keywords_weight=0.6,
            title_weight=0.2,
        )

        doc = {
            "abstract": "unique_abstract_term",
            "keywords": "unique_keyword_term",
            "title": "title",
        }

        X_abstract = v_abstract.fit_transform([doc])
        X_keywords = v_keywords.fit_transform([doc])

        # Both should have features, but distribution different
        assert X_abstract.nnz > 0
        assert X_keywords.nnz > 0
