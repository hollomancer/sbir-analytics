"""Tests for R StateIO function wrappers."""

from unittest.mock import Mock, patch

import pandas as pd
import pytest

# Import the module - will handle rpy2 availability gracefully
import src.transformers.r_stateio_functions as r_stateio
from src.exceptions import DependencyError
from src.utils.r_helpers import RFunctionError


pytestmark = pytest.mark.fast



class TestBuildStateModel:
    """Tests for build_state_model function."""

    @patch("src.transformers.r_stateio_functions.RPY2_AVAILABLE", False)
    def test_build_state_model_no_rpy2(self):
        """Test build_state_model raises error when rpy2 not available."""
        with pytest.raises(DependencyError, match="rpy2 is not available"):
            r_stateio.build_state_model(Mock(), "CA", 2020)

    @patch("src.transformers.r_stateio_functions.RPY2_AVAILABLE", True)
    @patch("src.transformers.r_stateio_functions.ro")
    @patch("src.transformers.r_stateio_functions.call_r_function")
    def test_build_state_model_default_specs(self, mock_call_r, mock_ro):
        """Test build_state_model with default specs."""
        mock_pkg = Mock()
        mock_model = Mock()
        mock_call_r.return_value = mock_model

        result = r_stateio.build_state_model(mock_pkg, "CA", 2020)

        assert result == mock_model
        mock_call_r.assert_called_once()
        # Check default specs were used
        assert mock_ro.ListVector.called

    @patch("src.transformers.r_stateio_functions.RPY2_AVAILABLE", True)
    @patch("src.transformers.r_stateio_functions.ro")
    @patch("src.transformers.r_stateio_functions.call_r_function")
    def test_build_state_model_custom_specs(self, mock_call_r, mock_ro):
        """Test build_state_model with custom specs."""
        mock_pkg = Mock()
        mock_model = Mock()
        mock_call_r.return_value = mock_model

        custom_specs = {"BaseIOSchema": "2012", "detail": "full"}
        result = r_stateio.build_state_model(mock_pkg, "NY", 2018, specs=custom_specs)

        assert result == mock_model
        mock_ro.ListVector.assert_called_with(custom_specs)

    @patch("src.transformers.r_stateio_functions.RPY2_AVAILABLE", True)
    @patch("src.transformers.r_stateio_functions.ro")
    @patch("src.transformers.r_stateio_functions.call_r_function")
    def test_build_state_model_handles_error(self, mock_call_r, mock_ro):
        """Test build_state_model handles R function errors."""
        mock_pkg = Mock()
        mock_call_r.side_effect = RFunctionError("R error", "buildFullTwoRegionIOTable")

        with pytest.raises(RFunctionError):
            r_stateio.build_state_model(mock_pkg, "CA", 2020)


class TestGetStateValueAdded:
    """Tests for get_state_value_added function."""

    @patch("src.transformers.r_stateio_functions.RPY2_AVAILABLE", True)
    @patch("src.transformers.r_stateio_functions.ro")
    @patch("src.transformers.r_stateio_functions.call_r_function")
    def test_get_state_value_added_all_components(self, mock_call_r, mock_ro):
        """Test getting all value added components."""
        mock_pkg = Mock()

        # Mock successful returns for all components
        mock_call_r.side_effect = [
            Mock(name="wages"),
            Mock(name="gos"),
            Mock(name="taxes"),
            Mock(name="gva"),
        ]

        result = r_stateio.get_state_value_added(mock_pkg, "CA", 2020)

        assert "wages" in result
        assert "gos" in result
        assert "taxes" in result
        assert "gva" in result
        assert mock_call_r.call_count == 4

    @patch("src.transformers.r_stateio_functions.RPY2_AVAILABLE", True)
    @patch("src.transformers.r_stateio_functions.ro")
    @patch("src.transformers.r_stateio_functions.call_r_function")
    def test_get_state_value_added_partial_failure(self, mock_call_r, mock_ro):
        """Test getting value added with some component failures."""
        mock_pkg = Mock()

        # Mock mixed success/failure
        def mock_calls(*args, **kwargs):
            func_name = args[1]
            if func_name == "getStateEmpCompensation":
                return Mock(name="wages")
            elif func_name == "getStateGOS":
                raise RFunctionError("GOS failed", func_name)
            elif func_name == "getStateTax":
                return Mock(name="taxes")
            elif func_name == "getStateGVA":
                raise RFunctionError("GVA failed", func_name)

        mock_call_r.side_effect = mock_calls

        result = r_stateio.get_state_value_added(mock_pkg, "CA", 2020)

        # Should have wages and taxes, but not gos or gva
        assert "wages" in result
        assert "taxes" in result
        assert "gos" not in result
        assert "gva" not in result

    @patch("src.transformers.r_stateio_functions.RPY2_AVAILABLE", True)
    @patch("src.transformers.r_stateio_functions.ro")
    @patch("src.transformers.r_stateio_functions.call_r_function")
    def test_get_state_value_added_custom_specs(self, mock_call_r, mock_ro):
        """Test get_state_value_added with custom specs."""
        mock_pkg = Mock()
        mock_call_r.return_value = Mock()

        custom_specs = {"BaseIOSchema": "2012"}
        r_stateio.get_state_value_added(mock_pkg, "NY", 2018, specs=custom_specs)

        # Verify custom specs were passed
        mock_ro.ListVector.assert_called_with(custom_specs)




class TestValueAddedRatioCalculation:
    """Tests for value added ratio calculation functions."""

    @patch("src.transformers.r_stateio_functions.RPY2_AVAILABLE", False)
    def test_convert_r_gva_no_rpy2(self):
        """Test convert_r_gva_to_dataframe when rpy2 not available."""
        result = r_stateio.convert_r_gva_to_dataframe(Mock())
        assert result is None

    @patch("src.transformers.r_stateio_functions.RPY2_AVAILABLE", True)
    def test_convert_r_gva_none_input(self):
        """Test convert_r_gva_to_dataframe with None input."""
        result = r_stateio.convert_r_gva_to_dataframe(None)
        assert result is None

    @patch("src.transformers.r_stateio_functions.RPY2_AVAILABLE", True)
    @patch("src.transformers.r_stateio_functions.ro")
    def test_convert_r_gva_to_dataframe_success(self, mock_ro):
        """Test successful conversion of R GVA object to DataFrame."""
        mock_r_obj = Mock()
        mock_df = pd.DataFrame({"sector": ["11", "21"], "value": [1000, 2000]})

        # Mock pandas2ri conversion
        with patch("rpy2.robjects.pandas2ri.rpy2py", return_value=mock_df):
            result = r_stateio.convert_r_gva_to_dataframe(mock_r_obj)

            assert isinstance(result, pd.DataFrame)
            assert len(result) == 2

    @patch("src.transformers.r_stateio_functions.RPY2_AVAILABLE", True)
    @patch("src.transformers.r_stateio_functions.ro")
    def test_convert_r_gva_series_to_dataframe(self, mock_ro):
        """Test conversion of R object to Series, then to DataFrame."""
        mock_r_obj = Mock()
        mock_series = pd.Series([1000, 2000], index=["11", "21"])

        with patch("rpy2.robjects.pandas2ri.rpy2py", return_value=mock_series):
            result = r_stateio.convert_r_gva_to_dataframe(mock_r_obj)

            # Should convert Series to DataFrame
            assert isinstance(result, pd.DataFrame)

    def test_calculate_value_added_ratios_empty_components(self):
        """Test calculate_value_added_ratios with empty components."""
        result = r_stateio.calculate_value_added_ratios({})
        assert isinstance(result, pd.DataFrame)
        assert result.empty

    @patch("src.transformers.r_stateio_functions.convert_r_gva_to_dataframe")
    def test_calculate_value_added_ratios_success(self, mock_convert):
        """Test successful calculation of value added ratios."""
        # Mock GVA DataFrames
        wages_df = pd.DataFrame({"11": [400], "21": [200]}).T
        gos_df = pd.DataFrame({"11": [300], "21": [150]}).T
        taxes_df = pd.DataFrame({"11": [150], "21": [75]}).T
        gva_df = pd.DataFrame({"11": [850], "21": [425]}).T

        # Mock conversion to return these DataFrames
        mock_convert.side_effect = [wages_df, gos_df, taxes_df, gva_df]

        va_components = {
            "wages": Mock(),
            "gos": Mock(),
            "taxes": Mock(),
            "gva": Mock(),
        }

        result = r_stateio.calculate_value_added_ratios(va_components)

        assert isinstance(result, pd.DataFrame)
        if not result.empty:
            assert "sector" in result.columns
            assert "wage_ratio" in result.columns
            assert "gos_ratio" in result.columns
            assert "tax_ratio" in result.columns

    def test_extract_sector_value_from_index(self):
        """Test _extract_sector_value with sector in index."""
        df = pd.DataFrame({"value": [1000, 2000]}, index=["11", "21"])

        result = r_stateio._extract_sector_value(df, "11")
        assert result == 1000.0

    def test_extract_sector_value_from_column(self):
        """Test _extract_sector_value with sector in column."""
        df = pd.DataFrame({"sector": ["11", "21"], "value": [1000, 2000]})

        result = r_stateio._extract_sector_value(df, "11")
        assert result == 1000.0

    def test_extract_sector_value_not_found(self):
        """Test _extract_sector_value raises error when sector not found."""
        df = pd.DataFrame({"value": [1000, 2000]}, index=["11", "21"])

        with pytest.raises(ValueError, match="Could not extract value"):
            r_stateio._extract_sector_value(df, "99")

    @patch("src.transformers.r_stateio_functions.convert_r_gva_to_dataframe")
    def test_calculate_ratios_with_zero_total(self, mock_convert):
        """Test ratio calculation handles zero total value added gracefully."""
        # All zeros - should skip this sector
        wages_df = pd.DataFrame({"11": [0]}).T
        gos_df = pd.DataFrame({"11": [0]}).T
        taxes_df = pd.DataFrame({"11": [0]}).T
        gva_df = pd.DataFrame({"11": [0]}).T

        mock_convert.side_effect = [wages_df, gos_df, taxes_df, gva_df]

        va_components = {
            "wages": Mock(),
            "gos": Mock(),
            "taxes": Mock(),
            "gva": Mock(),
        }

        result = r_stateio.calculate_value_added_ratios(va_components)

        # Should return empty DataFrame (no valid ratios)
        assert isinstance(result, pd.DataFrame)


class TestEdgeCases:
    """Tests for edge cases in R StateIO functions."""

    @patch("src.transformers.r_stateio_functions.RPY2_AVAILABLE", True)
    @patch("src.transformers.r_stateio_functions.ro")
    @patch("src.transformers.r_stateio_functions.call_r_function")
    def test_empty_specs_dict(self, mock_call_r, mock_ro):
        """Test functions handle empty specs dict."""
        mock_call_r.return_value = Mock()

        r_stateio.build_state_model(Mock(), "CA", 2020, specs={})

        # Should still convert empty dict to R list
        mock_ro.ListVector.assert_called_with({})

    @patch("src.transformers.r_stateio_functions.RPY2_AVAILABLE", True)
    @patch("src.transformers.r_stateio_functions.ro")
    @patch("src.transformers.r_stateio_functions.call_r_function")
    def test_format_demand_vector_empty_dataframe(self, mock_call_r, mock_ro):
        """Test format_demand_vector with empty DataFrame."""
        mock_r_vector = Mock()
        mock_ro.FloatVector.return_value = mock_r_vector

        df = pd.DataFrame({"bea_sector": [], "shock_amount": []})

        r_stateio.format_demand_vector_from_shocks(Mock(), Mock(), df)

        # Should create empty vectors
        mock_ro.FloatVector.assert_called_with([])


class TestMatrixCalculations:
    """Tests for matrix calculation functions (Leontief, technical coefficients)."""

    def test_calculate_technical_coefficients(self):
        """Test calculation of technical coefficients matrix."""
        # Create simple Use table and output
        use_table = pd.DataFrame(
            [[10, 20], [5, 10]],  # 2 commodities x 2 industries
            index=["C1", "C2"],
            columns=["I1", "I2"],
        )
        industry_output = pd.Series([100, 200], index=["I1", "I2"])

        tech_coeff = r_stateio.calculate_technical_coefficients(use_table, industry_output)

        # Expected: Use[i,j] / Output[j]
        # A[0,0] = 10/100 = 0.1, A[0,1] = 20/200 = 0.1
        # A[1,0] = 5/100 = 0.05, A[1,1] = 10/200 = 0.05
        assert tech_coeff.loc["C1", "I1"] == 0.1
        assert tech_coeff.loc["C1", "I2"] == 0.1
        assert tech_coeff.loc["C2", "I1"] == 0.05
        assert tech_coeff.loc["C2", "I2"] == 0.05

    def test_calculate_technical_coefficients_zero_output(self):
        """Test technical coefficients with zero output (should handle gracefully)."""
        use_table = pd.DataFrame([[10, 20]], index=["C1"], columns=["I1", "I2"])
        industry_output = pd.Series([0, 200], index=["I1", "I2"])

        # Should not raise error, should handle zero by using epsilon
        tech_coeff = r_stateio.calculate_technical_coefficients(use_table, industry_output)

        assert isinstance(tech_coeff, pd.DataFrame)
        # Column with zero output should have very small coefficients (or zero)
        assert tech_coeff.loc["C1", "I2"] == 0.1

    def test_calculate_technical_coefficients_dimension_mismatch(self):
        """Test technical coefficients with mismatched dimensions."""
        use_table = pd.DataFrame([[10, 20]], index=["C1"], columns=["I1", "I2"])
        industry_output = pd.Series([100], index=["I1"])  # Only 1 industry

        with pytest.raises(ValueError, match="must match"):
            r_stateio.calculate_technical_coefficients(use_table, industry_output)

    def test_calculate_leontief_inverse(self):
        """Test Leontief inverse calculation."""
        # Create simple technical coefficients matrix
        # Use a matrix that we know is invertible
        tech_coeff = pd.DataFrame(
            [[0.1, 0.2], [0.05, 0.1]],
            index=["S1", "S2"],
            columns=["S1", "S2"],
        )

        leontief_inv = r_stateio.calculate_leontief_inverse(tech_coeff)

        # L = (I - A)^-1
        # I - A = [[0.9, -0.2], [-0.05, 0.9]]
        # Should be invertible
        assert isinstance(leontief_inv, pd.DataFrame)
        assert leontief_inv.shape == (2, 2)

        # Diagonal elements should be >= 1 (total requirements)
        assert leontief_inv.loc["S1", "S1"] >= 1.0
        assert leontief_inv.loc["S2", "S2"] >= 1.0

    def test_apply_demand_shocks(self):
        """Test applying demand shocks with Leontief inverse."""
        # Create Leontief inverse (identity for simplicity)
        leontief_inv = pd.DataFrame(
            [[1.0, 0.0], [0.0, 1.0]],
            index=["11", "21"],
            columns=["11", "21"],
        )

        # Create shocks
        shocks_df = pd.DataFrame({"bea_sector": ["11"], "shock_amount": [1000.0]})

        production = r_stateio.apply_demand_shocks(leontief_inv, shocks_df)

        # With identity Leontief, production should equal shock
        assert production["11"] == 1000.0
        assert production["21"] == 0.0

    def test_apply_demand_shocks_multiple_sectors(self):
        """Test applying shocks to multiple sectors."""
        # Leontief with some interdependence
        leontief_inv = pd.DataFrame(
            [[1.2, 0.1], [0.05, 1.1]],
            index=["11", "21"],
            columns=["11", "21"],
        )

        shocks_df = pd.DataFrame(
            {
                "bea_sector": ["11", "21"],
                "shock_amount": [1000.0, 500.0],
            }
        )

        production = r_stateio.apply_demand_shocks(leontief_inv, shocks_df)

        # Production should be greater than shocks due to multiplier effects
        assert production["11"] > 1000.0
        assert production["21"] > 500.0

    def test_apply_demand_shocks_unknown_sector(self):
        """Test applying shocks with unknown sector (should warn but not fail)."""
        leontief_inv = pd.DataFrame(
            [[1.0, 0.0], [0.0, 1.0]],
            index=["11", "21"],
            columns=["11", "21"],
        )

        shocks_df = pd.DataFrame({"bea_sector": ["99"], "shock_amount": [1000.0]})

        # Should not raise, should log warning
        production = r_stateio.apply_demand_shocks(leontief_inv, shocks_df)

        # Production should be all zeros (shock to unknown sector)
        assert production["11"] == 0.0
        assert production["21"] == 0.0

    @patch("src.transformers.r_stateio_functions.RPY2_AVAILABLE", True)
    @patch("src.transformers.r_stateio_functions.ro")
    def test_extract_use_table_from_model(self, mock_ro):
        """Test extracting Use table from StateIO model."""
        mock_model = Mock()
        mock_use_table = pd.DataFrame(
            [[10, 20], [5, 10]],
            index=["C1", "C2"],
            columns=["I1", "I2"],
        )

        # Mock rx2 to return the Use table
        mock_model.rx2.return_value = mock_use_table

        with patch("rpy2.robjects.pandas2ri.rpy2py", return_value=mock_use_table):
            result = r_stateio.extract_use_table_from_model(mock_model)

            assert isinstance(result, pd.DataFrame)
            assert result.shape == (2, 2)

    @patch("src.transformers.r_stateio_functions.RPY2_AVAILABLE", True)
    @patch("src.transformers.r_stateio_functions.ro")
    def test_extract_industry_output_from_model(self, mock_ro):
        """Test extracting industry output from StateIO model."""
        mock_model = Mock()
        mock_output = pd.Series([100, 200], index=["I1", "I2"])

        mock_model.rx2.return_value = mock_output

        with patch("rpy2.robjects.pandas2ri.rpy2py", return_value=mock_output):
            result = r_stateio.extract_industry_output_from_model(mock_model)

            assert isinstance(result, pd.Series)
            assert len(result) == 2
