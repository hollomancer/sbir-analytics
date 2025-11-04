"""Unit tests for SBIR configuration schemas."""

import pytest

pytestmark = pytest.mark.fast

from src.config.schemas import (
    DataQualityConfig,
    ExtractionConfig,
    SbirDuckDBConfig,
    SbirValidationConfig,
)


class TestSbirValidationConfig:
    """Test SBIR validation configuration."""

    def test_default_values(self):
        """Test default configuration values."""
        config = SbirValidationConfig()
        assert config.pass_rate_threshold == 0.95
        assert config.completeness_threshold == 0.90
        assert config.uniqueness_threshold == 0.99

    def test_custom_values(self):
        """Test custom configuration values."""
        config = SbirValidationConfig(
            pass_rate_threshold=0.90,
            completeness_threshold=0.85,
            uniqueness_threshold=0.95,
        )
        assert config.pass_rate_threshold == 0.90
        assert config.completeness_threshold == 0.85
        assert config.uniqueness_threshold == 0.95

    def test_invalid_pass_rate_threshold(self):
        """Test invalid pass rate threshold."""
        with pytest.raises(ValueError, match="must be between 0.0 and 1.0"):
            SbirValidationConfig(pass_rate_threshold=1.5)

        with pytest.raises(ValueError, match="must be between 0.0 and 1.0"):
            SbirValidationConfig(pass_rate_threshold=-0.1)

    def test_invalid_completeness_threshold(self):
        """Test invalid completeness threshold."""
        with pytest.raises(ValueError, match="must be between 0.0 and 1.0"):
            SbirValidationConfig(completeness_threshold=1.2)

    def test_invalid_uniqueness_threshold(self):
        """Test invalid uniqueness threshold."""
        with pytest.raises(ValueError, match="must be between 0.0 and 1.0"):
            SbirValidationConfig(uniqueness_threshold=-0.5)


class TestSbirDuckDBConfig:
    """Test SBIR DuckDB configuration."""

    def test_default_values(self):
        """Test default configuration values."""
        config = SbirDuckDBConfig()
        assert config.csv_path == "data/raw/sbir/awards_data.csv"
        assert config.database_path == ":memory:"
        assert config.table_name == "sbir_awards"
        assert config.batch_size == 10000
        assert config.encoding == "utf-8"

    def test_custom_values(self):
        """Test custom configuration values."""
        config = SbirDuckDBConfig(
            csv_path="/custom/path/awards.csv",
            database_path="/tmp/sbir.duckdb",
            table_name="custom_awards",
            batch_size=5000,
            encoding="latin-1",
        )
        assert config.csv_path == "/custom/path/awards.csv"
        assert config.database_path == "/tmp/sbir.duckdb"
        assert config.table_name == "custom_awards"
        assert config.batch_size == 5000
        assert config.encoding == "latin-1"


class TestDataQualityConfigSbirIntegration:
    """Test SBIR validation config integration in DataQualityConfig."""

    def test_default_sbir_awards_config(self):
        """Test default SBIR awards validation config."""
        config = DataQualityConfig()
        assert isinstance(config.sbir_awards, SbirValidationConfig)
        assert config.sbir_awards.pass_rate_threshold == 0.95
        assert config.sbir_awards.completeness_threshold == 0.90
        assert config.sbir_awards.uniqueness_threshold == 0.99

    def test_custom_sbir_awards_config(self):
        """Test custom SBIR awards validation config."""
        sbir_config = SbirValidationConfig(
            pass_rate_threshold=0.85,
            completeness_threshold=0.80,
            uniqueness_threshold=0.90,
        )
        config = DataQualityConfig(sbir_awards=sbir_config)
        assert config.sbir_awards.pass_rate_threshold == 0.85
        assert config.sbir_awards.completeness_threshold == 0.80
        assert config.sbir_awards.uniqueness_threshold == 0.90


class TestExtractionConfigSbirIntegration:
    """Test SBIR DuckDB config integration in ExtractionConfig."""

    def test_default_sbir_config(self):
        """Test default SBIR extraction config."""
        config = ExtractionConfig()
        assert isinstance(config.sbir, SbirDuckDBConfig)
        assert config.sbir.csv_path == "data/raw/sbir/awards_data.csv"
        assert config.sbir.database_path == ":memory:"
        assert config.sbir.table_name == "sbir_awards"
        assert config.sbir.batch_size == 10000
        assert config.sbir.encoding == "utf-8"

    def test_custom_sbir_config(self):
        """Test custom SBIR extraction config."""
        sbir_config = SbirDuckDBConfig(
            csv_path="/data/sbir.csv",
            database_path="sbir.duckdb",
            table_name="awards",
            batch_size=20000,
            encoding="utf-8",
        )
        config = ExtractionConfig(sbir=sbir_config)
        assert config.sbir.csv_path == "/data/sbir.csv"
        assert config.sbir.database_path == "sbir.duckdb"
        assert config.sbir.table_name == "awards"
        assert config.sbir.batch_size == 20000
        assert config.sbir.encoding == "utf-8"
