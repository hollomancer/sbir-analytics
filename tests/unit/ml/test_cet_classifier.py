"""
Unit tests for CET classification module.

Tests CETAwareTfidfVectorizer and ApplicabilityModel including:
- Keyword boosting
- Model initialization
- Training
- Classification (single and batch)
- Model persistence
- Multi-threshold scoring
"""

import tempfile
from pathlib import Path

import pandas as pd
import pytest

from src.ml.models.cet_classifier import ApplicabilityModel, CETAwareTfidfVectorizer
from src.models.cet_models import CETArea, ClassificationLevel


@pytest.fixture
def sample_cet_areas():
    """Create sample CET areas for testing."""
    return [
        CETArea(
            cet_id="artificial_intelligence",
            name="Artificial Intelligence",
            definition="AI and machine learning technologies",
            keywords=[
                "machine learning",
                "neural network",
                "deep learning",
                "ai",
                "artificial intelligence",
            ],
            taxonomy_version="NSTC-2025Q1",
        ),
        CETArea(
            cet_id="quantum_computing",
            name="Quantum Computing",
            definition="Quantum information science and computing",
            keywords=["quantum", "qubit", "quantum computing", "quantum algorithm"],
            taxonomy_version="NSTC-2025Q1",
        ),
        CETArea(
            cet_id="advanced_materials",
            name="Advanced Materials",
            definition="Novel materials with enhanced properties",
            keywords=["composite", "metamaterial", "nanomaterial", "graphene"],
            taxonomy_version="NSTC-2025Q1",
        ),
    ]


@pytest.fixture
def sample_config():
    """Create sample configuration for testing."""
    return {
        "model_version": "v1.0.0-test",
        "confidence_thresholds": {
            "high": 70.0,
            "medium": 40.0,
            "low": 0.0,
        },
        "tfidf": {
            "max_features": 100,
            "min_df": 1,
            "max_df": 0.95,
            "ngram_range": [1, 2],
            "sublinear_tf": True,
            "use_idf": True,
            "smooth_idf": True,
            "norm": "l2",
            "keyword_boost_factor": 2.0,
        },
        "logistic_regression": {
            "penalty": "l2",
            "C": 1.0,
            "solver": "lbfgs",
            "max_iter": 100,
            "class_weight": "balanced",
            "random_state": 42,
            "n_jobs": 1,
        },
        "calibration": {
            "method": "sigmoid",
            "cv": 2,  # Reduced for faster tests
        },
        "feature_selection": {
            "enabled": True,
            "method": "chi2",
            "k_best": 50,
        },
        "batch": {
            "size": 10,
        },
    }


@pytest.fixture
def sample_training_data():
    """Create sample training documents and labels."""
    # Training documents with clear CET signals
    documents = [
        # AI documents
        "We develop machine learning algorithms for neural network optimization and deep learning applications",
        "Our artificial intelligence system uses advanced machine learning techniques",
        "Novel AI-based approach using deep learning and neural networks",
        # Quantum documents
        "Quantum computing system with superconducting qubits and quantum algorithms",
        "Development of quantum error correction for quantum information processing",
        "New quantum algorithm for optimization on quantum computers",
        # Materials documents
        "Advanced composite materials with enhanced strength using carbon nanotubes",
        "Metamaterial design for electromagnetic applications using graphene",
        "Novel nanomaterial synthesis and characterization",
        # Mixed/ambiguous
        "General research on computing and materials",
    ]

    # Binary labels for each CET area
    labels = pd.DataFrame(
        {
            "artificial_intelligence": [1, 1, 1, 0, 0, 0, 0, 0, 0, 0],
            "quantum_computing": [0, 0, 0, 1, 1, 1, 0, 0, 0, 0],
            "advanced_materials": [0, 0, 0, 0, 0, 0, 1, 1, 1, 1],
        }
    )

    return documents, labels


class TestCETAwareTfidfVectorizer:
    """Tests for CETAwareTfidfVectorizer."""

    def test_initialization(self, sample_cet_areas):
        """Test vectorizer initialization with CET keywords."""
        cet_keywords = {area.cet_id: area.keywords for area in sample_cet_areas}

        vectorizer = CETAwareTfidfVectorizer(
            cet_keywords=cet_keywords,
            keyword_boost_factor=2.0,
            max_features=100,
        )

        assert vectorizer.keyword_boost_factor == 2.0
        assert len(vectorizer.keyword_set) > 0
        assert "machine learning" in vectorizer.keyword_set
        assert "quantum" in vectorizer.keyword_set

    def test_keyword_boosting(self, sample_cet_areas):
        """Test that CET keywords get boosted TF-IDF scores."""
        cet_keywords = {area.cet_id: area.keywords for area in sample_cet_areas}

        vectorizer = CETAwareTfidfVectorizer(
            cet_keywords=cet_keywords,
            keyword_boost_factor=2.0,
            max_features=100,
        )

        # Documents with and without CET keywords
        docs = [
            "machine learning neural network deep learning",  # All CET keywords
            "general computing software development",  # No CET keywords
        ]

        X = vectorizer.fit_transform(docs)

        # Check that matrix is not empty
        assert X.shape[0] == 2
        assert X.shape[1] > 0

        # First document should have higher total score (boosted keywords)
        doc1_score = X[0].sum()
        doc2_score = X[1].sum()
        assert doc1_score > doc2_score

    def test_vocabulary_contains_keywords(self, sample_cet_areas):
        """Test that vocabulary includes CET keywords."""
        cet_keywords = {area.cet_id: area.keywords for area in sample_cet_areas}

        vectorizer = CETAwareTfidfVectorizer(
            cet_keywords=cet_keywords,
            keyword_boost_factor=2.0,
        )

        docs = ["machine learning and quantum computing are advanced technologies"]
        vectorizer.fit_transform(docs)

        # Check that CET keywords appear in vocabulary
        assert "machine" in vectorizer.vocabulary_ or "learning" in vectorizer.vocabulary_
        assert "quantum" in vectorizer.vocabulary_


class TestApplicabilityModel:
    """Tests for ApplicabilityModel."""

    def test_initialization(self, sample_cet_areas, sample_config):
        """Test model initialization."""
        model = ApplicabilityModel(
            cet_areas=sample_cet_areas,
            config=sample_config,
            taxonomy_version="NSTC-2025Q1",
        )

        assert model.is_trained is False
        assert len(model.cet_areas) == 3
        assert model.taxonomy_version == "NSTC-2025Q1"
        assert len(model.cet_keywords) == 3
        assert len(model.pipelines) == 0  # Not trained yet

    def test_metadata(self, sample_cet_areas, sample_config):
        """Test model metadata."""
        model = ApplicabilityModel(
            cet_areas=sample_cet_areas,
            config=sample_config,
            taxonomy_version="NSTC-2025Q1",
        )

        metadata = model.get_metadata()

        assert metadata["model_version"] == "v1.0.0-test"
        assert metadata["taxonomy_version"] == "NSTC-2025Q1"
        assert metadata["is_trained"] is False
        assert metadata["num_cet_areas"] == 3
        assert metadata["num_trained_classifiers"] == 0

    def test_training(self, sample_cet_areas, sample_config, sample_training_data):
        """Test model training."""
        model = ApplicabilityModel(
            cet_areas=sample_cet_areas,
            config=sample_config,
            taxonomy_version="NSTC-2025Q1",
        )

        X_train, y_train = sample_training_data

        metrics = model.train(X_train, y_train)

        # Check training completed
        assert model.is_trained is True
        assert len(model.pipelines) == 3
        assert model.training_date is not None

        # Check metrics returned
        assert "artificial_intelligence" in metrics
        assert "quantum_computing" in metrics
        assert "advanced_materials" in metrics

        # Check metric values are reasonable
        for cet_id, cet_metrics in metrics.items():
            assert 0.0 <= cet_metrics["accuracy"] <= 1.0
            assert 0.0 <= cet_metrics["precision"] <= 1.0
            assert 0.0 <= cet_metrics["recall"] <= 1.0
            assert cet_metrics["positive_examples"] > 0

    def test_classify_single_document(self, sample_cet_areas, sample_config, sample_training_data):
        """Test single document classification."""
        model = ApplicabilityModel(
            cet_areas=sample_cet_areas,
            config=sample_config,
            taxonomy_version="NSTC-2025Q1",
        )

        X_train, y_train = sample_training_data
        model.train(X_train, y_train)

        # Test AI document
        ai_text = (
            "We use deep learning and neural networks for artificial intelligence applications"
        )
        classifications = model.classify(ai_text)

        # Should return at least one classification
        assert len(classifications) > 0

        # Primary classification should be marked
        assert any(c.primary for c in classifications)

        # Highest scoring should be AI
        primary = [c for c in classifications if c.primary][0]
        assert primary.cet_id == "artificial_intelligence"

        # Check classification fields
        assert primary.score >= 0.0
        assert primary.score <= 100.0
        assert primary.classification in [
            ClassificationLevel.HIGH,
            ClassificationLevel.MEDIUM,
            ClassificationLevel.LOW,
        ]
        assert primary.taxonomy_version == "NSTC-2025Q1"

    def test_classify_returns_all_scores(
        self, sample_cet_areas, sample_config, sample_training_data
    ):
        """Test classification with return_all_scores=True."""
        model = ApplicabilityModel(
            cet_areas=sample_cet_areas,
            config=sample_config,
            taxonomy_version="NSTC-2025Q1",
        )

        X_train, y_train = sample_training_data
        model.train(X_train, y_train)

        text = "Machine learning and quantum computing research"
        classifications = model.classify(text, return_all_scores=True)

        # Should return scores for all CET areas
        cet_ids = {c.cet_id for c in classifications}
        assert "artificial_intelligence" in cet_ids
        assert "quantum_computing" in cet_ids
        assert "advanced_materials" in cet_ids

    def test_batch_classification(self, sample_cet_areas, sample_config, sample_training_data):
        """Test batch classification."""
        model = ApplicabilityModel(
            cet_areas=sample_cet_areas,
            config=sample_config,
            taxonomy_version="NSTC-2025Q1",
        )

        X_train, y_train = sample_training_data
        model.train(X_train, y_train)

        # Test batch of documents
        texts = [
            "Deep learning neural network AI system",
            "Quantum computing with qubits",
            "Composite materials and graphene",
        ]

        results = model.classify_batch(texts, batch_size=2)

        # Should return results for all documents
        assert len(results) == 3

        # Each result should have classifications
        for classifications in results:
            assert len(classifications) > 0
            assert any(c.primary for c in classifications)

        # Check expected CET areas
        assert results[0][0].cet_id == "artificial_intelligence"
        assert results[1][0].cet_id == "quantum_computing"
        assert results[2][0].cet_id == "advanced_materials"

    def test_multi_threshold_scoring(self, sample_cet_areas, sample_config, sample_training_data):
        """Test multi-threshold classification levels."""
        model = ApplicabilityModel(
            cet_areas=sample_cet_areas,
            config=sample_config,
            taxonomy_version="NSTC-2025Q1",
        )

        X_train, y_train = sample_training_data
        model.train(X_train, y_train)

        # Strong AI signal (should be HIGH)
        strong_ai = "machine learning deep learning neural network artificial intelligence AI"
        classifications = model.classify(strong_ai)

        primary = [c for c in classifications if c.primary][0]

        # Check classification level based on score
        if primary.score >= 70:
            assert primary.classification == ClassificationLevel.HIGH
        elif primary.score >= 40:
            assert primary.classification == ClassificationLevel.MEDIUM
        else:
            assert primary.classification == ClassificationLevel.LOW

    def test_model_save_load(self, sample_cet_areas, sample_config, sample_training_data):
        """Test model persistence (save/load)."""
        model = ApplicabilityModel(
            cet_areas=sample_cet_areas,
            config=sample_config,
            taxonomy_version="NSTC-2025Q1",
        )

        X_train, y_train = sample_training_data
        model.train(X_train, y_train)

        # Save model
        with tempfile.TemporaryDirectory() as tmpdir:
            model_path = Path(tmpdir) / "test_model.pkl"
            model.save(model_path)

            # Check file was created
            assert model_path.exists()

            # Load model
            loaded_model = ApplicabilityModel.load(model_path)

            # Check loaded model state
            assert loaded_model.is_trained is True
            assert len(loaded_model.pipelines) == 3
            assert loaded_model.taxonomy_version == "NSTC-2025Q1"
            assert loaded_model.model_version == "v1.0.0-test"

            # Test that loaded model can classify
            test_text = "Deep learning and neural networks"
            classifications = loaded_model.classify(test_text)

            assert len(classifications) > 0
            assert classifications[0].cet_id == "artificial_intelligence"

    def test_untrained_model_raises_error(self, sample_cet_areas, sample_config):
        """Test that untrained model raises error on classification."""
        model = ApplicabilityModel(
            cet_areas=sample_cet_areas,
            config=sample_config,
            taxonomy_version="NSTC-2025Q1",
        )

        with pytest.raises(RuntimeError, match="must be trained"):
            model.classify("test text")

    def test_save_untrained_model_raises_error(self, sample_cet_areas, sample_config):
        """Test that saving untrained model raises error."""
        model = ApplicabilityModel(
            cet_areas=sample_cet_areas,
            config=sample_config,
            taxonomy_version="NSTC-2025Q1",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            model_path = Path(tmpdir) / "test_model.pkl"

            with pytest.raises(RuntimeError, match="Cannot save untrained model"):
                model.save(model_path)

    def test_training_with_mismatched_labels(self, sample_cet_areas, sample_config):
        """Test that training with mismatched X/y lengths raises error."""
        model = ApplicabilityModel(
            cet_areas=sample_cet_areas,
            config=sample_config,
            taxonomy_version="NSTC-2025Q1",
        )

        X_train = ["doc1", "doc2"]
        y_train = pd.DataFrame(
            {
                "artificial_intelligence": [1, 0, 1],  # Wrong length
            }
        )

        with pytest.raises(ValueError, match="same length"):
            model.train(X_train, y_train)

    def test_classification_scores_sorted(
        self, sample_cet_areas, sample_config, sample_training_data
    ):
        """Test that classifications are sorted by score descending."""
        model = ApplicabilityModel(
            cet_areas=sample_cet_areas,
            config=sample_config,
            taxonomy_version="NSTC-2025Q1",
        )

        X_train, y_train = sample_training_data
        model.train(X_train, y_train)

        text = "Machine learning quantum computing materials"
        classifications = model.classify(text, return_all_scores=True)

        # Check scores are in descending order
        scores = [c.score for c in classifications]
        assert scores == sorted(scores, reverse=True)
