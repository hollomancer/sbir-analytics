"""Configuration for LightRAG integration."""

from __future__ import annotations

import os
from typing import Any

from pydantic import BaseModel, Field, model_validator


class LightRAGConfig(BaseModel):
    """Configuration for LightRAG integration with SBIR analytics.

    Loaded from the ``lightrag`` section of ``config/base.yaml`` or constructed
    directly.  Neo4j connection parameters default to environment variables
    matching the existing ``loading.neo4j`` convention.
    """

    # Feature flag
    enabled: bool = Field(False, description="Enable LightRAG features (opt-in)")

    # LightRAG workspace (namespaces Neo4j nodes)
    workspace: str = Field(
        "sbir", description="LightRAG workspace name for Neo4j namespace isolation"
    )

    # Neo4j connection (reuses existing env vars by default)
    neo4j_uri: str = Field("bolt://localhost:7687", description="Neo4j bolt URI")
    neo4j_username: str = Field("neo4j", description="Neo4j username")
    neo4j_password: str = Field("", description="Neo4j password")
    neo4j_database: str = Field("neo4j", description="Neo4j database name")

    # Embedding model (must match existing ModernBERT-Embed setup)
    embedding_model: str = Field(
        "nomic-ai/modernbert-embed-base",
        description="HuggingFace model identifier for embeddings",
    )
    embedding_dim: int = Field(768, description="Embedding dimension (768 for ModernBERT-Embed)")
    use_local_embeddings: bool = Field(
        False,
        description="Use local sentence-transformers instead of HuggingFace Inference API",
    )

    # LLM for entity extraction
    llm_model: str = Field(
        "claude-haiku-4-5-20251001",
        description="LLM model for entity/relationship extraction",
    )
    llm_max_tokens: int = Field(4096, description="Max tokens for LLM extraction responses")
    llm_max_async: int = Field(4, ge=1, description="Max concurrent LLM requests for extraction")
    llm_temperature: float = Field(0.0, ge=0.0, le=2.0)

    # Document chunking
    chunk_size: int = Field(1200, ge=100, description="Text chunk size for document ingestion")
    chunk_overlap: int = Field(100, ge=0, description="Overlap between chunks")

    # Community detection
    community_algorithm: str = Field("leiden", description="Community detection algorithm")
    max_community_levels: int = Field(
        3, ge=1, description="Max levels for hierarchical communities"
    )
    community_resolution: float = Field(1.0, gt=0.0, description="Leiden resolution parameter")

    # Retrieval defaults
    default_retrieval_mode: str = Field(
        "hybrid",
        description="Default retrieval mode: naive, local, global, hybrid",
    )
    retrieval_top_k: int = Field(10, ge=1, description="Default top-k for retrieval")
    similarity_threshold: float = Field(0.75, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def resolve_neo4j_env_vars(self) -> LightRAGConfig:
        """Fill Neo4j connection from environment variables if not explicitly set."""
        if not self.neo4j_uri or self.neo4j_uri == "bolt://localhost:7687":
            self.neo4j_uri = os.environ.get("NEO4J_URI", self.neo4j_uri)
        if not self.neo4j_password:
            self.neo4j_password = os.environ.get("NEO4J_PASSWORD", "")
        if self.neo4j_username == "neo4j":
            self.neo4j_username = os.environ.get("NEO4J_USER", self.neo4j_username)
        if self.neo4j_database == "neo4j":
            self.neo4j_database = os.environ.get("NEO4J_DATABASE", self.neo4j_database)
        return self

    @classmethod
    def from_yaml_config(cls, config: Any) -> LightRAGConfig:
        """Construct from a parsed YAML config dict or PipelineConfig model.

        Reads from the ``lightrag`` top-level key, falling back to
        ``loading.neo4j`` for connection parameters if not specified.

        Args:
            config: Parsed YAML config dict or a ``PipelineConfig`` Pydantic model
                    (as returned by ``get_config()``).
        """
        # Support both dict and Pydantic model (PipelineConfig) inputs
        if hasattr(config, "model_dump"):
            config_dict = config.model_dump()
        elif isinstance(config, dict):
            config_dict = config
        else:
            config_dict = dict(config)

        rag_cfg = config_dict.get("lightrag", {})

        # Flatten nested LLM section
        llm = rag_cfg.pop("llm", {})
        if llm:
            rag_cfg.setdefault("llm_model", llm.get("model"))
            rag_cfg.setdefault("llm_max_tokens", llm.get("max_tokens"))
            rag_cfg.setdefault("llm_max_async", llm.get("max_async"))
            rag_cfg.setdefault("llm_temperature", llm.get("temperature"))

        # Flatten nested chunking section
        chunking = rag_cfg.pop("chunking", {})
        if chunking:
            rag_cfg.setdefault("chunk_size", chunking.get("chunk_size"))
            rag_cfg.setdefault("chunk_overlap", chunking.get("chunk_overlap"))

        # Flatten nested community detection section
        community = rag_cfg.pop("community_detection", {})
        if community:
            rag_cfg.setdefault("community_algorithm", community.get("algorithm"))
            rag_cfg.setdefault("max_community_levels", community.get("max_levels"))
            rag_cfg.setdefault("community_resolution", community.get("resolution"))

        # Flatten nested retrieval section
        retrieval = rag_cfg.pop("retrieval", {})
        if retrieval:
            rag_cfg.setdefault("default_retrieval_mode", retrieval.get("default_mode"))
            rag_cfg.setdefault("retrieval_top_k", retrieval.get("top_k"))
            rag_cfg.setdefault("similarity_threshold", retrieval.get("similarity_threshold"))

        # Strip None values (from missing YAML keys) before constructing
        rag_cfg = {k: v for k, v in rag_cfg.items() if v is not None}

        return cls(**rag_cfg)
