"""Integration tests for configuration loading with different environments.

These tests verify that configuration properly loads and merges base, environment,
and environment variable overrides.
"""

import os
from pathlib import Path

import pytest

from src.config.loader import get_config, reload_config
from src.config.schemas import PipelineConfig


@pytest.fixture(autouse=True)
def clear_config_cache():
    """Clear configuration cache before each test."""
    reload_config()
    yield
    reload_config()


@pytest.fixture
def config_dir():
    """Get the config directory path."""
    return Path(__file__).parent.parent.parent / "config"


class TestConfigurationEnvironments:
    """Test configuration loading across different environments."""

    def test_load_base_config(self, config_dir):
        """Test loading base configuration without environment."""
        # Clear any environment override
        if "ENVIRONMENT" in os.environ:
            del os.environ["ENVIRONMENT"]

        reload_config()
        config = get_config(environment=None, config_dir=config_dir)

        assert isinstance(config, PipelineConfig)
        assert config.pipeline["name"] == "sbir-etl"
        assert "environment" in config.pipeline

    def test_load_dev_environment(self, config_dir):
        """Test loading development environment configuration."""
        reload_config()
        config = get_config(environment="dev", config_dir=config_dir)

        assert isinstance(config, PipelineConfig)
        # Dev environment should have specific settings
        assert config.neo4j.uri in ("bolt://localhost:7687", "bolt://neo4j:7687")
        assert config.neo4j.username == "neo4j"

    def test_load_prod_environment(self, config_dir):
        """Test loading production environment configuration."""
        reload_config()
        config = get_config(environment="prod", config_dir=config_dir)

        assert isinstance(config, PipelineConfig)
        # Prod environment should have specific settings
        assert "prod" in config.neo4j.uri or "production" in config.neo4j.uri.lower()

    def test_environment_variable_override(self, config_dir):
        """Test environment variable overrides configuration."""
        # Set environment variable override
        os.environ["SBIR_ETL__NEO4J__URI"] = "bolt://custom-host:7687"
        os.environ["SBIR_ETL__NEO4J__USERNAME"] = "custom_user"

        try:
            reload_config()
            config = get_config(
                environment="dev", config_dir=config_dir, apply_env_overrides_flag=True
            )

            assert config.neo4j.uri == "bolt://custom-host:7687"
            assert config.neo4j.username == "custom_user"
        finally:
            # Clean up
            del os.environ["SBIR_ETL__NEO4J__URI"]
            del os.environ["SBIR_ETL__NEO4J__USERNAME"]

    def test_nested_environment_variable_override(self, config_dir):
        """Test nested environment variable overrides."""
        os.environ["SBIR_ETL__DATA_QUALITY__COMPLETENESS__AWARD_ID"] = "0.99"

        try:
            reload_config()
            config = get_config(
                environment="dev", config_dir=config_dir, apply_env_overrides_flag=True
            )

            # Check that nested value was overridden
            assert config.data_quality.completeness.get("award_id") == 0.99
        finally:
            del os.environ["SBIR_ETL__DATA_QUALITY__COMPLETENESS__AWARD_ID"]

    def test_boolean_environment_variable(self, config_dir):
        """Test boolean conversion in environment variables."""
        os.environ["SBIR_ETL__LOGGING__CONSOLE_ENABLED"] = "false"

        try:
            reload_config()
            config = get_config(
                environment="dev", config_dir=config_dir, apply_env_overrides_flag=True
            )

            assert config.logging.console_enabled is False
        finally:
            del os.environ["SBIR_ETL__LOGGING__CONSOLE_ENABLED"]

    def test_integer_environment_variable(self, config_dir):
        """Test integer conversion in environment variables."""
        os.environ["SBIR_ETL__NEO4J__BATCH_SIZE"] = "500"

        try:
            reload_config()
            config = get_config(
                environment="dev", config_dir=config_dir, apply_env_overrides_flag=True
            )

            assert config.neo4j.batch_size == 500
        finally:
            del os.environ["SBIR_ETL__NEO4J__BATCH_SIZE"]

    def test_config_caching(self, config_dir):
        """Test that configuration is cached properly."""
        reload_config()

        # First call
        config1 = get_config(environment="dev", config_dir=config_dir)

        # Second call should return cached version
        config2 = get_config(environment="dev", config_dir=config_dir)

        # Should be the same object (cached)
        assert config1 is config2

    def test_reload_config_clears_cache(self, config_dir):
        """Test that reload_config clears the cache."""
        reload_config()
        config1 = get_config(environment="dev", config_dir=config_dir)

        # Reload should clear cache
        reload_config()
        config2 = get_config(environment="dev", config_dir=config_dir)

        # Should be different objects (cache cleared)
        assert config1 is not config2

    def test_all_required_sections_present(self, config_dir):
        """Test that all required configuration sections are present."""
        reload_config()
        config = get_config(environment="dev", config_dir=config_dir)

        # Verify all main sections exist
        assert config.pipeline is not None
        assert config.neo4j is not None
        assert config.data_quality is not None
        assert config.enrichment is not None
        assert config.extraction is not None
        assert config.transformation is not None
        assert config.logging is not None
        assert config.monitoring is not None

    def test_data_quality_thresholds(self, config_dir):
        """Test data quality threshold configurations."""
        reload_config()
        config = get_config(environment="dev", config_dir=config_dir)

        # Verify data quality thresholds are properly typed
        assert isinstance(config.data_quality.completeness, dict)
        assert isinstance(config.data_quality.uniqueness, dict)
        assert isinstance(config.data_quality.validity, dict)

        # Verify some specific thresholds
        assert "award_id" in config.data_quality.completeness
        assert config.data_quality.completeness["award_id"] <= 1.0

    def test_enrichment_configuration(self, config_dir):
        """Test enrichment service configurations."""
        reload_config()
        config = get_config(environment="dev", config_dir=config_dir)

        # Verify enrichment configs
        assert config.enrichment.sam_gov is not None
        assert "base_url" in config.enrichment.sam_gov
        assert config.enrichment.usaspending_api is not None
        assert "base_url" in config.enrichment.usaspending_api

    def test_neo4j_configuration(self, config_dir):
        """Test Neo4j connection configuration."""
        reload_config()
        config = get_config(environment="dev", config_dir=config_dir)

        # Verify Neo4j config
        assert config.neo4j.uri.startswith("bolt://")
        assert config.neo4j.username is not None
        assert config.neo4j.password is not None
        assert config.neo4j.database is not None
        assert isinstance(config.neo4j.batch_size, int)
        assert config.neo4j.batch_size > 0

    def test_logging_configuration(self, config_dir):
        """Test logging configuration."""
        reload_config()
        config = get_config(environment="dev", config_dir=config_dir)

        # Verify logging config
        assert isinstance(config.logging.console_enabled, bool)
        assert isinstance(config.logging.file_enabled, bool)
        assert config.logging.level in ["DEBUG", "INFO", "WARNING", "ERROR"]
        assert config.logging.format in ["json", "text"]


class TestConfigurationValidation:
    """Test configuration validation and error handling."""

    def test_invalid_environment_uses_base(self, config_dir):
        """Test that invalid environment falls back to base config."""
        reload_config()
        # Should not raise error, just use base config
        config = get_config(environment="nonexistent", config_dir=config_dir)
        assert isinstance(config, PipelineConfig)

    def test_missing_config_dir_raises_error(self):
        """Test that missing config directory raises error."""
        reload_config()

        with pytest.raises(Exception):  # ConfigurationError
            get_config(config_dir=Path("/nonexistent/path"))

    def test_config_validation_strict(self, config_dir):
        """Test that configuration validation is strict."""
        reload_config()
        config = get_config(environment="dev", config_dir=config_dir)

        # Config should be validated by Pydantic
        assert isinstance(config, PipelineConfig)

        # Try to access non-existent attribute should raise
        with pytest.raises(AttributeError):
            _ = config.nonexistent_field
