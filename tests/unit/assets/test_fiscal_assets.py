"""Tests for fiscal assets pipeline."""

from unittest.mock import Mock, patch

import pandas as pd
import pytest
from dagster import AssetCheckSeverity, Output

from src.assets.fiscal_assets import (
    _create_placeholder_impacts,
    bea_mapping_quality_check,
    economic_impacts,
    federal_tax_estimates,
    fiscal_naics_coverage_check,
    fiscal_naics_enriched_awards,
    fiscal_return_summary,
    fiscal_returns_report,
    inflation_adjusted_awards,
    inflation_adjustment_quality_check,
    sensitivity_scenarios,
    uncertainty_analysis,
)


# ==================== Fixtures ====================

pytestmark = pytest.mark.fast

from tests.utils.config_mocks import create_mock_pipeline_config
from tests.utils.fixtures import create_sample_enriched_awards_df


@pytest.fixture
def mock_context():
    """Mock Dagster execution context."""
    from tests.mocks import ContextMocks

    return ContextMocks.context_with_logging()


@pytest.fixture
def mock_config():
    """Mock configuration using consolidated utility."""
    from types import SimpleNamespace

    config = create_mock_pipeline_config()
    # Set fiscal_analysis settings
    if hasattr(config, "fiscal_analysis"):
        # Create quality_thresholds that supports both attribute and dict access
        thresholds_dict = {
            "naics_coverage_rate": 0.85,
            "bea_sector_mapping_rate": 0.90,
            "geographic_resolution_rate": 0.90,
            "naics_confidence_threshold": 0.60,
            "inflation_adjustment_success": 0.95,
        }
        # Use SimpleNamespace for attribute access, but add .get() method for dict-style access
        quality_thresholds = SimpleNamespace(**thresholds_dict)
        quality_thresholds.get = lambda key, default=None: thresholds_dict.get(key, default)
        config.fiscal_analysis.quality_thresholds = quality_thresholds

        # Create performance config that supports both attribute and dict access
        performance_dict = {
            "chunk_size": 10000,
        }
        performance = SimpleNamespace(**performance_dict)
        performance.get = lambda key, default=None: performance_dict.get(key, default)
        config.fiscal_analysis.performance = performance
    return config


@pytest.fixture
def sample_enriched_awards():
    """Sample enriched SBIR awards using consolidated utility."""
    df = create_sample_enriched_awards_df(num_awards=3)
    # Rename columns to match expected format
    df = df.rename(
        columns={
            "award_id": "Award Number",
            "company_name": "Company",
            "award_amount": "Amount",
            "company_state": "State",
        }
    )
    return df


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


@pytest.fixture
def sample_economic_shocks():
    """Sample economic shocks."""
    # Create 12 shocks to meet minimum threshold of 10
    states = ["CA", "MA", "TX", "NY", "FL", "WA", "IL", "PA", "OH", "GA", "NC", "VA"]
    sectors = [
        "5415",
        "5417",
        "3364",
        "5415",
        "5417",
        "3364",
        "5415",
        "5417",
        "3364",
        "5415",
        "5417",
        "3364",
    ]
    years = [2021, 2022, 2023, 2021, 2022, 2023, 2021, 2022, 2023, 2021, 2022, 2023]
    amounts = [
        100000,
        150000,
        200000,
        120000,
        160000,
        180000,
        110000,
        140000,
        190000,
        130000,
        170000,
        210000,
    ]

    return pd.DataFrame(
        {
            "state": states,
            "bea_sector": sectors,
            "fiscal_year": years,
            "shock_amount": amounts,
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
            "model_version": "stateior_1.0",
            "confidence": [0.90, 0.85, 0.95],
        }
    )


# ==================== NAICS Enrichment Tests ====================


class TestFiscalPreparation:
    """Tests for fiscal data preparation asset."""

    @patch("src.assets.fiscal_assets.get_config")
    @patch("src.assets.fiscal_assets.adjust_awards_for_inflation")
    @patch("src.assets.fiscal_assets.performance_monitor")
    def test_inflation_adjusted_awards_success(
        self,
        mock_perf_monitor,
        mock_adjust_func,
        mock_get_config,
        mock_context,
        mock_config,
        sample_bea_mapped_awards,
    ):
        """Test successful inflation adjustment."""
        mock_get_config.return_value = mock_config

        adjusted_df = sample_bea_mapped_awards.copy()
        adjusted_df["amount_nominal"] = adjusted_df["Amount"]
        adjusted_df["amount_real"] = adjusted_df["Amount"] * 1.1
        adjusted_df["inflation_factor"] = 1.1

        quality_metrics = {"adjustment_success_rate": 0.95}
        mock_adjust_func.return_value = (adjusted_df, quality_metrics)

        result = inflation_adjusted_awards(mock_context, sample_bea_mapped_awards)

        assert isinstance(result, Output)
        assert "amount_real" in result.value.columns
        assert "inflation_factor" in result.value.columns

    @patch("src.assets.fiscal_assets.get_config")
    def test_inflation_adjustment_quality_check_passes(self, mock_get_config, mock_config):
        """Test inflation adjustment quality check passes."""
        mock_get_config.return_value = mock_config

        adjusted_df = pd.DataFrame(
            {
                "award_amount": [100000, 150000, 200000],
                "inflation_adjusted_amount": [110000, 165000, 220000],
                "inflation_factor": [1.1, 1.1, 1.1],
            }
        )

        result = inflation_adjustment_quality_check(adjusted_df)

        assert result.passed is True
        assert "PASSED" in result.description


# ==================== Tax and ROI Tests ====================


class TestTaxAndROI:
    """Tests for tax estimation and ROI calculation assets."""

    @patch("src.assets.fiscal_assets.get_config")
    @patch("src.assets.fiscal_assets.FiscalTaxEstimator")
    @patch("src.assets.fiscal_assets.performance_monitor")
    def test_federal_tax_estimates_success(
        self,
        mock_perf_monitor,
        mock_tax_estimator_class,
        mock_get_config,
        mock_context,
        mock_config,
        sample_economic_impacts,
    ):
        """Test successful federal tax estimation."""
        mock_get_config.return_value = mock_config

        mock_estimator = Mock()

        # Create tax base components (input)
        tax_base_df = sample_economic_impacts.copy()

        # Create tax estimates (output)
        tax_df = sample_economic_impacts.copy()
        tax_df["individual_income_tax"] = 5000
        tax_df["payroll_tax"] = 3000
        tax_df["corporate_income_tax"] = 2000
        tax_df["excise_tax"] = 1000
        tax_df["total_tax_receipts"] = 11000

        mock_estimator.estimate_taxes_from_components.return_value = tax_df

        # Mock statistics
        mock_stats = Mock()
        mock_stats.total_tax_receipts = 33000.0
        mock_stats.total_individual_income_tax = 15000.0
        mock_stats.total_payroll_tax = 9000.0
        mock_stats.total_corporate_income_tax = 6000.0
        mock_stats.total_excise_tax = 3000.0
        mock_stats.avg_effective_rate = 22.0
        mock_estimator.get_estimation_statistics.return_value = mock_stats

        mock_tax_estimator_class.return_value = mock_estimator

        result = federal_tax_estimates(mock_context, tax_base_df)

        assert isinstance(result, Output)
        assert "total_tax_receipts" in result.value.columns

    @patch("src.assets.fiscal_assets.get_config")
    @patch("src.assets.fiscal_assets.FiscalROICalculator")
    @patch("src.assets.fiscal_assets.performance_monitor")
    def test_fiscal_return_summary_success(
        self,
        mock_perf_monitor,
        mock_roi_calculator_class,
        mock_get_config,
        mock_context,
        mock_config,
    ):
        """Test successful fiscal return summary calculation."""
        mock_get_config.return_value = mock_config

        mock_calculator = Mock()

        # Mock the summary object returned by calculate_roi_summary
        from datetime import datetime

        mock_summary = Mock()
        mock_summary.analysis_id = "test-123"
        mock_summary.analysis_date = datetime(2024, 1, 1)
        mock_summary.base_year = 2024
        mock_summary.methodology_version = "1.0"
        mock_summary.total_sbir_investment = 250000.0
        mock_summary.total_tax_receipts = 125000.0
        mock_summary.net_fiscal_return = -125000.0
        mock_summary.roi_ratio = 0.50
        mock_summary.payback_period_years = 8.0
        mock_summary.net_present_value = -50000.0
        mock_summary.benefit_cost_ratio = 0.50
        mock_summary.confidence_interval_low = 0.40
        mock_summary.confidence_interval_high = 0.60
        mock_summary.confidence_level = 0.95
        mock_summary.quality_score = 0.85
        mock_summary.quality_flags = []

        mock_calculator.calculate_roi_summary.return_value = mock_summary
        mock_roi_calculator_class.return_value = mock_calculator

        # Create tax estimates DataFrame
        tax_df = pd.DataFrame(
            {
                "fiscal_year": [2021, 2022],
                "total_tax_receipts": [50000, 75000],
                "shock_amount": [100000, 150000],
            }
        )

        # Create inflation adjusted awards DataFrame
        awards_df = pd.DataFrame(
            {
                "Award Number": ["AWD001", "AWD002"],
                "inflation_adjusted_amount": [100000, 150000],
            }
        )

        result = fiscal_return_summary(mock_context, tax_df, awards_df)

        assert isinstance(result, Output)
        assert "roi_ratio" in result.value.columns
        assert result.value["roi_ratio"].iloc[0] == 0.50


# ==================== Sensitivity and Uncertainty Tests ====================


class TestSensitivityUncertainty:
    """Tests for sensitivity and uncertainty analysis assets."""

    @patch("src.assets.fiscal_assets.get_config")
    @patch("src.assets.fiscal_assets.FiscalParameterSweep")
    @patch("src.assets.fiscal_assets.performance_monitor")
    def test_sensitivity_scenarios_success(
        self,
        mock_perf_monitor,
        mock_sweep_class,
        mock_get_config,
        mock_context,
        mock_config,
    ):
        """Test successful sensitivity scenarios generation."""
        mock_get_config.return_value = mock_config

        mock_sweep = Mock()

        scenarios_df = pd.DataFrame(
            {
                "scenario_id": ["base", "optimistic", "pessimistic"],
                "method": ["grid", "grid", "grid"],
                "multiplier": [1.0, 1.2, 0.8],
                "tax_rate": [0.25, 0.30, 0.20],
            }
        )

        mock_sweep.generate_scenarios.return_value = scenarios_df
        mock_sweep_class.return_value = mock_sweep

        result = sensitivity_scenarios(mock_context)

        assert isinstance(result, Output)
        assert len(result.value) == 3

    @patch("src.assets.fiscal_assets.get_config")
    @patch("src.assets.fiscal_assets.FiscalUncertaintyQuantifier")
    @patch("src.assets.fiscal_assets.performance_monitor")
    def test_uncertainty_analysis_success(
        self,
        mock_perf_monitor,
        mock_quantifier_class,
        mock_get_config,
        mock_context,
        mock_config,
    ):
        """Test successful uncertainty quantification."""
        from decimal import Decimal
        from src.transformers.fiscal.sensitivity import UncertaintyResult

        mock_get_config.return_value = mock_config

        mock_quantifier = Mock()

        # Create proper UncertaintyResult object
        uncertainty_result = UncertaintyResult(
            min_estimate=Decimal("0.40"),
            mean_estimate=Decimal("0.50"),
            max_estimate=Decimal("0.60"),
            confidence_intervals={0.95: (Decimal("0.40"), Decimal("0.60"))},
            sensitivity_indices={"multiplier": 0.8},
            quality_flags=[],
        )

        mock_quantifier.quantify_uncertainty.return_value = uncertainty_result
        mock_quantifier.flag_high_uncertainty.return_value = False
        mock_quantifier_class.return_value = mock_quantifier

        # Create scenarios DataFrame
        scenarios_df = pd.DataFrame(
            {
                "scenario_id": ["base", "optimistic", "pessimistic"],
                "method": ["grid", "grid", "grid"],
                "multiplier": [1.0, 1.2, 0.8],
            }
        )

        # Create tax estimates DataFrame
        tax_df = pd.DataFrame(
            {
                "fiscal_year": [2021, 2022],
                "total_tax_receipt": [50000, 75000],
            }
        )

        result = uncertainty_analysis(mock_context, scenarios_df, tax_df)

        assert isinstance(result, Output)
        assert isinstance(result.value, pd.DataFrame)
        assert "mean_estimate" in result.value.columns


# ==================== Reporting Tests ====================


class TestReporting:
    """Tests for fiscal returns reporting asset."""

    @patch("src.assets.fiscal_assets.get_config")
    @patch("src.assets.fiscal_assets.performance_monitor")
    def test_fiscal_returns_report_success(
        self,
        mock_perf_monitor,
        mock_get_config,
        mock_context,
        mock_config,
    ):
        """Test successful fiscal returns report generation."""
        mock_get_config.return_value = mock_config

        fiscal_return_summary = pd.DataFrame(
            {
                "fiscal_year": [2021, 2022],
                "roi_ratio": [0.50, 0.55],
            }
        )
        fiscal_return_summary.index = [0, 1]

        uncertainty_analysis = pd.DataFrame(
            {
                "metric": ["roi_ratio", "roi_ratio"],
                "mean": [0.50, 0.55],
                "ci_lower": [0.45, 0.50],
                "ci_upper": [0.55, 0.60],
            }
        )
        uncertainty_analysis.index = [0, 1]

        federal_tax_estimates = pd.DataFrame(
            {
                "total_tax_receipt": [50000, 75000],
            }
        )

        with patch("builtins.open", create=True):
            with patch("pathlib.Path.mkdir"):
                result = fiscal_returns_report(
                    mock_context, fiscal_return_summary, uncertainty_analysis, federal_tax_estimates
                )

        assert isinstance(result, Output)
        assert result.value is not None


# ==================== Edge Cases ====================


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    @patch("src.assets.fiscal_assets.get_config")
    def test_fiscal_naics_coverage_check_empty_dataframe(self, mock_get_config, mock_config):
        """Test NAICS coverage check with empty DataFrame."""
        mock_get_config.return_value = mock_config

        empty_df = pd.DataFrame()

        result = fiscal_naics_coverage_check(empty_df)

        assert result.passed is False
        assert result.severity == AssetCheckSeverity.ERROR

    @patch("src.assets.fiscal_assets.get_config")
    def test_bea_mapping_quality_check_empty(self, mock_get_config, mock_config):
        """Test BEA mapping quality check with empty DataFrame."""
        mock_get_config.return_value = mock_config

        empty_df = pd.DataFrame()

        result = bea_mapping_quality_check(empty_df)

        assert result.passed is False

    @patch("src.assets.fiscal_assets.get_config")
    @patch("src.assets.fiscal_assets.RStateIOAdapter")
    def test_economic_impacts_computation_error(
        self,
        mock_adapter_class,
        mock_get_config,
        mock_context,
        mock_config,
        sample_economic_shocks,
    ):
        """Test economic impacts handles computation errors."""
        mock_get_config.return_value = mock_config

        mock_adapter = Mock()
        mock_adapter.is_available.return_value = True
        mock_adapter.compute_impacts.side_effect = RuntimeError("Model failed")
        mock_adapter.get_model_version.return_value = "stateior_1.0"
        mock_adapter_class.return_value = mock_adapter

        result = economic_impacts(mock_context, sample_economic_shocks)

        # Should fall back to placeholder
        assert isinstance(result, Output)
        assert "warning" in result.metadata
        mock_context.log.error.assert_called()

    def test_create_placeholder_impacts_all_columns(self, mock_context, sample_economic_shocks):
        """Test placeholder impacts includes all required columns."""
        result = _create_placeholder_impacts(sample_economic_shocks, mock_context)

        required_cols = [
            "wage_impact",
            "proprietor_income_impact",
            "gross_operating_surplus",
            "consumption_impact",
            "tax_impact",
            "production_impact",
            "model_version",
            "confidence",
            "quality_flags",
        ]

        for col in required_cols:
            assert col in result.value.columns

    @patch("src.assets.fiscal_assets.get_config")
    @patch("src.assets.fiscal_assets.enrich_sbir_awards_with_fiscal_naics")
    @patch("src.assets.fiscal_assets.performance_monitor")
    def test_fiscal_naics_enriched_awards_no_usaspending_data(
        self,
        mock_perf_monitor,
        mock_enrich_func,
        mock_get_config,
        mock_context,
        mock_config,
        sample_enriched_awards,
        sample_naics_enriched_awards,
    ):
        """Test NAICS enrichment works without USAspending data."""
        mock_get_config.return_value = mock_config
        mock_perf_monitor.get_metrics_summary.return_value = {
            "fiscal_naics_enrichment": {
                "total_duration": 5.0,
                "max_peak_memory_mb": 256.0,
            }
        }

        quality_metrics = {
            "naics_coverage_threshold": 0.85,
            "coverage_meets_threshold": True,
        }
        mock_enrich_func.return_value = (sample_naics_enriched_awards, quality_metrics)

        result = fiscal_naics_enriched_awards(
            mock_context, sample_enriched_awards, raw_usaspending_recipients=None
        )

        assert isinstance(result, Output)
        mock_enrich_func.assert_called_once()
