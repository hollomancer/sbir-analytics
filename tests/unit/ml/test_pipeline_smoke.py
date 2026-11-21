"""Fast smoke tests covering the slow ML pipelines."""

from __future__ import annotations

import pandas as pd
import pytest

from sbir_ml.ml.models.patent_classifier import PatentCETClassifier


pytestmark = pytest.mark.fast


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
        from sbir_ml.ml.models.dummy_pipeline import DummyPipeline

        return DummyPipeline(cet_id=cet_id, keywords=keywords, keyword_boost=1.0)

    classifier.train_from_dataframe(
        df,
        title_col="title",
        assignee_col="assignee",
        cet_label_col="cet_labels",
        pipelines_factory=factory,
    )

    results = classifier.classify(
        "Neural network model for sensor fusion", assignee="Acme LLC", top_k=1
    )
    assert results
    assert results[0].cet_id in {"artificial_intelligence", "quantum_information_science"}
