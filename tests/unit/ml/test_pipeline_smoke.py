"""Fast smoke tests covering the slow ML pipelines."""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import pytest

from tests.utils.fixtures import create_sample_cet_area
from src.ml.models.patent_classifier import PatentCETClassifier
from src.ml.models.trainer import CETModelTrainer
from src.models.cet_models import CETArea, TrainingDataset, TrainingExample


pytestmark = pytest.mark.fast


@pytest.fixture
def smoke_cet_areas() -> list[CETArea]:
    """Create two CET areas using the shared fixtures module."""
    return [
        create_sample_cet_area(cet_id="artificial_intelligence", name="Artificial Intelligence"),
        create_sample_cet_area(cet_id="quantum_information_science", name="Quantum Computing"),
    ]


@pytest.fixture
def smoke_training_dataset() -> TrainingDataset:
    """Minimal dataset for trainer smoke test."""
    examples = [
        TrainingExample(
            example_id="ex001",
            text="Machine learning methods for neural network optimization",
            labels=["artificial_intelligence"],
            source="manual",
            annotated_at=datetime.utcnow(),
        ),
        TrainingExample(
            example_id="ex002",
            text="Quantum computing systems with qubit control",
            labels=["quantum_information_science"],
            source="manual",
            annotated_at=datetime.utcnow(),
        ),
        TrainingExample(
            example_id="ex003",
            text="Deep learning and AI-enabled sensing",
            labels=["artificial_intelligence"],
            source="manual",
            annotated_at=datetime.utcnow(),
        ),
    ]
    return TrainingDataset(
        dataset_id="smoke_dataset",
        examples=examples,
        taxonomy_version="NSTC-2025Q1",
        description="Smoke dataset for CI",
    )


def test_cet_trainer_smoke(smoke_cet_areas, smoke_training_dataset):
    """Ensure CETModelTrainer can prepare data on a tiny dataset."""
    trainer = CETModelTrainer(
        cet_areas=smoke_cet_areas,
        config={"training": {"test_size": 0.3, "random_state": 42}},
        taxonomy_version="NSTC-2025Q1",
    )
    X_train, y_train, X_test, y_test = trainer.prepare_data(smoke_training_dataset)

    assert len(X_train) + len(X_test) == len(smoke_training_dataset)
    assert y_train.ndim == 2
    assert y_test.ndim == 2


def test_patent_classifier_smoke():
    """Train PatentCETClassifier on fixture-backed rows and classify a sample."""
    df = pd.DataFrame(
        [
            {
                "title": "Neural network inference acceleration",
                "assignee": "Acme LLC",
                "cet_labels": ["artificial_intelligence"],
            },
            {
                "title": "Quantum error correction hardware",
                "assignee": "Quantum Labs",
                "cet_labels": ["quantum_information_science"],
            },
        ]
    )

    classifier = PatentCETClassifier(pipelines={})

    def factory(cet_id: str):
        keywords = ["quantum", "qubit"] if "quantum" in cet_id else ["machine learning", "neural"]
        from src.ml.models.dummy_pipeline import DummyPipeline

        return DummyPipeline(cet_id=cet_id, keywords=keywords, keyword_boost=1.0)

    classifier.train_from_dataframe(
        df,
        title_col="title",
        assignee_col="assignee",
        cet_label_col="cet_labels",
        pipelines_factory=factory,
        use_feature_extraction=False,
    )

    results = classifier.classify("Neural network model for sensor fusion", assignee="Acme LLC", top_k=1)
    assert results
    assert results[0].cet_id in {"artificial_intelligence", "quantum_information_science"}

