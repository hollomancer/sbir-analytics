"""
Unit tests for TaxonomyLoader.

Tests configuration loading, validation, and error handling.
"""

from pathlib import Path

import pytest

pytestmark = pytest.mark.fast
from pydantic import ValidationError

from src.ml.config.taxonomy_loader import ClassificationConfig, TaxonomyConfig, TaxonomyLoader


class TestTaxonomyLoader:
    """Tests for TaxonomyLoader configuration loading."""

    def test_init_with_default_config_dir(self) -> None:
        """Test initialization with default config directory."""
        loader = TaxonomyLoader()

        assert loader.config_dir.exists()
        assert loader.taxonomy_path.exists()
        assert loader.classification_path.exists()

    def test_init_with_custom_config_dir(self, tmp_path: Path) -> None:
        """Test initialization with custom config directory."""
        # Create temporary config files
        cet_dir = tmp_path / "cet"
        cet_dir.mkdir()

        # Create minimal taxonomy.yaml
        taxonomy_file = cet_dir / "taxonomy.yaml"
        taxonomy_file.write_text(
            """
version: "TEST-2025Q1"
last_updated: "2025-01-15"
description: "Test taxonomy"
cet_areas:
  - cet_id: "test_cet"
    name: "Test CET"
    definition: "Test definition"
    keywords: ["test"]
    taxonomy_version: "TEST-2025Q1"
"""
        )

        # Create minimal classification.yaml
        classification_file = cet_dir / "classification.yaml"
        classification_file.write_text(
            """
model_version: "v1.0.0"
created_date: "2025-01-15"
confidence_thresholds:
  high: 70.0
  medium: 40.0
  low: 0.0
tfidf: {}
logistic_regression: {}
calibration: {}
feature_selection: {}
evidence: {}
supporting: {}
batch: {}
performance: {}
quality: {}
analytics: {}
"""
        )

        loader = TaxonomyLoader(config_dir=cet_dir)
        assert loader.config_dir == cet_dir

    def test_missing_taxonomy_file(self, tmp_path: Path) -> None:
        """Test error when taxonomy.yaml is missing."""
        cet_dir = tmp_path / "cet"
        cet_dir.mkdir()

        # Only create classification.yaml, not taxonomy.yaml
        (cet_dir / "classification.yaml").write_text("model_version: v1.0.0\n")

        with pytest.raises(FileNotFoundError, match="Taxonomy file not found"):
            TaxonomyLoader(config_dir=cet_dir)

    def test_missing_classification_file(self, tmp_path: Path) -> None:
        """Test error when classification.yaml is missing."""
        cet_dir = tmp_path / "cet"
        cet_dir.mkdir()

        # Only create taxonomy.yaml
        (cet_dir / "taxonomy.yaml").write_text("version: v1.0.0\n")

        with pytest.raises(FileNotFoundError, match="Classification config not found"):
            TaxonomyLoader(config_dir=cet_dir)

    def test_load_taxonomy(self) -> None:
        """Test loading the real taxonomy configuration."""
        loader = TaxonomyLoader()
        taxonomy = loader.load_taxonomy()

        assert isinstance(taxonomy, TaxonomyConfig)
        assert taxonomy.version == "NSTC-2025Q1"
        assert len(taxonomy.cet_areas) == 21
        assert all(area.taxonomy_version == "NSTC-2025Q1" for area in taxonomy.cet_areas)

    def test_load_classification_config(self) -> None:
        """Test loading the classification configuration."""
        loader = TaxonomyLoader()
        config = loader.load_classification_config()

        assert isinstance(config, ClassificationConfig)
        assert config.model_version == "v1.0.0"
        assert "high" in config.confidence_thresholds
        assert "medium" in config.confidence_thresholds
        assert "low" in config.confidence_thresholds

    def test_get_cet_area(self) -> None:
        """Test retrieving a specific CET area by ID."""
        loader = TaxonomyLoader()
        area = loader.get_cet_area("artificial_intelligence")

        assert area is not None
        assert area.cet_id == "artificial_intelligence"
        assert area.name == "Artificial Intelligence"
        assert len(area.keywords) > 0

    def test_get_cet_area_not_found(self) -> None:
        """Test that None is returned for non-existent CET ID."""
        loader = TaxonomyLoader()
        area = loader.get_cet_area("nonexistent_cet")

        assert area is None

    def test_get_all_cet_ids(self) -> None:
        """Test getting list of all CET IDs."""
        loader = TaxonomyLoader()
        cet_ids = loader.get_all_cet_ids()

        assert len(cet_ids) == 21
        assert "artificial_intelligence" in cet_ids
        assert "quantum_information_science" in cet_ids
        assert "biotechnologies" in cet_ids

    def test_get_cet_keywords(self) -> None:
        """Test getting keywords for a specific CET area."""
        loader = TaxonomyLoader()
        keywords = loader.get_cet_keywords("artificial_intelligence")

        assert len(keywords) > 0
        assert "machine learning" in keywords or "artificial intelligence" in keywords

    def test_get_cet_keywords_not_found(self) -> None:
        """Test that empty list is returned for non-existent CET."""
        loader = TaxonomyLoader()
        keywords = loader.get_cet_keywords("nonexistent_cet")

        assert keywords == []


class TestTaxonomyConfig:
    """Tests for TaxonomyConfig validation."""

    def test_valid_taxonomy_config(self, tmp_path: Path) -> None:
        """Test creating a valid taxonomy configuration."""
        from src.models.cet_models import CETArea

        cet_areas = [
            CETArea(
                cet_id="ai",
                name="AI",
                definition="AI tech",
                keywords=["ml"],
                taxonomy_version="TEST-2025Q1",
            )
        ]

        config = TaxonomyConfig(
            version="TEST-2025Q1",
            last_updated="2025-01-15",
            description="Test",
            cet_areas=cet_areas,
        )

        assert config.version == "TEST-2025Q1"
        assert len(config.cet_areas) == 1

    def test_duplicate_cet_ids(self) -> None:
        """Test that duplicate CET IDs are rejected."""
        from src.models.cet_models import CETArea

        cet_areas = [
            CETArea(
                cet_id="ai",
                name="AI 1",
                definition="AI",
                taxonomy_version="TEST-2025Q1",
            ),
            CETArea(
                cet_id="ai",
                name="AI 2",
                definition="AI duplicate",
                taxonomy_version="TEST-2025Q1",
            ),
        ]

        with pytest.raises(ValidationError, match="CET IDs must be unique"):
            TaxonomyConfig(
                version="TEST-2025Q1",
                last_updated="2025-01-15",
                description="Test",
                cet_areas=cet_areas,
            )


class TestClassificationConfig:
    """Tests for ClassificationConfig validation."""

    def test_valid_classification_config(self) -> None:
        """Test creating a valid classification configuration."""
        config = ClassificationConfig(
            model_version="v1.0.0",
            created_date="2025-01-15",
            confidence_thresholds={"high": 70.0, "medium": 40.0, "low": 0.0},
            tfidf={},
            logistic_regression={},
            calibration={},
            feature_selection={},
            evidence={},
            supporting={},
            batch={},
            performance={},
            quality={},
            analytics={},
        )

        assert config.model_version == "v1.0.0"
        assert config.confidence_thresholds["high"] == 70.0

    def test_missing_threshold_keys(self) -> None:
        """Test that missing threshold keys are rejected."""
        with pytest.raises(ValidationError, match="Missing required threshold keys"):
            ClassificationConfig(
                model_version="v1.0.0",
                created_date="2025-01-15",
                confidence_thresholds={"high": 70.0},  # Missing medium and low
                tfidf={},
                logistic_regression={},
                calibration={},
                feature_selection={},
                evidence={},
                supporting={},
                batch={},
                performance={},
                quality={},
                analytics={},
            )

    def test_invalid_threshold_order(self) -> None:
        """Test that thresholds must be in ascending order."""
        with pytest.raises(ValidationError, match="must be in order"):
            ClassificationConfig(
                model_version="v1.0.0",
                created_date="2025-01-15",
                confidence_thresholds={
                    "high": 40.0,  # Wrong: high should be > medium
                    "medium": 70.0,
                    "low": 0.0,
                },
                tfidf={},
                logistic_regression={},
                calibration={},
                feature_selection={},
                evidence={},
                supporting={},
                batch={},
                performance={},
                quality={},
                analytics={},
            )
