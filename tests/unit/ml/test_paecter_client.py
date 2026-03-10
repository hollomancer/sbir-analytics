"""
Unit tests for the Specter2Client.
"""

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from src.ml.config import Specter2ClientConfig
from src.ml.specter2_client import Specter2Client


@pytest.fixture
def specter2_config():
    """
    Provides a Specter2ClientConfig for testing.
    """
    return Specter2ClientConfig(use_local=False, enable_cache=True)


@pytest.fixture
@patch("src.ml.specter2_client.InferenceClient")
def specter2_client(mock_inference_client, specter2_config):
    """
    Provides a Specter2Client instance with a mocked InferenceClient.
    """
    mock_client = MagicMock()
    mock_inference_client.return_value = mock_client
    return Specter2Client(specter2_config)


def test_generate_embeddings_caching(specter2_client):
    texts = ["text1", "text2", "text1"]

    # Mock the API response - should return 3 embeddings for 3 texts (including duplicate)
    mock_embeddings = np.random.rand(3, specter2_client.embedding_dim)
    specter2_client.client.feature_extraction.return_value = mock_embeddings

    # First call
    result1 = specter2_client.generate_embeddings(texts)

    assert result1.input_count == 3
    assert specter2_client.client.feature_extraction.call_count == 1

    # Check that "text1" and "text2" are in the cache
    assert "text1" in specter2_client.cache
    assert "text2" in specter2_client.cache

    # Second call with same texts
    result2 = specter2_client.generate_embeddings(texts)

    # The mock should not be called again (all from cache)
    assert specter2_client.client.feature_extraction.call_count == 1
    assert result2.input_count == 3

    # Check that the results are the same
    np.testing.assert_array_equal(result1.embeddings, result2.embeddings)


def test_pydantic_config():
    config = Specter2ClientConfig(use_local=True, device="cpu")
    assert config.use_local is True
    assert config.device == "cpu"
    assert config.model_name == "allenai/specter2"


def test_prepare_patent_text():
    title = "  A great invention  "
    abstract = "  This is how it works.  "
    expected = "A great invention This is how it works."
    assert Specter2Client.prepare_patent_text(title, abstract) == expected


def test_prepare_award_text():
    solicitation_title = "  Advanced materials  "
    award_title = "  Graphene production  "
    abstract = "  A new method for producing graphene.  "
    expected = "Advanced materials Graphene production A new method for producing graphene."
    assert Specter2Client.prepare_award_text(solicitation_title, abstract, award_title) == expected
