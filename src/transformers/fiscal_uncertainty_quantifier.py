"""
Uncertainty quantifier for fiscal returns sensitivity analysis.

This module computes confidence intervals and uncertainty bands from parameter
sweep results, supporting bootstrap resampling and parametric confidence intervals
with sensitivity indices.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import numpy as np
import pandas as pd
from loguru import logger

from ..config.loader import get_config


@dataclass
class UncertaintyResult:
    """Result of uncertainty quantification analysis."""

    min_estimate: Decimal
    mean_estimate: Decimal
    max_estimate: Decimal
    confidence_intervals: dict[float, tuple[Decimal, Decimal]]  # level -> (low, high)
    sensitivity_indices: dict[str, float]  # parameter -> sensitivity index
    quality_flags: list[str]


class FiscalUncertaintyQuantifier:
    """Quantify uncertainty from sensitivity analysis results.

    This quantifier computes confidence intervals, min/mean/max estimates, and
    sensitivity indices from parameter sweep scenario results.
    """

    def __init__(self, config: Any | None = None):
        """Initialize the uncertainty quantifier.

        Args:
            config: Optional configuration override
        """
        self.config = config or get_config().fiscal_analysis
        self.sensitivity_config = self.config.sensitivity_parameters

    def compute_percentile_confidence_intervals(
        self,
        estimates: pd.Series,
        confidence_levels: list[float] | None = None,
    ) -> dict[float, tuple[Decimal, Decimal]]:
        """Compute percentile-based confidence intervals.

        Args:
            estimates: Series of estimates from scenarios
            confidence_levels: List of confidence levels (e.g., [0.90, 0.95, 0.99])

        Returns:
            Dictionary mapping confidence level to (low, high) interval
        """
        if confidence_levels is None:
            # Handle both Pydantic model and dict
            if hasattr(self.sensitivity_config, "confidence_intervals"):
                ci_config = self.sensitivity_config.confidence_intervals
                if hasattr(ci_config, "__dict__"):
                    ci_config = ci_config.__dict__
            else:
                ci_config = self.sensitivity_config.get("confidence_intervals", {})
            confidence_levels = ci_config.get("levels", [0.90, 0.95, 0.99]) if isinstance(ci_config, dict) else getattr(ci_config, "levels", [0.90, 0.95, 0.99])

        if estimates.empty:
            return {level: (Decimal("0"), Decimal("0")) for level in confidence_levels}

        intervals = {}
        for level in confidence_levels:
            alpha = 1 - level
            low_percentile = (alpha / 2) * 100
            high_percentile = (1 - alpha / 2) * 100

            low_value = np.percentile(estimates, low_percentile)
            high_value = np.percentile(estimates, high_percentile)

            intervals[level] = (Decimal(str(low_value)), Decimal(str(high_value)))

        return intervals

    def compute_bootstrap_confidence_intervals(
        self,
        estimates: pd.Series,
        confidence_levels: list[float] | None = None,
        num_samples: int = 1000,
        random_seed: int | None = None,
    ) -> dict[float, tuple[Decimal, Decimal]]:
        """Compute bootstrap confidence intervals.

        Args:
            estimates: Series of estimates from scenarios
            confidence_levels: List of confidence levels
            num_samples: Number of bootstrap samples
            random_seed: Optional random seed

        Returns:
            Dictionary mapping confidence level to (low, high) interval
        """
        if confidence_levels is None:
            # Handle both Pydantic model and dict
            if hasattr(self.sensitivity_config, "confidence_intervals"):
                ci_config = self.sensitivity_config.confidence_intervals
                if hasattr(ci_config, "__dict__"):
                    ci_config = ci_config.__dict__
            else:
                ci_config = self.sensitivity_config.get("confidence_intervals", {})
            confidence_levels = ci_config.get("levels", [0.90, 0.95, 0.99]) if isinstance(ci_config, dict) else getattr(ci_config, "levels", [0.90, 0.95, 0.99])

        if estimates.empty:
            return {level: (Decimal("0"), Decimal("0")) for level in confidence_levels}

        if random_seed is not None:
            np.random.seed(random_seed)

        # Bootstrap resampling
        n = len(estimates)
        bootstrap_means = []

        for _ in range(num_samples):
            # Resample with replacement
            sample = np.random.choice(estimates, size=n, replace=True)
            bootstrap_means.append(np.mean(sample))

        bootstrap_means = np.array(bootstrap_means)

        intervals = {}
        for level in confidence_levels:
            alpha = 1 - level
            low_percentile = (alpha / 2) * 100
            high_percentile = (1 - alpha / 2) * 100

            low_value = np.percentile(bootstrap_means, low_percentile)
            high_value = np.percentile(bootstrap_means, high_percentile)

            intervals[level] = (Decimal(str(low_value)), Decimal(str(high_value)))

        return intervals

    def compute_sensitivity_indices(
        self,
        scenario_results_df: pd.DataFrame,
        target_column: str = "total_tax_receipt",
    ) -> dict[str, float]:
        """Compute sensitivity indices for parameters.

        Uses correlation-based sensitivity analysis (Pearson correlation).

        Args:
            scenario_results_df: DataFrame with scenario parameters and results
            target_column: Column name for target metric

        Returns:
            Dictionary mapping parameter name to sensitivity index
        """
        if scenario_results_df.empty or target_column not in scenario_results_df.columns:
            return {}

        # Identify parameter columns (exclude result and metadata columns)
        exclude_cols = {
            target_column,
            "scenario_id",
            "method",
            "random_seed",
            "points_per_dimension",
        }

        param_cols = [
            col
            for col in scenario_results_df.columns
            if col not in exclude_cols and scenario_results_df[col].dtype in [np.float64, float]
        ]

        sensitivity_indices = {}

        for param_col in param_cols:
            # Compute Pearson correlation
            correlation = scenario_results_df[param_col].corr(scenario_results_df[target_column])

            if pd.notna(correlation):
                # Use absolute value as sensitivity index
                sensitivity_indices[param_col] = abs(float(correlation))
            else:
                sensitivity_indices[param_col] = 0.0

        # Sort by sensitivity (highest first)
        sensitivity_indices = dict(
            sorted(sensitivity_indices.items(), key=lambda x: x[1], reverse=True)
        )

        return sensitivity_indices

    def quantify_uncertainty(
        self,
        scenario_results_df: pd.DataFrame,
        target_column: str = "total_tax_receipt",
        confidence_levels: list[float] | None = None,
    ) -> UncertaintyResult:
        """Quantify uncertainty from scenario results.

        Args:
            scenario_results_df: DataFrame with scenario parameters and results
            target_column: Column name for target metric
            confidence_levels: Optional confidence levels to compute

        Returns:
            UncertaintyResult with min/mean/max, confidence intervals, sensitivity indices
        """
        if scenario_results_df is None or scenario_results_df.empty:
            logger.warning("Empty scenario results DataFrame provided to uncertainty quantifier")
            return UncertaintyResult(
                min_estimate=Decimal("0"),
                mean_estimate=Decimal("0"),
                max_estimate=Decimal("0"),
                confidence_intervals={},
                sensitivity_indices={},
                quality_flags=["empty_dataframe"],
            )

        if target_column not in scenario_results_df.columns:
            logger.error(f"Target column {target_column} not found in results DataFrame")
            return UncertaintyResult(
                min_estimate=Decimal("0"),
                mean_estimate=Decimal("0"),
                max_estimate=Decimal("0"),
                confidence_intervals={},
                sensitivity_indices={},
                quality_flags=["missing_target_column"],
            )

        estimates = scenario_results_df[target_column]

        # Compute min/mean/max
        min_estimate = Decimal(str(estimates.min()))
        mean_estimate = Decimal(str(estimates.mean()))
        max_estimate = Decimal(str(estimates.max()))

        # Compute confidence intervals
        # Handle both Pydantic model and dict
        if hasattr(self.sensitivity_config, "confidence_intervals"):
            ci_config = self.sensitivity_config.confidence_intervals
            if hasattr(ci_config, "__dict__"):
                ci_config = ci_config.__dict__
        else:
            ci_config = self.sensitivity_config.get("confidence_intervals", {})
        
        method = ci_config.get("method", "percentile") if isinstance(ci_config, dict) else getattr(ci_config, "method", "percentile")

        if method == "bootstrap":
            bootstrap_samples = ci_config.get("bootstrap_samples", 1000) if isinstance(ci_config, dict) else getattr(ci_config, "bootstrap_samples", 1000)
            confidence_intervals = self.compute_bootstrap_confidence_intervals(
                estimates, confidence_levels=confidence_levels, num_samples=bootstrap_samples
            )
        else:
            # Default to percentile
            confidence_intervals = self.compute_percentile_confidence_intervals(
                estimates, confidence_levels=confidence_levels
            )

        # Compute sensitivity indices
        sensitivity_indices = self.compute_sensitivity_indices(
            scenario_results_df, target_column=target_column
        )

        # Quality flags
        quality_flags = []

        # Check coefficient of variation (CV = std / mean)
        if mean_estimate != 0:
            cv = float(estimates.std() / estimates.mean())
            if cv > 0.5:
                quality_flags.append("high_uncertainty")
            elif cv > 0.3:
                quality_flags.append("moderate_uncertainty")

        # Check if range is very large
        range_pct = float((max_estimate - min_estimate) / mean_estimate * 100) if mean_estimate != 0 else 0
        if range_pct > 200:
            quality_flags.append("very_wide_range")

        logger.info(
            "Uncertainty quantification complete",
            extra={
                "min_estimate": f"${min_estimate:,.2f}",
                "mean_estimate": f"${mean_estimate:,.2f}",
                "max_estimate": f"${max_estimate:,.2f}",
                "coefficient_of_variation": f"{cv:.3f}" if mean_estimate != 0 else "N/A",
                "num_scenarios": len(estimates),
            },
        )

        return UncertaintyResult(
            min_estimate=min_estimate,
            mean_estimate=mean_estimate,
            max_estimate=max_estimate,
            confidence_intervals=confidence_intervals,
            sensitivity_indices=sensitivity_indices,
            quality_flags=quality_flags,
        )

    def flag_high_uncertainty(
        self,
        uncertainty_result: UncertaintyResult,
        threshold_cv: float = 0.5,
    ) -> bool:
        """Flag if uncertainty exceeds thresholds.

        Args:
            uncertainty_result: Uncertainty quantification result
            threshold_cv: Threshold for coefficient of variation

        Returns:
            True if high uncertainty detected
        """
        if "high_uncertainty" in uncertainty_result.quality_flags:
            return True

        # Check CV if available
        if uncertainty_result.mean_estimate != 0:
            # Estimate CV from min/max (approximate)
            range_pct = float(
                (uncertainty_result.max_estimate - uncertainty_result.min_estimate)
                / uncertainty_result.mean_estimate
            )
            # CV ≈ range / (4 * mean) for normal distribution
            estimated_cv = range_pct / 4
            if estimated_cv > threshold_cv:
                return True

        return False

