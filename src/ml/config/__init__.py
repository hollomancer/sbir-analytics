"""Configuration loaders for CET taxonomy, hyperparameters, and SPECTER2 client."""

from pydantic import BaseModel, Field

from .taxonomy_loader import ClassificationConfig, TaxonomyConfig, TaxonomyLoader


class Specter2ClientConfig(BaseModel):
    """Configuration for the Specter2Client."""

    model_name: str = Field("allenai/specter2", description="HuggingFace model identifier")
    use_local: bool = Field(
        False, description="If True, use local sentence-transformers. If False, use API."
    )
    hf_token: str | None = Field(
        None, description="HuggingFace API token. If None, read from HF_TOKEN env var."
    )
    device: str | None = Field(None, description="Device for local inference ('cpu', 'cuda').")
    cache_folder: str | None = Field(None, description="Cache folder for local model.")
    enable_cache: bool = Field(True, description="Enable in-memory caching for embeddings.")


# Backward compatibility alias
PaECTERClientConfig = Specter2ClientConfig


__all__ = [
    "ClassificationConfig",
    "TaxonomyConfig",
    "TaxonomyLoader",
    "Specter2ClientConfig",
    "PaECTERClientConfig",
]
