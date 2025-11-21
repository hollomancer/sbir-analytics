"""Consolidated configuration mocking utilities for tests.

This module provides factory functions and fixtures for creating mock PipelineConfig
instances, reducing duplication across test files.

Usage:
    from tests.utils.config_mocks import create_mock_pipeline_config, mock_usaspending_config

    def test_my_feature():
        config = create_mock_pipeline_config()
        # Use config...
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock


try:
    import pytest
except ImportError:
    pytest = None  # pytest only needed for fixtures, not factory functions

from src.config.schemas import PipelineConfig


def create_mock_pipeline_config(**overrides: Any) -> PipelineConfig:
    """Create a mock PipelineConfig instance with sensible defaults.

    Args:
        **overrides: Keyword arguments to override default config values.
                     Nested keys can be specified with dot notation or by passing
                     nested dictionaries.

    Returns:
        PipelineConfig instance with defaults and overrides applied.

    Example:
        # Override specific nested values
        config = create_mock_pipeline_config(
            enrichment__usaspending_api__base_url="https://test.api.gov"
        )

        # Or pass nested dicts
        config = create_mock_pipeline_config(
            enrichment={"usaspending_api": {"base_url": "https://test.api.gov"}}
        )
    """
    # Start with a minimal valid config
    config_dict: dict[str, Any] = {
        "pipeline": {
            "name": "sbir-analytics",
            "version": "0.1.0",
            "environment": "test",
        },
        "paths": {
            "data_dir": "data",
            "cache_dir": "data/cache",
            "reports_dir": "reports",
        },
        "enrichment": {
            "usaspending_api": {
                "base_url": "https://api.usaspending.gov/api/v2",
                "timeout_seconds": 30,
                "retry_attempts": 3,
                "retry_backoff_seconds": 2,
            },
            "sam_gov": {
                "base_url": "https://api.sam.gov/entity-information/v3",
                "rate_limit_per_minute": 60,
                "timeout_seconds": 30,
            },
            "patentsview_api": {
                "base_url": "https://search.patentsview.org/api",
                "rate_limit_per_minute": 60,
                "timeout_seconds": 30,
            },
        },
        "enrichment_refresh": {
            "usaspending": {
                "timeout_seconds": 30,
                "retry_attempts": 3,
                "retry_backoff_seconds": 2.0,
                "retry_backoff_multiplier": 2.0,
                "rate_limit_per_minute": 120,
                "state_file": "data/state/enrichment_refresh_state.json",
            },
        },
        "neo4j": {
            "uri": "bolt://localhost:7687",
            "database": "neo4j",
            "batch_size": 1000,
        },
        "duckdb": {
            "database_path": ":memory:",
        },
        "logging": {
            "level": "INFO",
            "enabled": True,
        },
        "data_quality": {
            "completeness": {"award_id": 1.0},
        },
    }

    # Apply overrides (support both dot notation and nested dicts)
    for key, value in overrides.items():
        if "__" in key:
            # Handle dot notation: enrichment__usaspending_api__base_url
            parts = key.split("__")
            current = config_dict
            for part in parts[:-1]:
                if part not in current:
                    current[part] = {}
                current = current[part]
            current[parts[-1]] = value
        else:
            # Handle nested dicts or direct keys
            if isinstance(value, dict) and key in config_dict and isinstance(config_dict[key], dict):
                config_dict[key].update(value)
            else:
                config_dict[key] = value

    # Create PipelineConfig instance
    try:
        return PipelineConfig.model_validate(config_dict)
    except Exception:
        # If validation fails, return a MagicMock that behaves like PipelineConfig
        # This is useful for tests that don't need full validation
        mock_config = MagicMock(spec=PipelineConfig)
        for key, value in config_dict.items():
            setattr(mock_config, key, value)
        return mock_config


def create_mock_usaspending_config(
    base_url: str = "https://api.usaspending.gov/api/v2",
    timeout_seconds: int = 30,
    retry_attempts: int = 3,
    rate_limit_per_minute: int = 120,
    state_file: str | Path | None = None,
) -> dict[str, Any]:
    """Create a mock USAspending API configuration dictionary.

    Args:
        base_url: API base URL
        timeout_seconds: Request timeout
        retry_attempts: Number of retry attempts
        rate_limit_per_minute: Rate limit
        state_file: Path to state file (converted to string)

    Returns:
        Dictionary with USAspending config structure.
    """
    config = {
        "base_url": base_url,
        "timeout_seconds": timeout_seconds,
        "retry_attempts": retry_attempts,
        "retry_backoff_seconds": 2.0,
        "retry_backoff_multiplier": 2.0,
        "rate_limit_per_minute": rate_limit_per_minute,
    }
    if state_file:
        config["state_file"] = str(state_file)
    return config


def create_mock_neo4j_config(
    uri: str = "bolt://localhost:7687",
    database: str = "neo4j",
    batch_size: int = 1000,
    username: str | None = None,
    password: str | None = None,
) -> dict[str, Any]:
    """Create a mock Neo4j configuration dictionary.

    Args:
        uri: Neo4j connection URI
        database: Database name
        batch_size: Batch size for operations
        username: Username (optional)
        password: Password (optional)

    Returns:
        Dictionary with Neo4j config structure.
    """
    config: dict[str, Any] = {
        "uri": uri,
        "database": database,
        "batch_size": batch_size,
    }
    if username:
        config["username"] = username
    if password:
        config["password"] = password
    return config


def create_mock_enrichment_refresh_config(
    source: str = "usaspending",
    timeout_seconds: int = 30,
    retry_attempts: int = 3,
    rate_limit_per_minute: int = 120,
    state_file: str | Path | None = None,
) -> dict[str, Any]:
    """Create a mock enrichment refresh configuration dictionary.

    Args:
        source: Enrichment source name (usaspending, sam_gov, etc.)
        timeout_seconds: Request timeout
        retry_attempts: Number of retry attempts
        rate_limit_per_minute: Rate limit
        state_file: Path to state file

    Returns:
        Dictionary with enrichment refresh config structure.
    """
    config = {
        "timeout_seconds": timeout_seconds,
        "retry_attempts": retry_attempts,
        "retry_backoff_seconds": 2.0,
        "retry_backoff_multiplier": 2.0,
        "rate_limit_per_minute": rate_limit_per_minute,
    }
    if state_file:
        config["state_file"] = str(state_file)
    return {source: config}


if pytest is not None:
    @pytest.fixture
    def mock_pipeline_config() -> PipelineConfig:
        """Pytest fixture providing a default mock PipelineConfig."""
        return create_mock_pipeline_config()


    @pytest.fixture
    def mock_usaspending_config(tmp_path: Path) -> dict[str, Any]:
        """Pytest fixture providing mock USAspending configuration."""
        return create_mock_usaspending_config(state_file=tmp_path / "state.json")


    @pytest.fixture
    def mock_neo4j_config() -> dict[str, Any]:
        """Pytest fixture providing mock Neo4j configuration."""
        return create_mock_neo4j_config()


    @pytest.fixture
    def mock_get_config_patch(monkeypatch):
        """Pytest fixture that patches get_config() to return a mock config.

        Usage:
            def test_my_feature(mock_get_config_patch):
                # get_config() is now patched to return mock_pipeline_config()
                from src.config.loader import get_config
                config = get_config()
        """
        from unittest.mock import patch

        mock_config = create_mock_pipeline_config()

        with patch("src.config.loader.get_config", return_value=mock_config):
            yield mock_config


def create_mock_transition_scorer_config() -> Any:
    """Create a mock TransitionScorer configuration object.

    Returns an object with the structure expected by TransitionScorer tests:
    - base_score: float
    - confidence_thresholds: dict with 'high' and 'likely' keys
    - scoring: object with signal configs (agency_continuity, timing_proximity, etc.)

    Returns:
        Mock configuration object with required attributes
    """
    from dataclasses import dataclass, field

    @dataclass
    class ScoringConfig:
        """Mock scoring configuration."""
        agency_continuity: Any = field(default_factory=lambda: MagicMock(
            model_dump=lambda: {
                "enabled": True,
                "weight": 0.25,
                "same_agency_bonus": 0.25,
                "cross_service_bonus": 0.125,
                "different_dept_bonus": 0.05,
            }
        ))
        timing_proximity: Any = field(default_factory=lambda: MagicMock(
            model_dump=lambda: {
                "enabled": True,
                "weight": 0.20,
                "windows": [
                    {"range": [0, 90], "score": 1.0},
                    {"range": [91, 365], "score": 0.75},
                    {"range": [366, 730], "score": 0.5},
                ],
            }
        ))
        competition_type: Any = field(default_factory=lambda: MagicMock(
            model_dump=lambda: {
                "enabled": True,
                "weight": 0.20,
                "sole_source_bonus": 0.20,
                "limited_competition_bonus": 0.10,
                "full_and_open_bonus": 0.0,
            }
        ))
        patent_signal: Any = field(default_factory=lambda: MagicMock(
            model_dump=lambda: {
                "enabled": True,
                "weight": 0.15,
                "has_patent_bonus": 0.05,
                "patent_pre_contract_bonus": 0.03,
                "patent_topic_match_bonus": 0.02,
                "patent_similarity_threshold": 0.7,
            }
        ))
        cet_alignment: Any = field(default_factory=lambda: MagicMock(
            model_dump=lambda: {
                "enabled": True,
                "weight": 0.10,
                "same_cet_area_bonus": 0.05,
            }
        ))
        text_similarity: Any = field(default_factory=lambda: MagicMock(
            model_dump=lambda: {
                "enabled": False,
                "weight": 0.0,
            }
        ))

    @dataclass
    class TransitionScorerConfig:
        """Mock TransitionScorer configuration."""
        base_score: float = 0.15
        confidence_thresholds: dict[str, float] = field(default_factory=lambda: {
            "high": 0.85,
            "likely": 0.65,
        })
        scoring: ScoringConfig = field(default_factory=ScoringConfig)

    return TransitionScorerConfig()

