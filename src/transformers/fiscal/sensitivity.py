"""
Sensitivity analysis for fiscal returns analysis.

This module provides parameter sweep generation and uncertainty quantification
for fiscal returns sensitivity analysis. It supports Monte Carlo sampling,
Latin hypercube sampling, grid search, and various confidence interval methods.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import numpy as np
import pandas as pd
from loguru import logger

from ...config.loader import get_config


# =============================================================================
# Parameter Sweep Components
# =============================================================================


@dataclass
class ParameterRange:
    """Definition of a parameter range for sensitivity analysis."""

    name: str
    min_value: float
    max_value: float
    distribution: str = "uniform"  # uniform, normal, lognormal


@dataclass
class ParameterScenario:
    """A single parameter scenario combination."""

    scenario_id: int
    parameters: dict[str, float]
    metadata: dict[str, Any]


class FiscalParameterSweep:
    """Generate parameter sweep scenarios for sensitivity analysis.

    This engine creates scenario combinations from parameter ranges using
    various sampling methods for uncertainty quantification.
    """

    def __init__(self, config: Any | None = None):
        """Initialize the parameter sweep engine.

        Args:
            config: Optional configuration override
        """
        self.config = config or get_config().fiscal_analysis
        self.sensitivity_config = self.config.sensitivity_parameters

    def _get_parameter_ranges(self) -> dict[str, ParameterRange]:
        """Get parameter ranges from configuration.

        Returns:
            Dictionary of parameter name to ParameterRange
        """
        # Handle both dict and Pydantic model
        if hasattr(self.sensitivity_config, "uncertainty_parameters"):
            uncertainty_params = self.sensitivity_config.uncertainty_parameters
            if hasattr(uncertainty_params, "__dict__"):
                uncertainty_params = uncertainty_params.__dict__
        else:
            uncertainty_params = self.sensitivity_config.get("uncertainty_parameters", {})

        ranges = {}

        # Tax rate parameters
        if "tax_rates" in uncertainty_params:
            tax_config = uncertainty_params["tax_rates"]
            variation = tax_config.get("variation_percent", 0.10)
            base_rate = 0.22  # Default individual income tax rate

            ranges["individual_income_tax_rate"] = ParameterRange(
                name="individual_income_tax_rate",
                min_value=base_rate * (1 - variation),
                max_value=base_rate * (1 + variation),
                distribution=tax_config.get("distribution", "normal"),
            )

            ranges["corporate_income_tax_rate"] = ParameterRange(
                name="corporate_income_tax_rate",
                min_value=0.18 * (1 - variation),
                max_value=0.18 * (1 + variation),
                distribution=tax_config.get("distribution", "normal"),
            )

        # Economic multiplier parameters
        if "multipliers" in uncertainty_params:
            mult_config = uncertainty_params["multipliers"]
            variation = mult_config.get("variation_percent", 0.15)
            base_multiplier = 2.0

            ranges["economic_multiplier"] = ParameterRange(
                name="economic_multiplier",
                min_value=base_multiplier * (1 - variation),
                max_value=base_multiplier * (1 + variation),
                distribution=mult_config.get("distribution", "normal"),
            )

        # Discount rate for NPV
        ranges["discount_rate"] = ParameterRange(
            name="discount_rate",
            min_value=0.01,  # 1%
            max_value=0.07,  # 7%
            distribution="uniform",
        )

        return ranges

    def generate_monte_carlo_scenarios(
        self, num_scenarios: int, random_seed: int | None = None
    ) -> list[ParameterScenario]:
        """Generate scenarios using Monte Carlo sampling.

        Args:
            num_scenarios: Number of scenarios to generate
            random_seed: Optional random seed for reproducibility

        Returns:
            List of ParameterScenario objects
        """
        if random_seed is not None:
            random.seed(random_seed)
            np.random.seed(random_seed)

        ranges = self._get_parameter_ranges()
        scenarios = []

        for i in range(num_scenarios):
            parameters = {}

            for param_name, param_range in ranges.items():
                if param_range.distribution == "uniform":
                    value = random.uniform(param_range.min_value, param_range.max_value)  # nosec B311 - Monte Carlo sampling for sensitivity analysis
                elif param_range.distribution == "normal":
                    # Use truncated normal (mean at center, std based on range)
                    mean = (param_range.min_value + param_range.max_value) / 2
                    std = (param_range.max_value - param_range.min_value) / 4
                    value = np.random.normal(mean, std)
                    # Clip to range
                    value = max(param_range.min_value, min(param_range.max_value, value))
                else:
                    # Default to uniform
                    value = random.uniform(param_range.min_value, param_range.max_value)  # nosec B311 - Monte Carlo sampling for sensitivity analysis

                parameters[param_name] = float(value)

            scenario = ParameterScenario(
                scenario_id=i + 1,
                parameters=parameters,
                metadata={
                    "method": "monte_carlo",
                    "random_seed": random_seed,
                },
            )
            scenarios.append(scenario)

        logger.info(f"Generated {num_scenarios} Monte Carlo scenarios")
        return scenarios

    def generate_latin_hypercube_scenarios(
        self, num_scenarios: int, random_seed: int | None = None
    ) -> list[ParameterScenario]:
        """Generate scenarios using Latin Hypercube Sampling (LHS).

        Args:
            num_scenarios: Number of scenarios to generate
            random_seed: Optional random seed for reproducibility

        Returns:
            List of ParameterScenario objects
        """
        if random_seed is not None:
            np.random.seed(random_seed)

        ranges = self._get_parameter_ranges()
        param_names = list(ranges.keys())

        # Generate LHS samples
        # Simple implementation: divide each parameter range into num_scenarios bins
        # and sample one value from each bin
        scenarios = []

        # Create bins for each parameter
        param_bins = {}
        for param_name, param_range in ranges.items():
            bins = np.linspace(param_range.min_value, param_range.max_value, num_scenarios + 1)
            param_bins[param_name] = bins

        # Generate LHS: one sample per bin, randomly permuted
        for i in range(num_scenarios):
            parameters = {}

            for param_name in param_names:
                param_range = ranges[param_name]
                bins = param_bins[param_name]

                # Sample from bin i (uniform within bin)
                bin_min = bins[i]
                bin_max = bins[i + 1]
                value = np.random.uniform(bin_min, bin_max)

                # For normal distribution, adjust value toward mean
                if param_range.distribution == "normal":
                    mean = (param_range.min_value + param_range.max_value) / 2
                    # Bias toward mean
                    value = 0.7 * value + 0.3 * mean
                    value = max(param_range.min_value, min(param_range.max_value, value))

                parameters[param_name] = float(value)

            # Random permutation to break correlation
            if i > 0:
                # Swap with random previous scenario for one parameter
                swap_param = random.choice(param_names)  # nosec B311 - Latin Hypercube Sampling for sensitivity analysis
                prev_idx = random.randint(0, i - 1)  # nosec B311 - Latin Hypercube Sampling for sensitivity analysis
                temp = parameters[swap_param]
                parameters[swap_param] = scenarios[prev_idx].parameters[swap_param]
                scenarios[prev_idx].parameters[swap_param] = temp

            scenario = ParameterScenario(
                scenario_id=i + 1,
                parameters=parameters,
                metadata={
                    "method": "latin_hypercube",
                    "random_seed": random_seed,
                },
            )
            scenarios.append(scenario)

        logger.info(f"Generated {num_scenarios} Latin Hypercube scenarios")
        return scenarios

    def generate_grid_search_scenarios(
        self, points_per_dimension: int = 5
    ) -> list[ParameterScenario]:
        """Generate scenarios using grid search.

        Args:
            points_per_dimension: Number of points per parameter dimension

        Returns:
            List of ParameterScenario objects
        """
        ranges = self._get_parameter_ranges()
        param_names = list(ranges.keys())

        # Generate grid points for each parameter
        param_grids = {}
        for param_name, param_range in ranges.items():
            param_grids[param_name] = np.linspace(
                param_range.min_value,
                param_range.max_value,
                points_per_dimension,
            )

        # Generate all combinations (Cartesian product)
        from itertools import product

        scenarios = []
        scenario_id = 1

        for combo in product(*[param_grids[name] for name in param_names]):
            parameters = dict(zip(param_names, combo, strict=False))

            scenario = ParameterScenario(
                scenario_id=scenario_id,
                parameters=parameters,
                metadata={
                    "method": "grid_search",
                    "points_per_dimension": points_per_dimension,
                },
            )
            scenarios.append(scenario)
            scenario_id += 1

        logger.info(
            f"Generated {len(scenarios)} grid search scenarios "
            f"({points_per_dimension} points per {len(param_names)} dimensions)"
        )
        return scenarios

    def generate_scenarios(self) -> pd.DataFrame:
        """Generate scenarios using configured method.

        Returns:
            DataFrame with scenario parameters
        """
        # Handle both Pydantic model and dict
        if hasattr(self.sensitivity_config, "parameter_sweep"):
            sweep_config = self.sensitivity_config.parameter_sweep
            if hasattr(sweep_config, "__dict__"):
                sweep_config = sweep_config.__dict__
        else:
            sweep_config = self.sensitivity_config.get("parameter_sweep", {})

        method = (
            sweep_config.get("method", "monte_carlo")
            if isinstance(sweep_config, dict)
            else getattr(sweep_config, "method", "monte_carlo")
        )
        num_scenarios = (
            sweep_config.get("num_scenarios", 1000)
            if isinstance(sweep_config, dict)
            else getattr(sweep_config, "num_scenarios", 1000)
        )
        random_seed = (
            sweep_config.get("random_seed", 42)
            if isinstance(sweep_config, dict)
            else getattr(sweep_config, "random_seed", 42)
        )

        if method == "monte_carlo":
            scenarios = self.generate_monte_carlo_scenarios(num_scenarios, random_seed)
        elif method == "latin_hypercube":
            scenarios = self.generate_latin_hypercube_scenarios(num_scenarios, random_seed)
        elif method == "grid_search":
            ranges = self._get_parameter_ranges()
            num_params = len(ranges)
            if num_params > 0:
                points_per_dim = int(np.ceil(num_scenarios ** (1.0 / num_params)))
            else:
                points_per_dim = 3  # Default
            scenarios = self.generate_grid_search_scenarios(points_per_dim)
        else:
            logger.warning(f"Unknown method {method}, defaulting to monte_carlo")
            scenarios = self.generate_monte_carlo_scenarios(num_scenarios, random_seed)

        # Convert to DataFrame
        scenario_data = []
        for scenario in scenarios:
            row = {
                "scenario_id": scenario.scenario_id,
                **scenario.parameters,
                **scenario.metadata,
            }
            scenario_data.append(row)

        df = pd.DataFrame(scenario_data)

        logger.info(
            f"Generated {len(df)} scenarios using {method} method",
            extra={
                "num_scenarios": len(df),
                "method": method,
                "parameters": list(self._get_parameter_ranges().keys()),
            },
        )

        return df


# =============================================================================
# Uncertainty Quantification Components
# =============================================================================


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
            confidence_levels = (
                ci_config.get("levels", [0.90, 0.95, 0.99])
                if isinstance(ci_config, dict)
                else getattr(ci_config, "levels", [0.90, 0.95, 0.99])
            )

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
            confidence_levels = (
                ci_config.get("levels", [0.90, 0.95, 0.99])
                if isinstance(ci_config, dict)
                else getattr(ci_config, "levels", [0.90, 0.95, 0.99])
            )

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

        method = (
            ci_config.get("method", "percentile")
            if isinstance(ci_config, dict)
            else getattr(ci_config, "method", "percentile")
        )

        if method == "bootstrap":
            bootstrap_samples = (
                ci_config.get("bootstrap_samples", 1000)
                if isinstance(ci_config, dict)
                else getattr(ci_config, "bootstrap_samples", 1000)
            )
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
        range_pct = (
            float((max_estimate - min_estimate) / mean_estimate * 100) if mean_estimate != 0 else 0
        )
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
