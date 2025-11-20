"""PaECTER client for generating patent and SBIR award embeddings.

This module provides a simple interface to the PaECTER model from HuggingFace
(mpi-inno-comp/paecter) for generating embeddings from patent and award text.

By default, this client uses the HuggingFace Inference API (no local model download
or GPU required). You can optionally use local inference with sentence-transformers.

PaECTER (Patent Embeddings using Citation-informed TransformERs) generates
1024-dimensional dense vector embeddings optimized for patent similarity tasks.

References:
    - Model: https://huggingface.co/mpi-inno-comp/paecter
    - Paper: https://arxiv.org/pdf/2402.19411
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, Literal

import numpy as np
from loguru import logger

try:
    from huggingface_hub import InferenceClient
except ImportError:
    InferenceClient = None  # type: ignore

try:
    from sentence_transformers import SentenceTransformer
except ImportError:
    SentenceTransformer = None  # type: ignore


@dataclass
class EmbeddingResult:
    """Result from embedding generation.

    Attributes:
        embeddings: Generated embedding vectors (N x D array)
        model_version: Model identifier (e.g., "mpi-inno-comp/paecter")
        generation_timestamp: Elapsed time in seconds for generation (not epoch timestamp)
        input_count: Number of input texts processed
        dimension: Embedding dimension (1024 for PaECTER)
        inference_mode: "api" or "local"
    """

    embeddings: np.ndarray
    model_version: str
    generation_timestamp: float  # Elapsed time in seconds (not epoch timestamp)
    input_count: int
    dimension: int
    inference_mode: Literal["api", "local"]


from src.ml.config import PaECTERClientConfig

class PaECTERClient:
    """Client for interacting with the PaECTER embedding model."""

    def __init__(self, config: PaECTERClientConfig):
        """Initialize the PaECTER client."""
        self.config = config
        self.model_name = config.model_name
        self.embedding_dim = 1024  # PaECTER embeddings are 1024-dimensional
        self.cache: dict[str, np.ndarray] = {}

        if self.config.use_local:
            self._init_local_mode(config.device, config.cache_folder)
        else:
            self._init_api_mode(config.hf_token)

    def _init_api_mode(self, hf_token: str | None):
        """Initialize API mode using HuggingFace Inference API."""
        if InferenceClient is None:
            raise ImportError(
                "huggingface_hub is required for API mode. "
                "Install with: pip install huggingface-hub"
            )

        # Get token from parameter or environment
        token = hf_token or os.getenv("HF_TOKEN")
        if not token:
            logger.warning(
                "No HuggingFace token provided. API calls may fail or have rate limits. "
                "Set HF_TOKEN environment variable or pass hf_token parameter."
            )

        self.inference_mode = "api"
        self.client = InferenceClient(token=token)
        logger.info(f"Initialized PaECTER client in API mode: {self.model_name}")

    def _init_local_mode(self, device: str | None, cache_folder: str | None):
        """Initialize local mode using sentence-transformers."""
        if SentenceTransformer is None:
            raise ImportError(
                "sentence-transformers is required for local mode. "
                "Install with: pip install 'sbir-analytics[paecter-local]' or "
                "pip install sentence-transformers"
            )

        self.inference_mode = "local"
        logger.info(f"Loading PaECTER model locally: {self.model_name}")

        try:
            kwargs: dict[str, Any] = {}
            if device is not None:
                kwargs["device"] = device
            if cache_folder is not None:
                kwargs["cache_folder"] = cache_folder

            self.model = SentenceTransformer(self.model_name, **kwargs)
            self.embedding_dim = self.model.get_sentence_embedding_dimension()  # type: ignore

            logger.info(
                f"Successfully loaded local PaECTER model. "
                f"Embedding dimension: {self.embedding_dim}"
            )
        except Exception as e:
            logger.error(f"Failed to load local PaECTER model: {e}")
            raise RuntimeError(f"Failed to load model {self.model_name}: {e}") from e

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
            show_progress_bar: Whether to show progress bar (local mode only)
            normalize: Whether to normalize embeddings to unit length (recommended)

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

        if self.config.enable_cache:
            cached_embeddings = []
            texts_to_process = []
            indices_to_process = []
            
            for i, text in enumerate(texts):
                if text in self.cache:
                    cached_embeddings.append((i, self.cache[text]))
                else:
                    texts_to_process.append(text)
                    indices_to_process.append(i)

            if not texts_to_process:
                logger.debug("All embeddings found in cache.")
                embeddings = np.zeros((len(texts), self.embedding_dim))
                for i, embedding in cached_embeddings:
                    embeddings[i] = embedding
                return EmbeddingResult(
                    embeddings=embeddings,
                    model_version=self.model_name,
                    generation_timestamp=0.0,
                    input_count=len(texts),
                    dimension=self.embedding_dim,
                    inference_mode=self.inference_mode,
                )
        else:
            texts_to_process = texts

        logger.debug(f"Generating embeddings for {len(texts_to_process)} texts using {self.inference_mode} mode")
        start_time = time.time()

        try:
            if self.inference_mode == "api":
                new_embeddings = self._generate_embeddings_api(texts_to_process, batch_size, normalize)
            else:
                new_embeddings = self._generate_embeddings_local(
                    texts_to_process, batch_size, show_progress_bar, normalize
                )

            if self.config.enable_cache:
                for text, embedding in zip(texts_to_process, new_embeddings):
                    self.cache[text] = embedding

                # Combine cached and new embeddings
                embeddings = np.zeros((len(texts), self.embedding_dim))
                for i, embedding in cached_embeddings:
                    embeddings[i] = embedding
                
                for i, embedding in zip(indices_to_process, new_embeddings):
                    embeddings[i] = embedding
            else:
                embeddings = new_embeddings

            generation_time = time.time() - start_time
            logger.info(
                f"Generated {len(texts_to_process)} embeddings in {generation_time:.2f}s "
                f"({len(texts_to_process)/generation_time:.1f} embeddings/s if generation_time > 0 else 0) "
                f"[{self.inference_mode} mode]"
            )

            return EmbeddingResult(
                embeddings=embeddings,
                model_version=self.model_name,
                generation_timestamp=generation_time,
                input_count=len(texts),
                dimension=self.embedding_dim,
                inference_mode=self.inference_mode,
            )

        except Exception as e:
            logger.error(f"Failed to generate embeddings: {e}")
            raise RuntimeError(f"Embedding generation failed: {e}") from e

    def _generate_embeddings_api(
        self, texts: list[str], batch_size: int, normalize: bool
    ) -> np.ndarray:
        """Generate embeddings using HuggingFace Inference API."""
        all_embeddings = []

        # Process in batches to avoid API limits
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]

            # Use feature extraction endpoint
            response = self.client.feature_extraction(
                batch,
                model=self.model_name,
            )

            # Convert to numpy array
            batch_embeddings = np.array(response)

            # Handle both single and batch responses
            if len(batch) == 1 and batch_embeddings.ndim == 1:
                batch_embeddings = batch_embeddings.reshape(1, -1)

            all_embeddings.append(batch_embeddings)

            logger.debug(f"Processed batch {i//batch_size + 1}/{(len(texts) + batch_size - 1)//batch_size}")

        embeddings = np.vstack(all_embeddings)

        # Normalize if requested
        if normalize:
            norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
            embeddings = embeddings / norms

        return embeddings

    def _generate_embeddings_local(
        self, texts: list[str], batch_size: int, show_progress_bar: bool, normalize: bool
    ) -> np.ndarray:
        """Generate embeddings using local sentence-transformers model."""
        embeddings = self.model.encode(
            texts,
            batch_size=batch_size,
            show_progress_bar=show_progress_bar,
            normalize_embeddings=normalize,
            convert_to_numpy=True,
        )
        return embeddings  # type: ignore

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
