"""PaECTER client for generating patent and SBIR award embeddings.

This module provides a cloud-first interface to the PaECTER model from HuggingFace
(mpi-inno-comp/paecter) for generating embeddings from patent and award text.

PaECTER (Patent Embeddings using Citation-informed TransformERs) generates
1024-dimensional dense vector embeddings optimized for patent similarity tasks.

Cloud-First Approach:
1. Try HuggingFace Inference API (if HUGGINGFACE_API_TOKEN is set)
2. Fall back to local GPU/CPU if API unavailable

Benefits:
- No model downloads in development (~500MB saved)
- Serverless scaling via HuggingFace infrastructure
- Pay-per-use pricing (~$0.0002/1k tokens)
- Automatic fallback for offline/large batch scenarios

References:
    - Model: https://huggingface.co/mpi-inno-comp/paecter
    - Paper: https://arxiv.org/pdf/2402.19411

Usage:
    >>> # Cloud-first (default) - uses Inference API if token available
    >>> client = PaECTERClient()
    >>>
    >>> # Force local GPU (skip API)
    >>> client = PaECTERClient(prefer_cloud=False)
    >>>
    >>> # Generate embeddings
    >>> texts = ["Patent about solar cells", "Innovation in AI"]
    >>> result = client.generate_embeddings(texts)
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import numpy as np
from loguru import logger


@dataclass
class EmbeddingResult:
    """Result from embedding generation."""

    embeddings: np.ndarray
    model_version: str
    generation_timestamp: float
    input_count: int
    dimension: int
    backend: str  # "cloud" or "local"


@runtime_checkable
class EmbeddingBackend(Protocol):
    """Protocol for embedding generation backends."""

    def generate_embeddings(
        self, texts: list[str], normalize: bool = True, **kwargs
    ) -> np.ndarray:
        """Generate embeddings for texts."""
        ...

    def is_available(self) -> bool:
        """Check if backend is available."""
        ...


class PaECTERClient:
    """Client for interacting with the PaECTER embedding model (cloud-first).

    This client automatically selects the best available backend:
    1. HuggingFace Inference API (cloud) - if HUGGINGFACE_API_TOKEN is set
    2. Local GPU/CPU - fallback for offline or large batch scenarios

    The model uses mean pooling and processes the first 512 tokens (~393 words)
    of the input text, generating 1024-dimensional embeddings.

    Attributes:
        model_name: HuggingFace model identifier
        backend: Active embedding backend (cloud or local)
        embedding_dim: Dimension of output embeddings (1024 for PaECTER)
        backend_type: Type of backend being used ("cloud" or "local")

    Example:
        >>> # Cloud-first (uses API if available)
        >>> client = PaECTERClient()
        >>> texts = ["Novel method for solar cell efficiency", "Deep learning for drug discovery"]
        >>> result = client.generate_embeddings(texts)
        >>> print(result.embeddings.shape)  # (2, 1024)
        >>> print(result.backend)  # "cloud" or "local"
        >>>
        >>> # Force local GPU
        >>> client = PaECTERClient(prefer_cloud=False)
    """

    def __init__(
        self,
        model_name: str = "mpi-inno-comp/paecter",
        prefer_cloud: bool = True,
        api_token: str | None = None,
        device: str | None = None,
        cache_folder: str | None = None,
    ):
        """Initialize the PaECTER client with cloud-first approach.

        Args:
            model_name: HuggingFace model identifier (default: mpi-inno-comp/paecter)
            prefer_cloud: If True, try HuggingFace Inference API first (default: True)
            api_token: HuggingFace API token. If None, reads from HUGGINGFACE_API_TOKEN env var.
            device: Device for local inference ('cpu', 'cuda', etc.). Only used if using local backend.
            cache_folder: Custom cache folder for local model files. Only used if using local backend.

        Raises:
            RuntimeError: If no backend is available
        """
        self.model_name = model_name
        self.backend: EmbeddingBackend | None = None
        self.backend_type: str = "unknown"
        self.embedding_dim: int = 1024  # PaECTER standard dimension

        # Determine if cloud should be preferred
        prefer_cloud = prefer_cloud and bool(
            os.getenv("ML_PREFER_CLOUD", "true").lower() in ("true", "1", "yes")
        )

        if prefer_cloud:
            # Try cloud first
            try:
                from .huggingface_inference import HuggingFaceInferenceClient

                cloud_backend = HuggingFaceInferenceClient(
                    model_name=model_name,
                    api_token=api_token,
                )

                if cloud_backend.is_available():
                    self.backend = cloud_backend  # type: ignore
                    self.backend_type = "cloud"
                    logger.info(f"Using HuggingFace Inference API for {model_name}")
                    return

            except Exception as e:
                logger.warning(
                    f"HuggingFace Inference API not available: {e}. Falling back to local GPU/CPU."
                )

        # Fallback to local GPU/CPU
        try:
            from .huggingface_inference import LocalGPUClient

            logger.info(f"Loading {model_name} for local inference...")
            local_backend = LocalGPUClient(
                model_name=model_name,
                device=device,
            )

            if local_backend.is_available():
                self.backend = local_backend  # type: ignore
                self.backend_type = "local"
                logger.info(f"Using local GPU/CPU for {model_name}")
                return

        except Exception as e:
            logger.error(f"Failed to initialize local GPU/CPU backend: {e}")
            raise RuntimeError(
                f"No embedding backend available. Tried cloud and local. Last error: {e}"
            ) from e

        # If we got here, no backend is available
        raise RuntimeError(
            "No embedding backend available. "
            "Either set HUGGINGFACE_API_TOKEN for cloud API "
            "or install sentence-transformers for local inference."
        )

    def generate_embeddings(
        self,
        texts: list[str],
        batch_size: int = 32,
        show_progress_bar: bool = False,
        normalize: bool = True,
    ) -> EmbeddingResult:
        """Generate embeddings for a list of texts.

        Args:
            texts: List of text strings to embed
            batch_size: Number of texts to process in each batch
            show_progress_bar: Whether to show progress bar (only for local backend)
            normalize: Whether to normalize embeddings to unit length (recommended for cosine similarity)

        Returns:
            EmbeddingResult containing embeddings and metadata

        Raises:
            ValueError: If texts is empty
            RuntimeError: If embedding generation fails

        Example:
            >>> client = PaECTERClient()
            >>> texts = ["First patent abstract", "Second patent abstract"]
            >>> result = client.generate_embeddings(texts)
            >>> similarities = result.embeddings @ result.embeddings.T
            >>> print(f"Using {result.backend} backend")
        """
        if not texts:
            raise ValueError("texts cannot be empty")

        if self.backend is None:
            raise RuntimeError("No embedding backend available")

        logger.debug(
            f"Generating embeddings for {len(texts)} texts using {self.backend_type} backend"
        )
        start_time = time.time()

        try:
            # Generate embeddings using active backend
            embeddings = self.backend.generate_embeddings(
                texts=texts,
                normalize=normalize,
                batch_size=batch_size,
                # Only pass show_progress_bar to local backend
                **(
                    {"show_progress_bar": show_progress_bar}
                    if self.backend_type == "local"
                    else {}
                ),
            )

            generation_time = time.time() - start_time
            logger.info(
                f"Generated {len(texts)} embeddings in {generation_time:.2f}s "
                f"({len(texts)/generation_time:.1f} embeddings/s) "
                f"using {self.backend_type} backend"
            )

            return EmbeddingResult(
                embeddings=embeddings,
                model_version=self.model_name,
                generation_timestamp=time.time(),
                input_count=len(texts),
                dimension=embeddings.shape[1] if len(embeddings.shape) > 1 else 0,
                backend=self.backend_type,
            )

        except Exception as e:
            logger.error(f"Failed to generate embeddings: {e}")
            raise RuntimeError(f"Embedding generation failed: {e}") from e

    def compute_similarity(
        self, embeddings1: np.ndarray, embeddings2: np.ndarray
    ) -> np.ndarray:
        """Compute cosine similarity between two sets of embeddings.

        Args:
            embeddings1: First set of embeddings (N x D)
            embeddings2: Second set of embeddings (M x D)

        Returns:
            Similarity matrix (N x M) with cosine similarity scores

        Example:
            >>> client = PaECTERClient()
            >>> awards = client.generate_embeddings(["Award text 1", "Award text 2"])
            >>> patents = client.generate_embeddings(["Patent text 1", "Patent text 2"])
            >>> similarities = client.compute_similarity(awards.embeddings, patents.embeddings)
            >>> # similarities[i, j] is similarity between award i and patent j
        """
        # If embeddings are already normalized, cosine similarity is just dot product
        return embeddings1 @ embeddings2.T

    def get_backend_info(self) -> dict[str, str]:
        """Get information about the active backend.

        Returns:
            Dictionary with backend information

        Example:
            >>> client = PaECTERClient()
            >>> info = client.get_backend_info()
            >>> print(info)
            {'backend': 'cloud', 'model': 'mpi-inno-comp/paecter'}
        """
        return {
            "backend": self.backend_type,
            "model": self.model_name,
            "embedding_dimension": str(self.embedding_dim),
        }

    @staticmethod
    def prepare_patent_text(title: str | None, abstract: str | None) -> str:
        """Prepare patent text for embedding generation.

        Concatenates title and abstract as recommended by PaECTER authors.

        Args:
            title: Patent title
            abstract: Patent abstract

        Returns:
            Concatenated text suitable for PaECTER

        Example:
            >>> text = PaECTERClient.prepare_patent_text(
            ...     "Novel Solar Cell Design",
            ...     "This invention relates to improved solar cells..."
            ... )
        """
        parts = []
        if title:
            parts.append(title.strip())
        if abstract:
            parts.append(abstract.strip())

        return " ".join(parts) if parts else ""

    @staticmethod
    def prepare_award_text(
        solicitation_title: str | None, abstract: str | None, award_title: str | None = None
    ) -> str:
        """Prepare SBIR award text for embedding generation.

        Concatenates solicitation title, award title, and abstract.

        Args:
            solicitation_title: Solicitation title
            abstract: Award abstract
            award_title: Award/project title (optional)

        Returns:
            Concatenated text suitable for PaECTER

        Example:
            >>> text = PaECTERClient.prepare_award_text(
            ...     "Advanced Manufacturing Technologies",
            ...     "Development of novel 3D printing methods..."
            ... )
        """
        parts = []
        if solicitation_title:
            parts.append(solicitation_title.strip())
        if award_title:
            parts.append(award_title.strip())
        if abstract:
            parts.append(abstract.strip())

        return " ".join(parts) if parts else ""

    @staticmethod
    def check_cloud_availability() -> bool:
        """Check if HuggingFace Inference API is available.

        Returns:
            True if HUGGINGFACE_API_TOKEN is set, False otherwise

        Example:
            >>> if PaECTERClient.check_cloud_availability():
            ...     print("Cloud API available")
            ... else:
            ...     print("Will use local GPU/CPU")
        """
        return bool(os.getenv("HUGGINGFACE_API_TOKEN"))
