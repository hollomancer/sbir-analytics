"""LightRAG instance factory.

Creates a fully-configured ``LightRAG`` instance using:
- Neo4j as graph, vector, and KV storage backend
- ModernBERT-Embed (768-dim) via the embedding adapter
- Anthropic Claude for LLM entity/relationship extraction
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from sbir_rag.config import LightRAGConfig


async def create_lightrag_instance(config: LightRAGConfig):
    """Create and return a configured LightRAG instance.

    Args:
        config: LightRAG configuration.

    Returns:
        A ``LightRAG`` instance ready for document insertion and querying.

    Raises:
        ImportError: If ``lightrag`` is not installed.
    """
    try:
        from lightrag import LightRAG
        from lightrag.llm.base import EmbeddingFunc
    except ImportError as exc:
        raise ImportError(
            "lightrag-hku is required for RAG features. Install with: pip install sbir-rag"
        ) from exc

    from sbir_rag.embedding_adapter import create_embedding_func

    embedding_func = await create_embedding_func(config)

    # Resolve the LLM completion function based on model name.
    # LightRAG has built-in support for Anthropic models via
    # lightrag.llm.anthropic.anthropic_complete which reads the model
    # name from llm_model_name at call time.
    llm_model_func = _resolve_llm_func(config.llm_model)

    neo4j_params = {
        "uri": config.neo4j_uri,
        "user": config.neo4j_username,
        "password": config.neo4j_password,
        "database": config.neo4j_database,
    }

    rag = LightRAG(
        working_dir=f"/tmp/lightrag_{config.workspace}",
        llm_model_func=llm_model_func,
        llm_model_name=config.llm_model,
        llm_model_max_async=config.llm_max_async,
        llm_model_kwargs={
            "max_tokens": config.llm_max_tokens,
            "temperature": config.llm_temperature,
        },
        embedding_func=EmbeddingFunc(
            embedding_dim=config.embedding_dim,
            max_token_size=8192,  # ModernBERT-Embed context window
            func=embedding_func,
        ),
        graph_storage="Neo4JStorage",
        vector_storage="Neo4JStorage",
        kv_storage="Neo4JStorage",
        graph_storage_params=neo4j_params,
        vector_storage_params=neo4j_params,
        kv_storage_params=neo4j_params,
    )

    logger.info(
        "LightRAG instance created",
        workspace=config.workspace,
        llm_model=config.llm_model,
        embedding_model=config.embedding_model,
        neo4j_uri=config.neo4j_uri,
    )
    return rag


def _resolve_llm_func(model_name: str):
    """Return the appropriate LightRAG LLM function for the given model.

    Supports Anthropic Claude models (via lightrag's built-in adapter)
    and falls back to OpenAI-compatible models.
    """
    if "claude" in model_name.lower() or "anthropic" in model_name.lower():
        from lightrag.llm.anthropic import anthropic_complete

        return anthropic_complete

    # Default: OpenAI-compatible (covers GPT, local servers, etc.)
    from lightrag.llm.openai import openai_complete

    return openai_complete
