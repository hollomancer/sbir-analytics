"""Unit tests for fiscal parameter sweep engine."""

import pandas as pd
import pytest


pytestmark = pytest.mark.fast

from src.transformers.fiscal_parameter_sweep import (
    FiscalParameterSweep,
    ParameterRange,
    ParameterScenario,
)


@pytest.fixture
def sweep():
    """Create a FiscalParameterSweep instance."""
    return FiscalParameterSweep()


class TestFiscalParameterSweep:
    """Test FiscalParameterSweep class."""

    def test_get_parameter_ranges(self, sweep):
        """Test parameter range extraction from config."""
        ranges = sweep._get_parameter_ranges()

        assert len(ranges) > 0
        assert isinstance(ranges, dict)

        # Check expected parameter ranges exist
        assert "discount_rate" in ranges
        assert isinstance(ranges["discount_rate"], ParameterRange)

    def test_generate_monte_carlo_scenarios(self, sweep):
        """Test Monte Carlo scenario generation."""
        scenarios = sweep.generate_monte_carlo_scenarios(num_scenarios=10, random_seed=42)

        assert len(scenarios) == 10
        assert all(isinstance(s, ParameterScenario) for s in scenarios)

        # Check all scenarios have parameters
        for scenario in scenarios:
            assert len(scenario.parameters) > 0
            assert scenario.scenario_id > 0
            assert scenario.metadata["method"] == "monte_carlo"

    def test_generate_latin_hypercube_scenarios(self, sweep):
        """Test Latin Hypercube scenario generation."""
        scenarios = sweep.generate_latin_hypercube_scenarios(num_scenarios=10, random_seed=42)

        assert len(scenarios) == 10
        assert all(isinstance(s, ParameterScenario) for s in scenarios)

        # Check all scenarios have parameters
        for scenario in scenarios:
            assert len(scenario.parameters) > 0
            assert scenario.metadata["method"] == "latin_hypercube"

    def test_generate_grid_search_scenarios(self, sweep):
        """Test grid search scenario generation."""
        scenarios = sweep.generate_grid_search_scenarios(points_per_dimension=3)

        # Grid search should generate scenarios based on parameter combinations
        assert len(scenarios) > 0
        assert all(isinstance(s, ParameterScenario) for s in scenarios)

        # Check method metadata
        for scenario in scenarios:
            assert scenario.metadata["method"] == "grid_search"

    def test_generate_scenarios(self, sweep):
        """Test scenario generation using configured method."""
        scenarios_df = sweep.generate_scenarios()

        assert isinstance(scenarios_df, pd.DataFrame)
        assert len(scenarios_df) > 0
        assert "scenario_id" in scenarios_df.columns
        assert "method" in scenarios_df.columns

    def test_scenario_parameters_in_range(self, sweep):
        """Test that generated scenario parameters are within valid ranges."""
        ranges = sweep._get_parameter_ranges()
        scenarios = sweep.generate_monte_carlo_scenarios(num_scenarios=20, random_seed=42)

        for scenario in scenarios:
            for param_name, param_value in scenario.parameters.items():
                if param_name in ranges:
                    param_range = ranges[param_name]
                    assert param_range.min_value <= param_value <= param_range.max_value
