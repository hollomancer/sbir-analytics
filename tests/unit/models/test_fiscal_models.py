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


# Helper to create EconomicShock with defaults
def _make_shock(**overrides):
    """Create EconomicShock with sensible defaults."""
    defaults = {
        "state": "CA",
        "bea_sector": "54",
        "fiscal_year": 2022,
        "shock_amount": Decimal("500000"),
        "award_ids": ["AWARD-001"],
        "confidence": 0.9,
        "naics_coverage_rate": 0.85,
        "geographic_resolution_rate": 0.95,
        "base_year": 2020,
    }
    defaults.update(overrides)
    return EconomicShock(**defaults)


class TestEconomicShockModel:
    """Tests for the EconomicShock model."""

    def test_valid_economic_shock(self):
        """Test creating a valid economic shock with all fields."""
        shock = _make_shock(
            shock_amount=Decimal("1000000.00"),
            award_ids=["AWARD-001", "AWARD-002"],
            confidence=0.95,
            naics_coverage_rate=0.88,
            geographic_resolution_rate=1.0,
        )
        assert shock.state == "CA"
        assert shock.bea_sector == "54"
        assert shock.fiscal_year == 2022
        assert shock.shock_amount == Decimal("1000000.00")
        assert len(shock.award_ids) == 2

    def test_state_validator_normalizes_uppercase(self):
        """Test state code validator normalizes to uppercase."""
        shock = _make_shock(state="tx")
        assert shock.state == "TX"

    @pytest.mark.parametrize(
        "invalid_state",
        ["CAL", "C1", "X"],
        ids=["too_long", "non_alpha", "too_short"],
    )
    def test_state_validator_rejects_invalid(self, invalid_state):
        """Test state validator rejects invalid state codes."""
        with pytest.raises(ValidationError) as exc_info:
            _make_shock(state=invalid_state)
        assert "State code must be exactly two letters" in str(exc_info.value)

    @pytest.mark.parametrize(
        "valid_year",
        [1980, 2000, 2022, 2025, 2030],
        ids=["min_bound", "mid_range", "current", "near_future", "max_bound"],
    )
    def test_fiscal_year_validator_accepts_valid_range(self, valid_year):
        """Test fiscal_year validator accepts 1980-2030 range."""
        shock = _make_shock(fiscal_year=valid_year)
        assert shock.fiscal_year == valid_year

    @pytest.mark.parametrize(
        "invalid_year",
        [1979, 1900, 2031, 2050],
        ids=["before_1980", "way_before", "after_2030", "way_after"],
    )
    def test_fiscal_year_validator_rejects_invalid(self, invalid_year):
        """Test fiscal_year validator rejects years outside 1980-2030."""
        with pytest.raises(ValidationError) as exc_info:
            _make_shock(fiscal_year=invalid_year)
        assert "Fiscal year must be between 1980 and 2030" in str(exc_info.value)

    @pytest.mark.parametrize(
        "amount,should_pass",
        [
            (Decimal("0"), True),
            (Decimal("1000000"), True),
            (Decimal("-100"), False),
        ],
        ids=["zero_valid", "positive_valid", "negative_invalid"],
    )
    def test_shock_amount_validator(self, amount, should_pass):
        """Test shock_amount validator accepts zero/positive, rejects negative."""
        if should_pass:
            shock = _make_shock(shock_amount=amount)
            assert shock.shock_amount == amount
        else:
            with pytest.raises(ValidationError) as exc_info:
                _make_shock(shock_amount=amount)
            assert "Shock amount must be non-negative" in str(exc_info.value)

    def test_confidence_field_constraints(self):
        """Test confidence field has 0-1 constraints."""
        with pytest.raises(ValidationError):
            _make_shock(confidence=1.5)

    def test_created_at_default_factory(self):
        """Test created_at uses default factory."""
        shock = _make_shock()
        assert isinstance(shock.created_at, datetime)


# Helper to create TaxImpactEstimate with defaults
def _make_tax_estimate(**overrides):
    """Create TaxImpactEstimate with sensible defaults."""
    defaults = {
        "shock_id": "SHOCK-001",
        "state": "CA",
        "bea_sector": "54",
        "fiscal_year": 2022,
        "individual_income_tax": Decimal("50000"),
        "payroll_tax": Decimal("30000"),
        "corporate_income_tax": Decimal("20000"),
        "excise_tax": Decimal("5000"),
        "total_tax_receipt": Decimal("105000"),
        "wage_impact": Decimal("500000"),
        "proprietor_income_impact": Decimal("100000"),
        "gross_operating_surplus": Decimal("200000"),
        "consumption_impact": Decimal("300000"),
        "confidence_interval": (Decimal("95000"), Decimal("115000")),
        "methodology": "StateIO_v2.1",
        "tax_parameter_version": "2022Q1",
        "multiplier_version": "v1.0",
    }
    defaults.update(overrides)
    return TaxImpactEstimate(**defaults)


class TestTaxImpactEstimateModel:
    """Tests for the TaxImpactEstimate model."""

    def test_valid_tax_impact_estimate(self):
        """Test creating a valid tax impact estimate with all fields."""
        estimate = _make_tax_estimate()
        assert estimate.shock_id == "SHOCK-001"
        assert estimate.total_tax_receipt == Decimal("105000")

    def test_tax_amounts_validator_rejects_negative(self):
        """Test tax amounts validator rejects negative values."""
        with pytest.raises(ValidationError) as exc_info:
            _make_tax_estimate(individual_income_tax=Decimal("-1000"))
        assert "Tax amounts must be non-negative" in str(exc_info.value)

    @pytest.mark.parametrize(
        "low,high,should_pass",
        [
            (Decimal("100000"), Decimal("110000"), True),
            (Decimal("100000"), Decimal("100000"), True),
            (Decimal("120000"), Decimal("100000"), False),
        ],
        ids=["valid_range", "equal_bounds", "invalid_order"],
    )
    def test_confidence_interval_validator(self, low, high, should_pass):
        """Test confidence interval validator accepts low <= high."""
        if should_pass:
            estimate = _make_tax_estimate(confidence_interval=(low, high))
            assert estimate.confidence_interval == (low, high)
        else:
            with pytest.raises(ValidationError) as exc_info:
                _make_tax_estimate(confidence_interval=(low, high))
            assert "Confidence interval low value must be <= high value" in str(exc_info.value)

    def test_quality_flags_default_factory(self):
        """Test quality_flags uses default factory (empty list)."""
        estimate = _make_tax_estimate()
        assert estimate.quality_flags == []

    def test_computed_at_default_factory(self):
        """Test computed_at uses default factory."""
        estimate = _make_tax_estimate()
        assert isinstance(estimate.computed_at, datetime)


# Helper to create FiscalReturnSummary with defaults
def _make_summary(**overrides):
    """Create FiscalReturnSummary with sensible defaults."""
    defaults = {
        "analysis_id": "ANALYSIS-001",
        "base_year": 2020,
        "methodology_version": "v2.1",
        "total_sbir_investment": Decimal("10000000"),
        "total_tax_receipts": Decimal("15000000"),
        "net_fiscal_return": Decimal("5000000"),
        "roi_ratio": 1.5,
        "net_present_value": Decimal("4500000"),
        "benefit_cost_ratio": 1.5,
        "confidence_interval_low": Decimal("14000000"),
        "confidence_interval_high": Decimal("16000000"),
        "quality_score": 0.85,
    }
    defaults.update(overrides)
    return FiscalReturnSummary(**defaults)


class TestFiscalReturnSummaryModel:
    """Tests for the FiscalReturnSummary model."""

    def test_valid_fiscal_return_summary(self):
        """Test creating a valid fiscal return summary with all fields."""
        summary = _make_summary()
        assert summary.analysis_id == "ANALYSIS-001"
        assert summary.roi_ratio == 1.5

    @pytest.mark.parametrize(
        "investment,should_pass",
        [
            (Decimal("10000000"), True),
            (Decimal("0"), False),
            (Decimal("-1000000"), False),
        ],
        ids=["positive_valid", "zero_invalid", "negative_invalid"],
    )
    def test_total_sbir_investment_validator(self, investment, should_pass):
        """Test total_sbir_investment validator requires positive values."""
        if should_pass:
            summary = _make_summary(total_sbir_investment=investment)
            assert summary.total_sbir_investment == investment
        else:
            with pytest.raises(ValidationError) as exc_info:
                _make_summary(total_sbir_investment=investment)
            assert "Investment amount must be positive" in str(exc_info.value)

    @pytest.mark.parametrize(
        "receipts,should_pass",
        [
            (Decimal("15000000"), True),
            (Decimal("0"), True),
            (Decimal("-1000"), False),
        ],
        ids=["positive_valid", "zero_valid", "negative_invalid"],
    )
    def test_total_tax_receipts_validator(self, receipts, should_pass):
        """Test total_tax_receipts validator accepts zero/positive, rejects negative."""
        if should_pass:
            summary = _make_summary(
                total_tax_receipts=receipts,
                net_fiscal_return=receipts - Decimal("10000000"),
            )
            assert summary.total_tax_receipts == receipts
        else:
            with pytest.raises(ValidationError) as exc_info:
                _make_summary(total_tax_receipts=receipts)
            assert "Receipt amounts must be non-negative" in str(exc_info.value)

    @pytest.mark.parametrize(
        "ratio,should_pass",
        [
            (2.5, True),
            (0.0, True),
            (-0.5, False),
        ],
        ids=["positive_valid", "zero_valid", "negative_invalid"],
    )
    def test_roi_ratio_validator(self, ratio, should_pass):
        """Test roi_ratio validator accepts non-negative ratios."""
        if should_pass:
            summary = _make_summary(roi_ratio=ratio, benefit_cost_ratio=max(0, ratio))
            assert summary.roi_ratio == ratio
        else:
            with pytest.raises(ValidationError) as exc_info:
                _make_summary(roi_ratio=ratio)
            assert "ROI and benefit-cost ratios must be non-negative" in str(exc_info.value)

    @pytest.mark.parametrize(
        "period,should_pass",
        [
            (6.7, True),
            (0.1, True),
            (0.0, False),
            (-1.0, False),
        ],
        ids=["positive_valid", "small_positive", "zero_invalid", "negative_invalid"],
    )
    def test_payback_period_validator(self, period, should_pass):
        """Test payback_period validator requires positive values."""
        if should_pass:
            summary = _make_summary(payback_period_years=period)
            assert summary.payback_period_years == period
        else:
            with pytest.raises(ValidationError) as exc_info:
                _make_summary(payback_period_years=period)
            assert "Payback period must be positive" in str(exc_info.value)

    def test_compute_derived_metrics(self):
        """Test compute_derived_metrics method calculates ROI and benefit-cost ratio."""
        summary = _make_summary(
            total_tax_receipts=Decimal("20000000"),
            net_fiscal_return=Decimal("0"),
            roi_ratio=0.0,
            benefit_cost_ratio=0.0,
        )
        summary.compute_derived_metrics()
        assert summary.net_fiscal_return == Decimal("10000000")
        assert summary.roi_ratio == 2.0
        assert summary.benefit_cost_ratio == 2.0


# Helper to create InflationAdjustment with defaults
def _make_inflation(**overrides):
    """Create InflationAdjustment with sensible defaults."""
    defaults = {
        "award_id": "AWARD-001",
        "original_year": 2015,
        "base_year": 2020,
        "original_amount": Decimal("100000"),
        "adjusted_amount": Decimal("110500"),
        "inflation_factor": 1.105,
        "inflation_source": "BEA_GDP_deflator",
    }
    defaults.update(overrides)
    return InflationAdjustment(**defaults)


# Helper to create NAICSMapping with defaults
def _make_naics_mapping(**overrides):
    """Create NAICSMapping with sensible defaults."""
    defaults = {
        "award_id": "AWARD-001",
        "naics_code": "541715",
        "bea_sector_code": "54",
        "bea_sector_name": "Professional Services",
        "crosswalk_version": "2022",
        "naics_source": "usaspending",
        "naics_confidence": 0.95,
        "mapping_confidence": 0.90,
    }
    defaults.update(overrides)
    return NAICSMapping(**defaults)


# Helper to create GeographicResolution with defaults
def _make_geo_resolution(**overrides):
    """Create GeographicResolution with sensible defaults."""
    defaults = {
        "award_id": "AWARD-001",
        "resolved_state": "CA",
        "resolution_method": "direct",
        "resolution_confidence": 1.0,
    }
    defaults.update(overrides)
    return GeographicResolution(**defaults)


class TestInflationAdjustmentModel:
    """Tests for the InflationAdjustment model."""

    def test_valid_inflation_adjustment(self):
        """Test creating a valid inflation adjustment with all fields."""
        adjustment = _make_inflation()
        assert adjustment.award_id == "AWARD-001"
        assert adjustment.inflation_factor == 1.105

    @pytest.mark.parametrize(
        "field,value",
        [
            ("original_amount", Decimal("0")),
            ("original_amount", Decimal("-100")),
            ("adjusted_amount", Decimal("0")),
            ("adjusted_amount", Decimal("-110500")),
        ],
        ids=["original_zero", "original_negative", "adjusted_zero", "adjusted_negative"],
    )
    def test_amounts_validator_rejects_non_positive(self, field, value):
        """Test amounts validator rejects zero and negative values."""
        with pytest.raises(ValidationError) as exc_info:
            _make_inflation(**{field: value})
        assert "Award amounts must be positive" in str(exc_info.value)

    @pytest.mark.parametrize(
        "factor,should_pass",
        [
            (1.105, True),
            (0.95, True),
            (0.0, False),
            (-0.5, False),
        ],
        ids=["positive", "less_than_one", "zero_invalid", "negative_invalid"],
    )
    def test_inflation_factor_validator(self, factor, should_pass):
        """Test inflation_factor validator requires positive values."""
        if should_pass:
            adjustment = _make_inflation(inflation_factor=factor)
            assert adjustment.inflation_factor == factor
        else:
            with pytest.raises(ValidationError) as exc_info:
                _make_inflation(inflation_factor=factor)
            assert "Inflation factor must be positive" in str(exc_info.value)

    def test_adjusted_at_default_factory(self):
        """Test adjusted_at uses default factory."""
        adjustment = _make_inflation()
        assert isinstance(adjustment.adjusted_at, datetime)


class TestNAICSMappingModel:
    """Tests for the NAICSMapping model."""

    def test_valid_naics_mapping(self):
        """Test creating a valid NAICS mapping with all fields."""
        mapping = _make_naics_mapping(
            bea_sector_name="Professional, Scientific, and Technical Services"
        )
        assert mapping.naics_code == "541715"
        assert mapping.bea_sector_code == "54"

    def test_naics_code_validator_removes_non_digits(self):
        """Test naics_code validator removes non-digit characters."""
        mapping = _make_naics_mapping(naics_code="54-17-15")
        assert mapping.naics_code == "541715"

    @pytest.mark.parametrize(
        "code,expected",
        [
            ("54", "54"),
            ("541", "541"),
            ("5417", "5417"),
            ("54171", "54171"),
            ("541715", "541715"),
        ],
        ids=["2_digit", "3_digit", "4_digit", "5_digit", "6_digit"],
    )
    def test_naics_code_validator_accepts_valid_lengths(self, code, expected):
        """Test naics_code validator accepts 2-6 digit codes."""
        mapping = _make_naics_mapping(naics_code=code)
        assert mapping.naics_code == expected

    @pytest.mark.parametrize(
        "code",
        ["5", "5417150"],
        ids=["1_digit_invalid", "7_digit_invalid"],
    )
    def test_naics_code_validator_rejects_invalid_length(self, code):
        """Test naics_code validator rejects codes not 2-6 digits."""
        with pytest.raises(ValidationError) as exc_info:
            _make_naics_mapping(naics_code=code)
        assert "NAICS code must be 2-6 digits" in str(exc_info.value)

    def test_allocation_weight_default(self):
        """Test allocation_weight has default value of 1.0."""
        mapping = _make_naics_mapping()
        assert mapping.allocation_weight == 1.0

    def test_mapped_at_default_factory(self):
        """Test mapped_at uses default factory."""
        mapping = _make_naics_mapping()
        assert isinstance(mapping.mapped_at, datetime)


class TestGeographicResolutionModel:
    """Tests for the GeographicResolution model."""

    def test_valid_geographic_resolution(self):
        """Test creating a valid geographic resolution with all fields."""
        resolution = _make_geo_resolution(
            company_uei="ABC123DEF456",
            original_address="123 Main St, Boston, MA 02101",
            resolved_state="MA",
            resolved_city="Boston",
            resolved_zip="02101",
            data_sources=["sam.gov", "usaspending"],
        )
        assert resolution.resolved_state == "MA"
        assert resolution.resolution_method == "direct"

    def test_resolved_state_validator_normalizes_uppercase(self):
        """Test resolved_state validator normalizes to uppercase."""
        resolution = _make_geo_resolution(resolved_state="ca")
        assert resolution.resolved_state == "CA"

    @pytest.mark.parametrize(
        "state",
        ["CAL", "C1", "X"],
        ids=["too_long", "non_alpha", "too_short"],
    )
    def test_resolved_state_validator_rejects_invalid(self, state):
        """Test resolved_state validator rejects invalid state codes."""
        with pytest.raises(ValidationError) as exc_info:
            _make_geo_resolution(resolved_state=state)
        assert "State code must be exactly two letters" in str(exc_info.value)

    def test_data_sources_default_factory(self):
        """Test data_sources uses default factory (empty list)."""
        resolution = _make_geo_resolution()
        assert resolution.data_sources == []

    def test_resolved_at_default_factory(self):
        """Test resolved_at uses default factory."""
        resolution = _make_geo_resolution()
        assert isinstance(resolution.resolved_at, datetime)

    def test_optional_fields(self):
        """Test optional fields can be None."""
        resolution = _make_geo_resolution(
            company_uei=None,
            original_address=None,
            resolved_city=None,
            resolved_zip=None,
        )
        assert resolution.company_uei is None
        assert resolution.original_address is None
        assert resolution.resolved_city is None
        assert resolution.resolved_zip is None
