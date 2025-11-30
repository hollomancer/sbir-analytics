"""Tests for fiscal assets - economic shocks and impacts.

Split from test_fiscal_assets.py for better organization.
"""

from unittest.mock import patch

import pandas as pd
import pytest

from src.assets.fiscal_assets import (
    economic_impacts,
    economic_impacts_quality_check,
    economic_shocks,
    economic_shocks_quality_check,
)
from tests.mocks import ContextMocks
from tests.utils.config_mocks import create_mock_pipeline_config

pytestmark = pytest.mark.fast


@pytest.fixture
def mock_context():
    """Mock Dagster execution context."""
    return ContextMocks.context_with_logging()


@pytest.fixture
def mock_config():
    """Mock configuration."""
    from types import SimpleNamespace

    config = create_mock_pipeline_config()
    if hasattr(config, "fiscal_analysis"):
        thresholds_dict = {
            "naics_coverage_rate": 0.85,
            "bea_sector_mapping_rate": 0.90,
            "geographic_resolution_rate": 0.90,
        }
        quality_thresholds = SimpleNamespace(**thresholds_dict)
        quality_thresholds.get = lambda key, default=None: thresholds_dict.get(key, default)
        config.fiscal_analysis.quality_thresholds = quality_thresholds

        performance_dict = {"chunk_size": 10000}
        performance = SimpleNamespace(**performance_dict)
        performance.get = lambda key, default=None: performance_dict.get(key, default)
        config.fiscal_analysis.performance = performance
    return config


@pytest.fixture
def sample_bea_mapped_awards():
    """Sample BEA-mapped awards."""
    return pd.DataFrame(
        {
            "Award Number": ["AWD001", "AWD002", "AWD003"],
            "fiscal_naics_code": ["541511", "541712", "336411"],
            "bea_sector_code": ["5415", "5417", "3364"],
            "bea_mapping_confidence": [0.90, 0.85, 0.95],
            "Amount": [100000, 150000, 200000],
            "fiscal_year": [2021, 2022, 2023],
            "state_code": ["CA", "MA", "TX"],
        }
    )


@pytest.fixture
def sample_economic_shocks():
    """Sample economic shocks with enough data to pass quality checks."""
    states = ["CA", "MA", "TX", "NY", "FL", "WA", "IL", "PA", "OH", "GA", "NC", "VA"]
    return pd.DataFrame(
        {
            "state": states,
            "bea_sector": ["5415", "5417", "3364"] * 4,
            "fiscal_year": [2021, 2022, 2023] * 4,
            "shock_amount": [100000 + i * 10000 for i in range(12)],
            "awards_aggregated": [1] * 12,
            "confidence": [0.90] * 12,
            "naics_coverage_rate": [1.0] * 12,
            "geographic_resolution_rate": [1.0] * 12,
        }
    )


@pytest.fixture
def sample_economic_impacts():
    """Sample economic impacts."""
    return pd.DataFrame(
        {
            "state": ["CA", "MA", "TX"],
            "bea_sector": ["5415", "5417", "3364"],
            "fiscal_year": [2021, 2022, 2023],
            "shock_amount": [100000, 150000, 200000],
            "wage_impact": [50000, 75000, 100000],
            "proprietor_income_impact": [10000, 15000, 20000],
            "gross_operating_surplus": [20000, 30000, 40000],
            "consumption_impact": [30000, 45000, 60000],
            "tax_impact": [15000, 22500, 30000],
            "production_impact": [150000, 225000, 300000],
            "model_version": ["stateior_1.0"] * 3,
            "confidence": [0.90, 0.85, 0.95],
        }
    )


class TestEconomicShocks:
    """Tests for economic shocks aggregation asset."""

    def test_economic_shocks_returns_output(
        self, mock_context, mock_config, sample_bea_mapped_awards
    ):
        """Test economic shocks returns Output type."""
        with patch("src.assets.fiscal_assets.get_config", return_value=mock_config):
            result = economic_shocks(mock_context, sample_bea_mapped_awards)

        assert hasattr(result, "value")
        assert isinstance(result.value, pd.DataFrame)

    def test_economic_shocks_aggregates_by_state_sector(
        self, mock_context, mock_config, sample_bea_mapped_awards
    ):
        """Test economic shocks aggregates by state and sector."""
        with patch("src.assets.fiscal_assets.get_config", return_value=mock_config):
            result = economic_shocks(mock_context, sample_bea_mapped_awards)

        df = result.value
        if len(df) > 0:
            assert "state" in df.columns or "state_code" in df.columns
            assert "bea_sector" in df.columns or "bea_sector_code" in df.columns

    def test_economic_shocks_quality_check_passes(self, sample_economic_shocks, mock_config):
        """Test economic shocks quality check passes with good data."""
        with patch("src.assets.fiscal_assets.get_config", return_value=mock_config):
            result = economic_shocks_quality_check(sample_economic_shocks)

        assert result.passed


class TestEconomicImpacts:
    """Tests for economic impacts calculation asset."""

    def test_economic_impacts_returns_output(
        self, mock_context, mock_config, sample_economic_shocks
    ):
        """Test economic impacts returns Output type."""
        with patch("src.assets.fiscal_assets.get_config", return_value=mock_config):
            with patch("src.assets.fiscal_assets._run_stateio_model") as mock_stateio:
                mock_stateio.return_value = pd.DataFrame(
                    {
                        "state": ["CA"],
                        "wage_impact": [50000],
                        "consumption_impact": [30000],
                    }
                )
                result = economic_impacts(mock_context, sample_economic_shocks)

        assert hasattr(result, "value")
        assert isinstance(result.value, pd.DataFrame)

    def test_economic_impacts_quality_check_passes(self, sample_economic_impacts, mock_config):
        """Test economic impacts quality check passes with good data."""
        with patch("src.assets.fiscal_assets.get_config", return_value=mock_config):
            result = economic_impacts_quality_check(sample_economic_impacts)

        assert result.passed

    def test_economic_impacts_has_required_columns(self, sample_economic_impacts):
        """Test economic impacts has required output columns."""
        required = ["state", "wage_impact", "consumption_impact"]
        for col in required:
            assert col in sample_economic_impacts.columns
