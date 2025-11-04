# sbir-etl/tests/unit/ml/test_patent_feature_integration.py

import pytest


# These tests exercise integration between the lightweight patent feature
# extractor and the PatentCETClassifier training flow using DummyPipeline.
pd = pytest.importorskip("pandas")

from src.ml.models.dummy_pipeline import DummyPipeline
from src.ml.models.patent_classifier import PatentCETClassifier


# Feature helpers are optional in some environments; skip the integration test if not present.
pytest.importorskip("src.ml.features.patent_features")
from src.ml.features.patent_features import PatentFeatureVector, extract_features


def make_pipelines_factory():
    """
    Return a factory function that constructs DummyPipeline instances
    appropriate for a given CET id.
    """

    def factory(cet_id: str):
        if "artificial" in cet_id:
            return DummyPipeline(
                cet_id=cet_id, keywords=["machine learning", "neural network"], keyword_boost=1.0
            )
        if "quantum" in cet_id:
            return DummyPipeline(cet_id=cet_id, keywords=["quantum", "qubit"], keyword_boost=1.0)
        # default pipeline with no keywords yields 0.0 scores
        return DummyPipeline(cet_id=cet_id, keywords=[], keyword_boost=1.0)

    return factory


def test_extract_features_basic():
    rec = {
        "title": "Machine learning for sensor fusion",
        "abstract": "A novel neural network architecture.",
        "assignee": "Acme Technologies, Inc.",
        "ipc": "G06F 17/30",
        "application_year": 2022,
    }
    fv = extract_features(rec)
    assert isinstance(fv, PatentFeatureVector)
    d = fv.as_dict()
    # Basic expectations
    assert "machine" in d["normalized_title"]
    assert isinstance(d["tokens"], list)
    assert d["has_ipc"] is True
    assert d["assignee_type"] in ("company", "academic", "government", "individual", "unknown")


def test_train_classifier_with_feature_extraction_and_dummy_pipelines(tmp_path):
    # Build a small synthetic dataset with two CET labels across records
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
    df = pd.DataFrame(rows)

    # Classifier starts with no pipelines; we'll provide a pipelines_factory
    classifier = PatentCETClassifier(pipelines={})

    # Train using feature extraction (use_feature_extraction=True)
    pipelines_factory = make_pipelines_factory()
    classifier.train_from_dataframe(
        df,
        title_col="title",
        assignee_col="assignee",
        cet_label_col="cet_labels",
        pipelines_factory=pipelines_factory,
        use_feature_extraction=True,
    )

    # After training, classifier should be marked trained and pipelines should be present
    assert classifier.is_trained is True
    assert classifier.pipelines, "Pipelines should have been created by pipelines_factory"

    # Ensure each pipeline was fitted (DummyPipeline sets is_fitted on fit)
    for _cet, pipe in classifier.pipelines.items():
        # DummyPipeline exposes is_fitted attribute
        if hasattr(pipe, "is_fitted"):
            assert pipe.is_fitted is True

    # Classify a ML-related title and expect artificial_intelligence to be top
    res_ai = classifier.classify(
        "Neural network model for image reconstruction", assignee="Acme LLC", top_k=1
    )
    assert isinstance(res_ai, list) and len(res_ai) >= 1
    assert res_ai[0].cet_id == "artificial_intelligence"

    # Classify a quantum-related title and expect quantum_information_science to be top
    res_q = classifier.classify(
        "Improved qubit coherence times in a superconducting processor",
        assignee="National Quantum Lab",
        top_k=1,
    )
    assert isinstance(res_q, list) and len(res_q) >= 1
    assert res_q[0].cet_id == "quantum_information_science"

    # Optionally test save/load roundtrip
    model_path = tmp_path / "patent_model.pkl"
    classifier.save(model_path)
    assert model_path.exists()
    loaded = PatentCETClassifier.load(model_path)
    # Loaded classifier should be able to classify similarly on a sample text
    loaded_top = loaded.classify(
        "Neural network model for imaging sensors", assignee="Acme LLC", top_k=1
    )[0].cet_id
    assert loaded_top == "artificial_intelligence"
