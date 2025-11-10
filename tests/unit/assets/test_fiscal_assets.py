"""Tests for fiscal assets pipeline."""

from unittest.mock import Mock, patch

import pandas as pd
import pytest
from dagster import AssetCheckSeverity, AssetExecutionContext, Output

from src.assets.fiscal_assets import (
    _create_placeholder_impacts,
    bea_mapped_sbir_awards,
    bea_mapping_quality_check,
    economic_impacts,
    economic_impacts_quality_check,
    economic_shocks,
    economic_shocks_quality_check,
    federal_tax_estimates,
    fiscal_naics_coverage_check,
    fiscal_naics_enriched_awards,
    fiscal_naics_quality_check,
    fiscal_prepared_sbir_awards,
    fiscal_return_summary,
    fiscal_returns_report,
    inflation_adjusted_awards,
    inflation_adjustment_quality_check,
    sensitivity_scenarios,
    tax_base_components,
    uncertainty_analysis,
)


# ==================== Fixtures ====================


@pytest.fixture
def mock_context():
    """Mock Dagster execution context."""
    context = Mock(spec=AssetExecutionContext)
    context.log = Mock()
    context.log.info = Mock()
    context.log.warning = Mock()
    context.log.error = Mock()
    return context


@pytest.fixture
def mock_config():
    """Mock configuration."""
    config = Mock()
    config.fiscal_analysis.quality_thresholds = {
        "naics_coverage_rate": 0.85,
        "bea_sector_mapping_rate": 0.90,
        "geographic_resolution_rate": 0.90,
    }
    config.fiscal_analysis.quality_thresholds.get = lambda key, default: {
        "naics_coverage_rate": 0.85,
        "bea_sector_mapping_rate": 0.90,
        "geographic_resolution_rate": 0.90,
    }.get(key, default)
    config.fiscal_analysis.performance = {"chunk_size": 10000}
    config.fiscal_analysis.performance.get = lambda key, default: {
        "chunk_size": 10000,
    }.get(key, default)

    # Add naics_confidence_threshold attribute
    config.fiscal_analysis.quality_thresholds.naics_confidence_threshold = 0.60

    return config


@pytest.fixture
def sample_enriched_awards():
    """Sample enriched SBIR awards."""
    return pd.DataFrame({
        "Award Number": ["AWD001", "AWD002", "AWD003"],
        "Company": ["TechCo", "BioCo", "AeroCo"],
        "Amount": [100000, 150000, 200000],
        "State": ["CA", "MA", "TX"],
        "fiscal_year": [2021, 2022, 2023],
    })


@pytest.fixture
def sample_naics_enriched_awards():
    """Sample NAICS-enriched awards."""
    return pd.DataFrame({
        "Award Number": ["AWD001", "AWD002", "AWD003"],
        "Company": ["TechCo", "BioCo", "AeroCo"],
        "Amount": [100000, 150000, 200000],
        "fiscal_naics_code": ["541511", "541712", None],
        "fiscal_naics_source": ["original_data", "usaspending_dataframe", "missing"],
        "fiscal_naics_confidence": [0.95, 0.85, None],
        "fiscal_year": [2021, 2022, 2023],
        "state_code": ["CA", "MA", "TX"],
    })


@pytest.fixture
def sample_bea_mapped_awards():
    """Sample BEA-mapped awards."""
    return pd.DataFrame({
        "Award Number": ["AWD001", "AWD002", "AWD003"],
        "fiscal_naics_code": ["541511", "541712", "336411"],
        "bea_sector_code": ["5415", "5417", "3364"],
        "bea_mapping_confidence": [0.90, 0.85, 0.95],
        "Amount": [100000, 150000, 200000],
        "fiscal_year": [2021, 2022, 2023],
        "state_code": ["CA", "MA", "TX"],
    })


@pytest.fixture
def sample_economic_shocks():
    """Sample economic shocks."""
    return pd.DataFrame({
        "state": ["CA", "MA", "TX"],
        "bea_sector": ["5415", "5417", "3364"],
        "fiscal_year": [2021, 2022, 2023],
        "shock_amount": [100000, 150000, 200000],
        "awards_aggregated": [1, 1, 1],
        "confidence": [0.90, 0.85, 0.95],
        "naics_coverage_rate": [1.0, 1.0, 1.0],
        "geographic_resolution_rate": [1.0, 1.0, 1.0],
    })


@pytest.fixture
def sample_economic_impacts():
    """Sample economic impacts."""
    return pd.DataFrame({
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
    })


# ==================== NAICS Enrichment Tests ====================


class TestFiscalNAICSEnrichment:
    """Tests for NAICS enrichment asset."""

    @patch("src.assets.fiscal_assets.get_config")
    @patch("src.assets.fiscal_assets.enrich_sbir_awards_with_fiscal_naics")
    @patch("src.assets.fiscal_assets.performance_monitor")
    def test_fiscal_naics_enriched_awards_success(
        self,
        mock_perf_monitor,
        mock_enrich_func,
        mock_get_config,
        mock_context,
        mock_config,
        sample_enriched_awards,
        sample_naics_enriched_awards,
    ):
        """Test successful NAICS enrichment."""
        mock_get_config.return_value = mock_config
        mock_perf_monitor.monitor_block.return_value.__enter__ = Mock()
        mock_perf_monitor.monitor_block.return_value.__exit__ = Mock()
        mock_perf_monitor.get_metrics_summary.return_value = {
            "fiscal_naics_enrichment": {
                "total_duration": 10.5,
                "max_peak_memory_mb": 512.0,
            }
        }

        quality_metrics = {
            "naics_coverage_threshold": 0.85,
            "coverage_meets_threshold": True,
        }
        mock_enrich_func.return_value = (sample_naics_enriched_awards, quality_metrics)

        result = fiscal_naics_enriched_awards(mock_context, sample_enriched_awards)

        assert isinstance(result, Output)
        assert len(result.value) == 3
        assert "num_records" in result.metadata
        assert "naics_coverage" in result.metadata
        assert "confidence_stats" in result.metadata
        mock_context.log.info.assert_called()

    @patch("src.assets.fiscal_assets.get_config")
    def test_fiscal_naics_coverage_check_passes(
        self, mock_get_config, mock_config, sample_naics_enriched_awards
    ):
        """Test NAICS coverage check passes with sufficient coverage."""
        mock_get_config.return_value = mock_config

        result = fiscal_naics_coverage_check(sample_naics_enriched_awards)

        assert result.passed is True
        assert result.severity == AssetCheckSeverity.WARN
        assert "PASSED" in result.description
        assert "actual_coverage_rate" in result.metadata

    @patch("src.assets.fiscal_assets.get_config")
    def test_fiscal_naics_coverage_check_fails(self, mock_get_config, mock_config):
        """Test NAICS coverage check fails with low coverage."""
        mock_get_config.return_value = mock_config

        # Create DataFrame with low NAICS coverage
        low_coverage_df = pd.DataFrame({
            "fiscal_naics_code": [None, None, "541511", None, None],
            "fiscal_naics_source": ["missing"] * 5,
        })

        result = fiscal_naics_coverage_check(low_coverage_df)

        assert result.passed is False
        assert result.severity == AssetCheckSeverity.ERROR
        assert "FAILED" in result.description

    @patch("src.assets.fiscal_assets.get_config")
    def test_fiscal_naics_quality_check_passes(
        self, mock_get_config, mock_config, sample_naics_enriched_awards
    ):
        """Test NAICS quality check passes with good confidence scores."""
        mock_get_config.return_value = mock_config

        result = fiscal_naics_quality_check(sample_naics_enriched_awards)

        assert result.passed is True
        assert result.severity == AssetCheckSeverity.WARN
        assert "PASSED" in result.description
        assert "avg_confidence" in result.metadata

    @patch("src.assets.fiscal_assets.get_config")
    def test_fiscal_naics_quality_check_fails(self, mock_get_config, mock_config):
        """Test NAICS quality check fails with low confidence."""
        mock_get_config.return_value = mock_config

        # Create DataFrame with low confidence scores
        low_quality_df = pd.DataFrame({
            "fiscal_naics_code": ["541511", "541512"],
            "fiscal_naics_confidence": [0.30, 0.40],  # Below 0.60 threshold
            "fiscal_naics_source": ["fallback"] * 2,
        })

        result = fiscal_naics_quality_check(low_quality_df)

        assert result.passed is False
        assert result.severity == AssetCheckSeverity.ERROR
        assert "FAILED" in result.description


# ==================== BEA Mapping Tests ====================


class TestBEAMapping:
    """Tests for BEA sector mapping asset."""

    @patch("src.assets.fiscal_assets.get_config")
    @patch("src.assets.fiscal_assets.enrich_awards_with_bea_sectors")
    @patch("src.assets.fiscal_assets.NAICSToBEAMapper")
    @patch("src.assets.fiscal_assets.performance_monitor")
    def test_bea_mapped_sbir_awards_success(
        self,
        mock_perf_monitor,
        mock_mapper_class,
        mock_enrich_func,
        mock_get_config,
        mock_context,
        mock_config,
        sample_naics_enriched_awards,
        sample_bea_mapped_awards,
    ):
        """Test successful BEA sector mapping."""
        mock_get_config.return_value = mock_config
        mock_perf_monitor.monitor_block.return_value.__enter__ = Mock()
        mock_perf_monitor.monitor_block.return_value.__exit__ = Mock()

        mapping_stats = Mock()
        mapping_stats.coverage_rate = 0.95
        mapping_stats.avg_confidence = 0.88
        mock_enrich_func.return_value = (sample_bea_mapped_awards, mapping_stats)

        result = bea_mapped_sbir_awards(mock_context, sample_naics_enriched_awards)

        assert isinstance(result, Output)
        assert len(result.value) == 3
        assert "mapping_coverage_rate" in result.metadata
        assert "avg_confidence" in result.metadata
        mock_context.log.info.assert_called()

    @patch("src.assets.fiscal_assets.get_config")
    def test_bea_mapping_quality_check_passes(
        self, mock_get_config, mock_config, sample_bea_mapped_awards
    ):
        """Test BEA mapping quality check passes."""
        mock_get_config.return_value = mock_config

        result = bea_mapping_quality_check(sample_bea_mapped_awards)

        assert result.passed is True
        assert result.severity == AssetCheckSeverity.WARN
        assert "PASSED" in result.description

    @patch("src.assets.fiscal_assets.get_config")
    def test_bea_mapping_quality_check_fails_low_coverage(
        self, mock_get_config, mock_config
    ):
        """Test BEA mapping quality check fails with low coverage."""
        mock_get_config.return_value = mock_config

        low_coverage_df = pd.DataFrame({
            "bea_sector_code": [None, None, "5415", None],
            "bea_mapping_confidence": [None, None, 0.90, None],
        })

        result = bea_mapping_quality_check(low_coverage_df)

        assert result.passed is False
        assert result.severity == AssetCheckSeverity.ERROR
        assert "FAILED" in result.description


# ==================== Economic Shocks Tests ====================


class TestEconomicShocks:
    """Tests for economic shocks aggregation asset."""

    @patch("src.assets.fiscal_assets.get_config")
    @patch("src.assets.fiscal_assets.FiscalShockAggregator")
    @patch("src.assets.fiscal_assets.performance_monitor")
    def test_economic_shocks_success(
        self,
        mock_perf_monitor,
        mock_aggregator_class,
        mock_get_config,
        mock_context,
        mock_config,
        sample_bea_mapped_awards,
        sample_economic_shocks,
    ):
        """Test successful economic shock aggregation."""
        mock_get_config.return_value = mock_config
        mock_perf_monitor.monitor_block.return_value.__enter__ = Mock()
        mock_perf_monitor.monitor_block.return_value.__exit__ = Mock()

        mock_aggregator = Mock()
        mock_aggregator.aggregate_shocks_to_dataframe.return_value = sample_economic_shocks

        mock_stats = Mock()
        mock_stats.total_awards_aggregated = 3
        mock_stats.unique_states = 3
        mock_stats.unique_sectors = 3
        mock_stats.unique_fiscal_years = 3
        mock_stats.total_shock_amount = 450000.0
        mock_stats.avg_confidence = 0.90
        mock_stats.naics_coverage_rate = 0.95
        mock_stats.geographic_resolution_rate = 0.98
        mock_stats.awards_per_shock_avg = 1.0

        mock_aggregator.aggregate_shocks.return_value = []
        mock_aggregator.get_aggregation_statistics.return_value = mock_stats
        mock_aggregator_class.return_value = mock_aggregator

        result = economic_shocks(mock_context, sample_bea_mapped_awards)

        assert isinstance(result, Output)
        assert len(result.value) == 3
        assert "num_shocks" in result.metadata
        assert "total_shock_amount" in result.metadata

    @patch("src.assets.fiscal_assets.get_config")
    def test_economic_shocks_quality_check_passes(
        self, mock_get_config, mock_config, sample_economic_shocks
    ):
        """Test economic shocks quality check passes."""
        mock_get_config.return_value = mock_config

        result = economic_shocks_quality_check(sample_economic_shocks)

        assert result.passed is True
        assert result.severity == AssetCheckSeverity.WARN
        assert "PASSED" in result.description

    @patch("src.assets.fiscal_assets.get_config")
    def test_economic_shocks_quality_check_fails_empty(
        self, mock_get_config, mock_config
    ):
        """Test economic shocks quality check fails with empty DataFrame."""
        mock_get_config.return_value = mock_config

        empty_df = pd.DataFrame()

        result = economic_shocks_quality_check(empty_df)

        assert result.passed is False
        assert result.severity == AssetCheckSeverity.ERROR
        assert "FAILED" in result.description
        assert "No shocks generated" in result.description

    @patch("src.assets.fiscal_assets.get_config")
    def test_economic_shocks_quality_check_fails_low_quality(
        self, mock_get_config, mock_config
    ):
        """Test economic shocks quality check fails with low quality metrics."""
        mock_get_config.return_value = mock_config

        low_quality_df = pd.DataFrame({
            "shock_amount": [1000, 2000],
            "naics_coverage_rate": [0.40, 0.50],  # Low coverage
            "geographic_resolution_rate": [0.50, 0.60],  # Low coverage
            "confidence": [0.30, 0.40],  # Low confidence
        })

        result = economic_shocks_quality_check(low_quality_df)

        assert result.passed is False
        assert result.severity == AssetCheckSeverity.ERROR


# ==================== Economic Impacts Tests ====================


class TestEconomicImpacts:
    """Tests for economic impacts computation asset."""

    @patch("src.assets.fiscal_assets.get_config")
    @patch("src.assets.fiscal_assets.RStateIOAdapter")
    @patch("src.assets.fiscal_assets.performance_monitor")
    def test_economic_impacts_success(
        self,
        mock_perf_monitor,
        mock_adapter_class,
        mock_get_config,
        mock_context,
        mock_config,
        sample_economic_shocks,
        sample_economic_impacts,
    ):
        """Test successful economic impact computation."""
        mock_get_config.return_value = mock_config
        mock_perf_monitor.monitor_block.return_value.__enter__ = Mock()
        mock_perf_monitor.monitor_block.return_value.__exit__ = Mock()

        mock_adapter = Mock()
        mock_adapter.is_available.return_value = True
        mock_adapter.get_model_version.return_value = "stateior_1.0"

        impacts_df = sample_economic_impacts[
            ["state", "bea_sector", "fiscal_year", "wage_impact", "proprietor_income_impact",
             "gross_operating_surplus", "consumption_impact", "tax_impact", "production_impact"]
        ]
        mock_adapter.compute_impacts.return_value = impacts_df
        mock_adapter_class.return_value = mock_adapter

        result = economic_impacts(mock_context, sample_economic_shocks)

        assert isinstance(result, Output)
        assert len(result.value) == 3
        assert "wage_impact" in result.value.columns
        assert "model_version" in result.metadata

    @patch("src.assets.fiscal_assets.get_config")
    @patch("src.assets.fiscal_assets.RStateIOAdapter")
    def test_economic_impacts_r_adapter_unavailable(
        self,
        mock_adapter_class,
        mock_get_config,
        mock_context,
        mock_config,
        sample_economic_shocks,
    ):
        """Test economic impacts falls back to placeholder when R unavailable."""
        mock_get_config.return_value = mock_config

        mock_adapter = Mock()
        mock_adapter.is_available.return_value = False
        mock_adapter_class.return_value = mock_adapter

        result = economic_impacts(mock_context, sample_economic_shocks)

        assert isinstance(result, Output)
        assert "wage_impact" in result.value.columns
        assert (result.value["wage_impact"] == 0.0).all()
        assert "warning" in result.metadata

    @patch("src.assets.fiscal_assets.get_config")
    @patch("src.assets.fiscal_assets.RStateIOAdapter")
    def test_economic_impacts_import_error(
        self,
        mock_adapter_class,
        mock_get_config,
        mock_context,
        mock_config,
        sample_economic_shocks,
    ):
        """Test economic impacts handles ImportError gracefully."""
        mock_get_config.return_value = mock_config
        mock_adapter_class.side_effect = ImportError("rpy2 not installed")

        result = economic_impacts(mock_context, sample_economic_shocks)

        assert isinstance(result, Output)
        mock_context.log.warning.assert_called()

    def test_create_placeholder_impacts(self, mock_context, sample_economic_shocks):
        """Test _create_placeholder_impacts helper function."""
        result = _create_placeholder_impacts(sample_economic_shocks, mock_context)

        assert isinstance(result, Output)
        assert "wage_impact" in result.value.columns
        assert "tax_impact" in result.value.columns
        assert (result.value["wage_impact"] == 0.0).all()
        assert result.value["model_version"].iloc[0] == "placeholder"
        assert "warning" in result.metadata
        mock_context.log.warning.assert_called()

    @patch("src.assets.fiscal_assets.get_config")
    def test_economic_impacts_quality_check_passes(
        self, mock_get_config, mock_config, sample_economic_impacts
    ):
        """Test economic impacts quality check passes."""
        mock_get_config.return_value = mock_config

        result = economic_impacts_quality_check(sample_economic_impacts)

        assert result.passed is True
        assert "PASSED" in result.description

    @patch("src.assets.fiscal_assets.get_config")
    def test_economic_impacts_quality_check_fails_placeholder(
        self, mock_get_config, mock_config, sample_economic_shocks
    ):
        """Test economic impacts quality check fails with placeholder model."""
        mock_get_config.return_value = mock_config

        placeholder_df = sample_economic_shocks.copy()
        placeholder_df["wage_impact"] = 0.0
        placeholder_df["model_version"] = "placeholder"

        result = economic_impacts_quality_check(placeholder_df)

        assert result.passed is False
        assert "placeholder" in result.description.lower()


# ==================== Fiscal Preparation Tests ====================


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
        mock_perf_monitor.monitor_block.return_value.__enter__ = Mock()
        mock_perf_monitor.monitor_block.return_value.__exit__ = Mock()

        adjusted_df = sample_bea_mapped_awards.copy()
        adjusted_df["amount_nominal"] = adjusted_df["Amount"]
        adjusted_df["amount_real"] = adjusted_df["Amount"] * 1.1
        adjusted_df["inflation_factor"] = 1.1

        mock_adjust_func.return_value = adjusted_df

        result = inflation_adjusted_awards(mock_context, sample_bea_mapped_awards)

        assert isinstance(result, Output)
        assert "amount_real" in result.value.columns
        assert "inflation_factor" in result.value.columns

    @patch("src.assets.fiscal_assets.get_config")
    def test_inflation_adjustment_quality_check_passes(self, mock_get_config, mock_config):
        """Test inflation adjustment quality check passes."""
        mock_get_config.return_value = mock_config

        adjusted_df = pd.DataFrame({
            "amount_nominal": [100000, 150000, 200000],
            "amount_real": [110000, 165000, 220000],
            "inflation_factor": [1.1, 1.1, 1.1],
        })

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
        mock_perf_monitor.monitor_block.return_value.__enter__ = Mock()
        mock_perf_monitor.monitor_block.return_value.__exit__ = Mock()

        mock_estimator = Mock()

        tax_df = sample_economic_impacts.copy()
        tax_df["federal_individual_income_tax"] = 5000
        tax_df["federal_corporate_income_tax"] = 3000
        tax_df["federal_social_insurance_tax"] = 2000
        tax_df["total_federal_tax"] = 10000

        mock_estimator.estimate_taxes.return_value = tax_df
        mock_tax_estimator_class.return_value = mock_estimator

        result = federal_tax_estimates(mock_context, sample_economic_impacts)

        assert isinstance(result, Output)
        assert "total_federal_tax" in result.value.columns

    @patch("src.assets.fiscal_assets.get_config")
    @patch("src.assets.fiscal_assets.FiscalROICalculator")
    def test_fiscal_return_summary_success(
        self,
        mock_roi_calculator_class,
        mock_get_config,
        mock_context,
        mock_config,
    ):
        """Test successful fiscal return summary calculation."""
        mock_get_config.return_value = mock_config

        mock_calculator = Mock()

        summary_df = pd.DataFrame({
            "fiscal_year": [2021, 2022],
            "total_investment": [100000, 150000],
            "total_federal_tax_return": [50000, 75000],
            "roi_ratio": [0.50, 0.50],
            "breakeven_year": [2025, 2026],
        })

        mock_calculator.calculate_roi_summary.return_value = summary_df
        mock_roi_calculator_class.return_value = mock_calculator

        tax_df = pd.DataFrame({
            "fiscal_year": [2021, 2022],
            "total_federal_tax": [50000, 75000],
            "shock_amount": [100000, 150000],
        })

        result = fiscal_return_summary(mock_context, tax_df)

        assert isinstance(result, Output)
        assert "roi_ratio" in result.value.columns


# ==================== Sensitivity and Uncertainty Tests ====================


class TestSensitivityUncertainty:
    """Tests for sensitivity and uncertainty analysis assets."""

    @patch("src.assets.fiscal_assets.get_config")
    @patch("src.assets.fiscal_assets.FiscalParameterSweep")
    def test_sensitivity_scenarios_success(
        self,
        mock_sweep_class,
        mock_get_config,
        mock_context,
        mock_config,
        sample_economic_impacts,
    ):
        """Test successful sensitivity scenarios generation."""
        mock_get_config.return_value = mock_config

        mock_sweep = Mock()

        scenarios_df = pd.DataFrame({
            "scenario_id": ["base", "optimistic", "pessimistic"],
            "parameter": ["multiplier", "multiplier", "multiplier"],
            "value": [1.0, 1.2, 0.8],
            "total_impact": [100000, 120000, 80000],
        })

        mock_sweep.run_parameter_sweep.return_value = scenarios_df
        mock_sweep_class.return_value = mock_sweep

        result = sensitivity_scenarios(mock_context, sample_economic_impacts)

        assert isinstance(result, Output)
        assert len(result.value) == 3

    @patch("src.assets.fiscal_assets.get_config")
    @patch("src.assets.fiscal_assets.FiscalUncertaintyQuantifier")
    def test_uncertainty_analysis_success(
        self,
        mock_quantifier_class,
        mock_get_config,
        mock_context,
        mock_config,
        sample_economic_impacts,
    ):
        """Test successful uncertainty quantification."""
        mock_get_config.return_value = mock_config

        mock_quantifier = Mock()

        uncertainty_df = pd.DataFrame({
            "metric": ["roi_ratio", "tax_return"],
            "mean": [0.50, 50000],
            "std": [0.05, 5000],
            "ci_lower": [0.45, 45000],
            "ci_upper": [0.55, 55000],
        })

        mock_quantifier.quantify_uncertainty.return_value = uncertainty_df
        mock_quantifier_class.return_value = mock_quantifier

        result = uncertainty_analysis(mock_context, sample_economic_impacts)

        assert isinstance(result, Output)
        assert "mean" in result.value.columns
        assert "ci_lower" in result.value.columns


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
        mock_perf_monitor.monitor_block.return_value.__enter__ = Mock()
        mock_perf_monitor.monitor_block.return_value.__exit__ = Mock()

        roi_summary = pd.DataFrame({
            "fiscal_year": [2021, 2022],
            "roi_ratio": [0.50, 0.55],
        })

        sensitivity = pd.DataFrame({
            "scenario_id": ["base", "optimistic"],
            "total_impact": [100000, 120000],
        })

        uncertainty = pd.DataFrame({
            "metric": ["roi_ratio"],
            "mean": [0.50],
            "ci_lower": [0.45],
            "ci_upper": [0.55],
        })

        with patch("builtins.open", create=True):
            with patch("pathlib.Path.mkdir"):
                result = fiscal_returns_report(
                    mock_context, roi_summary, sensitivity, uncertainty
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

    def test_create_placeholder_impacts_all_columns(
        self, mock_context, sample_economic_shocks
    ):
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
        mock_perf_monitor.monitor_block.return_value.__enter__ = Mock()
        mock_perf_monitor.monitor_block.return_value.__exit__ = Mock()
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
