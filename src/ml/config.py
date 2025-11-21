"""
Pydantic models for ML configuration.
"""

from pydantic import BaseModel, Field


class PaECTERClientConfig(BaseModel):
    """
    Configuration for the PaECTERClient.
    """
    model_name: str = Field("mpi-inno-comp/paecter", description="HuggingFace model identifier")
    use_local: bool = Field(False, description="If True, use local sentence-transformers. If False, use API.")
    hf_token: str | None = Field(None, description="HuggingFace API token. If None, read from HF_TOKEN env var.")
    device: str | None = Field(None, description="Device for local inference ('cpu', 'cuda').")
    cache_folder: str | None = Field(None, description="Cache folder for local model.")
    enable_cache: bool = Field(True, description="Enable in-memory caching for embeddings.")
