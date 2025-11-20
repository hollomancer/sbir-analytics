"""Unit tests for SBIR fiscal impact pipeline."""

from decimal import Decimal
from unittest.mock import Mock, patch

import pandas as pd
import pytest

from src.transformers.sbir_fiscal_pipeline import SBIRFiscalImpactCalculator


pytestmark = pytest.mark.fast


@pytest.fixture
def sample_awards():
    """Create sample SBIR awards DataFrame."""
    return pd.DataFrame(
        {
            "award_id": ["SBIR001", "SBIR002", "SBIR003"],
            "award_amount": [1000000, 500000, 750000],
            "state": ["CA", "CA", "NY"],
            "naics_code": ["541512", "541330", "621111"],
            "fiscal_year": [2023, 2023, 2023],
        }
    )


@pytest.fixture
def sample_impacts():
    """Create sample impacts DataFrame."""
    return pd.DataFrame(
        {
            "state": ["CA", "NY"],
            "bea_sector": ["54", "62"],
            "fiscal_year": [2023, 2023],
            "wage_impact": [Decimal("400000"), Decimal("200000")],
            "tax_impact": [Decimal("150000"), Decimal("75000")],
            "production_impact": [Decimal("2000000"), Decimal("1000000")],
            "model_version": ["v2.1", "v2.1"],
            "confidence": [Decimal("0.85"), Decimal("0.85")],
            "quality_flags": ["stateio_direct_with_ratios", "stateio_direct_with_ratios"],
        }
    )


class TestSBIRFiscalImpactCalculator:
    """Test SBIR fiscal impact calculator."""

    @pytest.fixture
    def calculator(self):
        """Create calculator with mocked R adapter."""
        mock_adapter = Mock()
        return SBIRFiscalImpactCalculator(r_adapter=mock_adapter)

    def test_init_default(self):
        """Test initialization with defaults."""
        calc = SBIRFiscalImpactCalculator()
        assert calc.r_adapter is not None
        assert calc.naics_mapper is not None

    def test_validate_awards_input_success(self, calculator, sample_awards):
        """Test successful input validation."""
        # Should not raise
        calculator._validate_awards_input(sample_awards)

    def test_validate_awards_input_missing_columns(self, calculator):
        """Test validation fails with missing columns."""
        invalid_df = pd.DataFrame({"award_id": ["SBIR001"], "award_amount": [1000000]})

        with pytest.raises(ValueError, match="Missing required columns"):
            calculator._validate_awards_input(invalid_df)

    def test_validate_awards_input_empty(self, calculator):
        """Test validation fails with empty DataFrame."""
        empty_df = pd.DataFrame(columns=["award_amount", "state", "naics_code", "fiscal_year"])

        with pytest.raises(ValueError, match="empty"):
            calculator._validate_awards_input(empty_df)

    def test_validate_awards_input_null_values(self, calculator, sample_awards):
        """Test validation fails with null values."""
        awards_with_nulls = sample_awards.copy()
        awards_with_nulls.loc[0, "state"] = None

        with pytest.raises(ValueError, match="Null values"):
            calculator._validate_awards_input(awards_with_nulls)

    def test_map_naics_to_bea(self, calculator, sample_awards):
        """Test NAICS to BEA mapping."""
        result = calculator._map_naics_to_bea(sample_awards)

        assert "bea_sector" in result.columns
        # 541512 → 54, 541330 → 54, 621111 → 62
        assert result.loc[0, "bea_sector"] == "54"
        assert result.loc[1, "bea_sector"] == "54"
        assert result.loc[2, "bea_sector"] == "62"

    def test_aggregate_awards_to_shocks(self, calculator, sample_awards):
        """Test aggregation of awards to shocks."""
        # First map NAICS to BEA
        awards_with_bea = calculator._map_naics_to_bea(sample_awards)

        # Then aggregate
        shocks = calculator._aggregate_awards_to_shocks(awards_with_bea)

        # Should have 2 rows: CA/54 and NY/62
        assert len(shocks) == 2
        assert "shock_amount" in shocks.columns

        # CA sector 54 should be sum of first two awards
        ca_shock = shocks[(shocks["state"] == "CA") & (shocks["bea_sector"] == "54")]
        assert len(ca_shock) == 1
        assert ca_shock["shock_amount"].iloc[0] == Decimal("1500000")  # 1M + 500k

    def test_aggregate_awards_to_shocks_multiple_years(self, calculator):
        """Test aggregation with multiple fiscal years."""
        awards = pd.DataFrame(
            {
                "award_amount": [1000000, 500000],
                "state": ["CA", "CA"],
                "bea_sector": ["54", "54"],
                "fiscal_year": [2023, 2024],  # Different years
            }
        )

        shocks = calculator._aggregate_awards_to_shocks(awards)

        # Should have 2 rows (different years not aggregated)
        assert len(shocks) == 2
        assert shocks["fiscal_year"].tolist() == [2023, 2024]

    def test_add_employment_impacts(self, calculator, sample_impacts):
        """Test adding employment impacts."""
        result = calculator._add_employment_impacts(sample_impacts)

        assert "jobs_created" in result.columns

        # Jobs = wage_impact / 100k
        # CA: 400k / 100k = 4 jobs
        # NY: 200k / 100k = 2 jobs
        assert result.loc[0, "jobs_created"] == 4.0
        assert result.loc[1, "jobs_created"] == 2.0

    def test_add_employment_impacts_no_wage_column(self, calculator):
        """Test employment calculation without wage_impact column."""
        impacts_no_wage = pd.DataFrame({"state": ["CA"], "tax_impact": [Decimal("100000")]})

        result = calculator._add_employment_impacts(impacts_no_wage)

        assert "jobs_created" in result.columns
        assert result["jobs_created"].iloc[0] == 0.0

    def test_add_award_totals(self, calculator, sample_impacts):
        """Test adding award totals to impacts."""
        shocks = pd.DataFrame(
            {
                "state": ["CA", "NY"],
                "bea_sector": ["54", "62"],
                "fiscal_year": [2023, 2023],
                "shock_amount": [Decimal("1500000"), Decimal("750000")],
            }
        )

        result = calculator._add_award_totals(sample_impacts, shocks)

        assert "award_total" in result.columns
        assert result.loc[0, "award_total"] == Decimal("1500000")
        assert result.loc[1, "award_total"] == Decimal("750000")

    @patch.object(SBIRFiscalImpactCalculator, "_validate_awards_input")
    @patch.object(SBIRFiscalImpactCalculator, "_map_naics_to_bea")
    @patch.object(SBIRFiscalImpactCalculator, "_aggregate_awards_to_shocks")
    def test_calculate_impacts_from_sbir_awards(
        self,
        mock_aggregate,
        mock_map,
        mock_validate,
        calculator,
        sample_awards,
        sample_impacts,
    ):
        """Test full pipeline calculation."""
        # Setup mocks
        mock_map.return_value = sample_awards.copy()
        mock_shocks = pd.DataFrame(
            {
                "state": ["CA", "NY"],
                "bea_sector": ["54", "62"],
                "fiscal_year": [2023, 2023],
                "shock_amount": [Decimal("1500000"), Decimal("750000")],
            }
        )
        mock_aggregate.return_value = mock_shocks

        # Mock R adapter compute_impacts
        calculator.r_adapter.compute_impacts.return_value = sample_impacts.copy()

        # Run pipeline
        result = calculator.calculate_impacts_from_sbir_awards(sample_awards)

        # Verify pipeline steps called
        mock_validate.assert_called_once()
        mock_map.assert_called_once()
        mock_aggregate.assert_called_once()
        calculator.r_adapter.compute_impacts.assert_called_once()

        # Verify results have all expected columns
        assert "jobs_created" in result.columns
        assert "award_total" in result.columns
        assert len(result) == 2

    def test_calculate_summary_by_state(self, calculator, sample_impacts):
        """Test state-level summary calculation."""
        # Add required columns
        impacts = sample_impacts.copy()
        impacts["award_total"] = [Decimal("1500000"), Decimal("750000")]
        impacts["jobs_created"] = [4.0, 2.0]

        summary = calculator.calculate_summary_by_state(impacts)

        assert len(summary) == 2  # CA and NY
        assert "state" in summary.columns
        assert "total_awards" in summary.columns
        assert "total_tax_impact" in summary.columns
        assert "total_jobs_created" in summary.columns

    def test_calculate_summary_by_sector(self, calculator, sample_impacts):
        """Test sector-level summary calculation."""
        # Add required columns
        impacts = sample_impacts.copy()
        impacts["award_total"] = [Decimal("1500000"), Decimal("750000")]
        impacts["jobs_created"] = [4.0, 2.0]

        summary = calculator.calculate_summary_by_sector(impacts)

        assert len(summary) == 2  # Sectors 54 and 62
        assert "bea_sector" in summary.columns
        assert "sector_description" in summary.columns
        assert "total_awards" in summary.columns
        assert "total_tax_impact" in summary.columns
        assert "total_jobs_created" in summary.columns

        # Check descriptions added
        assert "Professional" in summary[summary["bea_sector"] == "54"]["sector_description"].iloc[0]
        assert "Health" in summary[summary["bea_sector"] == "62"]["sector_description"].iloc[0]
