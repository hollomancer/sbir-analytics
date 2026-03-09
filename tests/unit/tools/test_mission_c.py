"""Tests for Mission C: Fiscal Return Estimate tools."""

import pytest
import pandas as pd

from src.tools.mission_c.naics_to_bea_crosswalk import NAICSToBEACrosswalkTool
from src.tools.mission_c.stateio_multipliers import StateIOMultipliersTool
from src.tools.mission_c.tax_estimation import (
    TaxEstimationTool,
    DEFAULT_EFFECTIVE_TAX_RATES,
    PAYROLL_TAX_RATE,
    INDIVIDUAL_INCOME_TAX_RATE,
)


# ---- naics_to_bea_crosswalk ----

class TestNAICSToBEACrosswalkTool:
    def test_basic_mapping(self):
        awards = pd.DataFrame({
            "naics_code": ["541511", "236220", ""],
            "company": ["TechCo", "BuildCo", "NullCo"],
        })
        tool = NAICSToBEACrosswalkTool()
        result = tool.run(awards_df=awards)
        assert isinstance(result.data, dict)
        assert "awards" in result.data
        assert "mapping_stats" in result.data
        assert "bea_sector" in result.data["awards"].columns

    def test_empty_input(self):
        tool = NAICSToBEACrosswalkTool()
        result = tool.run()
        assert len(result.data) == 0

    def test_metadata_warnings_for_unmapped(self):
        awards = pd.DataFrame({
            "naics_code": ["999999"],  # Unlikely to map
            "company": ["UnknownCo"],
        })
        tool = NAICSToBEACrosswalkTool()
        result = tool.run(awards_df=awards)
        stats = result.data["mapping_stats"]
        # Either mapped or unmapped, but stats should be populated
        assert stats["total"] == 1


# ---- stateio_multipliers ----

class TestStateIOMultipliersTool:
    def test_default_fallback(self):
        tool = StateIOMultipliersTool()
        result = tool.run(states=["CA", "MA"], bea_sectors=["Manufacturing"])
        assert isinstance(result.data, pd.DataFrame)
        assert len(result.data) >= 1
        # Should fall back to default 1.0 multipliers
        assert "output_multiplier" in result.data.columns

    def test_from_awards_df(self):
        awards = pd.DataFrame({
            "state": ["CA", "MA"],
            "bea_sector": ["Manufacturing", "Information"],
        })
        tool = StateIOMultipliersTool()
        result = tool.run(awards_df=awards)
        assert len(result.data) == 2

    def test_empty_input(self):
        tool = StateIOMultipliersTool()
        result = tool.run()
        assert len(result.data) == 0


# ---- tax_estimation ----

class TestTaxEstimationTool:
    def test_basic_estimation(self):
        awards = pd.DataFrame({
            "bea_sector": ["Manufacturing", "Information"],
            "state": ["CA", "MA"],
            "award_amount": [500000, 300000],
            "fiscal_year": [2023, 2023],
            "canonical_id": ["co1", "co2"],
        })
        multipliers = pd.DataFrame({
            "state": ["CA", "MA"],
            "bea_sector": ["Manufacturing", "Information"],
            "output_multiplier": [1.8, 1.5],
            "value_added_multiplier": [1.2, 1.1],
        })
        tool = TaxEstimationTool()
        result = tool.run(awards_df=awards, multipliers_df=multipliers)
        assert isinstance(result.data, dict)
        assert "track_a_estimates" in result.data
        assert "summary" in result.data

        track_a = result.data["track_a_estimates"]
        assert len(track_a) == 2
        assert track_a["total_estimated_tax"].sum() > 0

    def test_tax_components(self):
        awards = pd.DataFrame({
            "bea_sector": ["Manufacturing"],
            "state": ["CA"],
            "award_amount": [1_000_000],
            "fiscal_year": [2023],
            "canonical_id": ["co1"],
        })
        multipliers = pd.DataFrame({
            "state": ["CA"],
            "bea_sector": ["Manufacturing"],
            "output_multiplier": [2.0],
            "value_added_multiplier": [1.5],
        })
        tool = TaxEstimationTool()
        result = tool.run(awards_df=awards, multipliers_df=multipliers)
        row = result.data["track_a_estimates"].iloc[0]

        # Check all tax components are present and positive
        assert row["individual_income_tax"] > 0
        assert row["payroll_tax"] > 0
        assert row["corporate_income_tax"] > 0
        assert row["total_estimated_tax"] > 0

        # Total should be sum of components
        expected_total = (
            row["individual_income_tax"] +
            row["payroll_tax"] +
            row["corporate_income_tax"]
        )
        assert row["total_estimated_tax"] == pytest.approx(expected_total, rel=0.01)

    def test_roi_calculation(self):
        awards = pd.DataFrame({
            "bea_sector": ["Manufacturing"],
            "state": ["CA"],
            "award_amount": [1_000_000],
            "fiscal_year": [2023],
            "canonical_id": ["co1"],
        })
        multipliers = pd.DataFrame({
            "state": ["CA"],
            "bea_sector": ["Manufacturing"],
            "output_multiplier": [2.0],
            "value_added_multiplier": [1.5],
        })
        tool = TaxEstimationTool()
        result = tool.run(awards_df=awards, multipliers_df=multipliers)
        summary = result.data["summary"]
        assert summary["track_a"]["implied_roi"] is not None
        assert summary["track_a"]["implied_roi"] > 0

    def test_empty_input(self):
        tool = TaxEstimationTool()
        result = tool.run()
        summary = result.data["summary"]
        assert summary["track_a"]["total_estimated_tax_receipts"] == 0.0

    def test_default_tax_rates(self):
        assert "Manufacturing" in DEFAULT_EFFECTIVE_TAX_RATES
        assert 0 < PAYROLL_TAX_RATE < 0.5
        assert 0 < INDIVIDUAL_INCOME_TAX_RATE < 0.5

    def test_limitation_disclosure(self):
        tool = TaxEstimationTool()
        result = tool.run()
        summary = result.data["summary"]
        assert "limitation_disclosure" in summary
        assert "private-sector" in summary["limitation_disclosure"].lower()

    def test_track_b_integration(self):
        """Test Track B data flows through when provided."""
        awards = pd.DataFrame({
            "bea_sector": ["Manufacturing"],
            "state": ["CA"],
            "award_amount": [500000],
            "fiscal_year": [2023],
            "canonical_id": ["co1"],
        })
        fpds = pd.DataFrame({
            "company_id": ["co1"],
            "fpds_total_revenue": [2_000_000],
        })
        tool = TaxEstimationTool()
        result = tool.run(awards_df=awards, fpds_revenue=fpds)
        assert result.data["track_b_observed"]["total_fpds_revenue"] == 2_000_000
