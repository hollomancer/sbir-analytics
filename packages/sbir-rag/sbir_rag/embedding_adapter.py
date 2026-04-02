"""Embedding adapter: wraps ModernBERT-Embed (PaECTERClient) for LightRAG.

LightRAG expects an async embedding function with signature::

    async def func(texts: list[str]) -> np.ndarray

This module bridges the synchronous ``PaECTERClient.generate_embeddings()``
into that interface using ``asyncio.to_thread``.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from collections.abc import Callable

    from sbir_rag.config import LightRAGConfig


async def create_embedding_func(config: LightRAGConfig) -> Callable[..., np.ndarray]:
    """Create an async embedding function backed by ModernBERT-Embed.

    The returned function is compatible with ``lightrag.EmbeddingFunc``.

    Args:
        config: LightRAG configuration (embedding model, local vs API mode).

    Returns:
        Async callable: ``(texts: list[str]) -> np.ndarray`` producing
        an ``(N, D)`` array of normalised embeddings.
    """
    from sbir_ml.ml.config import PaECTERClientConfig
    from sbir_ml.ml.paecter_client import PaECTERClient

    client = PaECTERClient(
        config=PaECTERClientConfig(
            model_name=config.embedding_model,
            use_local=config.use_local_embeddings,
            enable_cache=True,
        )
    )

    async def _embed(texts: list[str]) -> np.ndarray:
        result = await asyncio.to_thread(
            client.generate_embeddings,
            texts,
            normalize=True,
        )
        return result.embeddings

    return _embed
