"""Unit tests for fiscal uncertainty quantifier."""

from decimal import Decimal

import numpy as np
import pandas as pd
import pytest

pytestmark = pytest.mark.fast

from src.transformers.fiscal_uncertainty_quantifier import (
    FiscalUncertaintyQuantifier,
    UncertaintyResult,
)


@pytest.fixture
def sample_scenario_results_df():
    """Sample scenario results DataFrame for testing."""
    np.random.seed(42)
    return pd.DataFrame(
        {
            "scenario_id": range(1, 101),
            "individual_income_tax_rate": np.random.uniform(0.18, 0.26, 100),
            "corporate_income_tax_rate": np.random.uniform(0.15, 0.21, 100),
            "economic_multiplier": np.random.uniform(1.7, 2.3, 100),
            "discount_rate": np.random.uniform(0.01, 0.07, 100),
            "total_tax_receipt": np.random.uniform(100000, 200000, 100),
        }
    )


@pytest.fixture
def quantifier():
    """Create a FiscalUncertaintyQuantifier instance."""
    return FiscalUncertaintyQuantifier()


class TestFiscalUncertaintyQuantifier:
    """Test FiscalUncertaintyQuantifier class."""

    def test_compute_percentile_confidence_intervals(self, quantifier, sample_scenario_results_df):
        """Test percentile-based confidence interval computation."""
        estimates = sample_scenario_results_df["total_tax_receipt"]
        confidence_levels = [0.90, 0.95, 0.99]

        intervals = quantifier.compute_percentile_confidence_intervals(
            estimates, confidence_levels=confidence_levels
        )

        assert len(intervals) == 3
        for level in confidence_levels:
            assert level in intervals
            low, high = intervals[level]
            assert isinstance(low, Decimal)
            assert isinstance(high, Decimal)
            assert low <= high

    def test_compute_bootstrap_confidence_intervals(self, quantifier, sample_scenario_results_df):
        """Test bootstrap confidence interval computation."""
        estimates = sample_scenario_results_df["total_tax_receipt"]
        confidence_levels = [0.90, 0.95]

        intervals = quantifier.compute_bootstrap_confidence_intervals(
            estimates, confidence_levels=confidence_levels, num_samples=100, random_seed=42
        )

        assert len(intervals) == 2
        for level in confidence_levels:
            assert level in intervals
            low, high = intervals[level]
            assert low <= high

    def test_compute_sensitivity_indices(self, quantifier, sample_scenario_results_df):
        """Test sensitivity index computation."""
        indices = quantifier.compute_sensitivity_indices(
            sample_scenario_results_df, target_column="total_tax_receipt"
        )

        assert isinstance(indices, dict)
        assert len(indices) > 0

        # Check indices are between 0 and 1 (correlation-based)
        for _param, sensitivity in indices.items():
            assert 0.0 <= sensitivity <= 1.0

    def test_quantify_uncertainty(self, quantifier, sample_scenario_results_df):
        """Test uncertainty quantification."""
        result = quantifier.quantify_uncertainty(
            sample_scenario_results_df, target_column="total_tax_receipt"
        )

        assert isinstance(result, UncertaintyResult)
        assert result.min_estimate < result.mean_estimate < result.max_estimate
        assert len(result.confidence_intervals) > 0
        assert len(result.sensitivity_indices) > 0

    def test_quantify_uncertainty_empty(self, quantifier):
        """Test uncertainty quantification with empty DataFrame."""
        empty_df = pd.DataFrame()
        result = quantifier.quantify_uncertainty(empty_df, target_column="total_tax_receipt")

        # UncertaintyResult doesn't have is_valid - check quality_flags instead
        assert "empty_dataframe" in result.quality_flags
        assert result.min_estimate == Decimal("0")

    def test_quantify_uncertainty_missing_target(self, quantifier, sample_scenario_results_df):
        """Test uncertainty quantification with missing target column."""
        result = quantifier.quantify_uncertainty(
            sample_scenario_results_df, target_column="nonexistent_column"
        )

        # UncertaintyResult doesn't have is_valid - check quality_flags instead
        assert "missing_target_column" in result.quality_flags
        assert result.min_estimate == Decimal("0")

    def test_flag_high_uncertainty(self, quantifier):
        """Test high uncertainty flagging."""
        # Create result with high CV
        result = UncertaintyResult(
            min_estimate=Decimal("50000"),
            mean_estimate=Decimal("100000"),
            max_estimate=Decimal("200000"),
            confidence_intervals={0.95: (Decimal("80000"), Decimal("120000"))},
            sensitivity_indices={},
            quality_flags=["high_uncertainty"],
        )

        flagged = quantifier.flag_high_uncertainty(result)
        assert flagged is True
