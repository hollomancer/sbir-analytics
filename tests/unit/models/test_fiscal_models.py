"""Tests for SBIR fiscal returns Pydantic models."""

from datetime import datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError


pytestmark = pytest.mark.fast

from src.models.fiscal_models import (
    EconomicShock,
    FiscalReturnSummary,
    GeographicResolution,
    InflationAdjustment,
    NAICSMapping,
    TaxImpactEstimate,
)


pytestmark = pytest.mark.fast



class TestEconomicShockModel:
    """Tests for the EconomicShock model."""

    def test_valid_economic_shock(self):
        """Test creating a valid economic shock."""
        shock = EconomicShock(
            state="CA",
            bea_sector="54",
            fiscal_year=2022,
            shock_amount=Decimal("1000000.00"),
            award_ids=["AWARD-001", "AWARD-002"],
            confidence=0.95,
            naics_coverage_rate=0.88,
            geographic_resolution_rate=1.0,
            base_year=2020,
        )
        assert shock.state == "CA"
        assert shock.bea_sector == "54"
        assert shock.fiscal_year == 2022
        assert shock.shock_amount == Decimal("1000000.00")
        assert len(shock.award_ids) == 2

    def test_state_validator_normalizes_uppercase(self):
        """Test state code validator normalizes to uppercase."""
        shock = EconomicShock(
            state="tx",
            bea_sector="54",
            fiscal_year=2022,
            shock_amount=Decimal("500000"),
            award_ids=["AWARD-003"],
            confidence=0.9,
            naics_coverage_rate=0.85,
            geographic_resolution_rate=0.95,
            base_year=2020,
        )
        assert shock.state == "TX"

    def test_state_validator_rejects_invalid_length(self):
        """Test state validator rejects non-2-letter codes."""
        with pytest.raises(ValidationError) as exc_info:
            EconomicShock(
                state="CAL",
                bea_sector="54",
                fiscal_year=2022,
                shock_amount=Decimal("500000"),
                award_ids=["AWARD-004"],
                confidence=0.9,
                naics_coverage_rate=0.85,
                geographic_resolution_rate=0.95,
                base_year=2020,
            )
        assert "State code must be exactly two letters" in str(exc_info.value)

    def test_state_validator_rejects_non_alpha(self):
        """Test state validator rejects non-alphabetic codes."""
        with pytest.raises(ValidationError) as exc_info:
            EconomicShock(
                state="C1",
                bea_sector="54",
                fiscal_year=2022,
                shock_amount=Decimal("500000"),
                award_ids=["AWARD-005"],
                confidence=0.9,
                naics_coverage_rate=0.85,
                geographic_resolution_rate=0.95,
                base_year=2020,
            )
        assert "State code must be exactly two letters" in str(exc_info.value)

    def test_fiscal_year_validator_accepts_valid_range(self):
        """Test fiscal_year validator accepts 1980-2030 range."""
        shock = EconomicShock(
            state="MA",
            bea_sector="54",
            fiscal_year=2025,
            shock_amount=Decimal("500000"),
            award_ids=["AWARD-006"],
            confidence=0.9,
            naics_coverage_rate=0.85,
            geographic_resolution_rate=0.95,
            base_year=2020,
        )
        assert shock.fiscal_year == 2025

    def test_fiscal_year_validator_rejects_too_early(self):
        """Test fiscal_year validator rejects years before 1980."""
        with pytest.raises(ValidationError) as exc_info:
            EconomicShock(
                state="NY",
                bea_sector="54",
                fiscal_year=1979,
                shock_amount=Decimal("500000"),
                award_ids=["AWARD-007"],
                confidence=0.9,
                naics_coverage_rate=0.85,
                geographic_resolution_rate=0.95,
                base_year=2020,
            )
        assert "Fiscal year must be between 1980 and 2030" in str(exc_info.value)

    def test_fiscal_year_validator_rejects_too_late(self):
        """Test fiscal_year validator rejects years after 2030."""
        with pytest.raises(ValidationError) as exc_info:
            EconomicShock(
                state="FL",
                bea_sector="54",
                fiscal_year=2031,
                shock_amount=Decimal("500000"),
                award_ids=["AWARD-008"],
                confidence=0.9,
                naics_coverage_rate=0.85,
                geographic_resolution_rate=0.95,
                base_year=2020,
            )
        assert "Fiscal year must be between 1980 and 2030" in str(exc_info.value)

    def test_shock_amount_validator_accepts_zero(self):
        """Test shock_amount validator accepts zero."""
        shock = EconomicShock(
            state="OH",
            bea_sector="54",
            fiscal_year=2022,
            shock_amount=Decimal("0"),
            award_ids=[],
            confidence=0.0,
            naics_coverage_rate=0.0,
            geographic_resolution_rate=0.0,
            base_year=2020,
        )
        assert shock.shock_amount == Decimal("0")

    def test_shock_amount_validator_rejects_negative(self):
        """Test shock_amount validator rejects negative amounts."""
        with pytest.raises(ValidationError) as exc_info:
            EconomicShock(
                state="TX",
                bea_sector="54",
                fiscal_year=2022,
                shock_amount=Decimal("-100"),
                award_ids=["AWARD-009"],
                confidence=0.9,
                naics_coverage_rate=0.85,
                geographic_resolution_rate=0.95,
                base_year=2020,
            )
        assert "Shock amount must be non-negative" in str(exc_info.value)

    def test_confidence_field_constraints(self):
        """Test confidence field has 0-1 constraints."""
        with pytest.raises(ValidationError):
            EconomicShock(
                state="CA",
                bea_sector="54",
                fiscal_year=2022,
                shock_amount=Decimal("500000"),
                award_ids=["AWARD-010"],
                confidence=1.5,  # Invalid: > 1.0
                naics_coverage_rate=0.85,
                geographic_resolution_rate=0.95,
                base_year=2020,
            )

    def test_created_at_default_factory(self):
        """Test created_at uses default factory."""
        shock = EconomicShock(
            state="WA",
            bea_sector="54",
            fiscal_year=2022,
            shock_amount=Decimal("500000"),
            award_ids=["AWARD-011"],
            confidence=0.9,
            naics_coverage_rate=0.85,
            geographic_resolution_rate=0.95,
            base_year=2020,
        )
        assert isinstance(shock.created_at, datetime)


class TestTaxImpactEstimateModel:
    """Tests for the TaxImpactEstimate model."""

    def test_valid_tax_impact_estimate(self):
        """Test creating a valid tax impact estimate."""
        estimate = TaxImpactEstimate(
            shock_id="SHOCK-001",
            state="CA",
            bea_sector="54",
            fiscal_year=2022,
            individual_income_tax=Decimal("50000"),
            payroll_tax=Decimal("30000"),
            corporate_income_tax=Decimal("20000"),
            excise_tax=Decimal("5000"),
            total_tax_receipt=Decimal("105000"),
            wage_impact=Decimal("500000"),
            proprietor_income_impact=Decimal("100000"),
            gross_operating_surplus=Decimal("200000"),
            consumption_impact=Decimal("300000"),
            confidence_interval=(Decimal("95000"), Decimal("115000")),
            methodology="StateIO_v2.1",
            tax_parameter_version="2022Q1",
            multiplier_version="v1.0",
        )
        assert estimate.shock_id == "SHOCK-001"
        assert estimate.total_tax_receipt == Decimal("105000")

    def test_tax_amounts_validator_rejects_negative(self):
        """Test tax amounts validator rejects negative values."""
        with pytest.raises(ValidationError) as exc_info:
            TaxImpactEstimate(
                shock_id="SHOCK-002",
                state="TX",
                bea_sector="54",
                fiscal_year=2022,
                individual_income_tax=Decimal("-1000"),  # Invalid
                payroll_tax=Decimal("30000"),
                corporate_income_tax=Decimal("20000"),
                excise_tax=Decimal("5000"),
                total_tax_receipt=Decimal("105000"),
                wage_impact=Decimal("500000"),
                proprietor_income_impact=Decimal("100000"),
                gross_operating_surplus=Decimal("200000"),
                consumption_impact=Decimal("300000"),
                confidence_interval=(Decimal("95000"), Decimal("115000")),
                methodology="StateIO_v2.1",
                tax_parameter_version="2022Q1",
                multiplier_version="v1.0",
            )
        assert "Tax amounts must be non-negative" in str(exc_info.value)

    def test_confidence_interval_validator_accepts_valid(self):
        """Test confidence interval validator accepts low <= high."""
        estimate = TaxImpactEstimate(
            shock_id="SHOCK-003",
            state="NY",
            bea_sector="54",
            fiscal_year=2022,
            individual_income_tax=Decimal("50000"),
            payroll_tax=Decimal("30000"),
            corporate_income_tax=Decimal("20000"),
            excise_tax=Decimal("5000"),
            total_tax_receipt=Decimal("105000"),
            wage_impact=Decimal("500000"),
            proprietor_income_impact=Decimal("100000"),
            gross_operating_surplus=Decimal("200000"),
            consumption_impact=Decimal("300000"),
            confidence_interval=(Decimal("100000"), Decimal("110000")),
            methodology="StateIO_v2.1",
            tax_parameter_version="2022Q1",
            multiplier_version="v1.0",
        )
        assert estimate.confidence_interval == (Decimal("100000"), Decimal("110000"))

    def test_confidence_interval_validator_rejects_invalid_order(self):
        """Test confidence interval validator rejects low > high."""
        with pytest.raises(ValidationError) as exc_info:
            TaxImpactEstimate(
                shock_id="SHOCK-004",
                state="FL",
                bea_sector="54",
                fiscal_year=2022,
                individual_income_tax=Decimal("50000"),
                payroll_tax=Decimal("30000"),
                corporate_income_tax=Decimal("20000"),
                excise_tax=Decimal("5000"),
                total_tax_receipt=Decimal("105000"),
                wage_impact=Decimal("500000"),
                proprietor_income_impact=Decimal("100000"),
                gross_operating_surplus=Decimal("200000"),
                consumption_impact=Decimal("300000"),
                confidence_interval=(Decimal("120000"), Decimal("100000")),  # Invalid
                methodology="StateIO_v2.1",
                tax_parameter_version="2022Q1",
                multiplier_version="v1.0",
            )
        assert "Confidence interval low value must be <= high value" in str(exc_info.value)

    def test_quality_flags_default_factory(self):
        """Test quality_flags uses default factory (empty list)."""
        estimate = TaxImpactEstimate(
            shock_id="SHOCK-005",
            state="WA",
            bea_sector="54",
            fiscal_year=2022,
            individual_income_tax=Decimal("50000"),
            payroll_tax=Decimal("30000"),
            corporate_income_tax=Decimal("20000"),
            excise_tax=Decimal("5000"),
            total_tax_receipt=Decimal("105000"),
            wage_impact=Decimal("500000"),
            proprietor_income_impact=Decimal("100000"),
            gross_operating_surplus=Decimal("200000"),
            consumption_impact=Decimal("300000"),
            confidence_interval=(Decimal("95000"), Decimal("115000")),
            methodology="StateIO_v2.1",
            tax_parameter_version="2022Q1",
            multiplier_version="v1.0",
        )
        assert estimate.quality_flags == []

    def test_computed_at_default_factory(self):
        """Test computed_at uses default factory."""
        estimate = TaxImpactEstimate(
            shock_id="SHOCK-006",
            state="MA",
            bea_sector="54",
            fiscal_year=2022,
            individual_income_tax=Decimal("50000"),
            payroll_tax=Decimal("30000"),
            corporate_income_tax=Decimal("20000"),
            excise_tax=Decimal("5000"),
            total_tax_receipt=Decimal("105000"),
            wage_impact=Decimal("500000"),
            proprietor_income_impact=Decimal("100000"),
            gross_operating_surplus=Decimal("200000"),
            consumption_impact=Decimal("300000"),
            confidence_interval=(Decimal("95000"), Decimal("115000")),
            methodology="StateIO_v2.1",
            tax_parameter_version="2022Q1",
            multiplier_version="v1.0",
        )
        assert isinstance(estimate.computed_at, datetime)


class TestFiscalReturnSummaryModel:
    """Tests for the FiscalReturnSummary model."""

    def test_valid_fiscal_return_summary(self):
        """Test creating a valid fiscal return summary."""
        summary = FiscalReturnSummary(
            analysis_id="ANALYSIS-001",
            base_year=2020,
            methodology_version="v2.1",
            total_sbir_investment=Decimal("10000000"),
            total_tax_receipts=Decimal("15000000"),
            net_fiscal_return=Decimal("5000000"),
            roi_ratio=1.5,
            net_present_value=Decimal("4500000"),
            benefit_cost_ratio=1.5,
            confidence_interval_low=Decimal("14000000"),
            confidence_interval_high=Decimal("16000000"),
            quality_score=0.85,
        )
        assert summary.analysis_id == "ANALYSIS-001"
        assert summary.roi_ratio == 1.5

    def test_total_sbir_investment_validator_rejects_zero(self):
        """Test total_sbir_investment validator rejects zero."""
        with pytest.raises(ValidationError) as exc_info:
            FiscalReturnSummary(
                analysis_id="ANALYSIS-002",
                base_year=2020,
                methodology_version="v2.1",
                total_sbir_investment=Decimal("0"),  # Invalid
                total_tax_receipts=Decimal("15000000"),
                net_fiscal_return=Decimal("15000000"),
                roi_ratio=0.0,
                net_present_value=Decimal("0"),
                benefit_cost_ratio=0.0,
                confidence_interval_low=Decimal("14000000"),
                confidence_interval_high=Decimal("16000000"),
                quality_score=0.85,
            )
        assert "Investment amount must be positive" in str(exc_info.value)

    def test_total_sbir_investment_validator_rejects_negative(self):
        """Test total_sbir_investment validator rejects negative."""
        with pytest.raises(ValidationError) as exc_info:
            FiscalReturnSummary(
                analysis_id="ANALYSIS-003",
                base_year=2020,
                methodology_version="v2.1",
                total_sbir_investment=Decimal("-1000000"),  # Invalid
                total_tax_receipts=Decimal("15000000"),
                net_fiscal_return=Decimal("16000000"),
                roi_ratio=0.0,
                net_present_value=Decimal("0"),
                benefit_cost_ratio=0.0,
                confidence_interval_low=Decimal("14000000"),
                confidence_interval_high=Decimal("16000000"),
                quality_score=0.85,
            )
        assert "Investment amount must be positive" in str(exc_info.value)

    def test_total_tax_receipts_validator_accepts_zero(self):
        """Test total_tax_receipts validator accepts zero."""
        summary = FiscalReturnSummary(
            analysis_id="ANALYSIS-004",
            base_year=2020,
            methodology_version="v2.1",
            total_sbir_investment=Decimal("10000000"),
            total_tax_receipts=Decimal("0"),  # Valid
            net_fiscal_return=Decimal("-10000000"),
            roi_ratio=0.0,
            net_present_value=Decimal("-10000000"),
            benefit_cost_ratio=0.0,
            confidence_interval_low=Decimal("0"),
            confidence_interval_high=Decimal("0"),
            quality_score=0.5,
        )
        assert summary.total_tax_receipts == Decimal("0")

    def test_total_tax_receipts_validator_rejects_negative(self):
        """Test total_tax_receipts validator rejects negative."""
        with pytest.raises(ValidationError) as exc_info:
            FiscalReturnSummary(
                analysis_id="ANALYSIS-005",
                base_year=2020,
                methodology_version="v2.1",
                total_sbir_investment=Decimal("10000000"),
                total_tax_receipts=Decimal("-1000"),  # Invalid
                net_fiscal_return=Decimal("-10001000"),
                roi_ratio=0.0,
                net_present_value=Decimal("-10001000"),
                benefit_cost_ratio=0.0,
                confidence_interval_low=Decimal("0"),
                confidence_interval_high=Decimal("0"),
                quality_score=0.5,
            )
        assert "Receipt amounts must be non-negative" in str(exc_info.value)

    def test_roi_ratio_validator_accepts_valid(self):
        """Test roi_ratio validator accepts non-negative ratios."""
        summary = FiscalReturnSummary(
            analysis_id="ANALYSIS-006",
            base_year=2020,
            methodology_version="v2.1",
            total_sbir_investment=Decimal("10000000"),
            total_tax_receipts=Decimal("25000000"),
            net_fiscal_return=Decimal("15000000"),
            roi_ratio=2.5,
            net_present_value=Decimal("14000000"),
            benefit_cost_ratio=2.5,
            confidence_interval_low=Decimal("24000000"),
            confidence_interval_high=Decimal("26000000"),
            quality_score=0.9,
        )
        assert summary.roi_ratio == 2.5

    def test_roi_ratio_validator_rejects_negative(self):
        """Test roi_ratio validator rejects negative ratios."""
        with pytest.raises(ValidationError) as exc_info:
            FiscalReturnSummary(
                analysis_id="ANALYSIS-007",
                base_year=2020,
                methodology_version="v2.1",
                total_sbir_investment=Decimal("10000000"),
                total_tax_receipts=Decimal("5000000"),
                net_fiscal_return=Decimal("-5000000"),
                roi_ratio=-0.5,  # Invalid
                net_present_value=Decimal("-5500000"),
                benefit_cost_ratio=0.5,
                confidence_interval_low=Decimal("4500000"),
                confidence_interval_high=Decimal("5500000"),
                quality_score=0.7,
            )
        assert "ROI and benefit-cost ratios must be non-negative" in str(exc_info.value)

    def test_payback_period_validator_accepts_positive(self):
        """Test payback_period validator accepts positive values."""
        summary = FiscalReturnSummary(
            analysis_id="ANALYSIS-008",
            base_year=2020,
            methodology_version="v2.1",
            total_sbir_investment=Decimal("10000000"),
            total_tax_receipts=Decimal("15000000"),
            net_fiscal_return=Decimal("5000000"),
            roi_ratio=1.5,
            payback_period_years=6.7,
            net_present_value=Decimal("4500000"),
            benefit_cost_ratio=1.5,
            confidence_interval_low=Decimal("14000000"),
            confidence_interval_high=Decimal("16000000"),
            quality_score=0.85,
        )
        assert summary.payback_period_years == 6.7

    def test_payback_period_validator_rejects_zero(self):
        """Test payback_period validator rejects zero."""
        with pytest.raises(ValidationError) as exc_info:
            FiscalReturnSummary(
                analysis_id="ANALYSIS-009",
                base_year=2020,
                methodology_version="v2.1",
                total_sbir_investment=Decimal("10000000"),
                total_tax_receipts=Decimal("15000000"),
                net_fiscal_return=Decimal("5000000"),
                roi_ratio=1.5,
                payback_period_years=0.0,  # Invalid
                net_present_value=Decimal("4500000"),
                benefit_cost_ratio=1.5,
                confidence_interval_low=Decimal("14000000"),
                confidence_interval_high=Decimal("16000000"),
                quality_score=0.85,
            )
        assert "Payback period must be positive" in str(exc_info.value)

    def test_compute_derived_metrics(self):
        """Test compute_derived_metrics method."""
        summary = FiscalReturnSummary(
            analysis_id="ANALYSIS-010",
            base_year=2020,
            methodology_version="v2.1",
            total_sbir_investment=Decimal("10000000"),
            total_tax_receipts=Decimal("20000000"),
            net_fiscal_return=Decimal("0"),  # Will be computed
            roi_ratio=0.0,  # Will be computed
            net_present_value=Decimal("18000000"),
            benefit_cost_ratio=0.0,  # Will be computed
            confidence_interval_low=Decimal("19000000"),
            confidence_interval_high=Decimal("21000000"),
            quality_score=0.9,
        )
        summary.compute_derived_metrics()
        assert summary.net_fiscal_return == Decimal("10000000")
        assert summary.roi_ratio == 2.0
        assert summary.benefit_cost_ratio == 2.0


class TestInflationAdjustmentModel:
    """Tests for the InflationAdjustment model."""

    def test_valid_inflation_adjustment(self):
        """Test creating a valid inflation adjustment."""
        adjustment = InflationAdjustment(
            award_id="AWARD-001",
            original_year=2015,
            base_year=2020,
            original_amount=Decimal("100000"),
            adjusted_amount=Decimal("110500"),
            inflation_factor=1.105,
            inflation_source="BEA_GDP_deflator",
        )
        assert adjustment.award_id == "AWARD-001"
        assert adjustment.inflation_factor == 1.105

    def test_amounts_validator_rejects_zero(self):
        """Test amounts validator rejects zero."""
        with pytest.raises(ValidationError) as exc_info:
            InflationAdjustment(
                award_id="AWARD-002",
                original_year=2015,
                base_year=2020,
                original_amount=Decimal("0"),  # Invalid
                adjusted_amount=Decimal("110500"),
                inflation_factor=1.105,
                inflation_source="BEA_GDP_deflator",
            )
        assert "Award amounts must be positive" in str(exc_info.value)

    def test_amounts_validator_rejects_negative(self):
        """Test amounts validator rejects negative amounts."""
        with pytest.raises(ValidationError) as exc_info:
            InflationAdjustment(
                award_id="AWARD-003",
                original_year=2015,
                base_year=2020,
                original_amount=Decimal("100000"),
                adjusted_amount=Decimal("-110500"),  # Invalid
                inflation_factor=1.105,
                inflation_source="BEA_GDP_deflator",
            )
        assert "Award amounts must be positive" in str(exc_info.value)

    def test_inflation_factor_validator_accepts_positive(self):
        """Test inflation_factor validator accepts positive values."""
        adjustment = InflationAdjustment(
            award_id="AWARD-004",
            original_year=2015,
            base_year=2020,
            original_amount=Decimal("100000"),
            adjusted_amount=Decimal("95000"),
            inflation_factor=0.95,
            inflation_source="BEA_GDP_deflator",
        )
        assert adjustment.inflation_factor == 0.95

    def test_inflation_factor_validator_rejects_zero(self):
        """Test inflation_factor validator rejects zero."""
        with pytest.raises(ValidationError) as exc_info:
            InflationAdjustment(
                award_id="AWARD-005",
                original_year=2015,
                base_year=2020,
                original_amount=Decimal("100000"),
                adjusted_amount=Decimal("100000"),
                inflation_factor=0.0,  # Invalid
                inflation_source="BEA_GDP_deflator",
            )
        assert "Inflation factor must be positive" in str(exc_info.value)

    def test_adjusted_at_default_factory(self):
        """Test adjusted_at uses default factory."""
        adjustment = InflationAdjustment(
            award_id="AWARD-006",
            original_year=2015,
            base_year=2020,
            original_amount=Decimal("100000"),
            adjusted_amount=Decimal("110500"),
            inflation_factor=1.105,
            inflation_source="BEA_GDP_deflator",
        )
        assert isinstance(adjustment.adjusted_at, datetime)


class TestNAICSMappingModel:
    """Tests for the NAICSMapping model."""

    def test_valid_naics_mapping(self):
        """Test creating a valid NAICS mapping."""
        mapping = NAICSMapping(
            award_id="AWARD-001",
            naics_code="541715",
            bea_sector_code="54",
            bea_sector_name="Professional, Scientific, and Technical Services",
            crosswalk_version="2022",
            naics_source="usaspending",
            naics_confidence=0.95,
            mapping_confidence=0.90,
        )
        assert mapping.naics_code == "541715"
        assert mapping.bea_sector_code == "54"

    def test_naics_code_validator_removes_non_digits(self):
        """Test naics_code validator removes non-digit characters."""
        mapping = NAICSMapping(
            award_id="AWARD-002",
            naics_code="54-17-15",
            bea_sector_code="54",
            bea_sector_name="Professional Services",
            crosswalk_version="2022",
            naics_source="sam_gov",
            naics_confidence=0.90,
            mapping_confidence=0.85,
        )
        assert mapping.naics_code == "541715"

    def test_naics_code_validator_accepts_2_digit(self):
        """Test naics_code validator accepts 2-digit codes."""
        mapping = NAICSMapping(
            award_id="AWARD-003",
            naics_code="54",
            bea_sector_code="54",
            bea_sector_name="Professional Services",
            crosswalk_version="2022",
            naics_source="inferred",
            naics_confidence=0.70,
            mapping_confidence=0.75,
        )
        assert mapping.naics_code == "54"

    def test_naics_code_validator_accepts_6_digit(self):
        """Test naics_code validator accepts 6-digit codes."""
        mapping = NAICSMapping(
            award_id="AWARD-004",
            naics_code="541715",
            bea_sector_code="54",
            bea_sector_name="Professional Services",
            crosswalk_version="2022",
            naics_source="original",
            naics_confidence=1.0,
            mapping_confidence=0.95,
        )
        assert mapping.naics_code == "541715"

    def test_naics_code_validator_rejects_invalid_length(self):
        """Test naics_code validator rejects codes not 2-6 digits."""
        with pytest.raises(ValidationError) as exc_info:
            NAICSMapping(
                award_id="AWARD-005",
                naics_code="5",  # Invalid: 1 digit
                bea_sector_code="54",
                bea_sector_name="Professional Services",
                crosswalk_version="2022",
                naics_source="inferred",
                naics_confidence=0.70,
                mapping_confidence=0.75,
            )
        assert "NAICS code must be 2-6 digits" in str(exc_info.value)

    def test_allocation_weight_default(self):
        """Test allocation_weight has default value of 1.0."""
        mapping = NAICSMapping(
            award_id="AWARD-006",
            naics_code="541715",
            bea_sector_code="54",
            bea_sector_name="Professional Services",
            crosswalk_version="2022",
            naics_source="usaspending",
            naics_confidence=0.95,
            mapping_confidence=0.90,
        )
        assert mapping.allocation_weight == 1.0

    def test_mapped_at_default_factory(self):
        """Test mapped_at uses default factory."""
        mapping = NAICSMapping(
            award_id="AWARD-007",
            naics_code="541715",
            bea_sector_code="54",
            bea_sector_name="Professional Services",
            crosswalk_version="2022",
            naics_source="usaspending",
            naics_confidence=0.95,
            mapping_confidence=0.90,
        )
        assert isinstance(mapping.mapped_at, datetime)


class TestGeographicResolutionModel:
    """Tests for the GeographicResolution model."""

    def test_valid_geographic_resolution(self):
        """Test creating a valid geographic resolution."""
        resolution = GeographicResolution(
            award_id="AWARD-001",
            company_uei="ABC123DEF456",
            original_address="123 Main St, Boston, MA 02101",
            resolved_state="MA",  # pragma: allowlist secret
            resolved_city="Boston",
            resolved_zip="02101",
            resolution_method="direct",
            resolution_confidence=1.0,
            data_sources=["sam.gov", "usaspending"],
        )
        assert resolution.resolved_state == "MA"
        assert resolution.resolution_method == "direct"

    def test_resolved_state_validator_normalizes_uppercase(self):
        """Test resolved_state validator normalizes to uppercase."""
        resolution = GeographicResolution(
            award_id="AWARD-002",
            resolved_state="ca",
            resolution_method="geocoding",
            resolution_confidence=0.95,
        )
        assert resolution.resolved_state == "CA"

    def test_resolved_state_validator_rejects_invalid_length(self):
        """Test resolved_state validator rejects non-2-letter codes."""
        with pytest.raises(ValidationError) as exc_info:
            GeographicResolution(
                award_id="AWARD-003",
                resolved_state="CAL",  # Invalid
                resolution_method="fallback",
                resolution_confidence=0.70,
            )
        assert "State code must be exactly two letters" in str(exc_info.value)

    def test_resolved_state_validator_rejects_non_alpha(self):
        """Test resolved_state validator rejects non-alphabetic codes."""
        with pytest.raises(ValidationError) as exc_info:
            GeographicResolution(
                award_id="AWARD-004",
                resolved_state="C1",  # Invalid
                resolution_method="fallback",
                resolution_confidence=0.70,
            )
        assert "State code must be exactly two letters" in str(exc_info.value)

    def test_data_sources_default_factory(self):
        """Test data_sources uses default factory (empty list)."""
        resolution = GeographicResolution(
            award_id="AWARD-005",
            resolved_state="TX",
            resolution_method="direct",
            resolution_confidence=1.0,
        )
        assert resolution.data_sources == []

    def test_resolved_at_default_factory(self):
        """Test resolved_at uses default factory."""
        resolution = GeographicResolution(
            award_id="AWARD-006",
            resolved_state="NY",
            resolution_method="geocoding",
            resolution_confidence=0.90,
        )
        assert isinstance(resolution.resolved_at, datetime)

    def test_optional_fields(self):
        """Test optional fields can be None."""
        resolution = GeographicResolution(
            award_id="AWARD-007",
            company_uei=None,
            original_address=None,
            resolved_state="FL",
            resolved_city=None,
            resolved_zip=None,
            resolution_method="fallback",
            resolution_confidence=0.60,
        )
        assert resolution.company_uei is None
        assert resolution.original_address is None
        assert resolution.resolved_city is None
        assert resolution.resolved_zip is None
