import pandas as pd
import pytest

from src.ml.models.cet_classifier import ApplicabilityModel
from src.models.cet_models import CETArea


@pytest.mark.integration
@pytest.mark.slow
def test_cet_classifier_training_and_classification_synthetic():
    """
    Synthetic integration test that trains the CET ApplicabilityModel on a tiny dataset
    with two CET areas and verifies it classifies simple held-out texts correctly.

    Dataset:
      - artificial_intelligence (AI): "machine learning", "neural network"
      - quantum_information_science (QIS): "quantum", "qubit", "entanglement"

    Expectations:
      - Text with "neural network" should be classified as AI
      - Text with "quantum entanglement" should be classified as QIS
    """

    # Define a minimal taxonomy with two CET areas
    cet_areas = [
        CETArea(
            cet_id="artificial_intelligence",
            name="Artificial Intelligence",
            definition="AI and ML technologies",
            keywords=["machine learning", "neural network"],
            parent_cet_id=None,
        ),
        CETArea(
            cet_id="quantum_information_science",
            name="Quantum Information Science",
            definition="Quantum computing and related algorithms",
            keywords=["quantum", "qubit", "entanglement"],
            parent_cet_id=None,
        ),
    ]

    # Small, conservative config to avoid overfitting and keep runtime low
    config = {
        "model_version": "vtest",
        "tfidf": {
            "min_df": 1,
            "max_df": 1.0,
            "ngram_range": [1, 2],
            "keyword_boost_factor": 2.0,
            "sublinear_tf": True,
            "use_idf": True,
            "smooth_idf": True,
            "norm": "l2",
        },
        "logistic_regression": {
            "C": 1.0,
            "max_iter": 200,
            "solver": "lbfgs",
            # n_jobs is accepted by sklearn LogisticRegression signature; keep default for portability
        },
        # Disable feature selection for tiny training sets to avoid shape edge cases
        "feature_selection": {"enabled": False},
        # Keep calibration conservative; 2-fold is sufficient for this synthetic test
        "calibration": {"method": "sigmoid", "cv": 2},
        "batch": {"size": 16},
        # Classification thresholds are used by higher-level assets; not strictly needed here
        "confidence_thresholds": {"high": 70.0, "medium": 40.0, "low": 0.0},
    }

    # Instantiate model
    model = ApplicabilityModel(
        cet_areas=cet_areas,
        config=config,
        taxonomy_version="TEST-2025Q1",
    )

    # Build tiny training corpus
    X_train = [
        "machine learning for image analysis",
        "neural network optimization and deep learning",
        "quantum computing with qubits",
        "entanglement and quantum circuits",
    ]
    # Binary indicator columns per CET area (order aligned with cet_areas above)
    #   Row 0-1 -> AI positive; 2-3 -> QIS positive
    y_train = pd.DataFrame(
        [
            [1, 0],
            [1, 0],
            [0, 1],
            [0, 1],
        ],
        columns=[a.cet_id for a in cet_areas],
    )

    # Train the multi-label model
    train_metrics = model.train(X_train, y_train)
    assert isinstance(train_metrics, dict)
    # Sanity: at least the CET IDs should appear in training summary or the model marked as trained
    assert getattr(model, "is_trained", False) is True

    # Classify held-out texts
    texts = [
        "deep learning and neural network architectures",
        "quantum entanglement research for qubit coherence",
    ]
    results = model.classify_batch(texts, batch_size=8)

    # Expect two result lists (one per input text)
    assert isinstance(results, list) and len(results) == 2

    # Unpack primary predictions (sorted descending by score per classify_batch contract)
    primary_0 = results[0][0] if results[0] else None
    primary_1 = results[1][0] if results[1] else None

    assert primary_0 is not None, "First text should have at least one CET prediction"
    assert primary_1 is not None, "Second text should have at least one CET prediction"

    # Verify expected primary CETs
    assert primary_0.cet_id == "artificial_intelligence"
    assert primary_1.cet_id == "quantum_information_science"

    # Scores should be positive and primary > any alternate on the same text
    assert primary_0.score is not None and primary_0.score > 0
    assert primary_1.score is not None and primary_1.score > 0

    # If alternative predictions exist, primary score should be higher or equal
    if len(results[0]) > 1:
        assert primary_0.score >= results[0][1].score
    if len(results[1]) > 1:
        assert primary_1.score >= results[1][1].score
