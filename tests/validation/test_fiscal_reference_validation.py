"""Validation tests against reference implementation and edge cases.

These tests validate that the fiscal returns analysis produces reasonable
results and handles edge cases correctly. When a reference R implementation
is available, these tests can be extended to validate exact numerical results.
"""

from decimal import Decimal

import pandas as pd
import pytest

from src.transformers.fiscal import FiscalComponentCalculator, FiscalROICalculator, FiscalTaxEstimator


class TestBoundaryConditions:
    """Test boundary conditions and edge cases."""

    def test_zero_investment_roi(self):
        """Test ROI calculation with very small investment (edge case)."""
        calculator = FiscalROICalculator()
        tax_estimates = pd.DataFrame([{"total_tax_receipt": Decimal("100000")}])

        # Use very small positive investment to test edge case behavior
        # (validator requires positive investment, so use 0.01 instead of 0)
        summary = calculator.calculate_roi_summary(
            tax_estimates, sbir_investment=Decimal("0.01"), discount_rate=0.03
        )

        # ROI ratio should be very large (approaching infinity for near-zero investment)
        assert summary.roi_ratio >= 0
        assert summary.roi_ratio > 1000  # Should be very large with such small investment

    def test_zero_tax_receipts(self):
        """Test ROI calculation with zero tax receipts."""
        calculator = FiscalROICalculator()
        tax_estimates = pd.DataFrame([{"total_tax_receipt": Decimal("0")}])

        summary = calculator.calculate_roi_summary(
            tax_estimates, sbir_investment=Decimal("100000"), discount_rate=0.03
        )

        assert summary.roi_ratio == 0.0
        assert summary.net_fiscal_return < Decimal("0")

    def test_very_small_amounts(self):
        """Test calculations with very small monetary amounts."""
        estimator = FiscalTaxEstimator()

        # Very small wage impact
        tax = estimator.estimate_payroll_tax(Decimal("1.00"))
        assert tax >= Decimal("0")

        # Very small consumption
        tax = estimator.estimate_excise_tax(Decimal("0.01"))
        assert tax >= Decimal("0")

    def test_very_large_amounts(self):
        """Test calculations with very large monetary amounts."""
        estimator = FiscalTaxEstimator()

        # Very large wage impact (test for overflow)
        tax = estimator.estimate_payroll_tax(Decimal("1000000000"))
        assert tax > Decimal("0")
        assert tax < Decimal("1000000000")  # Should be reasonable

    def test_missing_components(self):
        """Test component calculator handles missing components."""
        calculator = FiscalComponentCalculator()

        impacts_df = pd.DataFrame(
            [
                {
                    "state": "CA",
                    "bea_sector": "11",
                    "fiscal_year": 2023,
                    # Missing component columns
                }
            ]
        )

        result = calculator.extract_components(impacts_df)
        assert len(result) == 1
        assert result.iloc[0]["component_total"] == Decimal("0")


class TestReasonablenessChecks:
    """Test that results are reasonable and consistent."""

    def test_tax_rates_reasonable(self):
        """Test that estimated tax rates are within reasonable bounds."""
        estimator = FiscalTaxEstimator()

        wage = Decimal("100000")
        gos = Decimal("100000")
        consumption = Decimal("100000")

        income_tax = estimator.estimate_individual_income_tax(wage, Decimal("0"))
        payroll_tax = estimator.estimate_payroll_tax(wage)
        corporate_tax = estimator.estimate_corporate_income_tax(gos)
        excise_tax = estimator.estimate_excise_tax(consumption)

        # Check effective rates are reasonable
        income_rate = float(income_tax / wage) if wage > 0 else 0
        assert 0.0 <= income_rate <= 0.50  # Should be between 0-50%

        payroll_rate = float(payroll_tax / wage) if wage > 0 else 0
        assert 0.10 <= payroll_rate <= 0.20  # Payroll is ~15%

        corporate_rate = float(corporate_tax / gos) if gos > 0 else 0
        assert 0.15 <= corporate_rate <= 0.21  # Corporate is ~18%

        excise_rate = float(excise_tax / consumption) if consumption > 0 else 0
        assert 0.0 <= excise_rate <= 0.10  # Excise is ~3%

    def test_roi_consistency(self):
        """Test ROI metrics are internally consistent."""
        calculator = FiscalROICalculator()
        tax_estimates = pd.DataFrame(
            [
                {"total_tax_receipt": Decimal("150000")},
                {"total_tax_receipt": Decimal("50000")},
            ]
        )

        summary = calculator.calculate_roi_summary(
            tax_estimates, sbir_investment=Decimal("100000"), discount_rate=0.03
        )

        # Check consistency
        assert summary.roi_ratio == summary.benefit_cost_ratio
        assert (
            summary.net_fiscal_return == summary.total_tax_receipts - summary.total_sbir_investment
        )

        # Check confidence intervals
        assert summary.confidence_interval_low <= summary.total_tax_receipts
        assert summary.confidence_interval_high >= summary.total_tax_receipts

    def test_component_sum_validation(self):
        """Test that component sums are validated correctly."""
        calculator = FiscalComponentCalculator()

        impacts_df = pd.DataFrame(
            [
                {
                    "state": "CA",
                    "bea_sector": "11",
                    "fiscal_year": 2023,
                    "wage_impact": Decimal("40000"),
                    "proprietor_income_impact": Decimal("30000"),
                    "gross_operating_surplus": Decimal("20000"),
                    "consumption_impact": Decimal("10000"),
                    "production_impact": Decimal("100000"),
                }
            ]
        )

        result = calculator.extract_components(impacts_df)

        # Components should sum to production impact
        component_total = result.iloc[0]["component_total"]
        assert component_total == Decimal("100000")
        assert result.iloc[0]["component_valid"] is True


class TestNumericalStability:
    """Test numerical stability and precision."""

    def test_decimal_precision(self):
        """Test that Decimal precision is maintained."""
        estimator = FiscalTaxEstimator()

        # Use precise decimal amounts
        wage = Decimal("123456.78")
        tax = estimator.estimate_payroll_tax(wage)

        # Should maintain precision
        assert isinstance(tax, Decimal)
        assert tax > Decimal("0")

    def test_large_dataset_stability(self):
        """Test stability with large datasets."""
        calculator = FiscalComponentCalculator()

        # Create large impacts DataFrame
        impacts_df = pd.DataFrame(
            [
                {
                    "state": f"ST{i % 50}",
                    "bea_sector": str(i % 100),
                    "fiscal_year": 2023 + (i % 5),
                    "wage_impact": Decimal(f"{1000 + i}"),
                    "proprietor_income_impact": Decimal(f"{500 + i}"),
                    "gross_operating_surplus": Decimal(f"{300 + i}"),
                    "consumption_impact": Decimal(f"{200 + i}"),
                }
                for i in range(10000)
            ]
        )

        result = calculator.extract_components(impacts_df)

        # Should process all rows without error
        assert len(result) == 10000
        assert all(result["component_valid"].notna())


class TestReferenceValidation:
    """Tests for validating against reference implementation (when available)."""

    @pytest.mark.skip(reason="Requires R reference implementation")
    def test_validate_against_r_reference(self):
        """Test that Python implementation matches R reference results.

        This test should be enabled when R reference implementation is available.
        It validates that key calculations (tax estimates, ROI metrics) match
        the reference within acceptable numerical precision.
        """
        # Placeholder for R reference validation
        # Would compare:
        # - Tax estimates for same inputs
        # - ROI calculations
        # - Component aggregations
        pass

    def test_sensitivity_analysis_consistency(self):
        """Test that sensitivity analysis produces consistent results."""
        from src.transformers.fiscal_parameter_sweep import FiscalParameterSweep

        sweep = FiscalParameterSweep()

        # Generate scenarios with same seed
        scenarios1 = sweep.generate_monte_carlo_scenarios(10, random_seed=42)
        scenarios2 = sweep.generate_monte_carlo_scenarios(10, random_seed=42)

        # Should be identical with same seed
        assert len(scenarios1) == len(scenarios2)
        for s1, s2 in zip(scenarios1, scenarios2, strict=False):
            assert s1.scenario_id == s2.scenario_id
            # Parameters should be very close (within numerical precision)
            for param in s1.parameters:
                assert abs(s1.parameters[param] - s2.parameters[param]) < 0.0001
