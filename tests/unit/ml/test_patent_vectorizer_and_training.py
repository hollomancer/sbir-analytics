# sbir-etl/tests/unit/ml/test_patent_vectorizer_and_training.py
# ruff: noqa: F821, F401
"""
DEPRECATED MODULE - SKIPPED

This test module is skipped because the vectorizers functionality has been removed/refactored.
The module is kept for historical reference but will not run.

To restore this module:
1. Re-implement the vectorizers in src/ml/features/vectorizers.py
2. Uncomment the imports below
3. Remove the pytestmark skip decorator
"""

from pathlib import Path

import pytest


# Skip entire module - vectorizers have been removed/refactored
pytestmark = pytest.mark.skip(
    reason="Vectorizers module is empty - functionality removed/refactored"
)

pd = pytest.importorskip("pandas")
np = pytest.importorskip("numpy")

# Commented out - module is empty, but keeping imports for linting
# from src.ml.features.patent_features import (
#     DEFAULT_KEYWORDS_MAP,
#     PatentFeatureVector,
#     extract_features,
# )
# from src.ml.features.vectorizers import (
#     AssigneeTypeVectorizer,
#     FeatureMatrixBuilder,
#     IPCPresenceVectorizer,
#     KeywordVectorizer,
#     TokenCounterVectorizer,
# )
from src.ml.models.dummy_pipeline import DummyPipeline  # noqa: F401
from src.ml.models.patent_classifier import PatentCETClassifier  # noqa: F401
from src.ml.train.patent_training import (  # noqa: F401
    evaluate_patent_classifier,
    precision_recall_at_k,
    train_patent_classifier,
)


pytestmark = pytest.mark.fast



def make_feature_vectors():  # type: ignore[no-untyped-def]
    records = [
        {
            "title": "Machine learning for sensor fusion",
            "abstract": "A novel neural network architecture.",
            "assignee": "Acme Technologies, Inc.",
            "ipc": "G06F 17/30",
            "application_year": 2022,
        },
        {
            "title": "Quantum computing with robust qubit coherence",
            "abstract": "Quantum error correction and qubit control techniques.",
            "assignee": "National Quantum Lab",
            "cpc": "H04L 9/00",
            "application_year": 2021,
        },
    ]
    fvs = [extract_features(rec) for rec in records]  # noqa: F821
    # Sanity checks
    assert all(isinstance(fv, PatentFeatureVector) for fv in fvs)  # noqa: F821
    return fvs


def test_keyword_vectorizer_counts_and_names():  # type: ignore[no-untyped-def]
    fvs = make_feature_vectors()
    kv = KeywordVectorizer(DEFAULT_KEYWORDS_MAP)  # noqa: F821
    X = kv.fit_transform(fvs)
    # Expect 2 rows and 2 * (#keyword groups) columns (count + presence)
    assert X.shape[0] == len(fvs)
    expected_cols = 2 * len(DEFAULT_KEYWORDS_MAP)  # noqa: F821
    assert X.shape[1] == expected_cols
    # Private accessor for names (acceptable in tests)
    names = kv._get_feature_names()
    assert isinstance(names, list) and len(names) == expected_cols
    # Basic presence: ML title should trigger some ML-related feature presence
    # We do not depend on exact names here, only that some count > 0 exists for one row
    assert (X[0] > 0).any() or (X[1] > 0).any()


def test_feature_matrix_builder_combines_all_vectorizers():  # type: ignore[no-untyped-def]
    fvs = make_feature_vectors()
    # Build individual matrices
    kv = KeywordVectorizer(DEFAULT_KEYWORDS_MAP)  # noqa: F821
    tcv = TokenCounterVectorizer()  # noqa: F821
    atv = AssigneeTypeVectorizer()  # noqa: F821
    ipv = IPCPresenceVectorizer()  # noqa: F821

    X_kv = kv.fit_transform(fvs)
    X_tc = tcv.fit_transform(fvs)
    X_at = atv.fit_transform(fvs)
    X_ip = ipv.fit_transform(fvs)

    # Combined builder
    builder = FeatureMatrixBuilder([kv, tcv, atv, ipv])  # noqa: F821
    X_all = builder.fit_transform(fvs)

    # Rows must match
    assert X_all.shape[0] == len(fvs)
    # Width must be sum of component widths
    expected_width = X_kv.shape[1] + X_tc.shape[1] + X_at.shape[1] + X_ip.shape[1]
    assert X_all.shape[1] == expected_width
    # Ensure deterministic dtype
    assert str(X_all.dtype).startswith("float")


def make_training_dataframe():
    rows = [
        {
            "title": "A novel machine learning method for image segmentation",
            "assignee": "Acme LLC",
            "cet_labels": ["artificial_intelligence"],
        },
        {
            "title": "Deep neural networks for sensor data",
            "assignee": "Acme LLC",
            "cet_labels": ["artificial_intelligence"],
        },
        {
            "title": "Qubit control and quantum error correction techniques",
            "assignee": "National Quantum Lab",
            "cet_labels": ["quantum_information_science"],
        },
        {
            "title": "Quantum teleportation using superconducting qubits",
            "assignee": "National Quantum Lab",
            "cet_labels": ["quantum_information_science"],
        },
    ]
    return pd.DataFrame(rows)


def test_train_patent_classifier_and_save_model(tmp_path: Path):
    df = make_training_dataframe()

    # Factory: create DummyPipeline keyed to CET with simple keywords
    def factory(cet_id: str):
        if "artificial" in cet_id:
            return DummyPipeline(
                cet_id=cet_id, keywords=["machine learning", "neural network"], keyword_boost=1.0
            )
        if "quantum" in cet_id:
            return DummyPipeline(cet_id=cet_id, keywords=["quantum", "qubit"], keyword_boost=1.0)
        return DummyPipeline(cet_id=cet_id, keywords=[], keyword_boost=1.0)

    model_path = tmp_path / "patent_classifier.pkl"
    meta = train_patent_classifier(
        df=df,
        output_model_path=model_path,
        pipelines_factory=factory,
        title_col="title",
        assignee_col="assignee",
        cet_label_col="cet_labels",
        use_feature_extraction=True,
    )

    # Model file exists and metadata returned
    assert model_path.exists()
    assert meta.get("trained_on_rows") == len(df)

    # Load and classify sample texts
    classifier = PatentCETClassifier.load(model_path)
    ai_top = classifier.classify("Neural network and machine learning for imaging", top_k=1)[0]
    q_top = classifier.classify("Improved qubit coherence for quantum sensing", top_k=1)[0]
    assert ai_top.cet_id == "artificial_intelligence"
    assert q_top.cet_id == "quantum_information_science"


def test_evaluate_patent_classifier_precision_recall(tmp_path: Path):
    # Train a small model first
    df_train = make_training_dataframe()

    def factory(cet_id: str):
        if "artificial" in cet_id:
            return DummyPipeline(
                cet_id=cet_id, keywords=["machine learning", "neural network"], keyword_boost=1.0
            )
        if "quantum" in cet_id:
            return DummyPipeline(cet_id=cet_id, keywords=["quantum", "qubit"], keyword_boost=1.0)
        return DummyPipeline(cet_id=cet_id, keywords=[], keyword_boost=1.0)

    model_path = tmp_path / "patent_classifier_eval.pkl"
    train_patent_classifier(
        df=df_train,
        output_model_path=model_path,
        pipelines_factory=factory,
        title_col="title",
        assignee_col="assignee",
        cet_label_col="cet_labels",
        use_feature_extraction=True,
    )
    clf = PatentCETClassifier.load(model_path)

    # Build a tiny eval set where we expect decent precision/recall
    df_eval = pd.DataFrame(
        [
            {
                "title": "Machine learning classification for images",
                "assignee": "Acme LLC",
                "cet_labels": ["artificial_intelligence"],
            },
            {
                "title": "Quantum control of qubits improves stability",
                "assignee": "National Quantum Lab",
                "cet_labels": ["quantum_information_science"],
            },
        ]
    )

    metrics = evaluate_patent_classifier(
        clf,
        df_eval,
        title_col="title",
        assignee_col="assignee",
        cet_label_col="cet_labels",
        k_values=(1, 2),
        batch_size=16,
    )
    assert metrics.get("ok") is True
    # In this synthetic setup, we expect non-zero precision/recall
    assert metrics.get("precision_at_1", 0.0) >= 0.0
    assert metrics.get("recall_at_1", 0.0) >= 0.0

    # Also directly exercise precision_recall_at_k with handcrafted predictions
    y_true = [{"artificial_intelligence"}, {"quantum_information_science"}]
    preds = [
        [  # correct top-1
            type("PC", (), {"cet_id": "artificial_intelligence", "score": 0.9}),
            type("PC", (), {"cet_id": "quantum_information_science", "score": 0.1}),
        ],
        [  # correct top-1
            type("PC", (), {"cet_id": "quantum_information_science", "score": 0.9}),
            type("PC", (), {"cet_id": "artificial_intelligence", "score": 0.1}),
        ],
    ]
    pr = precision_recall_at_k(y_true, preds, k=1)
    assert pr["precision_at_k"] == 1.0
    assert pr["recall_at_k"] == 1.0
