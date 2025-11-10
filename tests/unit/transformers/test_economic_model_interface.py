"""Tests for economic model interface."""

from decimal import Decimal

import pandas as pd
import pytest

from src.exceptions import ValidationError
from src.transformers.economic_model_interface import EconomicImpactResult, EconomicModelInterface


pytestmark = pytest.mark.fast



class TestEconomicImpactResult:
    """Tests for EconomicImpactResult dataclass."""

    def test_economic_impact_result_initialization(self):
        """Test EconomicImpactResult initialization with all fields."""
        result = EconomicImpactResult(
            state="CA",
            bea_sector="11",
            fiscal_year=2020,
            wage_impact=Decimal("1000.00"),
            proprietor_income_impact=Decimal("200.00"),
            gross_operating_surplus=Decimal("300.00"),
            consumption_impact=Decimal("500.00"),
            tax_impact=Decimal("150.00"),
            production_impact=Decimal("2000.00"),
            model_version="StateIO_v2.1",
            model_methodology="IO",
            multiplier_version="2020.1",
            confidence=0.95,
            quality_flags=[],
            metadata={},
        )

        assert result.state == "CA"
        assert result.bea_sector == "11"
        assert result.fiscal_year == 2020
        assert result.wage_impact == Decimal("1000.00")
        assert result.proprietor_income_impact == Decimal("200.00")
        assert result.gross_operating_surplus == Decimal("300.00")
        assert result.consumption_impact == Decimal("500.00")
        assert result.tax_impact == Decimal("150.00")
        assert result.production_impact == Decimal("2000.00")
        assert result.model_version == "StateIO_v2.1"
        assert result.model_methodology == "IO"
        assert result.multiplier_version == "2020.1"
        assert result.confidence == 0.95
        assert result.quality_flags == []
        assert result.metadata == {}

    def test_economic_impact_result_with_quality_flags(self):
        """Test EconomicImpactResult with quality flags."""
        result = EconomicImpactResult(
            state="NY",
            bea_sector="21",
            fiscal_year=2021,
            wage_impact=Decimal("500.00"),
            proprietor_income_impact=Decimal("100.00"),
            gross_operating_surplus=Decimal("150.00"),
            consumption_impact=Decimal("250.00"),
            tax_impact=Decimal("75.00"),
            production_impact=Decimal("1000.00"),
            model_version="StateIO_v2.1",
            model_methodology="IO",
            multiplier_version=None,
            confidence=0.85,
            quality_flags=["low_employment_data", "estimated_multiplier"],
            metadata={"note": "Rural area estimate"},
        )

        assert result.quality_flags == ["low_employment_data", "estimated_multiplier"]
        assert result.metadata == {"note": "Rural area estimate"}
        assert result.multiplier_version is None

    def test_economic_impact_result_with_metadata(self):
        """Test EconomicImpactResult with custom metadata."""
        metadata = {
            "source": "BEA",
            "adjustment_factor": 1.05,
            "inflation_index": "CPI-U",
        }

        result = EconomicImpactResult(
            state="TX",
            bea_sector="22",
            fiscal_year=2019,
            wage_impact=Decimal("750.00"),
            proprietor_income_impact=Decimal("150.00"),
            gross_operating_surplus=Decimal("200.00"),
            consumption_impact=Decimal("400.00"),
            tax_impact=Decimal("100.00"),
            production_impact=Decimal("1500.00"),
            model_version="StateIO_v2.0",
            model_methodology="RIMS",
            multiplier_version="2019.2",
            confidence=0.90,
            quality_flags=[],
            metadata=metadata,
        )

        assert result.metadata == metadata

    def test_economic_impact_result_zero_values(self):
        """Test EconomicImpactResult with zero impact values."""
        result = EconomicImpactResult(
            state="FL",
            bea_sector="23",
            fiscal_year=2020,
            wage_impact=Decimal("0.00"),
            proprietor_income_impact=Decimal("0.00"),
            gross_operating_surplus=Decimal("0.00"),
            consumption_impact=Decimal("0.00"),
            tax_impact=Decimal("0.00"),
            production_impact=Decimal("0.00"),
            model_version="StateIO_v2.1",
            model_methodology="IO",
            multiplier_version="2020.1",
            confidence=0.50,
            quality_flags=["no_data"],
            metadata={},
        )

        assert result.wage_impact == Decimal("0.00")
        assert result.tax_impact == Decimal("0.00")


class MockEconomicModel(EconomicModelInterface):
    """Mock implementation of EconomicModelInterface for testing."""

    def __init__(self, available: bool = True, version: str = "Mock_v1.0"):
        self.available = available
        self.version = version

    def compute_impacts(
        self,
        shocks_df: pd.DataFrame,
        model_version: str | None = None,
    ) -> pd.DataFrame:
        """Mock compute_impacts that returns simple results."""
        self.validate_input(shocks_df)

        results = []
        for _, row in shocks_df.iterrows():
            results.append(
                {
                    "state": row["state"],
                    "bea_sector": row["bea_sector"],
                    "fiscal_year": row["fiscal_year"],
                    "wage_impact": row["shock_amount"] * 0.5,
                    "proprietor_income_impact": row["shock_amount"] * 0.1,
                    "gross_operating_surplus": row["shock_amount"] * 0.15,
                    "consumption_impact": row["shock_amount"] * 0.25,
                    "tax_impact": row["shock_amount"] * 0.1,
                    "production_impact": row["shock_amount"] * 1.5,
                    "model_version": model_version or self.version,
                    "confidence": 0.95,
                    "quality_flags": [],
                }
            )

        return pd.DataFrame(results)

    def get_model_version(self) -> str:
        """Return mock model version."""
        return self.version

    def is_available(self) -> bool:
        """Return mock availability status."""
        return self.available


class TestEconomicModelInterfaceValidation:
    """Tests for validate_input method."""

    def test_validate_input_valid_dataframe(self):
        """Test validate_input with valid DataFrame."""
        model = MockEconomicModel()

        df = pd.DataFrame(
            {
                "state": ["CA", "NY", "TX"],
                "bea_sector": ["11", "21", "22"],
                "fiscal_year": [2020, 2020, 2020],
                "shock_amount": [1000.0, 2000.0, 1500.0],
            }
        )

        # Should not raise
        model.validate_input(df)

    def test_validate_input_missing_column(self):
        """Test validate_input with missing required column."""
        model = MockEconomicModel()

        df = pd.DataFrame(
            {
                "state": ["CA"],
                "bea_sector": ["11"],
                "fiscal_year": [2020],
                # Missing shock_amount
            }
        )

        with pytest.raises(ValidationError, match="Missing required columns"):
            model.validate_input(df)

    def test_validate_input_missing_multiple_columns(self):
        """Test validate_input with multiple missing columns."""
        model = MockEconomicModel()

        df = pd.DataFrame(
            {
                "state": ["CA"],
                # Missing bea_sector, fiscal_year, shock_amount
            }
        )

        with pytest.raises(ValidationError) as exc_info:
            model.validate_input(df)

        error = exc_info.value
        assert "bea_sector" in str(error.details["missing_columns"])
        assert "fiscal_year" in str(error.details["missing_columns"])
        assert "shock_amount" in str(error.details["missing_columns"])

    def test_validate_input_invalid_state_code_length(self):
        """Test validate_input with invalid state code length."""
        model = MockEconomicModel()

        df = pd.DataFrame(
            {
                "state": ["CAL", "NY", "TEX"],  # CAL and TEX are too long
                "bea_sector": ["11", "21", "22"],
                "fiscal_year": [2020, 2020, 2020],
                "shock_amount": [1000.0, 2000.0, 1500.0],
            }
        )

        with pytest.raises(ValidationError, match="State codes must be exactly 2 letters"):
            model.validate_input(df)

    def test_validate_input_single_character_state(self):
        """Test validate_input with single character state code."""
        model = MockEconomicModel()

        df = pd.DataFrame(
            {
                "state": ["C", "NY"],  # C is too short
                "bea_sector": ["11", "21"],
                "fiscal_year": [2020, 2020],
                "shock_amount": [1000.0, 2000.0],
            }
        )

        with pytest.raises(ValidationError, match="State codes must be exactly 2 letters"):
            model.validate_input(df)

    def test_validate_input_negative_shock_amount(self):
        """Test validate_input with negative shock amount."""
        model = MockEconomicModel()

        df = pd.DataFrame(
            {
                "state": ["CA", "NY"],
                "bea_sector": ["11", "21"],
                "fiscal_year": [2020, 2020],
                "shock_amount": [1000.0, -500.0],  # Negative amount
            }
        )

        with pytest.raises(ValidationError, match="Shock amounts must be non-negative"):
            model.validate_input(df)

    def test_validate_input_multiple_negative_shocks(self):
        """Test validate_input with multiple negative shock amounts."""
        model = MockEconomicModel()

        df = pd.DataFrame(
            {
                "state": ["CA", "NY", "TX"],
                "bea_sector": ["11", "21", "22"],
                "fiscal_year": [2020, 2020, 2020],
                "shock_amount": [-100.0, -200.0, 1500.0],
            }
        )

        with pytest.raises(ValidationError) as exc_info:
            model.validate_input(df)

        error = exc_info.value
        assert error.details["negative_count"] == 2
        assert error.details["total_rows"] == 3

    def test_validate_input_zero_shock_amounts(self):
        """Test validate_input accepts zero shock amounts."""
        model = MockEconomicModel()

        df = pd.DataFrame(
            {
                "state": ["CA", "NY"],
                "bea_sector": ["11", "21"],
                "fiscal_year": [2020, 2020],
                "shock_amount": [0.0, 0.0],
            }
        )

        # Should not raise - zeros are valid
        model.validate_input(df)

    def test_validate_input_extra_columns(self):
        """Test validate_input accepts extra columns."""
        model = MockEconomicModel()

        df = pd.DataFrame(
            {
                "state": ["CA"],
                "bea_sector": ["11"],
                "fiscal_year": [2020],
                "shock_amount": [1000.0],
                "extra_column": ["extra_value"],
                "another_column": [123],
            }
        )

        # Should not raise - extra columns are fine
        model.validate_input(df)

    def test_validate_input_empty_dataframe(self):
        """Test validate_input with empty DataFrame."""
        model = MockEconomicModel()

        df = pd.DataFrame(
            {
                "state": [],
                "bea_sector": [],
                "fiscal_year": [],
                "shock_amount": [],
            }
        )

        # Should not raise - empty is valid structure
        model.validate_input(df)


class TestMockEconomicModel:
    """Tests for MockEconomicModel implementation."""

    def test_compute_impacts_basic(self):
        """Test compute_impacts with basic input."""
        model = MockEconomicModel()

        df = pd.DataFrame(
            {
                "state": ["CA"],
                "bea_sector": ["11"],
                "fiscal_year": [2020],
                "shock_amount": [1000.0],
            }
        )

        result = model.compute_impacts(df)

        assert len(result) == 1
        assert result.iloc[0]["state"] == "CA"
        assert result.iloc[0]["wage_impact"] == 500.0  # 0.5 * 1000
        assert result.iloc[0]["tax_impact"] == 100.0  # 0.1 * 1000
        assert result.iloc[0]["production_impact"] == 1500.0  # 1.5 * 1000

    def test_compute_impacts_multiple_states(self):
        """Test compute_impacts with multiple states."""
        model = MockEconomicModel()

        df = pd.DataFrame(
            {
                "state": ["CA", "NY", "TX"],
                "bea_sector": ["11", "21", "22"],
                "fiscal_year": [2020, 2020, 2020],
                "shock_amount": [1000.0, 2000.0, 1500.0],
            }
        )

        result = model.compute_impacts(df)

        assert len(result) == 3
        assert result["state"].tolist() == ["CA", "NY", "TX"]
        assert result["wage_impact"].tolist() == [500.0, 1000.0, 750.0]

    def test_compute_impacts_with_custom_version(self):
        """Test compute_impacts with custom model version."""
        model = MockEconomicModel(version="Mock_v1.0")

        df = pd.DataFrame(
            {
                "state": ["CA"],
                "bea_sector": ["11"],
                "fiscal_year": [2020],
                "shock_amount": [1000.0],
            }
        )

        result = model.compute_impacts(df, model_version="Custom_v2.0")

        assert result.iloc[0]["model_version"] == "Custom_v2.0"

    def test_get_model_version(self):
        """Test get_model_version returns correct version."""
        model = MockEconomicModel(version="Mock_v2.5")

        assert model.get_model_version() == "Mock_v2.5"

    def test_is_available_true(self):
        """Test is_available returns True when available."""
        model = MockEconomicModel(available=True)

        assert model.is_available() is True

    def test_is_available_false(self):
        """Test is_available returns False when not available."""
        model = MockEconomicModel(available=False)

        assert model.is_available() is False

    def test_compute_impacts_validates_input(self):
        """Test compute_impacts validates input before processing."""
        model = MockEconomicModel()

        df = pd.DataFrame(
            {
                "state": ["CA"],
                "bea_sector": ["11"],
                "fiscal_year": [2020],
                "shock_amount": [-1000.0],  # Invalid negative
            }
        )

        with pytest.raises(ValidationError):
            model.compute_impacts(df)


class TestEconomicModelInterfaceEdgeCases:
    """Tests for edge cases in EconomicModelInterface."""

    def test_validate_input_numeric_state_codes(self):
        """Test validate_input with numeric state codes converted to string."""
        model = MockEconomicModel()

        df = pd.DataFrame(
            {
                "state": [12, 34],  # Numeric but 2 digits
                "bea_sector": ["11", "21"],
                "fiscal_year": [2020, 2020],
                "shock_amount": [1000.0, 2000.0],
            }
        )

        # Should not raise - converts to string and validates length
        model.validate_input(df)

    def test_validate_input_mixed_case_states(self):
        """Test validate_input accepts mixed case state codes."""
        model = MockEconomicModel()

        df = pd.DataFrame(
            {
                "state": ["ca", "NY", "Tx"],
                "bea_sector": ["11", "21", "22"],
                "fiscal_year": [2020, 2020, 2020],
                "shock_amount": [1000.0, 2000.0, 1500.0],
            }
        )

        # Should not raise - accepts any 2-character codes
        model.validate_input(df)

    def test_validate_input_large_shock_amounts(self):
        """Test validate_input with very large shock amounts."""
        model = MockEconomicModel()

        df = pd.DataFrame(
            {
                "state": ["CA"],
                "bea_sector": ["11"],
                "fiscal_year": [2020],
                "shock_amount": [1e12],  # 1 trillion
            }
        )

        # Should not raise
        model.validate_input(df)

    def test_validate_input_error_details(self):
        """Test validate_input error includes detailed information."""
        model = MockEconomicModel()

        df = pd.DataFrame(
            {
                "state": ["CA"],
                "bea_sector": ["11"],
                # Missing fiscal_year and shock_amount
            }
        )

        with pytest.raises(ValidationError) as exc_info:
            model.validate_input(df)

        error = exc_info.value
        assert error.component == "transformer.economic_model"
        assert error.operation == "validate_shocks_input"
        assert "missing_columns" in error.details
        assert "required_columns" in error.details
        assert "provided_columns" in error.details

    def test_validate_input_invalid_states_error_details(self):
        """Test validate_input shows invalid state codes in error."""
        model = MockEconomicModel()

        df = pd.DataFrame(
            {
                "state": ["CAL", "NEW", "TX"],
                "bea_sector": ["11", "21", "22"],
                "fiscal_year": [2020, 2020, 2020],
                "shock_amount": [1000.0, 2000.0, 1500.0],
            }
        )

        with pytest.raises(ValidationError) as exc_info:
            model.validate_input(df)

        error = exc_info.value
        assert "invalid_states" in error.details
        # Should list invalid states (CAL and NEW)
        invalid_states = error.details["invalid_states"]
        assert "CAL" in invalid_states
        assert "NEW" in invalid_states

    def test_validate_input_many_invalid_states_truncates(self):
        """Test validate_input truncates list of invalid states to 10."""
        model = MockEconomicModel()

        # Create 15 invalid state codes
        invalid_states = [f"S{i:02d}" for i in range(15)]  # S00, S01, ..., S14
        df = pd.DataFrame(
            {
                "state": invalid_states,
                "bea_sector": ["11"] * 15,
                "fiscal_year": [2020] * 15,
                "shock_amount": [1000.0] * 15,
            }
        )

        with pytest.raises(ValidationError) as exc_info:
            model.validate_input(df)

        error = exc_info.value
        # Should only show first 10
        assert len(error.details["invalid_states"]) == 10

    def test_compute_impacts_preserves_input_order(self):
        """Test compute_impacts preserves input row order."""
        model = MockEconomicModel()

        df = pd.DataFrame(
            {
                "state": ["NY", "CA", "TX", "FL"],
                "bea_sector": ["21", "11", "22", "23"],
                "fiscal_year": [2019, 2020, 2021, 2022],
                "shock_amount": [2000.0, 1000.0, 1500.0, 1200.0],
            }
        )

        result = model.compute_impacts(df)

        assert result["state"].tolist() == ["NY", "CA", "TX", "FL"]
        assert result["fiscal_year"].tolist() == [2019, 2020, 2021, 2022]
