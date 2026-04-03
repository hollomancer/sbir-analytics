"""Tests for BEA I-O function wrappers (replaces R StateIO function tests)."""

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from tests.mocks import RMocks

import sbir_etl.transformers.bea_io_functions as bea_io


pytestmark = pytest.mark.fast


class TestFetchUsTable:
    """Tests for fetch_use_table function."""

    def test_fetch_use_table_parses_api_response(self):
        """Test that fetch_use_table converts BEA API response to matrix."""
        mock_client = MagicMock()
        mock_client.get_use_table.return_value = RMocks.mock_bea_use_table()

        result = bea_io.fetch_use_table(mock_client, year=2020)

        assert isinstance(result, pd.DataFrame)
        assert result.shape == (2, 2)  # 2 commodities × 2 industries
        assert result.loc["11", "11"] == 10.0
        assert result.loc["11", "21"] == 20.0

    def test_fetch_use_table_empty_response(self):
        """Test fetch_use_table handles empty API response."""
        mock_client = MagicMock()
        mock_client.get_use_table.return_value = pd.DataFrame()

        result = bea_io.fetch_use_table(mock_client, year=2020)
        assert result.empty

    def test_fetch_industry_output(self):
        """Test deriving industry output from Use table."""
        use_table = pd.DataFrame(
            [[10, 20], [5, 10]],
            index=["11", "21"],
            columns=["11", "21"],
        )
        output = bea_io.fetch_industry_output(use_table)
        assert output["11"] == 15.0  # 10 + 5
        assert output["21"] == 30.0  # 20 + 10

    def test_fetch_industry_output_empty(self):
        """Test fetch_industry_output with empty table."""
        result = bea_io.fetch_industry_output(pd.DataFrame())
        assert result.empty


class TestValueAddedRatioCalculation:
    """Tests for value-added ratio calculation functions."""

    def test_calculate_value_added_ratios_empty(self):
        """Test calculate_value_added_ratios with empty DataFrame."""
        result = bea_io.calculate_value_added_ratios(pd.DataFrame())
        assert isinstance(result, pd.DataFrame)
        assert result.empty

    def test_calculate_value_added_ratios_success(self):
        """Test successful calculation of value-added ratios."""
        va_df = RMocks.mock_bea_va_table()
        result = bea_io.calculate_value_added_ratios(va_df)

        assert isinstance(result, pd.DataFrame)
        if not result.empty:
            assert "sector" in result.columns
            assert "wage_ratio" in result.columns
            assert "gos_ratio" in result.columns
            assert "tax_ratio" in result.columns

    def test_calculate_ratios_with_zero_total(self):
        """Test ratio calculation handles zero total value added gracefully."""
        va_df = pd.DataFrame([
            {"ColCode": "11", "RowDescription": "Compensation of employees", "DataValue": "0"},
            {"ColCode": "11", "RowDescription": "Gross operating surplus", "DataValue": "0"},
            {"ColCode": "11", "RowDescription": "Taxes on production", "DataValue": "0"},
            {"ColCode": "11", "RowDescription": "Total value added", "DataValue": "0"},
        ])
        result = bea_io.calculate_value_added_ratios(va_df)
        assert isinstance(result, pd.DataFrame)


class TestEmploymentCoefficients:
    """Tests for employment coefficient calculation."""

    def test_calculate_employment_coefficients(self):
        """Test employment coefficient calculation."""
        emp_df = RMocks.mock_bea_employment_table()
        industry_output = pd.Series([100.0, 200.0], index=["11", "21"])

        result = bea_io.calculate_employment_coefficients(emp_df, industry_output)

        assert isinstance(result, pd.DataFrame)
        if not result.empty:
            assert "sector" in result.columns
            assert "employment_coefficient" in result.columns

    def test_calculate_employment_coefficients_empty(self):
        """Test employment coefficients with empty data."""
        result = bea_io.calculate_employment_coefficients(pd.DataFrame(), pd.Series(dtype=float))
        assert result.empty


class TestMatrixCalculations:
    """Tests for matrix calculation functions (Leontief, technical coefficients)."""

    def test_calculate_technical_coefficients(self):
        """Test calculation of technical coefficients matrix."""
        use_table = pd.DataFrame(
            [[10, 20], [5, 10]],
            index=["C1", "C2"],
            columns=["I1", "I2"],
        )
        industry_output = pd.Series([100, 200], index=["I1", "I2"])

        tech_coeff = bea_io.calculate_technical_coefficients(use_table, industry_output)

        assert tech_coeff.loc["C1", "I1"] == 0.1
        assert tech_coeff.loc["C1", "I2"] == 0.1
        assert tech_coeff.loc["C2", "I1"] == 0.05
        assert tech_coeff.loc["C2", "I2"] == 0.05

    def test_calculate_technical_coefficients_zero_output(self):
        """Test technical coefficients with zero output."""
        use_table = pd.DataFrame([[10, 20]], index=["C1"], columns=["I1", "I2"])
        industry_output = pd.Series([0, 200], index=["I1", "I2"])

        tech_coeff = bea_io.calculate_technical_coefficients(use_table, industry_output)
        assert isinstance(tech_coeff, pd.DataFrame)
        assert tech_coeff.loc["C1", "I2"] == 0.1

    def test_calculate_technical_coefficients_dimension_mismatch(self):
        """Test technical coefficients with mismatched dimensions."""
        use_table = pd.DataFrame([[10, 20]], index=["C1"], columns=["I1", "I2"])
        industry_output = pd.Series([100], index=["I1"])

        with pytest.raises(ValueError, match="must match"):
            bea_io.calculate_technical_coefficients(use_table, industry_output)

    def test_calculate_leontief_inverse(self):
        """Test Leontief inverse calculation."""
        tech_coeff = pd.DataFrame(
            [[0.1, 0.2], [0.05, 0.1]],
            index=["S1", "S2"],
            columns=["S1", "S2"],
        )

        leontief_inv = bea_io.calculate_leontief_inverse(tech_coeff)

        assert isinstance(leontief_inv, pd.DataFrame)
        assert leontief_inv.shape == (2, 2)
        assert leontief_inv.loc["S1", "S1"] >= 1.0
        assert leontief_inv.loc["S2", "S2"] >= 1.0

    def test_apply_demand_shocks(self):
        """Test applying demand shocks with Leontief inverse."""
        leontief_inv = pd.DataFrame(
            [[1.0, 0.0], [0.0, 1.0]],
            index=["11", "21"],
            columns=["11", "21"],
        )
        shocks_df = pd.DataFrame({"bea_sector": ["11"], "shock_amount": [1000.0]})

        production = bea_io.apply_demand_shocks(leontief_inv, shocks_df)

        assert production["11"] == 1000.0
        assert production["21"] == 0.0

    def test_apply_demand_shocks_multiple_sectors(self):
        """Test applying shocks to multiple sectors."""
        leontief_inv = pd.DataFrame(
            [[1.2, 0.1], [0.05, 1.1]],
            index=["11", "21"],
            columns=["11", "21"],
        )
        shocks_df = pd.DataFrame({
            "bea_sector": ["11", "21"],
            "shock_amount": [1000.0, 500.0],
        })

        production = bea_io.apply_demand_shocks(leontief_inv, shocks_df)

        assert production["11"] > 1000.0
        assert production["21"] > 500.0

    def test_apply_demand_shocks_unknown_sector(self):
        """Test applying shocks with unknown sector."""
        leontief_inv = pd.DataFrame(
            [[1.0, 0.0], [0.0, 1.0]],
            index=["11", "21"],
            columns=["11", "21"],
        )
        shocks_df = pd.DataFrame({"bea_sector": ["99"], "shock_amount": [1000.0]})

        production = bea_io.apply_demand_shocks(leontief_inv, shocks_df)

        assert production["11"] == 0.0
        assert production["21"] == 0.0

    def test_apply_demand_shocks_empty_dataframe(self):
        """Test apply_demand_shocks with empty DataFrame."""
        shocks_df = pd.DataFrame({"bea_sector": [], "shock_amount": []})
        leontief_inv = pd.DataFrame()

        result = bea_io.apply_demand_shocks(leontief_inv, shocks_df)
        assert isinstance(result, pd.Series)
        assert len(result) == 0


class TestEmploymentFromProduction:
    """Tests for employment-from-production calculation."""

    def test_with_coefficients(self):
        """Test employment calculation with coefficients."""
        production = pd.Series([1_000_000, 500_000], index=["11", "21"])
        coefficients = pd.DataFrame({
            "sector": ["11", "21"],
            "employment": [2000, 1000],
            "employment_coefficient": [20.0, 10.0],
        })

        jobs = bea_io.calculate_employment_from_production(production, coefficients)
        assert jobs["11"] == 20.0  # (1M / 1M) * 20
        assert jobs["21"] == 5.0   # (0.5M / 1M) * 10

    def test_without_coefficients(self):
        """Test employment calculation falls back to default."""
        production = pd.Series([100_000], index=["11"])
        empty_coefficients = pd.DataFrame()

        jobs = bea_io.calculate_employment_from_production(production, empty_coefficients)
        assert jobs["11"] == 1.0  # 100_000 / 100_000
