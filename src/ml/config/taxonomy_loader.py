"""
Configuration loader for CET taxonomy and classification settings.

Loads YAML configuration files and validates them against Pydantic schemas.
"""

from pathlib import Path

import yaml
from loguru import logger
from pydantic import BaseModel, Field, field_validator

from src.models.cet_models import CETArea


class TaxonomyConfig(BaseModel):
    """Schema for taxonomy.yaml configuration file."""

    version: str = Field(..., description="Taxonomy version (e.g., 'NSTC-2025Q1')")
    last_updated: str = Field(..., description="Last update date")
    description: str = Field(..., description="Taxonomy description")
    cet_areas: list[CETArea] = Field(..., description="List of CET areas")

    @field_validator("cet_areas")
    @classmethod
    def validate_unique_cet_ids(cls, v: list[CETArea]) -> list[CETArea]:
        """Ensure all CET IDs are unique."""
        cet_ids = [area.cet_id for area in v]
        if len(cet_ids) != len(set(cet_ids)):
            raise ValueError("CET IDs must be unique")
        return v

    @field_validator("cet_areas")
    @classmethod
    def validate_cet_count(cls, v: list[CETArea]) -> list[CETArea]:
        """Validate we have 21 CET areas as per NSTC framework."""
        if len(v) != 21:
            logger.warning("Expected 21 CET areas from NSTC framework, got %d", len(v))
        return v


class ClassificationConfig(BaseModel):
    """Schema for classification.yaml configuration file."""

    model_version: str
    created_date: str
    confidence_thresholds: dict[str, float]
    tfidf: dict
    logistic_regression: dict
    calibration: dict
    feature_selection: dict
    evidence: dict
    supporting: dict
    batch: dict
    performance: dict
    quality: dict
    analytics: dict

    @field_validator("confidence_thresholds")
    @classmethod
    def validate_thresholds(cls, v: dict[str, float]) -> dict[str, float]:
        """Validate confidence threshold values."""
        required_keys = {"high", "medium", "low"}
        if not required_keys.issubset(v.keys()):
            raise ValueError(f"Missing required threshold keys: {required_keys - v.keys()}")

        if not (0 <= v["low"] < v["medium"] < v["high"] <= 100):
            raise ValueError("Thresholds must be in order: 0 <= low < medium < high <= 100")
        return v


class TaxonomyLoader:
    """
    Loader for CET taxonomy and classification configuration files.

    Provides validated access to taxonomy and ML configuration.
    """

    def __init__(self, config_dir: Path | None = None) -> None:
        """
        Initialize the taxonomy loader.

        Args:
            config_dir: Path to config/cet directory. Defaults to project config/cet.
        """
        if config_dir is None:
            # Default to project config/cet directory
            project_root = Path(__file__).parent.parent.parent.parent
            config_dir = project_root / "config" / "cet"

        self.config_dir = Path(config_dir)
        self.taxonomy_path = self.config_dir / "taxonomy.yaml"
        self.classification_path = self.config_dir / "classification.yaml"

        # Validate config files exist
        if not self.taxonomy_path.exists():
            raise FileNotFoundError(f"Taxonomy file not found: {self.taxonomy_path}")
        if not self.classification_path.exists():
            raise FileNotFoundError(f"Classification config not found: {self.classification_path}")

        logger.info("Initialized TaxonomyLoader", extra={"config_dir": str(self.config_dir)})

    def load_taxonomy(self) -> TaxonomyConfig:
        """
        Load and validate the CET taxonomy configuration.

        Returns:
            TaxonomyConfig: Validated taxonomy configuration

        Raises:
            FileNotFoundError: If taxonomy.yaml doesn't exist
            ValueError: If taxonomy fails validation
        """
        logger.info("Loading CET taxonomy", extra={"file": str(self.taxonomy_path)})

        with open(self.taxonomy_path) as f:
            raw_config = yaml.safe_load(f)

        # Convert cet_areas dict entries to CETArea objects
        cet_areas_raw = raw_config.get("cet_areas", [])
        cet_areas = [
            CETArea(**{**area, "taxonomy_version": raw_config["version"]}) for area in cet_areas_raw
        ]

        # Build validated config
        taxonomy = TaxonomyConfig(
            version=raw_config["version"],
            last_updated=raw_config["last_updated"],
            description=raw_config["description"],
            cet_areas=cet_areas,
        )

        logger.info(
            "Loaded CET taxonomy",
            extra={
                "version": taxonomy.version,
                "cet_count": len(taxonomy.cet_areas),
            },
        )

        return taxonomy

    def load_classification_config(self) -> ClassificationConfig:
        """
        Load and validate the classification configuration.

        Returns:
            ClassificationConfig: Validated classification configuration

        Raises:
            FileNotFoundError: If classification.yaml doesn't exist
            ValueError: If configuration fails validation
        """
        logger.info("Loading classification config", extra={"file": str(self.classification_path)})

        with open(self.classification_path) as f:
            raw_config = yaml.safe_load(f)

        config = ClassificationConfig(**raw_config)

        logger.info(
            "Loaded classification config",
            extra={"model_version": config.model_version},
        )

        return config

    def get_cet_area(self, cet_id: str) -> CETArea | None:
        """
        Get a specific CET area by ID.

        Args:
            cet_id: CET area identifier

        Returns:
            CETArea if found, None otherwise
        """
        taxonomy = self.load_taxonomy()
        for area in taxonomy.cet_areas:
            if area.cet_id == cet_id:
                return area
        return None

    def get_all_cet_ids(self) -> list[str]:
        """
        Get list of all CET IDs.

        Returns:
            List of CET identifiers
        """
        taxonomy = self.load_taxonomy()
        return [area.cet_id for area in taxonomy.cet_areas]

    def get_cet_keywords(self, cet_id: str) -> list[str]:
        """
        Get keywords for a specific CET area.

        Args:
            cet_id: CET area identifier

        Returns:
            List of keywords, empty list if CET not found
        """
        area = self.get_cet_area(cet_id)
        return area.keywords if area else []


__all__ = ["TaxonomyLoader", "TaxonomyConfig", "ClassificationConfig"]
