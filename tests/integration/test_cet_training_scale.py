"""Integration test: larger-scale synthetic training + classification for CET ApplicabilityModel.

This test intentionally marked as slow and integration-level. It creates a
synthetic labeled dataset for a small set of CET areas, trains the
ApplicabilityModel on the synthetic dataset, and verifies that held-out
texts are classified into the expected CET areas.

The test size is configurable via environment variable:
  CET_TRAIN_SCALE (default: 2000)
"""

import os
import random

import pytest


# Integration / slow markers
pytest.importorskip("sklearn", reason="scikit-learn required for integration training")
pytest.importorskip("pandas", reason="pandas required for integration training")

import numpy as np  # type: ignore
import pandas as pd  # type: ignore

from src.ml.models.cet_classifier import ApplicabilityModel  # type: ignore
from src.models.cet_models import CETArea  # type: ignore


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.compute_intensive
def test_cet_training_scale_synthetic():
    """
    Train ApplicabilityModel on a synthetic dataset of configurable size and verify
    that held-out texts are classified into the expected CET areas.

    This exercise validates:
      - Model training completes on a mid-sized synthetic dataset
      - The model can be used to classify held-out texts and produce plausible top predictions
    """
    # Configurable dataset size (total training rows)
    total_examples = int(os.getenv("CET_TRAIN_SCALE", "2000"))

    # Deterministic randomness for CI reproducibility
    seed = int(os.getenv("CET_TRAIN_SEED", "42"))
    random.seed(seed)
    np.random.seed(seed)

    # Define a small taxonomy of CET areas for synthetic training
    cet_areas: list[CETArea] = [
        CETArea(
            cet_id="artificial_intelligence",
            name="Artificial Intelligence",
            definition="AI and machine learning technologies",
            keywords=["machine learning", "neural network", "deep learning", "nlp"],
            parent_cet_id=None,
        ),
        CETArea(
            cet_id="quantum_information_science",
            name="Quantum Information Science",
            definition="Quantum computing and information science",
            keywords=["quantum", "qubit", "entanglement", "quantum algorithm"],
            parent_cet_id=None,
        ),
        CETArea(
            cet_id="biotechnology",
            name="Biotechnology",
            definition="Biotech, bioinformatics, genomics",
            keywords=["genome", "protein", "biomedical", "assay"],
            parent_cet_id=None,
        ),
    ]

    cet_ids = [c.cet_id for c in cet_areas]
    num_cets = len(cet_ids)

    # Build synthetic training corpus.
    # For each CET area, create a number of positive examples emphasizing that CET's keywords.
    examples: list[str] = []
    labels_rows: list[list[int]] = []

    # Distribute examples roughly evenly across CETs (allow some multi-label mixes)
    per_cet = max(10, total_examples // num_cets)
    remaining = total_examples - per_cet * num_cets

    def synth_text_for_cet(cet: CETArea) -> str:
        # Compose a synthetic document using CET keywords plus generic filler
        kw = random.choice(cet.keywords) if cet.keywords else "research"
        fillers = [
            "This project explores novel techniques",
            "We propose an approach leveraging",
            "Evaluation will use benchmarks and experiments",
            "Prototype and validation on real data",
            "Focus on performance and robustness",
        ]
        filler = random.choice(fillers)
        # Add some cross-cet noise occasionally
        noise = ""
        if random.random() < 0.2:
            other = random.choice([x for x in cet_areas if x.cet_id != cet.cet_id])
            noise = " " + random.choice(other.keywords)
        return f"{filler} {kw}. {noise}"

    # Create per-cet positive examples
    for cet in cet_areas:
        for _ in range(per_cet):
            text = synth_text_for_cet(cet)
            # Occasionally include multiple labels (multi-label)
            labels = [0] * num_cets
            idx = cet_ids.index(cet.cet_id)
            labels[idx] = 1
            if random.random() < 0.05:
                # add one additional random CET label
                other_idx = random.choice([i for i in range(num_cets) if i != idx])
                labels[other_idx] = 1
                text += " " + random.choice(cet_areas[other_idx].keywords)
            examples.append(text)
            labels_rows.append(labels)

    # Add remaining examples as mixed / negative noise
    for _ in range(remaining):
        # Randomly pick 1-2 CETs to be positive
        ks = random.sample(range(num_cets), k=random.choice([0, 1, 2]))
        labels = [1 if i in ks else 0 for i in range(num_cets)]
        # Compose a mixed text
        parts = []
        for i in ks:
            parts.append(random.choice(cet_areas[i].keywords))
        if not parts:
            parts.append("interdisciplinary research")
        text = " ".join([" ".join(parts), "applied research and evaluation", "prototype studies"])
        examples.append(text)
        labels_rows.append(labels)

    # Shuffle dataset
    combined = list(zip(examples, labels_rows, strict=False))
    random.shuffle(combined)
    examples, labels_rows = zip(*combined, strict=False) if combined else ([], [])

    # Split into train/test
    split_idx = int(len(examples) * 0.85)
    X_train = list(examples[:split_idx])
    X_test = list(examples[split_idx:])
    y_train_df = pd.DataFrame(list(labels_rows[:split_idx]), columns=cet_ids)
    y_test_df = pd.DataFrame(list(labels_rows[split_idx:]), columns=cet_ids)

    # Lightweight model config tuned for quicker training in CI
    config = {
        "model_version": "vtest-scale",
        "tfidf": {
            "max_features": 2000,
            "ngram_range": [1, 2],
            "min_df": 1,
            "max_df": 0.95,
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
            "class_weight": "balanced",
            "random_state": seed,
            "n_jobs": 1,
        },
        "feature_selection": {"enabled": False},
        "calibration": {"method": "sigmoid", "cv": 2},
        "batch": {"size": 512},
        "confidence_thresholds": {"high": 70.0, "medium": 40.0, "low": 0.0},
    }

    # Instantiate model
    model = ApplicabilityModel(cet_areas=cet_areas, config=config, taxonomy_version="TEST-2025Q1")

    # Train (may take time; marked slow)
    train_metrics = model.train(X_train, y_train_df)
    assert isinstance(train_metrics, dict) or getattr(
        model, "is_trained", False
    ), "Training did not return metrics or mark model as trained"

    # Verify model metadata
    assert getattr(model, "is_trained", False) is True

    # Classify a couple of held-out synthetic texts and assert expected top CET
    test_texts = [
        "This project uses neural network and deep learning methods for medical imaging",
        "Research on qubit entanglement and quantum algorithms for optimization",
        "Developing genomic assays and protein engineering for diagnostics",
    ]
    results = model.classify_batch(test_texts, batch_size=64)

    # Expect at least one prediction per text and top prediction matches expected CET
    assert isinstance(results, list) and len(results) == len(test_texts)
    primary_ids = []
    for preds in results:
        if not preds:
            primary_ids.append(None)
            continue
        # preds are objects or dicts depending on model impl; handle both
        top = preds[0]
        cet_id = getattr(top, "cet_id", top.get("cet_id") if isinstance(top, dict) else None)
        score = getattr(top, "score", top.get("score") if isinstance(top, dict) else None)
        primary_ids.append(cet_id)
        assert score is not None and score >= 0.0

    # Map expectations
    assert primary_ids[0] in (
        "artificial_intelligence",
    ), f"Unexpected primary for text 0: {primary_ids[0]}"
    assert primary_ids[1] in (
        "quantum_information_science",
    ), f"Unexpected primary for text 1: {primary_ids[1]}"
    assert primary_ids[2] in ("biotechnology",), f"Unexpected primary for text 2: {primary_ids[2]}"

    # Sanity: evaluate simple recall@1 on the test split for a minimal pass threshold
    # Build simple binary predictions using top-1 mapping for each test sample
    test_results = model.classify_batch(list(X_test[:200]), batch_size=256)
    hits = 0
    total = 0
    for y_true_row, preds in zip(y_test_df.iloc[:200].values.tolist(), test_results, strict=False):
        total += 1
        # Get true labels
        true_idxs = [i for i, v in enumerate(y_true_row) if int(v) == 1]
        if not true_idxs:
            continue
        if preds and len(preds) > 0:
            top = preds[0]
            top_id = getattr(top, "cet_id", top.get("cet_id") if isinstance(top, dict) else None)
            if top_id and top_id in [cet_ids[i] for i in true_idxs]:
                hits += 1
    recall_at_1 = hits / max(1, total)
    # Expect some signal ( > 0.2 ) for synthetic dataset - very lenient threshold
    assert recall_at_1 >= 0.20, f"Low recall@1 on synthetic test: {recall_at_1:.3f}"

    # If we reach here, training & classification on mid-sized synthetic data succeeded
    print(
        f"[CET SCALE TEST] Trained on {len(X_train)} examples, recall@1 (sample) = {recall_at_1:.3f}"
    )
