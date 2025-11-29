"""Integration tests for PaECTER client.

This module tests the PaECTER embedding generation functionality using
sample SBIR award and patent data.

By default, tests use local mode (requires sentence-transformers).
To test API mode, set HF_TOKEN environment variable and use use_local=False.

Tests are marked as integration tests and require:
- API mode: huggingface_hub library + HF_TOKEN env var
- Local mode: sentence-transformers library (first run downloads ~500MB model)
"""

import os

import numpy as np
import pytest

from src.ml.paecter_client import EmbeddingResult, PaECTERClient


# Sample SBIR award data
SAMPLE_AWARDS = [
    {
        "award_id": "AWARD-001",
        "solicitation_title": "Advanced Manufacturing Technologies",
        "award_title": "Novel 3D Printing Method for Aerospace Components",
        "abstract": (
            "This Phase I SBIR project will develop an innovative additive manufacturing "
            "technique for producing high-strength aerospace components using advanced "
            "materials. The method combines selective laser melting with in-situ alloy "
            "formation to achieve superior mechanical properties."
        ),
    },
    {
        "award_id": "AWARD-002",
        "solicitation_title": "Artificial Intelligence and Machine Learning",
        "award_title": "Deep Learning for Drug Discovery",
        "abstract": (
            "This project proposes a novel deep learning architecture for predicting "
            "drug-target interactions. Using transformer-based models and molecular "
            "fingerprints, we aim to accelerate the drug discovery process and identify "
            "promising therapeutic candidates for cancer treatment."
        ),
    },
    {
        "award_id": "AWARD-003",
        "solicitation_title": "Renewable Energy Systems",
        "award_title": "High-Efficiency Perovskite Solar Cells",
        "abstract": (
            "This Phase II SBIR award supports the development of next-generation "
            "perovskite solar cells with improved stability and efficiency. Our approach "
            "uses novel encapsulation techniques and interface engineering to achieve "
            "power conversion efficiencies exceeding 25%."
        ),
    },
]

# Sample patent data
SAMPLE_PATENTS = [
    {
        "patent_id": "US-10123456",
        "title": "Method for Additive Manufacturing of Metal Parts",
        "abstract": (
            "A method for producing metal components using layer-by-layer deposition. "
            "The invention includes a laser system for selective melting of metal powder "
            "and control systems for optimizing part quality and mechanical properties."
        ),
    },
    {
        "patent_id": "US-10234567",
        "title": "Neural Network Architecture for Molecular Property Prediction",
        "abstract": (
            "A deep learning system for predicting molecular properties and bioactivity. "
            "The invention uses graph neural networks to process molecular structures "
            "and transformer attention mechanisms for improved prediction accuracy."
        ),
    },
    {
        "patent_id": "US-10345678",
        "title": "High-Performance Photovoltaic Device",
        "abstract": (
            "A solar cell device with improved efficiency and stability. The invention "
            "features a multi-layer architecture with perovskite absorber materials and "
            "advanced encapsulation for protection against environmental degradation."
        ),
    },
]


@pytest.fixture(scope="module")
def paecter_client():
    """Create a PaECTER client for testing.

    This fixture creates a single client instance that is reused across all tests
    in this module to avoid reloading the model multiple times.

    Uses local mode by default (requires sentence-transformers).
    Set USE_PAECTER_API=1 environment variable to test API mode instead.
    """
    use_api = os.getenv("USE_PAECTER_API") == "1"

    if use_api:
        # API mode - requires HF_TOKEN
        pytest.importorskip("huggingface_hub")
        # Use hf_token fixture to skip if not available
        if not os.getenv("HF_TOKEN"):
            pytest.skip("HF_TOKEN environment variable required for API mode")
        from src.ml.config import PaECTERClientConfig

        config = PaECTERClientConfig(use_local=False)
        return PaECTERClient(config=config)
    else:
        # Local mode - requires sentence-transformers
        pytest.importorskip("sentence_transformers")
        from src.ml.config import PaECTERClientConfig

        config = PaECTERClientConfig(use_local=True)
        return PaECTERClient(config=config)


@pytest.mark.integration
@pytest.mark.slow
class TestPaECTERClient:
    """Integration tests for PaECTER client."""

    def test_client_initialization(self, paecter_client):
        """Test that client initializes successfully."""
        assert paecter_client.inference_mode in ("api", "local")
        assert paecter_client.embedding_dim == 1024  # PaECTER produces 1024-dim embeddings
        assert paecter_client.model_name == "mpi-inno-comp/paecter"

        # Check mode-specific attributes
        if paecter_client.inference_mode == "local":
            assert hasattr(paecter_client, "model")
            assert paecter_client.model is not None
        else:
            assert hasattr(paecter_client, "client")
            assert paecter_client.client is not None

    def test_generate_embeddings_single(self, paecter_client):
        """Test embedding generation for a single text."""
        texts = ["This is a test patent abstract about solar cells."]
        result = paecter_client.generate_embeddings(texts)

        assert isinstance(result, EmbeddingResult)
        assert result.embeddings.shape == (1, 1024)
        assert result.input_count == 1
        assert result.dimension == 1024
        assert result.model_version == "mpi-inno-comp/paecter"

    def test_generate_embeddings_batch(self, paecter_client):
        """Test embedding generation for multiple texts."""
        texts = [
            "First patent about machine learning",
            "Second patent about renewable energy",
            "Third patent about advanced materials",
        ]
        result = paecter_client.generate_embeddings(texts, batch_size=2)

        assert result.embeddings.shape == (3, 1024)
        assert result.input_count == 3

    def test_embeddings_are_normalized(self, paecter_client):
        """Test that embeddings are unit-normalized (for cosine similarity)."""
        texts = ["Test text for normalization check"]
        result = paecter_client.generate_embeddings(texts, normalize=True)

        # Check that embeddings have unit length (within floating point precision)
        norms = np.linalg.norm(result.embeddings, axis=1)
        np.testing.assert_allclose(norms, 1.0, rtol=1e-5)

    def test_prepare_patent_text(self):
        """Test patent text preparation."""
        title = "Novel Solar Cell Design"
        abstract = "This invention relates to improved solar cells with higher efficiency."

        text = PaECTERClient.prepare_patent_text(title, abstract)

        assert title in text
        assert abstract in text
        assert text == f"{title} {abstract}"

    def test_prepare_patent_text_missing_fields(self):
        """Test patent text preparation with missing fields."""
        # Only title
        text1 = PaECTERClient.prepare_patent_text("Title only", None)
        assert text1 == "Title only"

        # Only abstract
        text2 = PaECTERClient.prepare_patent_text(None, "Abstract only")
        assert text2 == "Abstract only"

        # Both missing
        text3 = PaECTERClient.prepare_patent_text(None, None)
        assert text3 == ""

    def test_prepare_award_text(self):
        """Test award text preparation."""
        solicitation = "Advanced Technologies Solicitation"
        award_title = "Novel Method for X"
        abstract = "This SBIR project will develop..."

        text = PaECTERClient.prepare_award_text(solicitation, abstract, award_title)

        assert solicitation in text
        assert award_title in text
        assert abstract in text

    def test_compute_similarity(self, paecter_client):
        """Test similarity computation between embeddings."""
        texts1 = ["Machine learning for drug discovery", "Deep learning for medicine"]
        texts2 = [
            "AI-based pharmaceutical research",
            "Solar cell efficiency improvements",
        ]

        result1 = paecter_client.generate_embeddings(texts1)
        result2 = paecter_client.generate_embeddings(texts2)

        similarities = paecter_client.compute_similarity(result1.embeddings, result2.embeddings)

        # Check shape
        assert similarities.shape == (2, 2)

        # Check that similar texts have higher similarity
        # texts1[0] and texts2[0] are both about drug discovery/pharma
        # texts1[0] and texts2[1] are about different topics
        assert similarities[0, 0] > similarities[0, 1]

    def test_award_embeddings(self, paecter_client):
        """Test embedding generation for sample SBIR awards."""
        award_texts = [
            PaECTERClient.prepare_award_text(
                award["solicitation_title"],
                award["abstract"],
                award.get("award_title"),
            )
            for award in SAMPLE_AWARDS
        ]

        result = paecter_client.generate_embeddings(award_texts)

        assert result.embeddings.shape == (len(SAMPLE_AWARDS), 1024)
        assert result.input_count == len(SAMPLE_AWARDS)

    def test_patent_embeddings(self, paecter_client):
        """Test embedding generation for sample patents."""
        patent_texts = [
            PaECTERClient.prepare_patent_text(
                patent["title"],
                patent["abstract"],
            )
            for patent in SAMPLE_PATENTS
        ]

        result = paecter_client.generate_embeddings(patent_texts)

        assert result.embeddings.shape == (len(SAMPLE_PATENTS), 1024)
        assert result.input_count == len(SAMPLE_PATENTS)

    def test_award_patent_similarity(self, paecter_client):
        """Test computing similarity between awards and patents.

        This is the core use case: finding patents similar to SBIR awards
        for technology transfer analysis.
        """
        # Prepare award texts
        award_texts = [
            PaECTERClient.prepare_award_text(
                award["solicitation_title"],
                award["abstract"],
                award.get("award_title"),
            )
            for award in SAMPLE_AWARDS
        ]

        # Prepare patent texts
        patent_texts = [
            PaECTERClient.prepare_patent_text(
                patent["title"],
                patent["abstract"],
            )
            for patent in SAMPLE_PATENTS
        ]

        # Generate embeddings
        award_result = paecter_client.generate_embeddings(award_texts)
        patent_result = paecter_client.generate_embeddings(patent_texts)

        # Compute similarities
        similarities = paecter_client.compute_similarity(
            award_result.embeddings, patent_result.embeddings
        )

        # Check shape: (num_awards x num_patents)
        assert similarities.shape == (len(SAMPLE_AWARDS), len(SAMPLE_PATENTS))

        # Expected high-similarity pairs (based on content):
        # Award 0 (3D printing) should be similar to Patent 0 (additive manufacturing)
        # Award 1 (drug discovery) should be similar to Patent 1 (molecular prediction)
        # Award 2 (solar cells) should be similar to Patent 2 (photovoltaic)

        # Check diagonal similarities are reasonably high
        for i in range(min(len(SAMPLE_AWARDS), len(SAMPLE_PATENTS))):
            assert similarities[i, i] > 0.5, (
                f"Expected high similarity for matching pair {i}, got {similarities[i, i]:.3f}"
            )

        # Find top-k similar patents for each award
        top_k = 2
        for i, award in enumerate(SAMPLE_AWARDS):
            top_indices = np.argsort(similarities[i])[::-1][:top_k]
            top_scores = similarities[i][top_indices]

            print(f"\nAward {i}: {award['award_title']}")
            for rank, (idx, score) in enumerate(zip(top_indices, top_scores, strict=False), 1):
                print(
                    f"  {rank}. Patent {idx}: {SAMPLE_PATENTS[idx]['title']} "
                    f"(similarity: {score:.3f})"
                )

    def test_empty_input_raises_error(self, paecter_client):
        """Test that empty input raises ValueError."""
        with pytest.raises(ValueError, match="texts cannot be empty"):
            paecter_client.generate_embeddings([])

    def test_semantic_similarity_properties(self, paecter_client):
        """Test that embeddings capture semantic similarity as expected."""
        # Similar texts should have high similarity
        similar_texts = [
            "Machine learning algorithm for classification",
            "Deep learning model for categorization",
        ]

        # Dissimilar texts should have lower similarity
        dissimilar_texts = [
            "Machine learning algorithm for classification",
            "Solar panel efficiency in desert environments",
        ]

        result_similar = paecter_client.generate_embeddings(similar_texts)
        result_dissimilar = paecter_client.generate_embeddings(dissimilar_texts)

        sim_score = paecter_client.compute_similarity(
            result_similar.embeddings[0:1], result_similar.embeddings[1:2]
        )[0, 0]

        dissim_score = paecter_client.compute_similarity(
            result_dissimilar.embeddings[0:1], result_dissimilar.embeddings[1:2]
        )[0, 0]

        assert sim_score > dissim_score, (
            f"Similar texts should have higher similarity "
            f"(got {sim_score:.3f} vs {dissim_score:.3f})"
        )


@pytest.mark.integration
def test_api_mode_requires_huggingface_hub():
    """Test that API mode requires huggingface_hub."""
    from src.ml.config import PaECTERClientConfig

    try:
        import huggingface_hub  # noqa: F401

        # If we get here, huggingface_hub is installed
        # API mode should work (even without token, just won't make requests)
        config = PaECTERClientConfig(use_local=False)
        client = PaECTERClient(config)
        assert client.config.use_local is False
        assert client.client is not None
    except ImportError:
        # If huggingface_hub is not installed, verify our error handling
        with pytest.raises(ImportError, match="huggingface_hub is required"):
            config = PaECTERClientConfig(use_local=False)
            PaECTERClient(config)


@pytest.mark.integration
@pytest.mark.slow
def test_local_mode_requires_sentence_transformers():
    """Test that local mode requires sentence-transformers."""
    from src.ml.config import PaECTERClientConfig

    try:
        import sentence_transformers  # noqa: F401

        # If we get here, sentence_transformers is installed
        config = PaECTERClientConfig(use_local=True)
        client = PaECTERClient(config)
        assert client.config.use_local is True
        assert client.model is not None
    except ImportError:
        # If sentence_transformers is not installed, verify our error handling
        with pytest.raises(ImportError, match="sentence-transformers is required"):
            config = PaECTERClientConfig(use_local=True)
            PaECTERClient(config)
