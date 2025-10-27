"""
Pytest fixtures for CET classification tests.

Provides reusable test fixtures for CET models, configuration, and sample data.
"""

from datetime import datetime
from pathlib import Path

import pytest
import yaml

from src.ml.config.taxonomy_loader import TaxonomyLoader
from src.models.cet_models import (
    CETArea,
    CETAssessment,
    CETClassification,
    ClassificationLevel,
    CompanyCETProfile,
    EvidenceStatement,
)


@pytest.fixture
def sample_cet_area() -> CETArea:
    """Sample CET area for testing."""
    return CETArea(
        cet_id="artificial_intelligence",
        name="Artificial Intelligence",
        definition="Machine learning, deep learning, and AI systems",
        keywords=["machine learning", "deep learning", "neural networks", "ai"],
        taxonomy_version="NSTC-2025Q1",
    )


@pytest.fixture
def sample_evidence_statement() -> EvidenceStatement:
    """Sample evidence statement for testing."""
    return EvidenceStatement(
        excerpt="This project develops machine learning algorithms for pattern recognition",
        source_location="abstract",
        rationale_tag="Contains: machine learning, pattern recognition",
    )


@pytest.fixture
def sample_high_confidence_classification(
    sample_evidence_statement: EvidenceStatement,
) -> CETClassification:
    """Sample high-confidence CET classification for testing."""
    return CETClassification(
        cet_id="artificial_intelligence",
        score=85.0,
        classification=ClassificationLevel.HIGH,
        primary=True,
        evidence=[sample_evidence_statement],
    )


@pytest.fixture
def sample_medium_confidence_classification() -> CETClassification:
    """Sample medium-confidence CET classification for testing."""
    return CETClassification(
        cet_id="autonomous_systems",
        score=55.0,
        classification=ClassificationLevel.MEDIUM,
        primary=False,
        evidence=[],
    )


@pytest.fixture
def sample_low_confidence_classification() -> CETClassification:
    """Sample low-confidence CET classification for testing."""
    return CETClassification(
        cet_id="biotechnologies",
        score=25.0,
        classification=ClassificationLevel.LOW,
        primary=False,
        evidence=[],
    )


@pytest.fixture
def sample_cet_assessment(
    sample_high_confidence_classification: CETClassification,
    sample_medium_confidence_classification: CETClassification,
) -> CETAssessment:
    """Sample CET assessment for testing."""
    return CETAssessment(
        entity_id="award_123",
        entity_type="award",
        primary_cet=sample_high_confidence_classification,
        supporting_cets=[sample_medium_confidence_classification],
        classified_at=datetime(2025, 1, 15, 10, 30, 0),
        taxonomy_version="NSTC-2025Q1",
        model_version="v1.0.0",
    )


@pytest.fixture
def sample_company_cet_profile() -> CompanyCETProfile:
    """Sample company CET profile for testing."""
    return CompanyCETProfile(
        company_id="company_123",
        dominant_cet_id="artificial_intelligence",
        award_count=15,
        total_funding=5000000.0,
        avg_score=78.5,
        specialization_score=0.65,
        dominant_phase="II",
        first_award_date=datetime(2020, 1, 1),
        last_award_date=datetime(2024, 12, 31),
        cet_areas=["artificial_intelligence", "autonomous_systems", "biotechnologies"],
    )


@pytest.fixture
def sample_award_data() -> dict:
    """Sample SBIR award data for classification testing."""
    return {
        "award_id": "award_001",
        "title": "Advanced Machine Learning for Pattern Recognition",
        "abstract": (
            "This project develops novel machine learning algorithms using deep neural networks "
            "for automated pattern recognition in large-scale datasets. The research focuses on "
            "transfer learning and ensemble methods to improve classification accuracy."
        ),
        "keywords": ["machine learning", "deep learning", "pattern recognition", "neural networks"],
        "agency": "DOD",
        "phase": "II",
        "award_amount": 750000.0,
        "award_date": "2024-01-15",
    }


@pytest.fixture
def sample_award_data_batch() -> list[dict]:
    """Sample batch of SBIR awards for batch classification testing."""
    return [
        {
            "award_id": "award_001",
            "title": "AI for Autonomous Vehicles",
            "abstract": "Developing artificial intelligence and machine learning for autonomous vehicle navigation",
            "keywords": ["ai", "autonomous", "machine learning"],
            "agency": "DOD",
        },
        {
            "award_id": "award_002",
            "title": "Quantum Computing Algorithms",
            "abstract": "Novel quantum algorithms for optimization problems using quantum entanglement",
            "keywords": ["quantum computing", "quantum algorithms", "optimization"],
            "agency": "NSF",
        },
        {
            "award_id": "award_003",
            "title": "Biotech Drug Discovery",
            "abstract": "Synthetic biology and genetic engineering for novel drug development",
            "keywords": ["synthetic biology", "genetic engineering", "drug discovery"],
            "agency": "NIH",
        },
    ]


@pytest.fixture
def taxonomy_loader() -> TaxonomyLoader:
    """TaxonomyLoader instance for testing."""
    return TaxonomyLoader()


@pytest.fixture
def mock_taxonomy_config(tmp_path: Path) -> Path:
    """Create a minimal mock taxonomy configuration for testing."""
    cet_dir = tmp_path / "cet"
    cet_dir.mkdir()

    taxonomy_data = {
        "version": "TEST-2025Q1",
        "last_updated": "2025-01-15",
        "description": "Test taxonomy",
        "cet_areas": [
            {
                "cet_id": "artificial_intelligence",
                "name": "Artificial Intelligence",
                "definition": "AI and ML technologies",
                "keywords": ["machine learning", "deep learning", "ai"],
                "parent_cet_id": None,
            },
            {
                "cet_id": "quantum_information_science",
                "name": "Quantum Information Science",
                "definition": "Quantum computing and communications",
                "keywords": ["quantum computing", "quantum algorithms", "qubits"],
                "parent_cet_id": None,
            },
        ],
    }

    taxonomy_file = cet_dir / "taxonomy.yaml"
    with open(taxonomy_file, "w") as f:
        yaml.dump(taxonomy_data, f)

    classification_data = {
        "model_version": "v1.0.0",
        "created_date": "2025-01-15",
        "confidence_thresholds": {"high": 70.0, "medium": 40.0, "low": 0.0},
        "tfidf": {
            "max_features": 5000,
            "ngram_range": [1, 2],
            "keyword_boost_factor": 2.0,
        },
        "logistic_regression": {"C": 1.0, "max_iter": 1000},
        "calibration": {"method": "sigmoid", "cv": 3},
        "feature_selection": {"enabled": True, "k_best": 3000},
        "evidence": {"max_statements": 3, "excerpt_max_words": 50},
        "supporting": {"max_supporting_areas": 3, "min_score_threshold": 40.0},
        "batch": {"size": 1000},
        "performance": {"target_throughput": 1000, "target_latency": 1.0},
        "quality": {
            "min_success_rate": 0.95,
            "min_high_confidence_rate": 0.60,
            "min_evidence_coverage": 0.80,
        },
        "analytics": {"use_duckdb": True},
    }

    classification_file = cet_dir / "classification.yaml"
    with open(classification_file, "w") as f:
        yaml.dump(classification_data, f)

    return cet_dir


@pytest.fixture
def mock_trained_model_path(tmp_path: Path) -> Path:
    """Path to a mock trained model file."""
    model_path = tmp_path / "models" / "cet_classifier_v1.pkl"
    model_path.parent.mkdir(parents=True, exist_ok=True)
    return model_path


@pytest.fixture
def sample_training_data() -> list[dict]:
    """Sample training data for model training tests."""
    return [
        {
            "text": "Machine learning and deep neural networks for computer vision applications",
            "label": "artificial_intelligence",
            "score": 0.95,
        },
        {
            "text": "Quantum computing algorithms using quantum entanglement and superposition",
            "label": "quantum_information_science",
            "score": 0.92,
        },
        {
            "text": "Synthetic biology and CRISPR gene editing for therapeutic applications",
            "label": "biotechnologies",
            "score": 0.88,
        },
        {
            "text": "Additive manufacturing and 3D printing for aerospace components",
            "label": "advanced_manufacturing",
            "score": 0.85,
        },
        {
            "text": "Autonomous drone systems with path planning and collision avoidance",
            "label": "autonomous_systems",
            "score": 0.90,
        },
    ]


@pytest.fixture
def cet_classification_thresholds() -> dict[str, float]:
    """Standard CET classification thresholds."""
    return {
        "high": 70.0,
        "medium": 40.0,
        "low": 0.0,
    }


@pytest.fixture
def all_cet_ids() -> list[str]:
    """List of all 21 CET area IDs."""
    return [
        "advanced_computing",
        "advanced_engineering_materials",
        "advanced_gas_turbine_engine_technologies",
        "advanced_manufacturing",
        "advanced_and_networked_sensing_and_signature_management",
        "advanced_nuclear_energy_systems",
        "artificial_intelligence",
        "autonomous_systems",
        "biotechnologies",
        "communication_and_networking_technologies",
        "directed_energy",
        "financial_technologies",
        "human_machine_interfaces",
        "hypersonics",
        "integrated_sensing_and_cyber",
        "quantum_information_science",
        "renewable_energy_generation_and_storage",
        "semiconductors_and_microelectronics",
        "space_technologies_and_systems",
        "trusted_ai_and_autonomy",
        "integrated_network_systems_of_systems",
    ]
