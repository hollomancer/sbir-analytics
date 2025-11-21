"""HuggingFace Inference API client for cloud-first ML embeddings.

This module implements a cloud-first approach to ML inference:
1. Try HuggingFace Inference API (serverless, pay-per-use)
2. Fall back to local GPU/CPU if API unavailable

Benefits of cloud-first approach:
- No model downloads required (saves ~500MB+ per model)
- Serverless scaling (HuggingFace infrastructure)
- Pay-per-use pricing (~$0.0002/1k tokens)
- Faster iteration during development
- Automatic fallback for offline/large batch scenarios

Usage:
    >>> from src.ml.huggingface_inference import HuggingFaceInferenceClient
    >>>
    >>> # Use HuggingFace Inference API
    >>> client = HuggingFaceInferenceClient(
    ...     model_name="mpi-inno-comp/paecter",
    ...     api_token="hf_xxxxx"  # or set HUGGINGFACE_API_TOKEN env var
    ... )
    >>>
    >>> texts = ["Patent about solar cells", "Innovation in AI"]
    >>> embeddings = client.generate_embeddings(texts)
    >>> print(embeddings.shape)  # (2, 1024)

Configuration:
    Set environment variables:
    - HUGGINGFACE_API_TOKEN: Your HuggingFace API token
    - ML_PREFER_CLOUD: "true" to prefer cloud API (default: true)

Cost Analysis:
    HuggingFace Inference API:
    - ~$0.0002 per 1k tokens
    - 1k SBIR abstracts (~500 words each) ≈ $0.10
    - Monthly budget: $5-10 for typical usage

    Local GPU (for comparison):
    - AWS g4dn.xlarge: ~$0.50/hour = $360/month (24/7)
    - Use local GPU for large batches (>10k texts)
"""

from __future__ import annotations

import os
import time
from typing import Any

import numpy as np
from loguru import logger


try:
    from huggingface_hub import InferenceClient as HFInferenceClient
    from huggingface_hub.utils import HfHubHTTPError

    HF_HUB_AVAILABLE = True
except ImportError:
    HF_HUB_AVAILABLE = False
    HfHubHTTPError = Exception  # type: ignore


class HuggingFaceInferenceClient:
    """HuggingFace Inference API client for cloud-based embeddings.

    This client uses the HuggingFace Inference API to generate embeddings
    without downloading models locally. It's ideal for:
    - Development environments (no model downloads)
    - Small to medium batch sizes (<10k texts)
    - Cost-effective production deployments

    Attributes:
        model_name: HuggingFace model identifier
        api_token: HuggingFace API token (from env or parameter)
        client: HuggingFace InferenceClient instance
        available: Whether the client is properly configured

    Example:
        >>> client = HuggingFaceInferenceClient("mpi-inno-comp/paecter")
        >>> embeddings = client.generate_embeddings(["Text 1", "Text 2"])
    """

    def __init__(
        self,
        model_name: str,
        api_token: str | None = None,
        timeout: float = 30.0,
    ):
        """Initialize HuggingFace Inference API client.

        Args:
            model_name: HuggingFace model identifier (e.g., "mpi-inno-comp/paecter")
            api_token: HuggingFace API token. If None, reads from HUGGINGFACE_API_TOKEN env var.
            timeout: Request timeout in seconds (default: 30.0)

        Raises:
            ImportError: If huggingface_hub is not installed
            ValueError: If no API token is provided
        """
        if not HF_HUB_AVAILABLE:
            raise ImportError(
                "huggingface_hub is required for HuggingFace Inference API. "
                "Install with: pip install huggingface_hub"
            )

        self.model_name = model_name
        self.api_token = api_token or os.getenv("HUGGINGFACE_API_TOKEN")
        self.timeout = timeout

        if not self.api_token:
            raise ValueError(
                "HuggingFace API token is required. "
                "Provide via api_token parameter or HUGGINGFACE_API_TOKEN environment variable. "
                "Get a token at: https://huggingface.co/settings/tokens"
            )

        try:
            self.client = HFInferenceClient(token=self.api_token, timeout=self.timeout)
            self.available = True
            logger.info(f"HuggingFace Inference API client initialized for model: {model_name}")
        except Exception as e:
            self.available = False
            logger.error(f"Failed to initialize HuggingFace Inference API client: {e}")
            raise

    def generate_embeddings(
        self,
        texts: list[str],
        normalize: bool = True,
        batch_size: int = 32,
        retry_on_error: bool = True,
        max_retries: int = 3,
    ) -> np.ndarray:
        """Generate embeddings for texts using HuggingFace Inference API.

        Args:
            texts: List of text strings to embed
            normalize: Whether to normalize embeddings to unit length (default: True)
            batch_size: Number of texts to process in each API call (default: 32)
            retry_on_error: Whether to retry on transient errors (default: True)
            max_retries: Maximum number of retries (default: 3)

        Returns:
            NumPy array of embeddings (N x D) where N is number of texts and D is embedding dimension

        Raises:
            ValueError: If texts is empty
            RuntimeError: If API calls fail after retries

        Example:
            >>> client = HuggingFaceInferenceClient("mpi-inno-comp/paecter")
            >>> texts = ["Innovation in solar energy", "Deep learning for healthcare"]
            >>> embeddings = client.generate_embeddings(texts)
            >>> print(embeddings.shape)  # (2, 1024)
            >>> # Compute similarity
            >>> similarity = embeddings @ embeddings.T
            >>> print(similarity[0, 1])  # Cosine similarity between texts
        """
        if not texts:
            raise ValueError("texts cannot be empty")

        if not self.available:
            raise RuntimeError("HuggingFace Inference API client is not available")

        logger.debug(f"Generating embeddings for {len(texts)} texts via Inference API")
        start_time = time.time()

        all_embeddings = []
        total_batches = (len(texts) + batch_size - 1) // batch_size

        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            batch_num = i // batch_size + 1

            logger.debug(f"Processing batch {batch_num}/{total_batches} ({len(batch)} texts)")

            retry_count = 0

            while retry_count <= (max_retries if retry_on_error else 0):
                try:
                    # Use feature_extraction endpoint
                    batch_embeddings = self.client.feature_extraction(
                        text=batch,
                        model=self.model_name,
                    )

                    # Convert to numpy array
                    if isinstance(batch_embeddings, list):
                        batch_embeddings = np.array(batch_embeddings)

                    all_embeddings.append(batch_embeddings)
                    break  # Success, exit retry loop

                except HfHubHTTPError as e:
                    retry_count += 1

                    if retry_count <= max_retries and retry_on_error:
                        wait_time = 2**retry_count  # Exponential backoff
                        logger.warning(
                            f"API error (attempt {retry_count}/{max_retries}): {e}. "
                            f"Retrying in {wait_time}s..."
                        )
                        time.sleep(wait_time)
                    else:
                        logger.error(f"API call failed after {retry_count} retries: {e}")
                        raise RuntimeError(
                            f"HuggingFace Inference API failed after {max_retries} retries: {e}"
                        ) from e

                except Exception as e:
                    logger.error(f"Unexpected error in API call: {e}")
                    raise RuntimeError(f"Embedding generation failed: {e}") from e

        # Concatenate all batch embeddings
        embeddings_array = (
            np.vstack(all_embeddings) if len(all_embeddings) > 1 else all_embeddings[0]
        )

        # Normalize if requested
        if normalize:
            norms = np.linalg.norm(embeddings_array, axis=1, keepdims=True)
            embeddings_array = embeddings_array / (norms + 1e-8)  # Avoid division by zero

        generation_time = time.time() - start_time
        texts_per_second = len(texts) / generation_time if generation_time > 0 else 0

        logger.info(
            f"Generated {len(texts)} embeddings in {generation_time:.2f}s "
            f"({texts_per_second:.1f} texts/s) via HuggingFace Inference API"
        )

        return embeddings_array

    def is_available(self) -> bool:
        """Check if the Inference API client is available and configured.

        Returns:
            True if client is properly configured, False otherwise
        """
        return self.available

    @staticmethod
    def check_token() -> bool:
        """Check if HuggingFace API token is available in environment.

        Returns:
            True if HUGGINGFACE_API_TOKEN is set, False otherwise
        """
        return bool(os.getenv("HUGGINGFACE_API_TOKEN"))


class LocalGPUClient:
    """Local GPU/CPU client for embedding generation (fallback).

    This client uses sentence-transformers to generate embeddings locally.
    Use when:
    - Processing large batches (>10k texts) - more cost-effective
    - Need offline capability
    - Have GPU available for faster processing

    Attributes:
        model_name: HuggingFace model identifier
        model: Loaded SentenceTransformer model instance
        device: Device being used (cuda/cpu)

    Example:
        >>> client = LocalGPUClient("mpi-inno-comp/paecter")
        >>> embeddings = client.generate_embeddings(["Text 1", "Text 2"])
    """

    def __init__(self, model_name: str, device: str | None = None):
        """Initialize local GPU/CPU client.

        Args:
            model_name: HuggingFace model identifier
            device: Device to use ('cpu', 'cuda', etc.). If None, auto-detect.

        Raises:
            ImportError: If sentence-transformers is not installed
            RuntimeError: If model loading fails
        """
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            raise ImportError(
                "sentence-transformers is required for local GPU client. "
                "Install with: pip install sentence-transformers"
            )

        self.model_name = model_name

        try:
            kwargs: dict[str, Any] = {}
            if device is not None:
                kwargs["device"] = device

            logger.info(f"Loading model {model_name} for local inference...")
            self.model = SentenceTransformer(model_name, **kwargs)
            self.device = self.model.device
            logger.info(f"Local GPU client initialized for {model_name} (device: {self.device})")
        except Exception as e:
            logger.error(f"Failed to load local model: {e}")
            raise RuntimeError(f"Failed to load model {model_name}: {e}") from e

    def generate_embeddings(
        self,
        texts: list[str],
        normalize: bool = True,
        batch_size: int = 32,
        show_progress_bar: bool = False,
    ) -> np.ndarray:
        """Generate embeddings locally using GPU/CPU.

        Args:
            texts: List of text strings to embed
            normalize: Whether to normalize embeddings to unit length
            batch_size: Number of texts to process in each batch
            show_progress_bar: Whether to show progress bar

        Returns:
            NumPy array of embeddings (N x D)

        Example:
            >>> client = LocalGPUClient("mpi-inno-comp/paecter", device="cuda")
            >>> embeddings = client.generate_embeddings(texts, batch_size=64)
        """
        if not texts:
            raise ValueError("texts cannot be empty")

        logger.debug(
            f"Generating embeddings for {len(texts)} texts locally (device: {self.device})"
        )
        start_time = time.time()

        embeddings = self.model.encode(
            texts,
            batch_size=batch_size,
            show_progress_bar=show_progress_bar,
            normalize_embeddings=normalize,
            convert_to_numpy=True,
        )

        generation_time = time.time() - start_time
        texts_per_second = len(texts) / generation_time if generation_time > 0 else 0

        logger.info(
            f"Generated {len(texts)} embeddings in {generation_time:.2f}s "
            f"({texts_per_second:.1f} texts/s) using local {self.device}"
        )

        return embeddings  # type: ignore

    def is_available(self) -> bool:
        """Check if local client is available.

        Returns:
            True if model is loaded successfully
        """
        return self.model is not None
