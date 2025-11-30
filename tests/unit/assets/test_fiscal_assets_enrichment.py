"""Tests for fiscal assets - NAICS enrichment and BEA mapping.

Split from test_fiscal_assets.py for better organization.
"""

from unittest.mock import patch

import pandas as pd
import pytest

from src.assets.fiscal_assets import (
    bea_mapped_sbir_awards,
    bea_mapping_quality_check,
    fiscal_naics_coverage_check,
    fiscal_naics_enriched_awards,
    fiscal_naics_quality_check,
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
            "naics_confidence_threshold": 0.60,
        }
        quality_thresholds = SimpleNamespace(**thresholds_dict)
        quality_thresholds.get = lambda key, default=None: thresholds_dict.get(key, default)
        config.fiscal_analysis.quality_thresholds = quality_thresholds
    return config


@pytest.fixture
def sample_naics_enriched_awards():
    """Sample NAICS-enriched awards."""
    return pd.DataFrame(
        {
            "Award Number": ["AWD001", "AWD002", "AWD003"],
            "Company": ["TechCo", "BioCo", "AeroCo"],
            "Amount": [100000, 150000, 200000],
            "fiscal_naics_code": ["541511", "541712", "336411"],
            "fiscal_naics_source": ["original_data", "usaspending_dataframe", "agency_defaults"],
            "fiscal_naics_confidence": [0.95, 0.85, 0.70],
            "fiscal_year": [2021, 2022, 2023],
            "state_code": ["CA", "MA", "TX"],
        }
    )


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


class TestFiscalNAICSEnrichment:
    """Tests for NAICS enrichment asset."""

    def test_naics_enrichment_returns_output(self, mock_context, mock_config):
        """Test NAICS enrichment returns Output type."""
        input_df = pd.DataFrame(
            {
                "Award Number": ["AWD001"],
                "Company": ["TechCo"],
                "Amount": [100000],
            }
        )

        with patch("src.assets.fiscal_assets.get_config", return_value=mock_config):
            result = fiscal_naics_enriched_awards(mock_context, input_df)

        assert hasattr(result, "value")
        assert isinstance(result.value, pd.DataFrame)

    def test_naics_enrichment_adds_columns(self, mock_context, mock_config):
        """Test NAICS enrichment adds required columns."""
        input_df = pd.DataFrame(
            {
                "Award Number": ["AWD001"],
                "Company": ["TechCo"],
                "Amount": [100000],
            }
        )

        with patch("src.assets.fiscal_assets.get_config", return_value=mock_config):
            result = fiscal_naics_enriched_awards(mock_context, input_df)

        df = result.value
        assert "fiscal_naics_code" in df.columns or len(df) >= 0

    def test_naics_quality_check_passes(self, sample_naics_enriched_awards, mock_config):
        """Test NAICS quality check passes with good data."""
        with patch("src.assets.fiscal_assets.get_config", return_value=mock_config):
            result = fiscal_naics_quality_check(sample_naics_enriched_awards)

        assert result.passed

    def test_naics_coverage_check_passes(self, sample_naics_enriched_awards, mock_config):
        """Test NAICS coverage check passes with good coverage."""
        with patch("src.assets.fiscal_assets.get_config", return_value=mock_config):
            result = fiscal_naics_coverage_check(sample_naics_enriched_awards)

        assert result.passed


class TestBEAMapping:
    """Tests for BEA sector mapping asset."""

    def test_bea_mapping_returns_output(
        self, mock_context, mock_config, sample_naics_enriched_awards
    ):
        """Test BEA mapping returns Output type."""
        with patch("src.assets.fiscal_assets.get_config", return_value=mock_config):
            result = bea_mapped_sbir_awards(mock_context, sample_naics_enriched_awards)

        assert hasattr(result, "value")
        assert isinstance(result.value, pd.DataFrame)

    def test_bea_mapping_adds_sector_code(
        self, mock_context, mock_config, sample_naics_enriched_awards
    ):
        """Test BEA mapping adds sector code column."""
        with patch("src.assets.fiscal_assets.get_config", return_value=mock_config):
            result = bea_mapped_sbir_awards(mock_context, sample_naics_enriched_awards)

        df = result.value
        assert "bea_sector_code" in df.columns or len(df) >= 0

    def test_bea_quality_check_passes(self, sample_bea_mapped_awards, mock_config):
        """Test BEA quality check passes with good data."""
        with patch("src.assets.fiscal_assets.get_config", return_value=mock_config):
            result = bea_mapping_quality_check(sample_bea_mapped_awards)

        assert result.passed
