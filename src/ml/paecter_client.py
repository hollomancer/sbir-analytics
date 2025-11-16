"""PaECTER client for generating patent and SBIR award embeddings.

This module provides a simple interface to the PaECTER model from HuggingFace
(mpi-inno-comp/paecter) for generating embeddings from patent and award text.

PaECTER (Patent Embeddings using Citation-informed TransformERs) generates
1024-dimensional dense vector embeddings optimized for patent similarity tasks.

References:
    - Model: https://huggingface.co/mpi-inno-comp/paecter
    - Paper: https://arxiv.org/pdf/2402.19411
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import numpy as np
from loguru import logger

try:
    from sentence_transformers import SentenceTransformer
except ImportError:
    SentenceTransformer = None  # type: ignore


@dataclass
class EmbeddingResult:
    """Result from embedding generation."""

    embeddings: np.ndarray
    model_version: str
    generation_timestamp: float
    input_count: int
    dimension: int


class PaECTERClient:
    """Client for interacting with the PaECTER embedding model.

    This client uses the sentence-transformers library to generate embeddings
    from patent and SBIR award text using the mpi-inno-comp/paecter model.

    The model uses mean pooling and processes the first 512 tokens (~393 words)
    of the input text.

    Attributes:
        model_name: HuggingFace model identifier
        model: Loaded SentenceTransformer model instance
        embedding_dim: Dimension of output embeddings (1024 for PaECTER)

    Example:
        >>> client = PaECTERClient()
        >>> texts = ["Novel method for solar cell efficiency", "Deep learning for drug discovery"]
        >>> result = client.generate_embeddings(texts)
        >>> print(result.embeddings.shape)
        (2, 1024)
    """

    def __init__(
        self,
        model_name: str = "mpi-inno-comp/paecter",
        device: str | None = None,
        cache_folder: str | None = None,
    ):
        """Initialize the PaECTER client.

        Args:
            model_name: HuggingFace model identifier (default: mpi-inno-comp/paecter)
            device: Device to use for inference ('cpu', 'cuda', etc.). If None, auto-detect.
            cache_folder: Custom cache folder for model files. If None, use default.

        Raises:
            ImportError: If sentence-transformers is not installed
            RuntimeError: If model loading fails
        """
        if SentenceTransformer is None:
            raise ImportError(
                "sentence-transformers is required for PaECTER. "
                "Install with: pip install sentence-transformers"
            )

        self.model_name = model_name
        logger.info(f"Loading PaECTER model: {model_name}")

        try:
            kwargs: dict[str, Any] = {}
            if device is not None:
                kwargs["device"] = device
            if cache_folder is not None:
                kwargs["cache_folder"] = cache_folder

            self.model = SentenceTransformer(model_name, **kwargs)
            self.embedding_dim = self.model.get_sentence_embedding_dimension()  # type: ignore

            logger.info(
                f"Successfully loaded PaECTER model. Embedding dimension: {self.embedding_dim}"
            )
        except Exception as e:
            logger.error(f"Failed to load PaECTER model: {e}")
            raise RuntimeError(f"Failed to load model {model_name}: {e}") from e

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
            show_progress_bar: Whether to show progress bar during encoding
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
        """
        if not texts:
            raise ValueError("texts cannot be empty")

        logger.debug(f"Generating embeddings for {len(texts)} texts")
        start_time = time.time()

        try:
            embeddings = self.model.encode(
                texts,
                batch_size=batch_size,
                show_progress_bar=show_progress_bar,
                normalize_embeddings=normalize,
                convert_to_numpy=True,
            )

            generation_time = time.time() - start_time
            logger.info(
                f"Generated {len(texts)} embeddings in {generation_time:.2f}s "
                f"({len(texts)/generation_time:.1f} embeddings/s)"
            )

            return EmbeddingResult(
                embeddings=embeddings,  # type: ignore
                model_version=self.model_name,
                generation_timestamp=time.time(),
                input_count=len(texts),
                dimension=self.embedding_dim,
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
