"""
Configuration loader for CET taxonomy and classification settings.

Loads YAML configuration files and validates them against Pydantic schemas.
"""

from pathlib import Path
from typing import Any

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

        # Run additional completeness validations (non-fatal; emits metrics for asset metadata)
        completeness = self.validate_taxonomy_completeness(taxonomy)
        # Store last completeness for inspection if needed
        self._last_completeness = completeness

        metadata = {
            "version": taxonomy.version,
            "cet_count": len(taxonomy.cet_areas),
            "completeness": completeness,
        }

        # Log an info record with completeness metrics; warn if there are notable gaps
        if (
            completeness.get("missing_required_fields")
            or completeness.get("areas_missing_keywords_count", 0) > 0
        ):
            logger.warning(
                "Loaded CET taxonomy with completeness issues",
                extra=metadata,
            )
        else:
            logger.info("Loaded CET taxonomy", extra=metadata)

        return taxonomy

    def validate_taxonomy_completeness(self, taxonomy: TaxonomyConfig) -> dict[str, Any]:
        """
        Perform lightweight completeness checks on a loaded taxonomy.

        Returns a dictionary of simple metrics useful for asset metadata and
        automated asset checks (e.g., number of areas missing keywords, missing definitions).

        This validation is intentionally non-fatal: it surfaces issues for review
        rather than blocking pipeline runs. If stricter behavior is desired, raise
        an exception instead.

        Args:
            taxonomy: TaxonomyConfig object returned by load_taxonomy()

        Returns:
            dict: completeness metrics
        """
        total = len(taxonomy.cet_areas)
        areas_missing_keywords: list[str] = []
        areas_missing_definition: list[str] = []
        areas_with_parent: int = 0
        missing_required_fields = False

        for area in taxonomy.cet_areas:
            # Keywords should be a non-empty list
            if not area.keywords or (isinstance(area.keywords, list) and len(area.keywords) == 0):
                areas_missing_keywords.append(area.cet_id)

            # Definition should be non-empty
            if not area.definition or not str(area.definition).strip():
                areas_missing_definition.append(area.cet_id)

            if area.parent_cet_id:
                areas_with_parent += 1

            # Check for core required fields presence (cet_id, name)
            if not getattr(area, "cet_id", None) or not getattr(area, "name", None):
                missing_required_fields = True

        metrics: dict[str, Any] = {
            "total_areas": total,
            "areas_missing_keywords_count": len(areas_missing_keywords),
            "areas_missing_keywords": areas_missing_keywords[:20],  # limit length for metadata
            "areas_missing_definition_count": len(areas_missing_definition),
            "areas_missing_definition": areas_missing_definition[:20],
            "areas_with_parent_count": areas_with_parent,
            "missing_required_fields": missing_required_fields,
            "missing_required_fields_flag": missing_required_fields,
            "missing_required_fields_detail": missing_required_fields,
        }

        # Simplify flag for consumers
        metrics["missing_required_fields"] = missing_required_fields
        metrics["missing_required_fields_flag"] = missing_required_fields

        return metrics

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
