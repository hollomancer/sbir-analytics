"""Machine learning configuration schemas (PaECTER, embeddings)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class PaECTERApiConfig(BaseModel):
    """Configuration for PaECTER HuggingFace Inference API."""

    token_env: str = Field(
        default="HF_TOKEN", description="Environment variable for HuggingFace API token"
    )
    batch_size: int = Field(default=32, ge=1, description="Batch size for API requests")
    max_qps: int = Field(default=10, ge=1, description="Maximum queries per second")
    timeout_seconds: int = Field(default=60, ge=1, description="API request timeout")
    max_retries: int = Field(default=5, ge=0, description="Maximum retry attempts")
    retry_backoff_seconds: float = Field(
        default=2.0, ge=0, description="Base backoff between retries"
    )


class PaECTERLocalConfig(BaseModel):
    """Configuration for local PaECTER model inference."""

    model_name: str = Field(
        default="mpi-inno-comp/paecter", description="HuggingFace model identifier"
    )
    device: str = Field(
        default="auto", description="Device for inference (auto, cpu, cuda)"
    )
    batch_size: int = Field(default=32, ge=1, description="Batch size for local inference")


class PaECTERTextConfig(BaseModel):
    """Configuration for text preprocessing before embedding."""

    max_length: int = Field(default=512, ge=1, description="Maximum token length (truncation)")
    award_fields: list[str] = Field(
        default_factory=lambda: ["solicitation_title", "abstract", "award_title"],
        description="Award fields to concatenate for embedding",
    )
    patent_fields: list[str] = Field(
        default_factory=lambda: ["title", "abstract"],
        description="Patent fields to concatenate for embedding",
    )


class PaECTERNeo4jConfig(BaseModel):
    """Configuration for loading PaECTER similarity edges into Neo4j."""

    enabled: bool = Field(default=False, description="Enable Neo4j similarity edge loading")
    batch_size: int = Field(default=1000, ge=1, description="Batch size for Neo4j loading")
    dry_run: bool = Field(default=False, description="Run without committing changes")
    prune_previous: bool = Field(
        default=False, description="Remove previous similarity edges before loading"
    )


class PaECTERConfig(BaseModel):
    """Configuration for PaECTER patent-award similarity embeddings."""

    provider: str = Field(
        default="huggingface",
        description="Provider selection: huggingface (API) or local (sentence-transformers)",
    )
    use_local: bool = Field(
        default=False, description="Use local model instead of API"
    )
    api: PaECTERApiConfig = Field(default_factory=PaECTERApiConfig)
    local: PaECTERLocalConfig = Field(default_factory=PaECTERLocalConfig)
    text: PaECTERTextConfig = Field(default_factory=PaECTERTextConfig)
    neo4j: PaECTERNeo4jConfig = Field(default_factory=PaECTERNeo4jConfig)

    # Similarity computation
    similarity_threshold: float = Field(
        default=0.80,
        ge=0.0,
        le=1.0,
        description="Minimum similarity score to include in results",
    )
    top_k: int = Field(default=10, ge=1, description="Number of top matches per award")

    # Validation thresholds
    coverage_threshold_awards: float = Field(
        default=0.95,
        ge=0.0,
        le=1.0,
        description="Minimum fraction of awards with valid embeddings",
    )
    coverage_threshold_patents: float = Field(
        default=0.98,
        ge=0.0,
        le=1.0,
        description="Minimum fraction of patents with valid embeddings",
    )

    # Caching
    enable_cache: bool = Field(
        default=False, description="Enable embedding caching to disk"
    )


class MLConfig(BaseModel):
    """Machine learning configuration."""

    paecter: PaECTERConfig = Field(
        default_factory=PaECTERConfig,
        description="PaECTER patent-award similarity configuration",
    )


__all__ = [
    "MLConfig",
    "PaECTERApiConfig",
    "PaECTERConfig",
    "PaECTERLocalConfig",
    "PaECTERNeo4jConfig",
    "PaECTERTextConfig",
]
