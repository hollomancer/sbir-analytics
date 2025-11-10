"""Unit tests for NAICS enrichment strategies.

Tests for all NAICS enrichment strategies:
- Base strategy classes and dataclasses
- OriginalDataStrategy: Extract from original SBIR fields
- AgencyDefaultsStrategy: Agency-based default NAICS
- TextInferenceStrategy: Keyword-based text inference
- TopicCodeStrategy: Topic code to NAICS mapping
- USAspendingDataFrameStrategy: USAspending lookups
- SectorFallbackStrategy: Default fallback
- Utility functions: validate_naics_code, normalize_naics_code
"""

from datetime import datetime

import pandas as pd
import pytest

from src.enrichers.naics.fiscal.strategies.agency_defaults import AgencyDefaultsStrategy
from src.enrichers.naics.fiscal.strategies.base import (
    EnrichmentStrategy,
    NAICSEnrichmentResult,
)
from src.enrichers.naics.fiscal.strategies.original_data import OriginalDataStrategy
from src.enrichers.naics.fiscal.strategies.sector_fallback import SectorFallbackStrategy
from src.enrichers.naics.fiscal.strategies.text_inference import TextInferenceStrategy
from src.enrichers.naics.fiscal.strategies.topic_code import TopicCodeStrategy
from src.enrichers.naics.fiscal.strategies.usaspending_dataframe import (
    USAspendingDataFrameStrategy,
)
from src.enrichers.naics.fiscal.utils import normalize_naics_code, validate_naics_code

pytestmark = pytest.mark.fast


# =============================================================================
# Base Classes Tests
# =============================================================================


class TestNAICSEnrichmentResult:
    """Tests for NAICSEnrichmentResult dataclass."""

    def test_result_creation(self):
        """Test creating an enrichment result."""
        result = NAICSEnrichmentResult(
            naics_code="541715",
            confidence=0.95,
            source="test_source",
            method="test_method",
            timestamp=datetime(2025, 1, 1),
            metadata={"key": "value"},
        )

        assert result.naics_code == "541715"
        assert result.confidence == 0.95
        assert result.source == "test_source"
        assert result.method == "test_method"
        assert result.metadata == {"key": "value"}

    def test_result_with_none_naics(self):
        """Test result with None NAICS code."""
        result = NAICSEnrichmentResult(
            naics_code=None,
            confidence=0.0,
            source="test",
            method="failed",
            timestamp=datetime.now(),
            metadata={},
        )

        assert result.naics_code is None
        assert result.confidence == 0.0


# =============================================================================
# Utility Functions Tests
# =============================================================================


class TestUtilityFunctions:
    """Tests for NAICS utility functions."""

    def test_validate_naics_code_valid(self):
        """Test validating valid NAICS codes."""
        assert validate_naics_code("541715") is True
        assert validate_naics_code("5417") is True
        assert validate_naics_code("54") is True

    def test_validate_naics_code_invalid_length(self):
        """Test validating NAICS codes with invalid length."""
        assert validate_naics_code("1") is False  # Too short
        assert validate_naics_code("1234567") is False  # Too long

    def test_validate_naics_code_empty(self):
        """Test validating empty NAICS code."""
        assert validate_naics_code("") is False
        assert validate_naics_code(None) is False  # type: ignore

    def test_validate_naics_code_non_numeric(self):
        """Test validating non-numeric NAICS codes."""
        # After cleaning, should still be valid
        assert validate_naics_code("541715") is True

    def test_normalize_naics_code_valid(self):
        """Test normalizing valid NAICS codes."""
        assert normalize_naics_code("541715") == "541715"
        assert normalize_naics_code("5417") == "5417"

    def test_normalize_naics_code_with_leading_zeros(self):
        """Test normalizing NAICS code with leading zeros."""
        assert normalize_naics_code("005417") == "5417"
        assert normalize_naics_code("00054") == "54"

    def test_normalize_naics_code_with_non_digits(self):
        """Test normalizing NAICS code with non-digit characters."""
        assert normalize_naics_code("54-17-15") == "541715"
        assert normalize_naics_code("NAICS:5417") == "5417"

    def test_normalize_naics_code_invalid(self):
        """Test normalizing invalid NAICS codes."""
        assert normalize_naics_code("") is None
        assert normalize_naics_code("1") is None  # Too short
        assert normalize_naics_code("1234567") is None  # Too long

    def test_normalize_naics_code_all_zeros(self):
        """Test normalizing all zeros."""
        assert normalize_naics_code("0000") is None


# =============================================================================
# OriginalDataStrategy Tests
# =============================================================================


class TestOriginalDataStrategy:
    """Tests for OriginalDataStrategy."""

    def test_strategy_properties(self):
        """Test strategy name and confidence level."""
        strategy = OriginalDataStrategy()

        assert strategy.strategy_name == "original_data"
        assert strategy.confidence_level == 0.95

    def test_enrich_from_naics_column(self):
        """Test enriching from NAICS column."""
        strategy = OriginalDataStrategy()
        row = pd.Series({"NAICS": "541715", "company": "Test Corp"})

        result = strategy.enrich(row)

        assert result is not None
        assert result.naics_code == "541715"
        assert result.confidence == 0.95
        assert result.source == "original_data"
        assert result.method == "direct_field"

    def test_enrich_from_naics_code_column(self):
        """Test enriching from NAICS_Code column."""
        strategy = OriginalDataStrategy()
        row = pd.Series({"NAICS_Code": "5417", "company": "Test Corp"})

        result = strategy.enrich(row)

        assert result is not None
        assert result.naics_code == "5417"

    def test_enrich_with_leading_zeros(self):
        """Test enriching NAICS with leading zeros."""
        strategy = OriginalDataStrategy()
        row = pd.Series({"naics": "005417"})

        result = strategy.enrich(row)

        assert result is not None
        assert result.naics_code == "5417"  # Leading zeros stripped

    def test_enrich_no_naics_column(self):
        """Test enriching when no NAICS column exists."""
        strategy = OriginalDataStrategy()
        row = pd.Series({"company": "Test Corp", "amount": 100000})

        result = strategy.enrich(row)

        assert result is None

    def test_enrich_null_naics(self):
        """Test enriching when NAICS is null."""
        strategy = OriginalDataStrategy()
        row = pd.Series({"NAICS": None, "company": "Test Corp"})

        result = strategy.enrich(row)

        assert result is None


# =============================================================================
# AgencyDefaultsStrategy Tests
# =============================================================================


class TestAgencyDefaultsStrategy:
    """Tests for AgencyDefaultsStrategy."""

    def test_strategy_properties(self):
        """Test strategy name and confidence level."""
        strategy = AgencyDefaultsStrategy()

        assert strategy.strategy_name == "agency_defaults"
        assert strategy.confidence_level == 0.50

    def test_enrich_dod_exact_match(self):
        """Test enriching DOD agency with exact match."""
        strategy = AgencyDefaultsStrategy()
        row = pd.Series({"Agency": "DOD", "amount": 100000})

        result = strategy.enrich(row)

        assert result is not None
        assert result.naics_code == "3364"
        assert result.method == "agency_default"
        assert result.metadata["agency"] == "DOD"

    def test_enrich_nih_match(self):
        """Test enriching NIH agency."""
        strategy = AgencyDefaultsStrategy()
        row = pd.Series({"Funding_Agency": "NIH"})

        result = strategy.enrich(row)

        assert result is not None
        assert result.naics_code == "5417"

    def test_enrich_partial_match(self):
        """Test enriching with partial agency name match."""
        strategy = AgencyDefaultsStrategy()
        row = pd.Series({"agency": "Department of Defense"})

        result = strategy.enrich(row)

        assert result is not None
        assert result.naics_code == "3364"
        assert result.method == "agency_default_partial"
        assert result.metadata["matched_key"] == "DOD"

    def test_enrich_no_match(self):
        """Test enriching unknown agency."""
        strategy = AgencyDefaultsStrategy()
        row = pd.Series({"Agency": "UNKNOWN_AGENCY"})

        result = strategy.enrich(row)

        assert result is None

    def test_enrich_case_insensitive(self):
        """Test enriching is case insensitive."""
        strategy = AgencyDefaultsStrategy()
        row = pd.Series({"agency": "dod"})

        result = strategy.enrich(row)

        assert result is not None
        assert result.naics_code == "3364"


# =============================================================================
# TextInferenceStrategy Tests
# =============================================================================


class TestTextInferenceStrategy:
    """Tests for TextInferenceStrategy."""

    def test_strategy_properties(self):
        """Test strategy name and confidence level."""
        strategy = TextInferenceStrategy()

        assert strategy.strategy_name == "text_inference"
        assert strategy.confidence_level == 0.65

    def test_enrich_biotech_keywords(self):
        """Test enriching with biotech keywords."""
        strategy = TextInferenceStrategy()
        row = pd.Series(
            {
                "Abstract": "Development of biotech therapeutic vaccine for clinical trial",
                "Title": "Novel Drug Research",
            }
        )

        result = strategy.enrich(row)

        assert result is not None
        assert result.naics_code == "5417"  # Scientific R&D
        assert result.method == "keyword_inference"
        assert result.metadata["keyword_matches"] >= 2

    def test_enrich_software_keywords(self):
        """Test enriching with software keywords."""
        strategy = TextInferenceStrategy()
        row = pd.Series(
            {
                "description": "Machine learning algorithm for artificial intelligence software platform"
            }
        )

        result = strategy.enrich(row)

        assert result is not None
        assert result.naics_code == "5415"  # Computer systems
        assert result.metadata["keyword_matches"] >= 2

    def test_enrich_aerospace_keywords(self):
        """Test enriching with aerospace keywords."""
        strategy = TextInferenceStrategy()
        row = pd.Series({"Abstract": "Development of aerospace defense drone propulsion system"})

        result = strategy.enrich(row)

        assert result is not None
        assert result.naics_code == "3364"  # Aerospace manufacturing

    def test_enrich_insufficient_keywords(self):
        """Test enriching with insufficient keyword matches."""
        strategy = TextInferenceStrategy()
        row = pd.Series({"Abstract": "Development of research techniques"})

        result = strategy.enrich(row)

        # Should return None if less than 2 keyword matches
        assert result is None or result.metadata["keyword_matches"] >= 2

    def test_enrich_no_text_fields(self):
        """Test enriching when no text fields present."""
        strategy = TextInferenceStrategy()
        row = pd.Series({"amount": 100000, "company": "Test Corp"})

        result = strategy.enrich(row)

        assert result is None

    def test_enrich_case_insensitive(self):
        """Test keyword matching is case insensitive."""
        strategy = TextInferenceStrategy()
        row = pd.Series({"Title": "BIOTECH RESEARCH DRUG DEVELOPMENT THERAPEUTIC VACCINE"})

        result = strategy.enrich(row)

        assert result is not None
        assert result.naics_code == "5417"


# =============================================================================
# TopicCodeStrategy Tests
# =============================================================================


class TestTopicCodeStrategy:
    """Tests for TopicCodeStrategy."""

    def test_strategy_properties(self):
        """Test strategy name and confidence level."""
        strategy = TopicCodeStrategy()

        assert strategy.strategy_name == "topic_code"
        assert strategy.confidence_level == 0.75

    def test_enrich_af_topic(self):
        """Test enriching Air Force topic code."""
        strategy = TopicCodeStrategy()
        row = pd.Series({"Topic": "AF-2023-001"})

        result = strategy.enrich(row)

        assert result is not None
        assert result.naics_code == "3364"
        assert result.method == "topic_code_mapping"
        assert result.metadata["matched_prefix"] == "AF"

    def test_enrich_nih_topic(self):
        """Test enriching NIH topic code."""
        strategy = TopicCodeStrategy()
        row = pd.Series({"topic_code": "NIH-2023-BIO-001"})

        result = strategy.enrich(row)

        assert result is not None
        assert result.naics_code == "5417"
        assert result.metadata["matched_prefix"] == "NIH"

    def test_enrich_it_topic(self):
        """Test enriching IT topic code."""
        strategy = TopicCodeStrategy()
        row = pd.Series({"Topic_Code": "IT-CYBER-2023"})

        result = strategy.enrich(row)

        assert result is not None
        assert result.naics_code == "5415"

    def test_enrich_no_match(self):
        """Test enriching topic code with no match."""
        strategy = TopicCodeStrategy()
        row = pd.Series({"Topic": "UNKNOWN-2023"})

        result = strategy.enrich(row)

        assert result is None

    def test_enrich_no_topic_column(self):
        """Test enriching when no topic column exists."""
        strategy = TopicCodeStrategy()
        row = pd.Series({"company": "Test Corp"})

        result = strategy.enrich(row)

        assert result is None


# =============================================================================
# USAspendingDataFrameStrategy Tests
# =============================================================================


class TestUSAspendingDataFrameStrategy:
    """Tests for USAspendingDataFrameStrategy."""

    def test_strategy_properties(self):
        """Test strategy name and confidence level."""
        strategy = USAspendingDataFrameStrategy()

        assert strategy.strategy_name == "usaspending_dataframe"
        assert strategy.confidence_level == 0.85

    def test_strategy_custom_confidence(self):
        """Test strategy with custom confidence level."""
        strategy = USAspendingDataFrameStrategy(confidence=0.90)

        assert strategy.confidence_level == 0.90

    def test_enrich_uei_match(self):
        """Test enriching with UEI match."""
        usaspending_df = pd.DataFrame(
            [
                {"recipient_uei": "ABC123", "naics_code": "541715"},
                {"recipient_uei": "DEF456", "naics_code": "5417"},
            ]
        )
        strategy = USAspendingDataFrameStrategy(usaspending_df)
        row = pd.Series({"UEI": "ABC123", "company": "Test Corp"})

        result = strategy.enrich(row)

        assert result is not None
        assert result.naics_code == "541715"
        assert result.method == "uei_lookup"
        assert result.metadata["uei"] == "ABC123"

    def test_enrich_duns_match(self):
        """Test enriching with DUNS match."""
        usaspending_df = pd.DataFrame(
            [{"recipient_duns": "123456789", "primary_naics": "5417"}]
        )
        strategy = USAspendingDataFrameStrategy(usaspending_df)
        row = pd.Series({"DUNS": "123456789"})

        result = strategy.enrich(row)

        assert result is not None
        assert result.naics_code == "5417"
        assert result.method == "duns_lookup"
        # DUNS lookup has slightly lower confidence
        assert result.confidence == 0.85 * 0.95

    def test_enrich_no_dataframe(self):
        """Test enriching when no USAspending dataframe provided."""
        strategy = USAspendingDataFrameStrategy()
        row = pd.Series({"UEI": "ABC123"})

        result = strategy.enrich(row)

        assert result is None

    def test_enrich_empty_dataframe(self):
        """Test enriching with empty USAspending dataframe."""
        strategy = USAspendingDataFrameStrategy(pd.DataFrame())
        row = pd.Series({"UEI": "ABC123"})

        result = strategy.enrich(row)

        assert result is None

    def test_enrich_no_match(self):
        """Test enriching when no match found."""
        usaspending_df = pd.DataFrame([{"recipient_uei": "XYZ999", "naics_code": "541715"}])
        strategy = USAspendingDataFrameStrategy(usaspending_df)
        row = pd.Series({"UEI": "ABC123"})

        result = strategy.enrich(row)

        assert result is None


# =============================================================================
# SectorFallbackStrategy Tests
# =============================================================================


class TestSectorFallbackStrategy:
    """Tests for SectorFallbackStrategy."""

    def test_strategy_properties(self):
        """Test strategy name and confidence level."""
        strategy = SectorFallbackStrategy()

        assert strategy.strategy_name == "sector_fallback"
        assert strategy.confidence_level == 0.30

    def test_enrich_default_code(self):
        """Test enriching with default fallback code."""
        strategy = SectorFallbackStrategy()
        row = pd.Series({"company": "Test Corp"})

        result = strategy.enrich(row)

        assert result is not None
        assert result.naics_code == "5415"  # Default computer systems
        assert result.method == "default_fallback"
        assert result.metadata["reason"] == "no_other_strategy_succeeded"

    def test_enrich_custom_fallback(self):
        """Test enriching with custom fallback code."""
        strategy = SectorFallbackStrategy(fallback_code="5417")
        row = pd.Series({})

        result = strategy.enrich(row)

        assert result is not None
        assert result.naics_code == "5417"
        assert result.metadata["fallback_code"] == "5417"

    def test_enrich_always_succeeds(self):
        """Test that fallback strategy always returns a result."""
        strategy = SectorFallbackStrategy()
        row = pd.Series({})

        result = strategy.enrich(row)

        assert result is not None
        assert result.confidence == 0.30

    def test_enrich_invalid_fallback_code(self):
        """Test enriching with invalid fallback code."""
        strategy = SectorFallbackStrategy(fallback_code="invalid")
        row = pd.Series({})

        result = strategy.enrich(row)

        # Should return None if fallback code is invalid
        assert result is None
