"""
Tests for src/enrichers/geographic_resolver.py

Tests the GeographicResolver for normalizing company locations to state-level
codes using multiple resolution strategies.
"""

from datetime import datetime
from unittest.mock import patch

import pandas as pd
import pytest

from src.enrichers.geographic_resolver import (
    GeographicResolutionResult,
    GeographicResolver,
    resolve_award_geography,
)
from tests.assertions import assert_dataframe_has_columns


pytestmark = pytest.mark.fast

from tests.utils.config_mocks import create_mock_pipeline_config


@pytest.fixture
def mock_config():
    """Mock configuration for testing using consolidated utility."""
    from src.config.schemas.fiscal import FiscalAnalysisConfig

    config = create_mock_pipeline_config()
    # Ensure fiscal_analysis exists and is properly configured
    if not hasattr(config, "fiscal_analysis") or config.fiscal_analysis is None:
        config.fiscal_analysis = FiscalAnalysisConfig()

    # Set quality_thresholds (it's a dict)
    if not hasattr(config.fiscal_analysis, "quality_thresholds"):
        config.fiscal_analysis.quality_thresholds = {}

    # Ensure it's a dict and set the value
    if not isinstance(config.fiscal_analysis.quality_thresholds, dict):
        config.fiscal_analysis.quality_thresholds = {}

    config.fiscal_analysis.quality_thresholds["geographic_resolution_rate"] = 0.90
    return config


@pytest.fixture
def resolver(mock_config):
    """Default GeographicResolver instance."""
    with patch("src.enrichers.geographic_resolver.get_config", return_value=mock_config):
        return GeographicResolver()


class TestGeographicResolutionResult:
    """Tests for GeographicResolutionResult dataclass."""

    def test_creation(self):
        """Test creating a GeographicResolutionResult."""
        result = GeographicResolutionResult(
            state_code="CA",
            state_name="California",
            confidence=0.95,
            source="state_field",
            method="direct_code",
            timestamp=datetime.now(),
            metadata={"column": "State"},
        )

        assert result.state_code == "CA"
        assert result.state_name == "California"
        assert result.confidence == 0.95
        assert result.source == "state_field"
        assert result.method == "direct_code"


class TestGeographicResolverInitialization:
    """Tests for GeographicResolver initialization."""

    def test_initialization_with_default_config(self, mock_config):
        """Test initialization loads state mappings."""
        with patch("src.enrichers.geographic_resolver.get_config", return_value=mock_config):
            resolver = GeographicResolver()

            assert len(resolver.state_mappings) > 50  # 50 states + territories
            assert "CA" in resolver.state_mappings
            assert resolver.state_mappings["CA"] == "California"
            assert "NY" in resolver.state_mappings
            assert resolver.state_mappings["NY"] == "New York"

    def test_initialization_creates_reverse_mapping(self, resolver):
        """Test initialization creates name-to-code mapping."""
        assert "CALIFORNIA" in resolver.name_to_code
        assert resolver.name_to_code["CALIFORNIA"] == "CA"
        assert "NEW YORK" in resolver.name_to_code
        assert resolver.name_to_code["NEW YORK"] == "NY"

    def test_initialization_includes_variations(self, resolver):
        """Test initialization includes state variations."""
        assert "CALIF" in resolver.state_variations
        assert resolver.state_variations["CALIF"] == "CA"
        assert "MASS" in resolver.state_variations
        assert resolver.state_variations["MASS"] == "MA"

    def test_initialization_creates_valid_state_codes_set(self, resolver):
        """Test initialization creates valid state codes set."""
        assert "CA" in resolver.valid_state_codes
        assert "NY" in resolver.valid_state_codes
        assert "TX" in resolver.valid_state_codes
        assert "INVALID" not in resolver.valid_state_codes


class TestNormalizeStateInput:
    """Tests for normalize_state_input method."""

    def test_normalize_uppercase(self, resolver):
        """Test normalization converts to uppercase."""
        result = resolver.normalize_state_input("california")
        assert result == "CALIFORNIA"

    def test_normalize_strips_whitespace(self, resolver):
        """Test normalization strips leading/trailing whitespace."""
        result = resolver.normalize_state_input("  CA  ")
        assert result == "CA"

    def test_normalize_removes_punctuation(self, resolver):
        """Test normalization removes punctuation."""
        result = resolver.normalize_state_input("N.Y.")
        assert result == "NY"

    def test_normalize_collapses_whitespace(self, resolver):
        """Test normalization collapses internal whitespace."""
        result = resolver.normalize_state_input("NEW   YORK")
        assert result == "NEW YORK"

    def test_normalize_empty_string(self, resolver):
        """Test normalization handles empty string."""
        result = resolver.normalize_state_input("")
        assert result == ""

    def test_normalize_none_value(self, resolver):
        """Test normalization handles None."""
        result = resolver.normalize_state_input(None)
        assert result == ""


class TestExtractStateFromAddress:
    """Tests for extract_state_from_address method."""

    @pytest.mark.parametrize(
        "address,expected",
        [
            ("123 Main St, San Francisco, CA 94102", "CA"),  # ZIP pattern
            ("456 Oak Ave, New York, NY 10001-1234", "NY"),  # ZIP+4
            ("123 Main St, Boston, MA", "MA"),  # code without ZIP
            ("123 Main St, California", "CA"),  # full state name
            ("123 Main St, North Carolina", "NC"),  # multi-word name
            ("123 Main St, Calif", "CA"),  # variation
        ],
        ids=["zip_pattern", "zip_plus_4", "code_no_zip", "full_name", "multi_word", "variation"],
    )
    def test_extract_state_from_address_valid(self, resolver, address, expected):
        """Test extracting state from various valid address formats."""
        result = resolver.extract_state_from_address(address)
        assert result == expected

    @pytest.mark.parametrize(
        "address",
        [
            "",  # empty
            None,  # None
            "123 Main St, Some City",  # no state
        ],
        ids=["empty", "none", "no_match"],
    )
    def test_extract_state_from_address_invalid(self, resolver, address):
        """Test extraction returns None for invalid/unresolvable addresses."""
        result = resolver.extract_state_from_address(address)
        assert result is None


class TestResolveFromStateField:
    """Tests for resolve_from_state_field method."""

    def test_resolve_direct_state_code(self, resolver):
        """Test resolution from direct state code with full validation."""
        row = pd.Series({"State": "CA", "Company": "Acme Corp"})
        result = resolver.resolve_from_state_field(row)

        assert result is not None
        assert result.state_code == "CA"
        assert result.state_name == "California"
        assert result.confidence == 0.95
        assert result.source == "state_field"
        assert result.method == "direct_code"

    def test_resolve_state_name(self, resolver):
        """Test resolution from state name with full validation."""
        row = pd.Series({"State": "California"})
        result = resolver.resolve_from_state_field(row)

        assert result is not None
        assert result.state_code == "CA"
        assert result.state_name == "California"
        assert result.confidence == 0.90
        assert result.method == "name_mapping"

    @pytest.mark.parametrize(
        "row_data,expected_code",
        [
            ({"State": "Calif"}, "CA"),  # variation
            ({"state": "ca"}, "CA"),  # lowercase
            ({"company_state": "NY"}, "NY"),  # alternative column
        ],
        ids=["variation", "lowercase", "alt_column"],
    )
    def test_resolve_state_field_variants(self, resolver, row_data, expected_code):
        """Test resolution from various state field formats."""
        row = pd.Series(row_data)
        result = resolver.resolve_from_state_field(row)

        assert result is not None
        assert result.state_code == expected_code

    @pytest.mark.parametrize(
        "row_data",
        [
            {"Company": "Acme"},  # no state column
            {"State": ""},  # empty value
        ],
        ids=["no_column", "empty_value"],
    )
    def test_resolve_state_field_returns_none(self, resolver, row_data):
        """Test resolution returns None for invalid inputs."""
        row = pd.Series(row_data)
        result = resolver.resolve_from_state_field(row)

        assert result is None


class TestResolveFromAddressField:
    """Tests for resolve_from_address_field method."""

    def test_resolve_from_address(self, resolver):
        """Test resolution from full address."""
        row = pd.Series({"Address": "123 Main St, San Francisco, CA 94102"})
        result = resolver.resolve_from_address_field(row)

        assert result is not None
        assert result.state_code == "CA"
        assert result.state_name == "California"
        assert result.confidence == 0.85
        assert result.source == "address_field"
        assert result.method == "address_parsing"

    def test_resolve_from_company_address(self, resolver):
        """Test resolution from company_address column."""
        row = pd.Series({"Company_Address": "456 Oak Ave, New York, NY 10001"})
        result = resolver.resolve_from_address_field(row)

        assert result is not None
        assert result.state_code == "NY"

    def test_resolve_no_address_column(self, resolver):
        """Test resolution returns None when no address column."""
        row = pd.Series({"Company": "Acme"})
        result = resolver.resolve_from_address_field(row)

        assert result is None

    def test_resolve_address_no_state(self, resolver):
        """Test resolution returns None when address has no state."""
        row = pd.Series({"Address": "123 Main St"})
        result = resolver.resolve_from_address_field(row)

        assert result is None


class TestResolveFromCityState:
    """Tests for resolve_from_city_state method."""

    def test_resolve_from_city_and_state(self, resolver):
        """Test resolution from separate city and state fields."""
        row = pd.Series({"City": "San Francisco", "State": "CA"})
        result = resolver.resolve_from_city_state(row)

        assert result is not None
        assert result.state_code == "CA"
        assert result.state_name == "California"
        assert result.confidence == 0.92
        assert result.source == "city_state_fields"

    def test_resolve_city_state_with_name(self, resolver):
        """Test resolution with state name instead of code."""
        row = pd.Series({"City": "Boston", "State": "Massachusetts"})
        result = resolver.resolve_from_city_state(row)

        assert result is not None
        assert result.state_code == "MA"
        assert result.confidence == 0.88

    def test_resolve_alternative_city_state_columns(self, resolver):
        """Test resolution with alternative column names."""
        row = pd.Series({"company_city": "Austin", "company_state": "TX"})
        result = resolver.resolve_from_city_state(row)

        assert result is not None
        assert result.state_code == "TX"

    def test_resolve_missing_city(self, resolver):
        """Test resolution returns None when city missing."""
        row = pd.Series({"State": "CA"})
        result = resolver.resolve_from_city_state(row)

        assert result is None

    def test_resolve_missing_state(self, resolver):
        """Test resolution returns None when state missing."""
        row = pd.Series({"City": "San Francisco"})
        result = resolver.resolve_from_city_state(row)

        assert result is None


class TestResolveFromEnrichedData:
    """Tests for resolve_from_enriched_data method."""

    def test_resolve_from_enriched_company_state(self, resolver):
        """Test resolution from enriched company data."""
        row = pd.Series({"company_state": "WA"})
        result = resolver.resolve_from_enriched_data(row)

        assert result is not None
        assert result.state_code == "WA"
        assert result.state_name == "Washington"
        assert result.confidence == 0.80
        assert result.source == "enriched_data"

    def test_resolve_from_recipient_state(self, resolver):
        """Test resolution from recipient_state field."""
        row = pd.Series({"recipient_state": "OR"})
        result = resolver.resolve_from_enriched_data(row)

        assert result is not None
        assert result.state_code == "OR"

    def test_resolve_enriched_with_name(self, resolver):
        """Test resolution from enriched data with state name."""
        row = pd.Series({"company_state": "Oregon"})
        result = resolver.resolve_from_enriched_data(row)

        assert result is not None
        assert result.state_code == "OR"
        assert result.confidence == 0.75


class TestResolveSingleAward:
    """Tests for resolve_single_award method."""

    def test_resolve_hierarchical_priority(self, resolver):
        """Test resolution uses hierarchical priority."""
        # State field should take priority over address
        row = pd.Series(
            {
                "State": "CA",
                "Address": "123 Main St, Austin, TX 78701",  # Different state
            }
        )

        result = resolver.resolve_single_award(row)

        assert result is not None
        assert result.state_code == "CA"  # Should use state field, not address

    def test_resolve_fallback_to_address(self, resolver):
        """Test resolution falls back to address when state field missing."""
        row = pd.Series({"Address": "123 Main St, Seattle, WA 98101"})

        result = resolver.resolve_single_award(row)

        assert result is not None
        assert result.state_code == "WA"
        assert result.source == "address_field"

    def test_resolve_no_valid_source(self, resolver):
        """Test resolution returns None when no valid source."""
        row = pd.Series({"Company": "Acme Corp"})

        result = resolver.resolve_single_award(row)

        assert result is None

    def test_resolve_handles_exceptions(self, resolver):
        """Test resolution continues after method exception."""
        # Create a row that will cause an exception in one method
        row = pd.Series({"State": None})  # Will be handled gracefully

        # Should not raise, should return None or continue to other methods
        resolver.resolve_single_award(row)
        # Result could be None or from another method


class TestResolveAwardsDataFrame:
    """Tests for resolve_awards_dataframe method."""

    def test_resolve_dataframe_basic(self, resolver):
        """Test resolving entire DataFrame."""
        df = pd.DataFrame(
            {
                "award_id": ["AWD001", "AWD002", "AWD003"],
                "State": ["CA", "NY", "TX"],
                "Company": ["Acme", "Beta", "Gamma"],
            }
        )

        result_df = resolver.resolve_awards_dataframe(df)

        assert_dataframe_has_columns(
            result_df, ["fiscal_state_code", "fiscal_state_name", "fiscal_geo_confidence"]
        )
        assert result_df["fiscal_state_code"].iloc[0] == "CA"
        assert result_df["fiscal_state_code"].iloc[1] == "NY"
        assert result_df["fiscal_state_code"].iloc[2] == "TX"

    def test_resolve_dataframe_mixed_sources(self, resolver):
        """Test DataFrame resolution with mixed sources."""
        df = pd.DataFrame(
            {
                "award_id": ["AWD001", "AWD002"],
                "State": ["CA", None],
                "Address": ["", "123 Main St, Boston, MA 02101"],
            }
        )

        result_df = resolver.resolve_awards_dataframe(df)

        # First row from state field
        assert result_df["fiscal_geo_source"].iloc[0] == "state_field"
        # Second row from address
        assert result_df["fiscal_geo_source"].iloc[1] == "address_field"

    def test_resolve_dataframe_tracks_metadata(self, resolver):
        """Test DataFrame resolution tracks metadata."""
        df = pd.DataFrame({"award_id": ["AWD001"], "State": ["CA"]})

        result_df = resolver.resolve_awards_dataframe(df)

        assert result_df["fiscal_geo_metadata"].iloc[0] is not None
        assert "column" in str(result_df["fiscal_geo_metadata"].iloc[0])

    def test_resolve_dataframe_empty(self, resolver):
        """Test resolving empty DataFrame."""
        df = pd.DataFrame(columns=["award_id", "State"])

        result_df = resolver.resolve_awards_dataframe(df)

        assert len(result_df) == 0
        assert "fiscal_state_code" in result_df.columns

    def test_resolve_dataframe_handles_errors(self, resolver):
        """Test DataFrame resolution continues after row errors."""
        df = pd.DataFrame(
            {
                "award_id": ["AWD001", "AWD002"],
                "State": ["CA", "NY"],
            }
        )

        # Should complete without raising
        result_df = resolver.resolve_awards_dataframe(df)

        assert len(result_df) == 2


class TestValidateResolutionQuality:
    """Tests for validate_resolution_quality method."""

    def test_validate_quality_high_resolution(self, resolver):
        """Test quality validation with high resolution rate."""
        df = pd.DataFrame(
            {
                "fiscal_state_code": ["CA", "NY", "TX", "FL", "WA"],
                "fiscal_geo_confidence": [0.95, 0.92, 0.90, 0.88, 0.85],
                "fiscal_geo_source": ["state_field"] * 5,
            }
        )

        quality = resolver.validate_resolution_quality(df)

        assert quality["total_awards"] == 5
        assert quality["resolved_count"] == 5
        assert quality["resolution_rate"] == 1.0
        assert quality["resolution_meets_threshold"]

    def test_validate_quality_low_resolution(self, resolver):
        """Test quality validation with low resolution rate."""
        df = pd.DataFrame(
            {
                "fiscal_state_code": ["CA", None, None, None, None],
                "fiscal_geo_confidence": [0.95, None, None, None, None],
                "fiscal_geo_source": ["state_field", None, None, None, None],
            }
        )

        quality = resolver.validate_resolution_quality(df)

        assert quality["total_awards"] == 5
        assert quality["resolved_count"] == 1
        assert quality["resolution_rate"] == 0.2
        assert not quality["resolution_meets_threshold"]

    def test_validate_quality_confidence_distribution(self, resolver):
        """Test quality validation calculates confidence distribution."""
        df = pd.DataFrame(
            {
                "fiscal_state_code": ["CA", "NY", "TX", "FL"],
                "fiscal_geo_confidence": [0.95, 0.85, 0.65, 0.50],
                "fiscal_geo_source": ["state_field"] * 4,
            }
        )

        quality = resolver.validate_resolution_quality(df)

        assert quality["confidence_distribution"]["high_confidence"] == 2  # 0.95, 0.85 (>=0.80)
        assert quality["confidence_distribution"]["medium_confidence"] == 1  # 0.65 (0.60-0.80)
        assert quality["confidence_distribution"]["low_confidence"] == 1  # 0.50 (<0.60)

    def test_validate_quality_source_distribution(self, resolver):
        """Test quality validation tracks source distribution."""
        df = pd.DataFrame(
            {
                "fiscal_state_code": ["CA", "NY", "TX"],
                "fiscal_geo_confidence": [0.95, 0.85, 0.80],
                "fiscal_geo_source": ["state_field", "address_field", "state_field"],
            }
        )

        quality = resolver.validate_resolution_quality(df)

        assert quality["source_distribution"]["state_field"] == 2
        assert quality["source_distribution"]["address_field"] == 1

    def test_validate_quality_state_distribution(self, resolver):
        """Test quality validation tracks state distribution."""
        df = pd.DataFrame(
            {
                "fiscal_state_code": ["CA", "CA", "NY", "TX"],
                "fiscal_geo_confidence": [0.95] * 4,
                "fiscal_geo_source": ["state_field"] * 4,
            }
        )

        quality = resolver.validate_resolution_quality(df)

        assert quality["state_distribution"]["CA"] == 2
        assert quality["state_distribution"]["NY"] == 1
        assert quality["state_distribution"]["TX"] == 1
        assert quality["unique_states_resolved"] == 3

    def test_validate_quality_empty_dataframe(self, resolver):
        """Test quality validation with empty DataFrame."""
        df = pd.DataFrame(
            columns=["fiscal_state_code", "fiscal_geo_confidence", "fiscal_geo_source"]
        )

        quality = resolver.validate_resolution_quality(df)

        assert quality["total_awards"] == 0
        assert quality["resolution_rate"] == 0.0


class TestResolveAwardGeography:
    """Tests for resolve_award_geography function."""

    def test_resolve_award_geography_success(self, mock_config):
        """Test main function resolves and validates."""
        df = pd.DataFrame(
            {
                "award_id": ["AWD001", "AWD002"],
                "State": ["CA", "NY"],
            }
        )

        with patch("src.enrichers.geographic_resolver.get_config", return_value=mock_config):
            enriched_df, quality_metrics = resolve_award_geography(df)

        assert "fiscal_state_code" in enriched_df.columns
        assert enriched_df["fiscal_state_code"].iloc[0] == "CA"
        assert enriched_df["fiscal_state_code"].iloc[1] == "NY"

        assert "resolution_rate" in quality_metrics
        assert quality_metrics["resolution_rate"] == 1.0

    def test_resolve_award_geography_with_custom_config(self):
        """Test main function with custom config."""
        from src.config.schemas.fiscal import FiscalAnalysisConfig

        df = pd.DataFrame({"award_id": ["AWD001"], "State": ["CA"]})

        # Create a proper FiscalAnalysisConfig with custom threshold
        custom_fiscal_config = FiscalAnalysisConfig()
        custom_fiscal_config.quality_thresholds["geographic_resolution_rate"] = 0.95

        enriched_df, quality_metrics = resolve_award_geography(df, config=custom_fiscal_config)

        assert quality_metrics["resolution_threshold"] == 0.95


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_state_mappings_include_territories(self, resolver):
        """Test state mappings include US territories."""
        assert "PR" in resolver.state_mappings
        assert resolver.state_mappings["PR"] == "Puerto Rico"
        assert "VI" in resolver.state_mappings
        assert "GU" in resolver.state_mappings

    def test_resolve_with_whitespace_padding(self, resolver):
        """Test resolution handles whitespace in values."""
        row = pd.Series({"State": "  CA  "})
        result = resolver.resolve_single_award(row)

        assert result is not None
        assert result.state_code == "CA"

    def test_resolve_with_mixed_case(self, resolver):
        """Test resolution handles mixed case input."""
        row = pd.Series({"State": "cAliFoRnIa"})
        result = resolver.resolve_single_award(row)

        assert result is not None
        assert result.state_code == "CA"

    def test_resolve_with_dots_in_state(self, resolver):
        """Test resolution handles dots in state abbreviations."""
        row = pd.Series({"State": "N.Y."})
        result = resolver.resolve_single_award(row)

        assert result is not None
        assert result.state_code == "NY"

    def test_resolve_invalid_state_code(self, resolver):
        """Test resolution returns None for invalid state code."""
        row = pd.Series({"State": "ZZ"})  # Invalid code
        result = resolver.resolve_single_award(row)

        assert result is None

    def test_extract_state_ignores_non_state_two_letter_words(self, resolver):
        """Test extraction doesn't match non-state two-letter words."""
        address = "123 To Be Or Not To Be Street"
        # "TO" and "BE" and "OR" are two-letter words, but OR is a valid state
        result = resolver.extract_state_from_address(address)

        # Should only match OR if it's actually the state
        if result:
            assert result == "OR"

    def test_resolve_dataframe_preserves_original_columns(self, resolver):
        """Test DataFrame resolution preserves original columns."""
        df = pd.DataFrame(
            {
                "award_id": ["AWD001"],
                "Company": ["Acme"],
                "State": ["CA"],
            }
        )

        result_df = resolver.resolve_awards_dataframe(df)

        # Original columns should still exist
        assert "award_id" in result_df.columns
        assert "Company" in result_df.columns
        assert "State" in result_df.columns

    def test_quality_validation_zero_denominator(self, resolver):
        """Test quality validation handles zero awards gracefully."""
        df = pd.DataFrame(
            columns=[
                "fiscal_state_code",
                "fiscal_geo_confidence",
                "fiscal_geo_source",
            ]
        )

        quality = resolver.validate_resolution_quality(df)

        assert quality["resolution_rate"] == 0.0
        assert quality["average_confidence"] == 0.0
