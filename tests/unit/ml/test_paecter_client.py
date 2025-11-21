"""
Unit tests for the PaECTERClient.
"""

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from src.ml.config import PaECTERClientConfig
from src.ml.paecter_client import PaECTERClient


@pytest.fixture
def paecter_config():
    """
    Provides a PaECTERClientConfig for testing.
    """
    return PaECTERClientConfig(use_local=False, enable_cache=True)


@pytest.fixture
@patch("src.ml.paecter_client.InferenceClient")
def paecter_client(mock_inference_client, paecter_config):
    """
    Provides a PaECTERClient instance with a mocked InferenceClient.
    """
    mock_client = MagicMock()
    mock_inference_client.return_value = mock_client
    return PaECTERClient(paecter_config)


def test_generate_embeddings_caching(paecter_client):
    texts = ["text1", "text2", "text1"]

    # Mock the API response
    mock_embeddings = np.random.rand(2, paecter_client.embedding_dim)
    paecter_client.client.feature_extraction.return_value = mock_embeddings

    # First call
    result1 = paecter_client.generate_embeddings(texts)

    assert result1.input_count == 3
    assert paecter_client.client.feature_extraction.call_count == 1

    # Check that "text1" is in the cache
    assert "text1" in paecter_client.cache
    assert "text2" in paecter_client.cache

    # Second call
    result2 = paecter_client.generate_embeddings(texts)

    # The mock should not be called again
    assert paecter_client.client.feature_extraction.call_count == 1
    assert result2.input_count == 3

    # Check that the results are the same
    np.testing.assert_array_equal(result1.embeddings, result2.embeddings)


def test_pydantic_config():
    config = PaECTERClientConfig(use_local=True, device="cpu")
    assert config.use_local is True
    assert config.device == "cpu"
    assert config.model_name == "mpi-inno-comp/paecter"


def test_prepare_patent_text():
    title = "  A great invention  "
    abstract = "  This is how it works.  "
    expected = "A great invention This is how it works."
    assert PaECTERClient.prepare_patent_text(title, abstract) == expected


def test_prepare_award_text():
    solicitation_title = "  Advanced materials  "
    award_title = "  Graphene production  "
    abstract = "  A new method for producing graphene.  "
    expected = "Advanced materials Graphene production A new method for producing graphene."
    assert PaECTERClient.prepare_award_text(solicitation_title, abstract, award_title) == expected
