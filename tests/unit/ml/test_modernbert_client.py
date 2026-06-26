"""
Unit tests for the ModernBertClient.
"""

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from sbir_ml.ml.config import ModernBertClientConfig
from sbir_ml.ml.modernbert_client import ModernBertClient


@pytest.fixture
def modernbert_config():
    """
    Provides a ModernBertClientConfig for testing.
    """
    return ModernBertClientConfig(use_local=False, enable_cache=True)


@pytest.fixture
@patch("sbir_ml.ml.modernbert_client.InferenceClient")
def modernbert_client(mock_inference_client, modernbert_config):
    """
    Provides a ModernBertClient instance with a mocked InferenceClient.
    """
    mock_client = MagicMock()
    mock_inference_client.return_value = mock_client
    return ModernBertClient(modernbert_config)


def test_generate_embeddings_caching(modernbert_client):
    texts = ["text1", "text2", "text1"]

    # Mock the API response - should return 3 embeddings for 3 texts (including duplicate)
    mock_embeddings = np.random.rand(3, modernbert_client.embedding_dim)
    modernbert_client.client.feature_extraction.return_value = mock_embeddings

    # First call
    result1 = modernbert_client.generate_embeddings(texts)

    assert result1.input_count == 3
    assert modernbert_client.client.feature_extraction.call_count == 1

    # Check that "text1" and "text2" are in the cache
    assert "text1" in modernbert_client.cache
    assert "text2" in modernbert_client.cache

    # Second call with same texts
    result2 = modernbert_client.generate_embeddings(texts)

    # The mock should not be called again (all from cache)
    assert modernbert_client.client.feature_extraction.call_count == 1
    assert result2.input_count == 3

    # Check that the results are the same
    np.testing.assert_array_equal(result1.embeddings, result2.embeddings)


def test_pydantic_config():
    config = ModernBertClientConfig(use_local=True, device="cpu")
    assert config.use_local is True
    assert config.device == "cpu"
    assert config.model_name == "nomic-ai/modernbert-embed-base"


def test_prepare_patent_text():
    title = "  A great invention  "
    abstract = "  This is how it works.  "
    expected = "A great invention This is how it works."
    assert ModernBertClient.prepare_patent_text(title, abstract) == expected


def test_prepare_award_text():
    solicitation_title = "  Advanced materials  "
    award_title = "  Graphene production  "
    abstract = "  A new method for producing graphene.  "
    expected = "Advanced materials Graphene production A new method for producing graphene."
    assert (
        ModernBertClient.prepare_award_text(solicitation_title, abstract, award_title) == expected
    )


# ---------------------------------------------------------------------------
# Text preprocessing edge cases
# ---------------------------------------------------------------------------


class TestPreparePatentTextEdgeCases:
    """Test text preprocessing with missing or empty fields."""

    def test_none_title_and_abstract(self):
        assert ModernBertClient.prepare_patent_text(None, None) == ""

    def test_none_title(self):
        assert ModernBertClient.prepare_patent_text(None, "Abstract text") == "Abstract text"

    def test_none_abstract(self):
        assert ModernBertClient.prepare_patent_text("Title text", None) == "Title text"

    def test_empty_strings(self):
        assert ModernBertClient.prepare_patent_text("", "") == ""

    def test_whitespace_only(self):
        # Whitespace-only strings are truthy, strip() makes them empty but they
        # still get joined, resulting in a space-separated empty string
        result = ModernBertClient.prepare_patent_text("   ", "   ")
        assert result.strip() == ""


class TestPrepareAwardTextEdgeCases:
    """Test award text preprocessing with missing or empty fields."""

    def test_all_none(self):
        assert ModernBertClient.prepare_award_text(None, None, None) == ""

    def test_only_abstract(self):
        assert ModernBertClient.prepare_award_text(None, "Abstract only", None) == "Abstract only"

    def test_only_solicitation(self):
        assert ModernBertClient.prepare_award_text("Title only", None) == "Title only"

    def test_empty_strings(self):
        assert ModernBertClient.prepare_award_text("", "", "") == ""


# ---------------------------------------------------------------------------
# Configuration tests
# ---------------------------------------------------------------------------


class TestModernBertClientConfig:
    """Test ModernBert client configuration."""

    def test_default_config(self):
        config = ModernBertClientConfig()
        assert config.use_local is False
        assert config.model_name == "nomic-ai/modernbert-embed-base"
        assert config.enable_cache is True  # Cache enabled by default

    def test_local_mode_config(self):
        config = ModernBertClientConfig(use_local=True, device="cpu")
        assert config.use_local is True
        assert config.device == "cpu"

    def test_cache_enabled(self):
        config = ModernBertClientConfig(enable_cache=True)
        assert config.enable_cache is True


# ---------------------------------------------------------------------------
# Similarity computation tests
# ---------------------------------------------------------------------------


class TestComputeSimilarity:
    """Test cosine similarity computation."""

    @patch("sbir_ml.ml.modernbert_client.InferenceClient")
    def test_identical_embeddings_max_similarity(self, mock_ic):
        """Identical normalized vectors should have similarity ~1.0."""
        config = ModernBertClientConfig(use_local=False, enable_cache=False)
        client = ModernBertClient(config)

        # Create normalized embeddings
        emb = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
        result = client.compute_similarity(emb, emb)
        np.testing.assert_array_almost_equal(np.diag(result), [1.0, 1.0])

    @patch("sbir_ml.ml.modernbert_client.InferenceClient")
    def test_orthogonal_embeddings_zero_similarity(self, mock_ic):
        """Orthogonal vectors should have similarity ~0.0."""
        config = ModernBertClientConfig(use_local=False, enable_cache=False)
        client = ModernBertClient(config)

        emb1 = np.array([[1.0, 0.0]])
        emb2 = np.array([[0.0, 1.0]])
        result = client.compute_similarity(emb1, emb2)
        np.testing.assert_array_almost_equal(result, [[0.0]])

    @patch("sbir_ml.ml.modernbert_client.InferenceClient")
    def test_similarity_matrix_shape(self, mock_ic):
        """Similarity matrix should have shape (N, M)."""
        config = ModernBertClientConfig(use_local=False, enable_cache=False)
        client = ModernBertClient(config)

        emb1 = np.random.rand(3, 10)
        emb2 = np.random.rand(5, 10)
        result = client.compute_similarity(emb1, emb2)
        assert result.shape == (3, 5)
