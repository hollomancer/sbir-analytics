"""
Parameter sweep engine for fiscal returns sensitivity analysis.

This module generates scenario combinations for uncertainty quantification,
supporting Monte Carlo sampling, Latin hypercube sampling, and grid search
with parallel execution capabilities.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from loguru import logger

from ..config.loader import get_config


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
                    value = random.uniform(param_range.min_value, param_range.max_value)
                elif param_range.distribution == "normal":
                    # Use truncated normal (mean at center, std based on range)
                    mean = (param_range.min_value + param_range.max_value) / 2
                    std = (param_range.max_value - param_range.min_value) / 4
                    value = np.random.normal(mean, std)
                    # Clip to range
                    value = max(param_range.min_value, min(param_range.max_value, value))
                else:
                    # Default to uniform
                    value = random.uniform(param_range.min_value, param_range.max_value)

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
                swap_param = random.choice(param_names)
                prev_idx = random.randint(0, i - 1)
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
            parameters = dict(zip(param_names, combo))

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
        sweep_config = self.sensitivity_config.get("parameter_sweep", {})
        method = sweep_config.get("method", "monte_carlo")
        num_scenarios = sweep_config.get("num_scenarios", 1000)
        random_seed = sweep_config.get("random_seed", 42)

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

