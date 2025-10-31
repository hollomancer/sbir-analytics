"""Pydantic models for SBIR fiscal returns analysis."""

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class EconomicShock(BaseModel):
    """Economic shock representing aggregated SBIR spending by state, sector, and fiscal year."""

    # Geographic and sectoral identifiers
    state: str = Field(..., description="Two-letter state code (e.g., 'CA', 'TX')")
    bea_sector: str = Field(..., description="BEA Input-Output sector code")
    fiscal_year: int = Field(..., description="Government fiscal year")

    # Economic impact data
    shock_amount: Decimal = Field(..., description="Total SBIR spending amount (inflation-adjusted)")
    award_ids: list[str] = Field(..., description="List of SBIR award IDs contributing to this shock")

    # Quality and confidence metrics
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score for this aggregation")
    naics_coverage_rate: float = Field(..., ge=0.0, le=1.0, description="Percentage of awards with NAICS codes")
    geographic_resolution_rate: float = Field(..., ge=0.0, le=1.0, description="Percentage of awards with resolved geography")

    # Metadata
    created_at: datetime = Field(default_factory=datetime.now, description="When this shock was computed")
    base_year: int = Field(..., description="Base year for inflation adjustment")

    model_config = ConfigDict(
        validate_assignment=True,
        json_encoders={Decimal: str, datetime: lambda v: v.isoformat()},
    )

    @field_validator("state")
    @classmethod
    def validate_state_code(cls, v: str) -> str:
        """Validate state code is two letters."""
        if len(v) != 2 or not v.isalpha():
            raise ValueError("State code must be exactly two letters")
        return v.upper()

    @field_validator("fiscal_year")
    @classmethod
    def validate_fiscal_year(cls, v: int) -> int:
        """Validate fiscal year is reasonable."""
        if not (1980 <= v <= 2030):
            raise ValueError("Fiscal year must be between 1980 and 2030")
        return v

    @field_validator("shock_amount")
    @classmethod
    def validate_shock_amount(cls, v: Decimal) -> Decimal:
        """Validate shock amount is positive."""
        if v < 0:
            raise ValueError("Shock amount must be non-negative")
        return v


class TaxImpactEstimate(BaseModel):
    """Federal tax impact estimate from economic activity induced by SBIR spending."""

    # Identifiers
    shock_id: str = Field(..., description="Identifier linking to the economic shock")
    state: str = Field(..., description="State where economic activity occurs")
    bea_sector: str = Field(..., description="BEA sector generating the tax impact")
    fiscal_year: int = Field(..., description="Fiscal year of the impact")

    # Tax receipt estimates by category
    individual_income_tax: Decimal = Field(..., description="Individual income tax receipts")
    payroll_tax: Decimal = Field(..., description="Payroll tax receipts (Social Security + Medicare)")
    corporate_income_tax: Decimal = Field(..., description="Corporate income tax receipts")
    excise_tax: Decimal = Field(..., description="Excise tax receipts")
    total_tax_receipt: Decimal = Field(..., description="Total federal tax receipts")

    # Economic components underlying tax calculations
    wage_impact: Decimal = Field(..., description="Wage income generated")
    proprietor_income_impact: Decimal = Field(..., description="Proprietor income generated")
    gross_operating_surplus: Decimal = Field(..., description="Corporate profits generated")
    consumption_impact: Decimal = Field(..., description="Consumer spending generated")

    # Uncertainty quantification
    confidence_interval: tuple[Decimal, Decimal] = Field(
        ..., description="95% confidence interval (low, high) for total tax receipt"
    )
    confidence_level: float = Field(default=0.95, description="Confidence level for interval")

    # Methodology and parameters
    methodology: str = Field(..., description="Economic model used (e.g., 'StateIO_v2.1')")
    tax_parameter_version: str = Field(..., description="Version of tax parameters used")
    multiplier_version: str = Field(..., description="Version of economic multipliers used")

    # Quality flags
    quality_flags: list[str] = Field(default_factory=list, description="Quality issues or assumptions")

    # Metadata
    computed_at: datetime = Field(default_factory=datetime.now, description="When estimate was computed")

    model_config = ConfigDict(
        validate_assignment=True,
        json_encoders={Decimal: str, datetime: lambda v: v.isoformat()},
    )

    @field_validator("individual_income_tax", "payroll_tax", "corporate_income_tax", "excise_tax", "total_tax_receipt")
    @classmethod
    def validate_tax_amounts(cls, v: Decimal) -> Decimal:
        """Validate tax amounts are non-negative."""
        if v < 0:
            raise ValueError("Tax amounts must be non-negative")
        return v

    @field_validator("confidence_interval")
    @classmethod
    def validate_confidence_interval(cls, v: tuple[Decimal, Decimal]) -> tuple[Decimal, Decimal]:
        """Validate confidence interval has low <= high."""
        low, high = v
        if low > high:
            raise ValueError("Confidence interval low value must be <= high value")
        return v

    def __post_init__(self):
        """Validate that total tax receipt equals sum of components."""
        computed_total = (
            self.individual_income_tax +
            self.payroll_tax +
            self.corporate_income_tax +
            self.excise_tax
        )
        if abs(computed_total - self.total_tax_receipt) > Decimal("0.01"):
            raise ValueError("Total tax receipt must equal sum of individual tax components")


class FiscalReturnSummary(BaseModel):
    """Summary of fiscal returns and ROI analysis for SBIR program evaluation."""

    # Analysis metadata
    analysis_id: str = Field(..., description="Unique identifier for this analysis")
    analysis_date: datetime = Field(default_factory=datetime.now, description="When analysis was performed")
    base_year: int = Field(..., description="Base year for monetary normalization")
    methodology_version: str = Field(..., description="Version of analysis methodology")

    # Investment and returns
    total_sbir_investment: Decimal = Field(..., description="Total SBIR program investment (inflation-adjusted)")
    total_tax_receipts: Decimal = Field(..., description="Total federal tax receipts generated")
    net_fiscal_return: Decimal = Field(..., description="Net return to Treasury (receipts - investment)")

    # ROI metrics
    roi_ratio: float = Field(..., description="Return on investment ratio (receipts / investment)")
    payback_period_years: float | None = Field(None, description="Years to recover investment")
    net_present_value: Decimal = Field(..., description="Net present value of returns")
    benefit_cost_ratio: float = Field(..., description="Benefit-cost ratio")

    # Uncertainty quantification
    confidence_interval_low: Decimal = Field(..., description="Lower bound of 95% confidence interval")
    confidence_interval_high: Decimal = Field(..., description="Upper bound of 95% confidence interval")
    confidence_level: float = Field(default=0.95, description="Confidence level for intervals")

    # Sensitivity analysis results
    sensitivity_analysis: dict[str, Any] = Field(
        default_factory=dict,
        description="Sensitivity analysis results by parameter"
    )

    # Coverage and quality metrics
    coverage_metrics: dict[str, float] = Field(
        default_factory=dict,
        description="Data coverage rates (NAICS, geographic, etc.)"
    )

    # Breakdown by dimensions
    breakdown_by_state: dict[str, Decimal] = Field(
        default_factory=dict,
        description="Tax receipts by state"
    )
    breakdown_by_sector: dict[str, Decimal] = Field(
        default_factory=dict,
        description="Tax receipts by BEA sector"
    )
    breakdown_by_fiscal_year: dict[int, Decimal] = Field(
        default_factory=dict,
        description="Tax receipts by fiscal year"
    )

    # Analysis parameters used
    analysis_parameters: dict[str, Any] = Field(
        default_factory=dict,
        description="Key parameters used in analysis"
    )

    # Quality assessment
    quality_score: float = Field(..., ge=0.0, le=1.0, description="Overall quality score for analysis")
    quality_flags: list[str] = Field(default_factory=list, description="Quality issues identified")

    model_config = ConfigDict(
        validate_assignment=True,
        json_encoders={Decimal: str, datetime: lambda v: v.isoformat()},
    )

    @field_validator("total_sbir_investment", "total_tax_receipts")
    @classmethod
    def validate_positive_amounts(cls, v: Decimal) -> Decimal:
        """Validate investment and receipt amounts are positive."""
        if v <= 0:
            raise ValueError("Investment and receipt amounts must be positive")
        return v

    @field_validator("roi_ratio", "benefit_cost_ratio")
    @classmethod
    def validate_ratios(cls, v: float) -> float:
        """Validate ratios are non-negative."""
        if v < 0:
            raise ValueError("ROI and benefit-cost ratios must be non-negative")
        return v

    @field_validator("payback_period_years")
    @classmethod
    def validate_payback_period(cls, v: float | None) -> float | None:
        """Validate payback period is positive if provided."""
        if v is not None and v <= 0:
            raise ValueError("Payback period must be positive")
        return v

    def compute_derived_metrics(self) -> None:
        """Compute derived metrics from base values."""
        # Compute net fiscal return
        self.net_fiscal_return = self.total_tax_receipts - self.total_sbir_investment

        # Compute ROI ratio
        if self.total_sbir_investment > 0:
            self.roi_ratio = float(self.total_tax_receipts / self.total_sbir_investment)

        # Compute benefit-cost ratio
        if self.total_sbir_investment > 0:
            self.benefit_cost_ratio = float(self.total_tax_receipts / self.total_sbir_investment)


class InflationAdjustment(BaseModel):
    """Inflation adjustment record for monetary normalization."""

    # Identifiers
    award_id: str = Field(..., description="SBIR award identifier")
    original_year: int = Field(..., description="Original year of the award")
    base_year: int = Field(..., description="Base year for adjustment")

    # Amounts
    original_amount: Decimal = Field(..., description="Original award amount")
    adjusted_amount: Decimal = Field(..., description="Inflation-adjusted amount")
    inflation_factor: float = Field(..., description="Inflation adjustment factor applied")

    # Data source and quality
    inflation_source: str = Field(..., description="Source of inflation data (e.g., 'BEA_GDP_deflator')")
    quality_flag: str | None = Field(None, description="Quality flag if adjustment is estimated")

    # Metadata
    adjusted_at: datetime = Field(default_factory=datetime.now, description="When adjustment was computed")

    model_config = ConfigDict(
        validate_assignment=True,
        json_encoders={Decimal: str, datetime: lambda v: v.isoformat()},
    )

    @field_validator("original_amount", "adjusted_amount")
    @classmethod
    def validate_amounts(cls, v: Decimal) -> Decimal:
        """Validate amounts are positive."""
        if v <= 0:
            raise ValueError("Award amounts must be positive")
        return v

    @field_validator("inflation_factor")
    @classmethod
    def validate_inflation_factor(cls, v: float) -> float:
        """Validate inflation factor is positive."""
        if v <= 0:
            raise ValueError("Inflation factor must be positive")
        return v


class NAICSMapping(BaseModel):
    """NAICS to BEA sector mapping record."""

    # Identifiers
    award_id: str = Field(..., description="SBIR award identifier")
    naics_code: str = Field(..., description="NAICS code (original or enriched)")
    bea_sector_code: str = Field(..., description="BEA Input-Output sector code")
    bea_sector_name: str = Field(..., description="BEA sector description")

    # Mapping details
    allocation_weight: float = Field(default=1.0, ge=0.0, le=1.0, description="Allocation weight for proportional mapping")
    crosswalk_version: str = Field(..., description="Version of NAICS-BEA crosswalk used")

    # Data quality
    naics_source: str = Field(..., description="Source of NAICS code (original, sam_gov, usaspending, etc.)")
    naics_confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence in NAICS code accuracy")
    mapping_confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence in BEA sector mapping")

    # Metadata
    mapped_at: datetime = Field(default_factory=datetime.now, description="When mapping was performed")

    model_config = ConfigDict(
        validate_assignment=True,
        json_encoders={datetime: lambda v: v.isoformat()},
    )

    @field_validator("naics_code")
    @classmethod
    def validate_naics_code(cls, v: str) -> str:
        """Validate NAICS code format."""
        # Remove any non-digit characters and validate length
        digits_only = ''.join(c for c in v if c.isdigit())
        if len(digits_only) not in [2, 3, 4, 5, 6]:
            raise ValueError("NAICS code must be 2-6 digits")
        return digits_only


class GeographicResolution(BaseModel):
    """Geographic resolution record for state-level mapping."""

    # Identifiers
    award_id: str = Field(..., description="SBIR award identifier")
    company_uei: str | None = Field(None, description="Company UEI if available")

    # Geographic data
    original_address: str | None = Field(None, description="Original company address")
    resolved_state: str = Field(..., description="Resolved two-letter state code")
    resolved_city: str | None = Field(None, description="Resolved city name")
    resolved_zip: str | None = Field(None, description="Resolved ZIP code")

    # Resolution details
    resolution_method: str = Field(..., description="Method used for resolution (direct, geocoding, fallback)")
    resolution_confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence in geographic resolution")

    # Data sources
    data_sources: list[str] = Field(default_factory=list, description="Data sources used for resolution")

    # Metadata
    resolved_at: datetime = Field(default_factory=datetime.now, description="When resolution was performed")

    model_config = ConfigDict(
        validate_assignment=True,
        json_encoders={datetime: lambda v: v.isoformat()},
    )

    @field_validator("resolved_state")
    @classmethod
    def validate_state_code(cls, v: str) -> str:
        """Validate state code is two letters."""
        if len(v) != 2 or not v.isalpha():
            raise ValueError("State code must be exactly two letters")
        return v.upper()
