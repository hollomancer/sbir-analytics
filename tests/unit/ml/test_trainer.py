"""
Unit tests for the CETModelTrainer class.

Tests cover:
- Trainer initialization
- Data preparation and splitting
- Model training workflow
- Cross-validation and hyperparameter tuning
- Model evaluation and metrics
- Model saving and loading
- Training report generation
"""

from datetime import datetime
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

pytestmark = pytest.mark.slow

from src.ml.models.trainer import CETModelTrainer
from src.models.cet_models import CETArea, TrainingDataset, TrainingExample


@pytest.fixture
def sample_cet_areas():
    """Sample CET areas for testing."""
    return [
        CETArea(
            cet_id="cet001",
            name="Artificial Intelligence",
            definition="AI technologies including machine learning and neural networks",
            keywords=["machine learning", "neural network", "deep learning", "AI"],
            taxonomy_version="NSTC-2025Q1",
        ),
        CETArea(
            cet_id="cet002",
            name="Quantum Computing",
            definition="Quantum technologies for computing and cryptography",
            keywords=["quantum computing", "qubits", "quantum algorithm"],
            taxonomy_version="NSTC-2025Q1",
        ),
    ]


@pytest.fixture
def sample_config():
    """Sample configuration for testing."""
    return {
        "training": {
            "test_size": 0.2,
            "val_size": 0.1,
            "random_state": 42,
            "cv_folds": 3,
            "param_grid": {
                "keyword_boost_factor": [1.5, 2.0, 2.5],
                "max_features": [1000, 2000, 5000],
                "c_value": [0.1, 1.0, 10.0],
            },
            "calibration_method": "sigmoid",
            "calibration_cv": 3,
        },
        "classification": {
            "keyword_boost_factor": 2.0,
            "max_features": 2000,
        },
        "evidence": {
            "max_statements": 3,
            "max_excerpt_words": 50,
        },
        "spacy": {
            "model": "en_core_web_sm",
        },
    }


@pytest.fixture
def sample_training_dataset():
    """Sample training dataset."""
    examples = [
        TrainingExample(
            example_id="ex001",
            text="Research on machine learning algorithms for neural network optimization",
            labels=["cet001"],
            source="manual",
            annotated_at=datetime.utcnow(),
        ),
        TrainingExample(
            example_id="ex002",
            text="Development of quantum computing systems using qubits",
            labels=["cet002"],
            source="manual",
            annotated_at=datetime.utcnow(),
        ),
        TrainingExample(
            example_id="ex003",
            text="AI and machine learning for deep learning applications",
            labels=["cet001"],
            source="manual",
            annotated_at=datetime.utcnow(),
        ),
        TrainingExample(
            example_id="ex004",
            text="Quantum algorithm development for cryptography",
            labels=["cet002"],
            source="manual",
            annotated_at=datetime.utcnow(),
        ),
        TrainingExample(
            example_id="ex005",
            text="Neural networks and quantum computing integration",
            labels=["cet001", "cet002"],  # Multi-label
            source="manual",
            annotated_at=datetime.utcnow(),
        ),
    ]

    return TrainingDataset(
        dataset_id="test_dataset",
        examples=examples,
        taxonomy_version="NSTC-2025Q1",
        description="Test dataset for unit tests",
    )


class TestTrainerInitialization:
    """Test CETModelTrainer initialization."""

    def test_initialization(self, sample_cet_areas, sample_config):
        """Test successful initialization."""
        trainer = CETModelTrainer(
            cet_areas=sample_cet_areas,
            config=sample_config,
            taxonomy_version="NSTC-2025Q1",
        )

        assert trainer.cet_areas == sample_cet_areas
        assert trainer.config == sample_config
        assert trainer.taxonomy_version == "NSTC-2025Q1"
        assert trainer.test_size == 0.2
        assert trainer.cv_folds == 3
        assert trainer.calibration_method == "sigmoid"

    def test_default_configuration(self, sample_cet_areas):
        """Test initialization with minimal configuration."""
        minimal_config = {}
        trainer = CETModelTrainer(
            cet_areas=sample_cet_areas,
            config=minimal_config,
            taxonomy_version="NSTC-2025Q1",
        )

        # Should use defaults
        assert trainer.test_size == 0.2
        assert trainer.cv_folds == 3
        assert trainer.calibration_method == "sigmoid"


class TestDataPreparation:
    """Test data preparation and splitting."""

    def test_prepare_data(self, sample_cet_areas, sample_config, sample_training_dataset):
        """Test data preparation from TrainingDataset."""
        trainer = CETModelTrainer(
            cet_areas=sample_cet_areas,
            config=sample_config,
            taxonomy_version="NSTC-2025Q1",
        )

        X_train, y_train, X_test, y_test = trainer.prepare_data(sample_training_dataset)

        # Check shapes
        assert len(X_train) + len(X_test) == len(sample_training_dataset)
        assert len(y_train) + len(y_test) == len(sample_training_dataset)
        assert len(X_train) > 0
        assert len(X_test) > 0

        # Check that labels are binarized
        assert y_train.ndim == 2
        assert y_test.ndim == 2

    def test_train_test_split_ratio(self, sample_cet_areas, sample_config, sample_training_dataset):
        """Test that train/test split respects configured ratio."""
        trainer = CETModelTrainer(
            cet_areas=sample_cet_areas,
            config=sample_config,
            taxonomy_version="NSTC-2025Q1",
        )

        X_train, y_train, X_test, y_test = trainer.prepare_data(sample_training_dataset)

        total_size = len(sample_training_dataset)
        expected_test_size = int(total_size * 0.2)

        # Allow for rounding differences
        assert abs(len(X_test) - expected_test_size) <= 1

    def test_multi_label_encoding(self, sample_cet_areas, sample_config, sample_training_dataset):
        """Test that multi-label examples are properly encoded."""
        trainer = CETModelTrainer(
            cet_areas=sample_cet_areas,
            config=sample_config,
            taxonomy_version="NSTC-2025Q1",
        )

        X_train, y_train, X_test, y_test = trainer.prepare_data(sample_training_dataset)

        # MultiLabelBinarizer should have created binary matrix
        assert y_train.dtype == np.int64 or y_train.dtype == np.float64
        assert all(val in [0, 1] for val in y_train.flatten())


class TestModelTraining:
    """Test model training workflow."""

    def test_train_without_cv(self, sample_cet_areas, sample_config, sample_training_dataset):
        """Test training without cross-validation."""
        with patch("src.ml.models.trainer.ApplicabilityModel") as MockModel:
            # Setup mock model
            mock_model_instance = MagicMock()
            mock_model_instance.train.return_value = {"loss": 0.5}
            mock_model_instance.classify.return_value = []
            MockModel.return_value = mock_model_instance

            trainer = CETModelTrainer(
                cet_areas=sample_cet_areas,
                config=sample_config,
                taxonomy_version="NSTC-2025Q1",
            )

            trainer.train(sample_training_dataset, perform_cv=False, perform_calibration=False)

            # Verify model was created and trained
            MockModel.assert_called_once()
            mock_model_instance.train.assert_called_once()

            # Verify metrics were collected
            assert "training" in trainer.metrics
            assert "test" in trainer.metrics
            assert "dataset_size" in trainer.metrics

    def test_train_with_cv(self, sample_cet_areas, sample_config, sample_training_dataset):
        """Test training with cross-validation."""
        with patch("src.ml.models.trainer.ApplicabilityModel") as MockModel:
            # Setup mock model
            mock_model_instance = MagicMock()
            mock_model_instance.train.return_value = {"loss": 0.5}
            mock_model_instance.classify.return_value = []
            MockModel.return_value = mock_model_instance

            trainer = CETModelTrainer(
                cet_areas=sample_cet_areas,
                config=sample_config,
                taxonomy_version="NSTC-2025Q1",
            )

            trainer.train(sample_training_dataset, perform_cv=True, perform_calibration=False)

            # Verify hyperparameters were tuned
            assert "hyperparameters" in trainer.metrics
            assert len(trainer.metrics["hyperparameters"]) > 0


class TestModelEvaluation:
    """Test model evaluation."""

    def test_evaluate_metrics(self, sample_cet_areas, sample_config):
        """Test that evaluation produces expected metrics."""
        trainer = CETModelTrainer(
            cet_areas=sample_cet_areas,
            config=sample_config,
            taxonomy_version="NSTC-2025Q1",
        )

        # Prepare mock data
        trainer.mlb.fit([["cet001"], ["cet002"]])
        X_test = ["test text 1", "test text 2"]
        y_test = np.array([[1, 0], [0, 1]])

        # Mock model
        mock_model = MagicMock()
        mock_model.classify.return_value = []

        metrics = trainer._evaluate(mock_model, X_test, y_test)

        # Check that all expected metrics are present
        assert "hamming_loss" in metrics
        assert "accuracy" in metrics
        assert "precision_micro" in metrics
        assert "recall_micro" in metrics
        assert "f1_micro" in metrics
        assert "precision_macro" in metrics
        assert "recall_macro" in metrics
        assert "f1_macro" in metrics
        assert "per_class" in metrics


class TestModelSaving:
    """Test model saving functionality."""

    def test_save_model(self, sample_cet_areas, sample_config, tmp_path):
        """Test saving model to disk."""
        trainer = CETModelTrainer(
            cet_areas=sample_cet_areas,
            config=sample_config,
            taxonomy_version="NSTC-2025Q1",
        )

        # Set some metrics
        trainer.metrics = {"test": {"f1_macro": 0.85}}

        # Mock model
        mock_model = MagicMock()
        mock_model.save = MagicMock()

        model_path = tmp_path / "test_model.pkl"
        trainer.save_model(mock_model, model_path, include_metrics=True)

        # Verify model save was called
        mock_model.save.assert_called_once_with(model_path)

        # Verify metrics file was created
        metrics_path = tmp_path / "test_model_metrics.json"
        assert metrics_path.exists()

    def test_save_model_without_metrics(self, sample_cet_areas, sample_config, tmp_path):
        """Test saving model without metrics."""
        trainer = CETModelTrainer(
            cet_areas=sample_cet_areas,
            config=sample_config,
            taxonomy_version="NSTC-2025Q1",
        )

        # Mock model
        mock_model = MagicMock()
        mock_model.save = MagicMock()

        model_path = tmp_path / "test_model.pkl"
        trainer.save_model(mock_model, model_path, include_metrics=False)

        # Verify model save was called
        mock_model.save.assert_called_once_with(model_path)

        # Verify metrics file was NOT created
        metrics_path = tmp_path / "test_model_metrics.json"
        assert not metrics_path.exists()


class TestReportGeneration:
    """Test training report generation."""

    def test_generate_report_with_metrics(self, sample_cet_areas, sample_config):
        """Test generating report with metrics."""
        trainer = CETModelTrainer(
            cet_areas=sample_cet_areas,
            config=sample_config,
            taxonomy_version="NSTC-2025Q1",
        )

        # Set sample metrics
        trainer.metrics = {
            "dataset_size": 100,
            "train_size": 80,
            "test_size": 20,
            "num_labels": 2,
            "training_duration_seconds": 45.5,
            "taxonomy_version": "NSTC-2025Q1",
            "trained_at": "2024-01-01T00:00:00Z",
            "hyperparameters": {"keyword_boost_factor": 2.0},
            "test": {
                "accuracy": 0.85,
                "hamming_loss": 0.15,
                "precision_micro": 0.87,
                "recall_micro": 0.83,
                "f1_micro": 0.85,
                "precision_macro": 0.86,
                "recall_macro": 0.82,
                "f1_macro": 0.84,
                "per_class": {
                    "cet001": {"f1-score": 0.90},
                    "cet002": {"f1-score": 0.78},
                },
            },
        }

        report = trainer.generate_report()

        # Verify report contains key information
        assert "TRAINING REPORT" in report
        assert "100" in report  # dataset size
        assert "80" in report  # train size
        assert "0.85" in report  # accuracy
        assert "NSTC-2025Q1" in report
        assert "keyword_boost_factor" in report

    def test_generate_report_without_metrics(self, sample_cet_areas, sample_config):
        """Test generating report without metrics."""
        trainer = CETModelTrainer(
            cet_areas=sample_cet_areas,
            config=sample_config,
            taxonomy_version="NSTC-2025Q1",
        )

        report = trainer.generate_report()

        assert "No training metrics available" in report

    def test_get_metrics(self, sample_cet_areas, sample_config):
        """Test getting metrics dictionary."""
        trainer = CETModelTrainer(
            cet_areas=sample_cet_areas,
            config=sample_config,
            taxonomy_version="NSTC-2025Q1",
        )

        trainer.metrics = {"test": {"f1_macro": 0.85}}

        metrics = trainer.get_metrics()
        assert metrics == trainer.metrics
        assert "test" in metrics
