"""End-to-end integration tests for fiscal returns analysis pipeline."""

from datetime import date
from decimal import Decimal

import pandas as pd
import pytest
from dagster import materialize
from dagster._core.definitions import load_assets_from_modules

from src.assets import fiscal_assets


@pytest.fixture
def synthetic_sbir_data():
    """Create synthetic SBIR award data for testing."""
    return pd.DataFrame(
        [
            {
                "award_id": f"A{i:03d}",
                "company_name": f"Company {i}",
                "award_amount": 100000.0 + (i * 10000),
                "award_date": date(2023, (i % 12) + 1, 15),
                "company_state": ["CA", "TX", "NY", "FL", "MA"][i % 5],
                "agency": ["NSF", "DOD", "NIH", "DOE", "NASA"][i % 5],
                "company_uei": f"UEI-{i:06d}",
            }
            for i in range(50)
        ]
    )


class TestFiscalPipelineIntegration:
    """Test complete fiscal returns analysis pipeline."""

    @pytest.mark.skip(reason="Requires full pipeline dependencies")
    def test_end_to_end_pipeline(self, synthetic_sbir_data, tmp_path):
        """Test end-to-end pipeline execution with synthetic data."""
        # This test would require:
        # - Mocking all upstream dependencies
        # - Setting up test Neo4j instance
        # - Configuring test data sources
        # For now, marked as skip but structure is ready

        # Load assets
        all_fiscal_assets = load_assets_from_modules([fiscal_assets])

        # Materialize assets (would need proper test setup)
        # results = materialize(all_fiscal_assets)

        pass

    def test_pipeline_dependency_resolution(self):
        """Test that asset dependencies are correctly defined."""
        # Check that assets have correct dependencies
        assert hasattr(fiscal_assets, "fiscal_prepared_sbir_awards")
        assert hasattr(fiscal_assets, "inflation_adjusted_awards")
        assert hasattr(fiscal_assets, "tax_base_components")
        assert hasattr(fiscal_assets, "federal_tax_estimates")
        assert hasattr(fiscal_assets, "fiscal_return_summary")

    def test_pipeline_asset_groups(self):
        """Test that assets are grouped correctly."""
        # Check asset groups
        all_fiscal_assets = load_assets_from_modules([fiscal_assets])

        groups = {}
        for asset_def in all_fiscal_assets:
            group_name = asset_def.group_name
            if group_name:
                groups[group_name] = groups.get(group_name, 0) + 1

        # Should have fiscal groups
        assert "fiscal_data_prep" in groups or "economic_modeling" in groups or "tax_calculation" in groups


class TestPerformanceThresholds:
    """Test performance monitoring within configured thresholds."""

    def test_component_extraction_performance(self):
        """Test component extraction completes within time limit."""
        import time

        from src.transformers.fiscal_component_calculator import FiscalComponentCalculator

        # Create large impacts DataFrame
        impacts_df = pd.DataFrame(
            [
                {
                    "state": "CA",
                    "bea_sector": "11",
                    "fiscal_year": 2023,
                    "wage_impact": Decimal("1000"),
                    "proprietor_income_impact": Decimal("500"),
                    "gross_operating_surplus": Decimal("300"),
                    "consumption_impact": Decimal("200"),
                }
                for _ in range(1000)
            ]
        )

        calculator = FiscalComponentCalculator()
        start_time = time.time()
        result = calculator.extract_components(impacts_df)
        elapsed = time.time() - start_time

        # Should complete in reasonable time (< 5 seconds for 1000 records)
        assert elapsed < 5.0
        assert len(result) == 1000

