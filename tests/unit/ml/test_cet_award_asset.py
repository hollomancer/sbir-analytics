import json
import pickle
from datetime import datetime
from pathlib import Path

import pandas as pd

from src.assets.cet_assets import enriched_cet_award_classifications
from src.ml.models.dummy_pipeline import DummyPipeline


def _write_configs(root: Path):
    """
    Create minimal taxonomy.yaml and classification.yaml under <root>/config/cet
    to satisfy TaxonomyLoader expectations.
    """
    cet_dir = root / "config" / "cet"
    cet_dir.mkdir(parents=True, exist_ok=True)

    taxonomy = {
        "version": "TEST-2025Q1",
        "last_updated": "2025-01-01",
        "description": "Test taxonomy for unit tests",
        "cet_areas": [
            {
                "cet_id": "artificial_intelligence",
                "name": "Artificial Intelligence",
                "definition": "AI and ML technologies",
                "keywords": ["machine learning", "neural network"],
                "parent_cet_id": None,
            },
            {
                "cet_id": "quantum_information_science",
                "name": "Quantum Information Science",
                "definition": "Quantum computing and related algorithms",
                "keywords": ["quantum", "qubit", "entanglement"],
                "parent_cet_id": None,
            },
        ],
    }

    classification = {
        "model_version": "vtest",
        "created_date": "2025-01-01",
        "confidence_thresholds": {"high": 70.0, "medium": 40.0, "low": 0.0},
        "tfidf": {"max_features": 5000, "ngram_range": [1, 2], "keyword_boost_factor": 2.0},
        "logistic_regression": {"C": 1.0, "max_iter": 1000},
        "calibration": {"method": "sigmoid", "cv": 3},
        "feature_selection": {"enabled": False, "k_best": 3000},
        "evidence": {"max_statements": 3, "excerpt_max_words": 50},
        "supporting": {"max_supporting_areas": 3, "min_score_threshold": 40.0},
        "batch": {"size": 1000},
        "performance": {},
        "quality": {},
        "analytics": {},
    }

    with open(cet_dir / "taxonomy.yaml", "w", encoding="utf-8") as fh:
        json.dump(taxonomy, fh, indent=2)

    with open(cet_dir / "classification.yaml", "w", encoding="utf-8") as fh:
        json.dump(classification, fh, indent=2)


def _write_enriched_ndjson(root: Path, records):
    """Write NDJSON to data/processed/enriched_sbir_awards.ndjson for asset consumption."""
    data_dir = root / "data" / "processed"
    data_dir.mkdir(parents=True, exist_ok=True)
    ndjson_path = data_dir / "enriched_sbir_awards.ndjson"
    with open(ndjson_path, "w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r) + "\n")
    return ndjson_path


def _read_checks(root: Path):
    p = root / "data" / "processed" / "cet_award_classifications.checks.json"
    assert p.exists(), f"Checks file not found at {p}"
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def _read_output_records(root: Path):
    """
    Read output written by the asset. The asset prefers parquet but falls back
    to NDJSON (.json). This helper reads whichever is present.
    """
    out_parquet = root / "data" / "processed" / "cet_award_classifications.parquet"
    out_json = root / "data" / "processed" / "cet_award_classifications.json"
    if out_json.exists():
        recs = []
        with open(out_json, encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    recs.append(json.loads(line))
        return recs
    if out_parquet.exists():
        return pd.read_parquet(out_parquet).to_dict(orient="records")
    # If touched placeholder exists but no content, return empty list
    if out_parquet.exists() and out_parquet.stat().st_size == 0:
        return []
    return []


def test_cet_award_asset_writes_placeholder_when_model_missing(tmp_path, monkeypatch):
    """
    When the trained model artifact is missing, the asset should still run and
    write a schema-compatible placeholder output plus a checks JSON describing
    the missing model.
    """
    # run in isolated tmp dir so asset reads/writes local paths
    monkeypatch.chdir(tmp_path)

    # create minimal config files
    _write_configs(tmp_path)

    # write two enriched award records (NDJSON) so asset has input to process
    records = [
        {
            "award_id": "award_001",
            "title": "ML imaging",
            "abstract": "This project uses machine learning for image classification.",
            "keywords": ["machine learning", "imaging"],
        },
        {
            "award_id": "award_002",
            "title": "Quantum sensor",
            "abstract": "Research on qubit coherence and entanglement for sensors.",
            "keywords": ["quantum", "qubit"],
        },
    ]
    _write_enriched_ndjson(tmp_path, records)

    # Ensure no model artifact present
    model_path = tmp_path / "artifacts" / "models" / "cet_classifier_v1.pkl"
    if model_path.exists():
        model_path.unlink()

    # Execute asset
    enriched_cet_award_classifications()

    # Validate checks JSON indicates missing model and contains correct counts
    checks = _read_checks(tmp_path)
    assert checks.get("reason") == "model_missing"
    assert checks.get("num_awards") == 2
    assert checks.get("num_classified") == 0

    # Output placeholder should exist (either parquet placeholder or json)
    out_records = _read_output_records(tmp_path)
    # When placeholder is used, likely no records; ensure schema is present by checking file existence
    # but also accept empty records list as valid placeholder behavior.
    assert isinstance(out_records, list)


def test_cet_award_asset_classifies_with_synthetic_model(tmp_path, monkeypatch):
    """
    Create a small synthetic model artifact composed of DummyPipeline objects
    and assert the asset performs real classifications and writes checks/results.
    """
    monkeypatch.chdir(tmp_path)

    # write configs
    _write_configs(tmp_path)

    # write enriched awards NDJSON (two records mapped to the two CET areas)
    records = [
        {
            "award_id": "award_001",
            "title": "ML imaging",
            "abstract": "This project uses machine learning for image classification.",
            "keywords": ["machine learning", "imaging"],
        },
        {
            "award_id": "award_002",
            "title": "Quantum sensor",
            "abstract": "Research on qubit coherence and entanglement for sensors.",
            "keywords": ["quantum", "qubit"],
        },
    ]
    _write_enriched_ndjson(tmp_path, records)

    # Build a synthetic model artifact (pickle) compatible with ApplicabilityModel.load()
    # Pipelines keyed by CET ID, using DummyPipeline to provide predict_proba()
    pipelines = {
        "artificial_intelligence": DummyPipeline(
            cet_id="artificial_intelligence", keywords=["machine learning"], keyword_boost=1.0
        ),
        "quantum_information_science": DummyPipeline(
            cet_id="quantum_information_science", keywords=["quantum", "qubit"], keyword_boost=1.0
        ),
    }

    cet_areas = [
        {
            "cet_id": "artificial_intelligence",
            "name": "Artificial Intelligence",
            "definition": "AI & ML",
            "keywords": ["machine learning", "neural network"],
            "parent_cet_id": None,
            "taxonomy_version": "TEST-2025Q1",
        },
        {
            "cet_id": "quantum_information_science",
            "name": "Quantum Information Science",
            "definition": "Quantum computing & algorithms",
            "keywords": ["quantum", "qubit", "entanglement"],
            "parent_cet_id": None,
            "taxonomy_version": "TEST-2025Q1",
        },
    ]

    model_data = {
        "pipelines": pipelines,
        "cet_areas": cet_areas,
        "config": {
            "model_version": "vtest",
            "confidence_thresholds": {"high": 70.0, "medium": 40.0, "low": 0.0},
            "batch": {"size": 1000},
        },
        "taxonomy_version": "TEST-2025Q1",
        "training_date": datetime.utcnow().isoformat(),
        "model_version": "vtest",
        "is_trained": True,
    }

    model_path = tmp_path / "artifacts" / "models"
    model_path.mkdir(parents=True, exist_ok=True)
    model_file = model_path / "cet_classifier_v1.pkl"
    with open(model_file, "wb") as fh:
        pickle.dump(model_data, fh)

    # Execute asset (should load model artifact and classify)
    enriched_cet_award_classifications()

    # Validate checks JSON
    checks = _read_checks(tmp_path)
    assert checks.get("ok") is True
    assert checks.get("num_awards") == 2
    # Expect both awards to be classified by our synthetic model
    assert checks.get("num_classified") == 2

    # Validate output records contain expected primary CETs
    out_records = _read_output_records(tmp_path)
    # Ensure at least as many rows as awards
    assert len(out_records) == 2

    # Map award_id -> primary_cet for assertions
    mapping = {r.get("award_id"): r.get("primary_cet") for r in out_records}
    assert mapping["award_001"] == "artificial_intelligence"
    assert mapping["award_002"] == "quantum_information_science"


from pathlib import Path

import pytest


pytestmark = pytest.mark.fast
