"""Tests for fiscal sensitivity analysis."""

from decimal import Decimal
from unittest.mock import Mock, patch

import numpy as np
import pandas as pd
import pytest

from src.transformers.fiscal.sensitivity import (
    FiscalParameterSweep,
    FiscalUncertaintyQuantifier,
    ParameterRange,
    ParameterScenario,
    UncertaintyResult,
)


pytestmark = pytest.mark.fast



class TestParameterRange:
    """Tests for ParameterRange dataclass."""

    def test_parameter_range_default_distribution(self):
        """Test ParameterRange with default uniform distribution."""
        pr = ParameterRange(name="tax_rate", min_value=0.1, max_value=0.3)

        assert pr.name == "tax_rate"
        assert pr.min_value == 0.1
        assert pr.max_value == 0.3
        assert pr.distribution == "uniform"

    def test_parameter_range_custom_distribution(self):
        """Test ParameterRange with custom distribution."""
        pr = ParameterRange(
            name="multiplier",
            min_value=1.5,
            max_value=2.5,
            distribution="normal",
        )

        assert pr.distribution == "normal"

    def test_parameter_range_lognormal(self):
        """Test ParameterRange with lognormal distribution."""
        pr = ParameterRange(
            name="volatility",
            min_value=0.01,
            max_value=0.1,
            distribution="lognormal",
        )

        assert pr.distribution == "lognormal"


class TestParameterScenario:
    """Tests for ParameterScenario dataclass."""

    def test_parameter_scenario_basic(self):
        """Test ParameterScenario initialization."""
        scenario = ParameterScenario(
            scenario_id=1,
            parameters={"tax_rate": 0.22, "multiplier": 2.0},
            metadata={"method": "monte_carlo"},
        )

        assert scenario.scenario_id == 1
        assert scenario.parameters["tax_rate"] == 0.22
        assert scenario.parameters["multiplier"] == 2.0
        assert scenario.metadata["method"] == "monte_carlo"

    def test_parameter_scenario_empty_parameters(self):
        """Test ParameterScenario with empty parameters."""
        scenario = ParameterScenario(
            scenario_id=1,
            parameters={},
            metadata={},
        )

        assert scenario.parameters == {}
        assert scenario.metadata == {}


class TestFiscalParameterSweepInitialization:
    """Tests for FiscalParameterSweep initialization."""

    @patch("src.transformers.fiscal.sensitivity.get_config")
    def test_initialization_with_config(self, mock_get_config):
        """Test FiscalParameterSweep initialization with config."""
        from tests.utils.config_mocks import create_mock_pipeline_config

        mock_config = create_mock_pipeline_config()
        # Ensure fiscal_analysis.sensitivity_parameters exists
        if hasattr(mock_config, "fiscal_analysis"):
            if not hasattr(mock_config.fiscal_analysis, "sensitivity_parameters"):
                mock_config.fiscal_analysis.sensitivity_parameters = {}
        mock_get_config.return_value = mock_config

        sweep = FiscalParameterSweep()

        assert sweep.config is not None

    def test_initialization_with_custom_config(self):
        """Test FiscalParameterSweep initialization with custom config."""
        custom_config = Mock()
        custom_config.sensitivity_parameters = {}

        sweep = FiscalParameterSweep(config=custom_config)

        assert sweep.config == custom_config


class TestGenerateMonteCarloScenarios:
    """Tests for generate_monte_carlo_scenarios method."""

    @patch("src.transformers.fiscal.sensitivity.get_config")
    def test_generate_monte_carlo_basic(self, mock_get_config):
        """Test Monte Carlo scenario generation."""
        mock_config = Mock()
        mock_config.fiscal_analysis.sensitivity_parameters = Mock(uncertainty_parameters={})
        mock_get_config.return_value = mock_config

        sweep = FiscalParameterSweep()

        scenarios = sweep.generate_monte_carlo_scenarios(num_scenarios=10, random_seed=42)

        assert len(scenarios) == 10
        assert all(isinstance(s, ParameterScenario) for s in scenarios)
        assert all(s.metadata["method"] == "monte_carlo" for s in scenarios)

    @patch("src.transformers.fiscal.sensitivity.get_config")
    def test_generate_monte_carlo_reproducible(self, mock_get_config):
        """Test Monte Carlo scenarios are reproducible with seed."""
        mock_config = Mock()
        mock_config.fiscal_analysis.sensitivity_parameters = Mock(uncertainty_parameters={})
        mock_get_config.return_value = mock_config

        sweep = FiscalParameterSweep()

        scenarios1 = sweep.generate_monte_carlo_scenarios(num_scenarios=5, random_seed=42)
        scenarios2 = sweep.generate_monte_carlo_scenarios(num_scenarios=5, random_seed=42)

        # Same parameters with same seed
        for s1, s2 in zip(scenarios1, scenarios2, strict=False):
            assert s1.parameters == s2.parameters

    @patch("src.transformers.fiscal.sensitivity.get_config")
    def test_generate_monte_carlo_different_seeds(self, mock_get_config):
        """Test Monte Carlo scenarios differ with different seeds."""
        mock_config = Mock()
        mock_config.fiscal_analysis.sensitivity_parameters = Mock(uncertainty_parameters={})
        mock_get_config.return_value = mock_config

        sweep = FiscalParameterSweep()

        scenarios1 = sweep.generate_monte_carlo_scenarios(num_scenarios=5, random_seed=42)
        scenarios2 = sweep.generate_monte_carlo_scenarios(num_scenarios=5, random_seed=99)

        # Different parameters with different seeds (high probability)
        differences = sum(
            s1.parameters != s2.parameters for s1, s2 in zip(scenarios1, scenarios2, strict=False)
        )
        assert differences > 0

    @patch("src.transformers.fiscal.sensitivity.get_config")
    def test_generate_monte_carlo_single_scenario(self, mock_get_config):
        """Test Monte Carlo with single scenario."""
        mock_config = Mock()
        mock_config.fiscal_analysis.sensitivity_parameters = Mock(uncertainty_parameters={})
        mock_get_config.return_value = mock_config

        sweep = FiscalParameterSweep()

        scenarios = sweep.generate_monte_carlo_scenarios(num_scenarios=1, random_seed=42)

        assert len(scenarios) == 1


class TestGenerateLatinHypercubeScenarios:
    """Tests for generate_latin_hypercube_scenarios method."""

    @patch("src.transformers.fiscal.sensitivity.get_config")
    def test_generate_lhs_basic(self, mock_get_config):
        """Test Latin Hypercube Sampling scenario generation."""
        mock_config = Mock()
        mock_config.fiscal_analysis.sensitivity_parameters = Mock(uncertainty_parameters={})
        mock_get_config.return_value = mock_config

        sweep = FiscalParameterSweep()

        scenarios = sweep.generate_latin_hypercube_scenarios(num_scenarios=10, random_seed=42)

        assert len(scenarios) == 10
        assert all(isinstance(s, ParameterScenario) for s in scenarios)
        assert all(s.metadata["method"] == "latin_hypercube" for s in scenarios)

    @patch("src.transformers.fiscal.sensitivity.get_config")
    def test_generate_lhs_reproducible(self, mock_get_config):
        """Test LHS scenarios are reproducible with seed."""
        mock_config = Mock()
        mock_config.fiscal_analysis.sensitivity_parameters = Mock(uncertainty_parameters={})
        mock_get_config.return_value = mock_config

        sweep = FiscalParameterSweep()

        scenarios1 = sweep.generate_latin_hypercube_scenarios(num_scenarios=5, random_seed=42)
        scenarios2 = sweep.generate_latin_hypercube_scenarios(num_scenarios=5, random_seed=42)

        # Should be reproducible
        for s1, s2 in zip(scenarios1, scenarios2, strict=False):
            for key in s1.parameters:
                assert abs(s1.parameters[key] - s2.parameters[key]) < 1e-10


class TestGenerateGridSearchScenarios:
    """Tests for generate_grid_search_scenarios method."""

    @patch("src.transformers.fiscal.sensitivity.get_config")
    def test_generate_grid_search_basic(self, mock_get_config):
        """Test grid search scenario generation."""
        mock_config = Mock()
        mock_config.fiscal_analysis.sensitivity_parameters = Mock(uncertainty_parameters={})
        mock_get_config.return_value = mock_config

        sweep = FiscalParameterSweep()

        scenarios = sweep.generate_grid_search_scenarios(points_per_dimension=3)

        # With default parameters (4 params), should have 3^4 = 81 scenarios
        assert len(scenarios) > 0
        assert all(isinstance(s, ParameterScenario) for s in scenarios)
        assert all(s.metadata["method"] == "grid_search" for s in scenarios)

    @patch("src.transformers.fiscal.sensitivity.get_config")
    def test_generate_grid_search_single_point(self, mock_get_config):
        """Test grid search with single point per dimension."""
        mock_config = Mock()
        mock_config.fiscal_analysis.sensitivity_parameters = Mock(uncertainty_parameters={})
        mock_get_config.return_value = mock_config

        sweep = FiscalParameterSweep()

        scenarios = sweep.generate_grid_search_scenarios(points_per_dimension=1)

        # With 1 point per dimension, should have 1 scenario
        assert len(scenarios) == 1


class TestUncertaintyResult:
    """Tests for UncertaintyResult dataclass."""

    def test_uncertainty_result_basic(self):
        """Test UncertaintyResult initialization."""
        result = UncertaintyResult(
            min_estimate=Decimal("1000.00"),
            mean_estimate=Decimal("1500.00"),
            max_estimate=Decimal("2000.00"),
            confidence_intervals={
                0.90: (Decimal("1100.00"), Decimal("1900.00")),
                0.95: (Decimal("1050.00"), Decimal("1950.00")),
            },
            sensitivity_indices={"tax_rate": 0.8, "multiplier": 0.6},
            quality_flags=["moderate_uncertainty"],
        )

        assert result.min_estimate == Decimal("1000.00")
        assert result.mean_estimate == Decimal("1500.00")
        assert result.max_estimate == Decimal("2000.00")
        assert len(result.confidence_intervals) == 2
        assert result.sensitivity_indices["tax_rate"] == 0.8
        assert "moderate_uncertainty" in result.quality_flags

    def test_uncertainty_result_empty(self):
        """Test UncertaintyResult with empty collections."""
        result = UncertaintyResult(
            min_estimate=Decimal("0"),
            mean_estimate=Decimal("0"),
            max_estimate=Decimal("0"),
            confidence_intervals={},
            sensitivity_indices={},
            quality_flags=[],
        )

        assert result.confidence_intervals == {}
        assert result.sensitivity_indices == {}
        assert result.quality_flags == []


class TestComputePercentileConfidenceIntervals:
    """Tests for compute_percentile_confidence_intervals method."""

    @patch("src.transformers.fiscal.sensitivity.get_config")
    def test_compute_percentile_ci_basic(self, mock_get_config):
        """Test percentile confidence interval computation."""
        mock_config = Mock()
        mock_config.fiscal_analysis.sensitivity_parameters = Mock(
            confidence_intervals=Mock(levels=[0.90, 0.95])
        )
        mock_get_config.return_value = mock_config

        quantifier = FiscalUncertaintyQuantifier()

        estimates = pd.Series(range(100))  # 0 to 99
        intervals = quantifier.compute_percentile_confidence_intervals(estimates)

        assert 0.90 in intervals
        assert 0.95 in intervals
        # Check intervals are tuples of Decimals
        assert isinstance(intervals[0.90][0], Decimal)
        assert isinstance(intervals[0.90][1], Decimal)

    @patch("src.transformers.fiscal.sensitivity.get_config")
    def test_compute_percentile_ci_empty_series(self, mock_get_config):
        """Test percentile CI with empty series."""
        mock_config = Mock()
        mock_config.fiscal_analysis.sensitivity_parameters = Mock(
            confidence_intervals=Mock(levels=[0.90])
        )
        mock_get_config.return_value = mock_config

        quantifier = FiscalUncertaintyQuantifier()

        estimates = pd.Series([])
        intervals = quantifier.compute_percentile_confidence_intervals(estimates)

        # Should return zero intervals
        assert intervals[0.90] == (Decimal("0"), Decimal("0"))

    @patch("src.transformers.fiscal.sensitivity.get_config")
    def test_compute_percentile_ci_custom_levels(self, mock_get_config):
        """Test percentile CI with custom confidence levels."""
        mock_config = Mock()
        mock_config.fiscal_analysis.sensitivity_parameters = {}
        mock_get_config.return_value = mock_config

        quantifier = FiscalUncertaintyQuantifier()

        estimates = pd.Series(range(100))
        intervals = quantifier.compute_percentile_confidence_intervals(
            estimates, confidence_levels=[0.80, 0.99]
        )

        assert 0.80 in intervals
        assert 0.99 in intervals


class TestComputeBootstrapConfidenceIntervals:
    """Tests for compute_bootstrap_confidence_intervals method."""

    @patch("src.transformers.fiscal.sensitivity.get_config")
    def test_compute_bootstrap_ci_basic(self, mock_get_config):
        """Test bootstrap confidence interval computation."""
        mock_config = Mock()
        mock_config.fiscal_analysis.sensitivity_parameters = Mock(
            confidence_intervals=Mock(levels=[0.90])
        )
        mock_get_config.return_value = mock_config

        quantifier = FiscalUncertaintyQuantifier()

        estimates = pd.Series(range(100))
        intervals = quantifier.compute_bootstrap_confidence_intervals(
            estimates, num_samples=100, random_seed=42
        )

        assert 0.90 in intervals
        assert isinstance(intervals[0.90][0], Decimal)

    @patch("src.transformers.fiscal.sensitivity.get_config")
    def test_compute_bootstrap_ci_reproducible(self, mock_get_config):
        """Test bootstrap CI is reproducible with seed."""
        mock_config = Mock()
        mock_config.fiscal_analysis.sensitivity_parameters = Mock(
            confidence_intervals=Mock(levels=[0.90])
        )
        mock_get_config.return_value = mock_config

        quantifier = FiscalUncertaintyQuantifier()

        estimates = pd.Series(range(100))

        intervals1 = quantifier.compute_bootstrap_confidence_intervals(
            estimates, num_samples=100, random_seed=42
        )
        intervals2 = quantifier.compute_bootstrap_confidence_intervals(
            estimates, num_samples=100, random_seed=42
        )

        assert intervals1[0.90] == intervals2[0.90]

    @patch("src.transformers.fiscal.sensitivity.get_config")
    def test_compute_bootstrap_ci_empty_series(self, mock_get_config):
        """Test bootstrap CI with empty series."""
        mock_config = Mock()
        mock_config.fiscal_analysis.sensitivity_parameters = Mock(
            confidence_intervals=Mock(levels=[0.90])
        )
        mock_get_config.return_value = mock_config

        quantifier = FiscalUncertaintyQuantifier()

        estimates = pd.Series([])
        intervals = quantifier.compute_bootstrap_confidence_intervals(estimates)

        assert intervals[0.90] == (Decimal("0"), Decimal("0"))


class TestComputeSensitivityIndices:
    """Tests for compute_sensitivity_indices method."""

    @patch("src.transformers.fiscal.sensitivity.get_config")
    def test_compute_sensitivity_indices_basic(self, mock_get_config):
        """Test sensitivity indices computation."""
        mock_config = Mock()
        mock_config.fiscal_analysis.sensitivity_parameters = {}
        mock_get_config.return_value = mock_config

        quantifier = FiscalUncertaintyQuantifier()

        # Create correlated data
        df = pd.DataFrame(
            {
                "tax_rate": np.linspace(0.1, 0.3, 100),
                "multiplier": np.linspace(1.5, 2.5, 100),
                "total_tax_receipt": np.linspace(1000, 2000, 100),  # Positive correlation
            }
        )

        indices = quantifier.compute_sensitivity_indices(df)

        assert "tax_rate" in indices
        assert "multiplier" in indices
        # Both should have positive sensitivity
        assert indices["tax_rate"] > 0
        assert indices["multiplier"] > 0

    @patch("src.transformers.fiscal.sensitivity.get_config")
    def test_compute_sensitivity_indices_empty_df(self, mock_get_config):
        """Test sensitivity indices with empty DataFrame."""
        mock_config = Mock()
        mock_config.fiscal_analysis.sensitivity_parameters = {}
        mock_get_config.return_value = mock_config

        quantifier = FiscalUncertaintyQuantifier()

        df = pd.DataFrame()
        indices = quantifier.compute_sensitivity_indices(df)

        assert indices == {}

    @patch("src.transformers.fiscal.sensitivity.get_config")
    def test_compute_sensitivity_indices_missing_target(self, mock_get_config):
        """Test sensitivity indices with missing target column."""
        mock_config = Mock()
        mock_config.fiscal_analysis.sensitivity_parameters = {}
        mock_get_config.return_value = mock_config

        quantifier = FiscalUncertaintyQuantifier()

        df = pd.DataFrame(
            {
                "tax_rate": [0.1, 0.2, 0.3],
                "multiplier": [1.5, 2.0, 2.5],
            }
        )

        indices = quantifier.compute_sensitivity_indices(df, target_column="missing")

        assert indices == {}

    @patch("src.transformers.fiscal.sensitivity.get_config")
    def test_compute_sensitivity_indices_sorted(self, mock_get_config):
        """Test sensitivity indices are sorted by magnitude."""
        mock_config = Mock()
        mock_config.fiscal_analysis.sensitivity_parameters = {}
        mock_get_config.return_value = mock_config

        quantifier = FiscalUncertaintyQuantifier()

        df = pd.DataFrame(
            {
                "param_a": np.random.randn(100),
                "param_b": np.linspace(0, 10, 100),
                "total_tax_receipt": np.linspace(0, 10, 100),  # Highly correlated with param_b
            }
        )

        indices = quantifier.compute_sensitivity_indices(df)

        # Should be sorted (highest sensitivity first)
        indices_list = list(indices.items())
        for i in range(len(indices_list) - 1):
            assert indices_list[i][1] >= indices_list[i + 1][1]


class TestQuantifyUncertainty:
    """Tests for quantify_uncertainty method."""

    @patch("src.transformers.fiscal.sensitivity.get_config")
    def test_quantify_uncertainty_basic(self, mock_get_config):
        """Test uncertainty quantification."""
        mock_config = Mock()
        mock_config.fiscal_analysis.sensitivity_parameters = Mock(
            confidence_intervals=Mock(method="percentile", levels=[0.90])
        )
        mock_get_config.return_value = mock_config

        quantifier = FiscalUncertaintyQuantifier()

        df = pd.DataFrame(
            {
                "tax_rate": np.linspace(0.1, 0.3, 100),
                "total_tax_receipt": np.linspace(1000, 2000, 100),
            }
        )

        result = quantifier.quantify_uncertainty(df)

        assert isinstance(result, UncertaintyResult)
        assert result.min_estimate == Decimal("1000.0")
        assert result.max_estimate == Decimal("2000.0")
        assert 0.90 in result.confidence_intervals

    @patch("src.transformers.fiscal.sensitivity.get_config")
    def test_quantify_uncertainty_empty_df(self, mock_get_config):
        """Test uncertainty quantification with empty DataFrame."""
        mock_config = Mock()
        mock_config.fiscal_analysis.sensitivity_parameters = {}
        mock_get_config.return_value = mock_config

        quantifier = FiscalUncertaintyQuantifier()

        result = quantifier.quantify_uncertainty(pd.DataFrame())

        assert result.min_estimate == Decimal("0")
        assert result.mean_estimate == Decimal("0")
        assert result.max_estimate == Decimal("0")
        assert "empty_dataframe" in result.quality_flags

    @patch("src.transformers.fiscal.sensitivity.get_config")
    def test_quantify_uncertainty_missing_column(self, mock_get_config):
        """Test uncertainty quantification with missing target column."""
        mock_config = Mock()
        mock_config.fiscal_analysis.sensitivity_parameters = {}
        mock_get_config.return_value = mock_config

        quantifier = FiscalUncertaintyQuantifier()

        df = pd.DataFrame({"tax_rate": [0.1, 0.2, 0.3]})

        result = quantifier.quantify_uncertainty(df, target_column="missing")

        assert "missing_target_column" in result.quality_flags

    @patch("src.transformers.fiscal.sensitivity.get_config")
    def test_quantify_uncertainty_high_cv(self, mock_get_config):
        """Test uncertainty quantification flags high coefficient of variation."""
        mock_config = Mock()
        mock_config.fiscal_analysis.sensitivity_parameters = Mock(
            confidence_intervals=Mock(method="percentile", levels=[0.90])
        )
        mock_get_config.return_value = mock_config

        quantifier = FiscalUncertaintyQuantifier()

        # Create data with high variance
        df = pd.DataFrame(
            {
                "total_tax_receipt": [100, 200, 300, 400, 1000, 2000, 3000],
            }
        )

        result = quantifier.quantify_uncertainty(df)

        assert (
            "high_uncertainty" in result.quality_flags
            or "moderate_uncertainty" in result.quality_flags
        )

    @patch("src.transformers.fiscal.sensitivity.get_config")
    def test_quantify_uncertainty_bootstrap_method(self, mock_get_config):
        """Test uncertainty quantification with bootstrap method."""
        mock_config = Mock()
        mock_config.fiscal_analysis.sensitivity_parameters = Mock(
            confidence_intervals=Mock(method="bootstrap", levels=[0.90], bootstrap_samples=100)
        )
        mock_get_config.return_value = mock_config

        quantifier = FiscalUncertaintyQuantifier()

        df = pd.DataFrame(
            {
                "total_tax_receipt": np.linspace(1000, 2000, 100),
            }
        )

        result = quantifier.quantify_uncertainty(df)

        assert 0.90 in result.confidence_intervals


class TestFlagHighUncertainty:
    """Tests for flag_high_uncertainty method."""

    @patch("src.transformers.fiscal.sensitivity.get_config")
    def test_flag_high_uncertainty_true(self, mock_get_config):
        """Test flagging high uncertainty returns True."""
        mock_config = Mock()
        mock_config.fiscal_analysis.sensitivity_parameters = {}
        mock_get_config.return_value = mock_config

        quantifier = FiscalUncertaintyQuantifier()

        result = UncertaintyResult(
            min_estimate=Decimal("1000"),
            mean_estimate=Decimal("1500"),
            max_estimate=Decimal("2000"),
            confidence_intervals={},
            sensitivity_indices={},
            quality_flags=["high_uncertainty"],
        )

        assert quantifier.flag_high_uncertainty(result) is True

    @patch("src.transformers.fiscal.sensitivity.get_config")
    def test_flag_high_uncertainty_false(self, mock_get_config):
        """Test flagging low uncertainty returns False."""
        mock_config = Mock()
        mock_config.fiscal_analysis.sensitivity_parameters = {}
        mock_get_config.return_value = mock_config

        quantifier = FiscalUncertaintyQuantifier()

        result = UncertaintyResult(
            min_estimate=Decimal("1450"),
            mean_estimate=Decimal("1500"),
            max_estimate=Decimal("1550"),
            confidence_intervals={},
            sensitivity_indices={},
            quality_flags=[],
        )

        assert quantifier.flag_high_uncertainty(result) is False

    @patch("src.transformers.fiscal.sensitivity.get_config")
    def test_flag_high_uncertainty_estimated_cv(self, mock_get_config):
        """Test flagging based on estimated CV from range."""
        mock_config = Mock()
        mock_config.fiscal_analysis.sensitivity_parameters = {}
        mock_get_config.return_value = mock_config

        quantifier = FiscalUncertaintyQuantifier()

        # Large range relative to mean
        result = UncertaintyResult(
            min_estimate=Decimal("500"),
            mean_estimate=Decimal("1000"),
            max_estimate=Decimal("3000"),
            confidence_intervals={},
            sensitivity_indices={},
            quality_flags=[],
        )

        # Range = 2500, Mean = 1000, estimated CV ≈ 2500 / (4 * 1000) = 0.625 > 0.5
        assert quantifier.flag_high_uncertainty(result, threshold_cv=0.5) is True


class TestEdgeCases:
    """Tests for edge cases in sensitivity analysis."""

    @patch("src.transformers.fiscal.sensitivity.get_config")
    def test_zero_scenarios(self, mock_get_config):
        """Test handling zero scenarios requested."""
        mock_config = Mock()
        mock_config.fiscal_analysis.sensitivity_parameters = Mock(uncertainty_parameters={})
        mock_get_config.return_value = mock_config

        sweep = FiscalParameterSweep()

        scenarios = sweep.generate_monte_carlo_scenarios(num_scenarios=0)

        assert len(scenarios) == 0

    @patch("src.transformers.fiscal.sensitivity.get_config")
    def test_negative_values_in_estimates(self, mock_get_config):
        """Test handling negative values in estimates."""
        mock_config = Mock()
        mock_config.fiscal_analysis.sensitivity_parameters = Mock(
            confidence_intervals=Mock(method="percentile", levels=[0.90])
        )
        mock_get_config.return_value = mock_config

        quantifier = FiscalUncertaintyQuantifier()

        df = pd.DataFrame(
            {
                "total_tax_receipt": [-500, -100, 100, 500, 1000],
            }
        )

        result = quantifier.quantify_uncertainty(df)

        assert result.min_estimate == Decimal("-500.0")
        assert result.max_estimate == Decimal("1000.0")

    @patch("src.transformers.fiscal.sensitivity.get_config")
    def test_single_value_estimates(self, mock_get_config):
        """Test handling single unique value in estimates."""
        mock_config = Mock()
        mock_config.fiscal_analysis.sensitivity_parameters = Mock(
            confidence_intervals=Mock(method="percentile", levels=[0.90])
        )
        mock_get_config.return_value = mock_config

        quantifier = FiscalUncertaintyQuantifier()

        df = pd.DataFrame(
            {
                "total_tax_receipt": [1000, 1000, 1000, 1000],
            }
        )

        result = quantifier.quantify_uncertainty(df)

        assert result.min_estimate == result.max_estimate == Decimal("1000.0")
