"""Unit tests for NAICS fiscal enrichment strategies."""

import pandas as pd
import pytest

pytestmark = pytest.mark.fast


class TestOriginalDataStrategy:
    """Tests for OriginalDataStrategy."""

    def test_extracts_naics_from_standard_column(self):
        """Test extraction from NAICS column."""
        from src.enrichers.naics.fiscal.strategies.original_data import OriginalDataStrategy

        strategy = OriginalDataStrategy()
        row = pd.Series({"NAICS": "541715", "company_name": "Test Corp"})

        result = strategy.enrich(row)

        assert result is not None
        assert result.naics_code == "541715"
        assert result.confidence == 0.95
        assert result.source == "original_data"
        assert result.method == "direct_field"

    def test_extracts_naics_from_alternative_columns(self):
        """Test extraction from alternative column names."""
        from src.enrichers.naics.fiscal.strategies.original_data import OriginalDataStrategy

        strategy = OriginalDataStrategy()

        for col_name in ["naics", "NAICS_Code", "naics_code", "Primary_NAICS"]:
            row = pd.Series({col_name: "334111", "company_name": "Test Corp"})
            result = strategy.enrich(row)

            assert result is not None
            assert result.naics_code == "334111"

    def test_returns_none_when_no_naics_column(self):
        """Test returns None when no NAICS column present."""
        from src.enrichers.naics.fiscal.strategies.original_data import OriginalDataStrategy

        strategy = OriginalDataStrategy()
        row = pd.Series({"company_name": "Test Corp", "award_amount": 100000})

        result = strategy.enrich(row)

        assert result is None

    def test_returns_none_for_null_naics(self):
        """Test returns None when NAICS value is null."""
        from src.enrichers.naics.fiscal.strategies.original_data import OriginalDataStrategy

        strategy = OriginalDataStrategy()
        row = pd.Series({"NAICS": None, "company_name": "Test Corp"})

        result = strategy.enrich(row)

        assert result is None

    def test_strategy_properties(self):
        """Test strategy name and confidence level."""
        from src.enrichers.naics.fiscal.strategies.original_data import OriginalDataStrategy

        strategy = OriginalDataStrategy()

        assert strategy.strategy_name == "original_data"
        assert strategy.confidence_level == 0.95


class TestSectorFallbackStrategy:
    """Tests for SectorFallbackStrategy."""

    def test_returns_default_fallback_code(self):
        """Test returns default 5415 code."""
        from src.enrichers.naics.fiscal.strategies.sector_fallback import SectorFallbackStrategy

        strategy = SectorFallbackStrategy()
        row = pd.Series({"company_name": "Test Corp"})

        result = strategy.enrich(row)

        assert result is not None
        assert result.naics_code == "5415"
        assert result.confidence == 0.30
        assert result.source == "sector_fallback"
        assert result.method == "default_fallback"

    def test_custom_fallback_code(self):
        """Test with custom fallback code."""
        from src.enrichers.naics.fiscal.strategies.sector_fallback import SectorFallbackStrategy

        strategy = SectorFallbackStrategy(fallback_code="541712")
        row = pd.Series({"company_name": "Test Corp"})

        result = strategy.enrich(row)

        assert result is not None
        assert result.naics_code == "541712"

    def test_always_succeeds(self):
        """Test fallback always returns a result."""
        from src.enrichers.naics.fiscal.strategies.sector_fallback import SectorFallbackStrategy

        strategy = SectorFallbackStrategy()

        # Even with empty row, should return fallback
        row = pd.Series({})
        result = strategy.enrich(row)

        assert result is not None
        assert result.naics_code == "5415"

    def test_strategy_properties(self):
        """Test strategy name and confidence level."""
        from src.enrichers.naics.fiscal.strategies.sector_fallback import SectorFallbackStrategy

        strategy = SectorFallbackStrategy()

        assert strategy.strategy_name == "sector_fallback"
        assert strategy.confidence_level == 0.30


class TestAgencyDefaultsStrategy:
    """Tests for AgencyDefaultsStrategy."""

    def test_returns_dod_default(self):
        """Test DOD agency returns aerospace manufacturing code."""
        from src.enrichers.naics.fiscal.strategies.agency_defaults import AgencyDefaultsStrategy

        strategy = AgencyDefaultsStrategy()
        row = pd.Series({"agency": "DOD", "company_name": "Test Corp"})

        result = strategy.enrich(row)

        assert result is not None
        assert result.naics_code == "3364"  # Aerospace manufacturing
        assert result.source == "agency_defaults"

    def test_returns_hhs_default(self):
        """Test HHS agency returns biotech R&D code."""
        from src.enrichers.naics.fiscal.strategies.agency_defaults import AgencyDefaultsStrategy

        strategy = AgencyDefaultsStrategy()
        row = pd.Series({"agency": "HHS", "company_name": "Test Corp"})

        result = strategy.enrich(row)

        assert result is not None
        assert result.naics_code == "5417"  # Biotech R&D

    def test_returns_none_for_unknown_agency(self):
        """Test returns None for unknown agency."""
        from src.enrichers.naics.fiscal.strategies.agency_defaults import AgencyDefaultsStrategy

        strategy = AgencyDefaultsStrategy()
        row = pd.Series({"agency": "UNKNOWN_AGENCY", "company_name": "Test Corp"})

        result = strategy.enrich(row)

        assert result is None

    def test_returns_none_when_no_agency(self):
        """Test returns None when agency column missing."""
        from src.enrichers.naics.fiscal.strategies.agency_defaults import AgencyDefaultsStrategy

        strategy = AgencyDefaultsStrategy()
        row = pd.Series({"company_name": "Test Corp"})

        result = strategy.enrich(row)

        assert result is None

    def test_strategy_properties(self):
        """Test strategy name and confidence level."""
        from src.enrichers.naics.fiscal.strategies.agency_defaults import AgencyDefaultsStrategy

        strategy = AgencyDefaultsStrategy()

        assert strategy.strategy_name == "agency_defaults"
        assert strategy.confidence_level == 0.50
