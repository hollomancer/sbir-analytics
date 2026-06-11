"""Unit tests for NAICS fiscal enrichment strategies."""

import pandas as pd
import pytest

pytestmark = pytest.mark.fast


class TestOriginalDataStrategy:
    """Tests for OriginalDataStrategy."""

    def test_extracts_naics_from_standard_column(self):
        """Test extraction from NAICS column."""
        from sbir_etl.enrichers.naics.fiscal.strategies.simple_strategies import (
            OriginalDataStrategy,
        )

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
        from sbir_etl.enrichers.naics.fiscal.strategies.simple_strategies import (
            OriginalDataStrategy,
        )

        strategy = OriginalDataStrategy()

        for col_name in ["naics", "NAICS_Code", "naics_code", "Primary_NAICS"]:
            row = pd.Series({col_name: "334111", "company_name": "Test Corp"})
            result = strategy.enrich(row)

            assert result is not None
            assert result.naics_code == "334111"

    def test_returns_none_when_no_naics_column(self):
        """Test returns None when no NAICS column present."""
        from sbir_etl.enrichers.naics.fiscal.strategies.simple_strategies import (
            OriginalDataStrategy,
        )

        strategy = OriginalDataStrategy()
        row = pd.Series({"company_name": "Test Corp", "award_amount": 100000})

        result = strategy.enrich(row)

        assert result is None

    def test_returns_none_for_null_naics(self):
        """Test returns None when NAICS value is null."""
        from sbir_etl.enrichers.naics.fiscal.strategies.simple_strategies import (
            OriginalDataStrategy,
        )

        strategy = OriginalDataStrategy()
        row = pd.Series({"NAICS": None, "company_name": "Test Corp"})

        result = strategy.enrich(row)

        assert result is None

    def test_strategy_properties(self):
        """Test strategy name and confidence level."""
        from sbir_etl.enrichers.naics.fiscal.strategies.simple_strategies import (
            OriginalDataStrategy,
        )

        strategy = OriginalDataStrategy()

        assert strategy.strategy_name == "original_data"
        assert strategy.confidence_level == 0.95


class TestSectorFallbackStrategy:
    """Tests for SectorFallbackStrategy."""

    def test_returns_default_fallback_code(self):
        """Test returns default 5415 code."""
        from sbir_etl.enrichers.naics.fiscal.strategies.simple_strategies import (
            SectorFallbackStrategy,
        )

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
        from sbir_etl.enrichers.naics.fiscal.strategies.simple_strategies import (
            SectorFallbackStrategy,
        )

        strategy = SectorFallbackStrategy(fallback_code="541712")
        row = pd.Series({"company_name": "Test Corp"})

        result = strategy.enrich(row)

        assert result is not None
        assert result.naics_code == "541712"

    def test_always_succeeds(self):
        """Test fallback always returns a result."""
        from sbir_etl.enrichers.naics.fiscal.strategies.simple_strategies import (
            SectorFallbackStrategy,
        )

        strategy = SectorFallbackStrategy()

        # Even with empty row, should return fallback
        row = pd.Series({})
        result = strategy.enrich(row)

        assert result is not None
        assert result.naics_code == "5415"

    def test_strategy_properties(self):
        """Test strategy name and confidence level."""
        from sbir_etl.enrichers.naics.fiscal.strategies.simple_strategies import (
            SectorFallbackStrategy,
        )

        strategy = SectorFallbackStrategy()

        assert strategy.strategy_name == "sector_fallback"
        assert strategy.confidence_level == 0.30


class TestAgencyDefaultsStrategy:
    """Tests for AgencyDefaultsStrategy."""

    def test_returns_dod_default(self):
        """Test DOD agency returns aerospace manufacturing code."""
        from sbir_etl.enrichers.naics.fiscal.strategies.simple_strategies import (
            AgencyDefaultsStrategy,
        )

        strategy = AgencyDefaultsStrategy()
        row = pd.Series({"agency": "DOD", "company_name": "Test Corp"})

        result = strategy.enrich(row)

        assert result is not None
        assert result.naics_code == "3364"  # Aerospace manufacturing
        assert result.source == "agency_defaults"

    def test_returns_hhs_default(self):
        """Test HHS agency returns biotech R&D code."""
        from sbir_etl.enrichers.naics.fiscal.strategies.simple_strategies import (
            AgencyDefaultsStrategy,
        )

        strategy = AgencyDefaultsStrategy()
        row = pd.Series({"agency": "HHS", "company_name": "Test Corp"})

        result = strategy.enrich(row)

        assert result is not None
        assert result.naics_code == "5417"  # Biotech R&D

    def test_returns_none_for_unknown_agency(self):
        """Test returns None for unknown agency."""
        from sbir_etl.enrichers.naics.fiscal.strategies.simple_strategies import (
            AgencyDefaultsStrategy,
        )

        strategy = AgencyDefaultsStrategy()
        row = pd.Series({"agency": "UNKNOWN_AGENCY", "company_name": "Test Corp"})

        result = strategy.enrich(row)

        assert result is None

    def test_returns_none_when_no_agency(self):
        """Test returns None when agency column missing."""
        from sbir_etl.enrichers.naics.fiscal.strategies.simple_strategies import (
            AgencyDefaultsStrategy,
        )

        strategy = AgencyDefaultsStrategy()
        row = pd.Series({"company_name": "Test Corp"})

        result = strategy.enrich(row)

        assert result is None

    def test_strategy_properties(self):
        """Test strategy name and confidence level."""
        from sbir_etl.enrichers.naics.fiscal.strategies.simple_strategies import (
            AgencyDefaultsStrategy,
        )

        strategy = AgencyDefaultsStrategy()

        assert strategy.strategy_name == "agency_defaults"
        assert strategy.confidence_level == 0.50


# =============================================================================
# R4 — Strategy registry tests
# =============================================================================


class TestDefaultStrategies:
    """Tests for the strategy_registry.default_strategies factory."""

    def test_returns_list_of_six_strategies(self):
        """default_strategies() returns six strategies in the expected order."""
        from sbir_etl.enrichers.naics.fiscal.strategy_registry import default_strategies
        from sbir_etl.enrichers.naics.fiscal.strategies.simple_strategies import (
            AgencyDefaultsStrategy,
            OriginalDataStrategy,
            SectorFallbackStrategy,
            TopicCodeStrategy,
        )
        from sbir_etl.enrichers.naics.fiscal.strategies.text_inference import TextInferenceStrategy
        from sbir_etl.enrichers.naics.fiscal.strategies.usaspending_dataframe import (
            USAspendingDataFrameStrategy,
        )

        strategies = default_strategies()

        assert len(strategies) == 6
        assert isinstance(strategies[0], OriginalDataStrategy)
        assert isinstance(strategies[1], USAspendingDataFrameStrategy)
        assert isinstance(strategies[2], TopicCodeStrategy)
        assert isinstance(strategies[3], TextInferenceStrategy)
        assert isinstance(strategies[4], AgencyDefaultsStrategy)
        assert isinstance(strategies[5], SectorFallbackStrategy)

    def test_passes_usaspending_df_to_strategy(self):
        """default_strategies(usaspending_df=...) propagates df to the USAspending strategy."""
        import pandas as pd
        from sbir_etl.enrichers.naics.fiscal.strategy_registry import default_strategies
        from sbir_etl.enrichers.naics.fiscal.strategies.usaspending_dataframe import (
            USAspendingDataFrameStrategy,
        )

        df = pd.DataFrame({"recipient_uei": ["ABC123"]})
        strategies = default_strategies(usaspending_df=df)

        usa_strat = strategies[1]
        assert isinstance(usa_strat, USAspendingDataFrameStrategy)
        assert usa_strat.usaspending_df is df


class TestFiscalNAICSEnricherStrategiesArg:
    """Tests for FiscalNAICSEnricher accepting a custom strategies= argument."""

    def test_custom_strategies_override_default(self):
        """Passing strategies=[...] replaces the default strategy list."""
        from unittest.mock import MagicMock
        from sbir_etl.enrichers.naics.fiscal.enricher import FiscalNAICSEnricher
        from sbir_etl.enrichers.naics.fiscal.strategies.base import EnrichmentStrategy

        sentinel = MagicMock(spec=EnrichmentStrategy)
        enricher = FiscalNAICSEnricher(strategies=[sentinel])

        assert enricher.strategies == [sentinel]

    def test_default_strategies_used_when_none_passed(self):
        """Without strategies=, the enricher builds the default six-strategy list."""
        from sbir_etl.enrichers.naics.fiscal.enricher import FiscalNAICSEnricher

        enricher = FiscalNAICSEnricher()

        assert len(enricher.strategies) == 6
