"""Integration tests for exception handling across the pipeline.

These tests verify that exceptions are properly raised, caught, and provide
useful information in real pipeline scenarios.
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.exceptions import (
    APIError,
    ConfigurationError,
    DependencyError,
    ValidationError,
    is_retryable,
)
from tests.utils.exception_helpers import (
    assert_exception_structure,
    assert_non_retryable_exception,
    assert_retryable_exception,
)


pytestmark = pytest.mark.integration


class TestConfigurationErrorHandling:
    """Integration tests for configuration error handling."""

    def test_missing_config_file_raises_configuration_error(self):
        """Test that missing config file raises ConfigurationError with context."""
        from src.config.loader import load_config_from_files

        with pytest.raises(ConfigurationError) as exc_info:
            load_config_from_files(
                base_path=Path("/nonexistent"),
                config_dir=Path("/nonexistent"),
            )

        exc = exc_info.value
        assert_exception_structure(
            exc,
            expected_message="Base configuration file not found",
            expected_operation="load_config_from_files",
        )
        assert_non_retryable_exception(exc)
        assert "file_path" in exc.details

    def test_invalid_yaml_raises_configuration_error(self):
        """Test that invalid YAML raises ConfigurationError."""
        from src.config.loader import load_config_from_files

        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)
            base_file = config_dir / "base.yaml"
            base_file.write_text("invalid: yaml: content: [unclosed")

            with pytest.raises(ConfigurationError) as exc_info:
                load_config_from_files(base_path=Path.cwd(), config_dir=config_dir)

            exc = exc_info.value
            assert_exception_structure(
                exc,
                expected_message="Failed to parse base config",
                expected_operation="load_config_from_files",
            )
            assert exc.cause is not None  # Should preserve original YAML error


class TestAPIErrorHandling:
    """Integration tests for API error handling."""

    @pytest.mark.asyncio
    async def test_usaspending_api_invalid_method_raises_configuration_error(self):
        """Test that invalid HTTP method raises ConfigurationError."""
        from src.enrichers.usaspending import USAspendingAPIClient

        with patch("src.enrichers.usaspending_api_client.get_config") as mock_config:
            mock_cfg = MagicMock()
            mock_cfg.enrichment_refresh.usaspending.model_dump.return_value = {
                "timeout_seconds": 30,
                "rate_limit_per_minute": 120,
                "state_file": "/tmp/state.json",
            }
            mock_cfg.enrichment.usaspending_api = {"base_url": "https://api.usaspending.gov/api/v2"}
            mock_config.return_value = mock_cfg

            client = USAspendingAPIClient()

            with pytest.raises(ConfigurationError) as exc_info:
                await client._make_request("INVALID", "/test")

            exc = exc_info.value
            assert_exception_structure(
                exc,
                expected_message="Unsupported HTTP method",
                expected_component="enricher.usaspending",
                expected_operation="_make_request",
            )
            assert "method" in exc.details
            assert "supported_methods" in exc.details


class TestValidationErrorHandling:
    """Integration tests for validation error handling."""

    def test_company_enricher_missing_column_raises_validation_error(self):
        """Test that missing DataFrame columns raise ValidationError."""
        from src.enrichers.company_enricher import enrich_companies

        # Create DataFrames without required columns
        awards_df = pd.DataFrame({"wrong_column": ["value"]})
        companies_df = pd.DataFrame({"Company Name": ["Test Co"]})

        with pytest.raises(ValidationError) as exc_info:
            enrich_companies(
                awards_df,
                companies_df,
                award_company_col="Company",  # This column doesn't exist
            )

        exc = exc_info.value
        assert_exception_structure(
            exc,
            expected_message="not in awards_df",
            expected_component="enricher.company",
            expected_operation="enrich_companies",
        )
        assert "award_company_col" in exc.details
        assert "available_columns" in exc.details
        assert_non_retryable_exception(exc)

    def test_economic_model_missing_columns_raises_validation_error(self):
        """Test that economic model validation raises ValidationError."""
        from src.transformers.economic_model_interface import EconomicModelInterface

        # Create DataFrame missing required columns
        df = pd.DataFrame({"wrong": ["column"]})

        # Use abstract base class method directly (it's not abstract)
        interface = type(
            "TestInterface",
            (EconomicModelInterface,),
            {"is_available": lambda self: True, "calculate_impacts": lambda self, df: df},
        )()

        with pytest.raises(ValidationError) as exc_info:
            interface.validate_shocks_input(df)

        exc = exc_info.value
        assert_exception_structure(
            exc,
            expected_message="Missing required columns",
            expected_component="transformer.economic_model",
            expected_operation="validate_shocks_input",
        )
        assert "missing_columns" in exc.details
        assert "required_columns" in exc.details
        assert "provided_columns" in exc.details


class TestDependencyErrorHandling:
    """Integration tests for dependency error handling."""

    def test_neo4j_loader_without_driver_raises_configuration_error(self):
        """Test Neo4j loader without driver/credentials raises ConfigurationError."""
        from src.loaders.neo4j_patent_loader import Neo4jPatentCETLoader

        with pytest.raises(ConfigurationError) as exc_info:
            Neo4jPatentCETLoader(
                driver=None,
                uri=None,  # Missing credentials
                user=None,
                password=None,
            )

        exc = exc_info.value
        assert_exception_structure(
            exc,
            expected_message="Provide either a driver or uri/user/password",
            expected_component="loader.neo4j_patent",
            expected_operation="__init__",
        )
        assert "driver_provided" in exc.details
        assert "uri_provided" in exc.details


class TestExceptionRetryability:
    """Integration tests for exception retryability."""

    def test_api_5xx_errors_are_retryable(self):
        """Test that 5xx API errors are marked as retryable."""
        exc = APIError(
            "Server error",
            api_name="usaspending",
            http_status=503,
        )

        assert_retryable_exception(exc)
        assert is_retryable(exc)

    def test_api_4xx_errors_not_retryable(self):
        """Test that 4xx API errors are not retryable."""
        exc = APIError(
            "Bad request",
            api_name="usaspending",
            http_status=400,
        )

        assert_non_retryable_exception(exc)
        assert not is_retryable(exc)

    def test_configuration_errors_not_retryable(self):
        """Test that configuration errors are not retryable."""
        exc = ConfigurationError("Missing config")

        assert_non_retryable_exception(exc)
        assert not is_retryable(exc)

    def test_dependency_errors_not_retryable(self):
        """Test that dependency errors are not retryable."""
        exc = DependencyError("Package not installed", dependency_name="neo4j")

        assert_non_retryable_exception(exc)
        assert not is_retryable(exc)


class TestExceptionContextPreservation:
    """Tests that exception context is preserved through the stack."""

    def test_wrapped_exception_preserves_cause(self):
        """Test that wrap_exception preserves the original exception."""
        from src.exceptions import wrap_exception

        original = ValueError("Original error message")

        wrapped = wrap_exception(
            original,
            ValidationError,
            message="Wrapped message",
            component="test",
        )

        assert wrapped.cause is original
        assert "Original error message" in str(wrapped.cause)
        assert wrapped.message == "Wrapped message"

    def test_exception_serialization_includes_cause(self):
        """Test that serialized exceptions include cause information."""
        from src.exceptions import wrap_exception

        original = KeyError("missing_key")
        wrapped = wrap_exception(
            original,
            ValidationError,
            component="test",
        )

        data = wrapped.to_dict()
        assert data["cause"] is not None
        assert "missing_key" in data["cause"]


class TestExceptionDetailsUsability:
    """Tests that exception details provide actionable information."""

    def test_validation_error_shows_available_columns(self):
        """Test ValidationError includes list of available columns for debugging."""
        from src.enrichers.company_enricher import enrich_companies

        awards_df = pd.DataFrame({"col1": [1], "col2": [2]})
        companies_df = pd.DataFrame({"Company Name": ["Test"]})

        with pytest.raises(ValidationError) as exc_info:
            enrich_companies(
                awards_df,
                companies_df,
                award_company_col="missing_col",
            )

        exc = exc_info.value
        assert "available_columns" in exc.details
        available = exc.details["available_columns"]
        assert "col1" in available
        assert "col2" in available

    def test_dependency_error_includes_install_command(self):
        """Test DependencyError includes installation instructions."""
        exc = DependencyError(
            "Package not found",
            dependency_name="neo4j",
            details={"install_command": "pip install neo4j"},
        )

        assert "install_command" in exc.details
        assert "pip install neo4j" in exc.details["install_command"]

    def test_api_error_includes_endpoint_and_status(self):
        """Test APIError includes useful debugging information."""
        exc = APIError(
            "Request failed",
            api_name="usaspending",
            endpoint="/v2/awards/123",
            http_status=404,
            operation="fetch_award",
        )

        assert exc.details["endpoint"] == "/v2/awards/123"
        assert exc.details["http_status"] == 404
        assert exc.operation == "fetch_award"
        assert exc.component == "api.usaspending"
