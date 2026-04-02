"""Tests for the embedding adapter."""

from __future__ import annotations

import asyncio
import sys
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from sbir_rag.config import LightRAGConfig


def _make_mock_sbir_ml(mock_client_cls):
    """Set up fake sbir_ml modules in sys.modules so lazy imports resolve."""
    mock_config_mod = MagicMock()
    mock_client_mod = MagicMock()
    mock_client_mod.PaECTERClient = mock_client_cls
    return {
        "sbir_ml": MagicMock(),
        "sbir_ml.ml": MagicMock(),
        "sbir_ml.ml.config": mock_config_mod,
        "sbir_ml.ml.paecter_client": mock_client_mod,
    }


class TestCreateEmbeddingFunc:
    """Test the async embedding function factory."""

    @pytest.fixture
    def config(self):
        return LightRAGConfig(
            embedding_model="nomic-ai/modernbert-embed-base",
            use_local_embeddings=False,
        )

    def test_creates_callable(self, config):
        """Embedding func factory should return an async callable."""
        mock_result = MagicMock()
        mock_result.embeddings = np.random.randn(2, 768).astype(np.float32)

        mock_client_cls = MagicMock()
        mock_client_cls.return_value.generate_embeddings.return_value = mock_result

        with patch.dict(sys.modules, _make_mock_sbir_ml(mock_client_cls)):
            # Reimport to pick up mocked modules
            import importlib

            import sbir_rag.embedding_adapter as mod

            importlib.reload(mod)

            func = asyncio.get_event_loop().run_until_complete(mod.create_embedding_func(config))
            assert callable(func)

    def test_returns_correct_shape(self, config):
        """Returned embeddings should be (N, 768)."""
        expected = np.random.randn(3, 768).astype(np.float32)
        mock_result = MagicMock()
        mock_result.embeddings = expected

        mock_client_cls = MagicMock()
        mock_client_cls.return_value.generate_embeddings.return_value = mock_result

        with patch.dict(sys.modules, _make_mock_sbir_ml(mock_client_cls)):
            import importlib

            import sbir_rag.embedding_adapter as mod

            importlib.reload(mod)

            loop = asyncio.get_event_loop()
            func = loop.run_until_complete(mod.create_embedding_func(config))
            result = loop.run_until_complete(func(["text1", "text2", "text3"]))

            assert result.shape == (3, 768)
            np.testing.assert_array_equal(result, expected)

    def test_passes_normalize_true(self, config):
        """Adapter should always request normalized embeddings."""
        mock_result = MagicMock()
        mock_result.embeddings = np.zeros((1, 768))

        mock_client = MagicMock()
        mock_client.generate_embeddings.return_value = mock_result
        mock_client_cls = MagicMock(return_value=mock_client)

        with patch.dict(sys.modules, _make_mock_sbir_ml(mock_client_cls)):
            import importlib

            import sbir_rag.embedding_adapter as mod

            importlib.reload(mod)

            loop = asyncio.get_event_loop()
            func = loop.run_until_complete(mod.create_embedding_func(config))
            loop.run_until_complete(func(["hello"]))

            mock_client.generate_embeddings.assert_called_once_with(
                ["hello"],
                normalize=True,
            )
