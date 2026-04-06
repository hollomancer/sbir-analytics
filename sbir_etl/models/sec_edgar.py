"""Pydantic models for SEC EDGAR data.

Models for representing SEC EDGAR company filings, CIK resolutions,
and extracted financial data used to enrich SBIR company analysis.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class FilingType(str, Enum):
    """SEC filing types relevant to SBIR analysis."""

    FORM_10K = "10-K"
    FORM_10Q = "10-Q"
    FORM_8K = "8-K"
    FORM_S1 = "S-1"
    FORM_DEF14A = "DEF 14A"
    FORM_4 = "4"
    FORM_SC13D = "SC 13D"
    FORM_20F = "20-F"


class MAAcquisitionType(str, Enum):
    """Types of M&A events detected from 8-K filings."""

    ACQUISITION = "acquisition"
    MERGER = "merger"
    ASSET_PURCHASE = "asset_purchase"
    UNKNOWN = "unknown"


class EdgarCompanyMatch(BaseModel):
    """Result of matching an SBIR company to a SEC EDGAR entity."""

    cik: str = Field(..., description="Central Index Key (SEC identifier)")
    entity_name: str = Field(..., description="Entity name as registered with SEC")
    ticker: str | None = Field(None, description="Stock ticker symbol")
    exchange: str | None = Field(None, description="Stock exchange listing")
    sic_code: str | None = Field(None, description="Standard Industrial Classification code")
    sic_description: str | None = Field(None, description="SIC code description")
    state_of_incorporation: str | None = Field(None, description="State of incorporation")
    ein: str | None = Field(None, description="Employer Identification Number")

    match_confidence: float = Field(
        ..., ge=0.0, le=1.0, description="Confidence of the name match (0-1)"
    )
    match_method: str = Field(
        ..., description="Method used for matching (e.g., 'name_fuzzy', 'ein_exact')"
    )

    model_config = ConfigDict(validate_assignment=True)


class EdgarFiling(BaseModel):
    """A single SEC filing extracted from EDGAR."""

    accession_number: str = Field(..., description="SEC accession number")
    filing_type: str = Field(..., description="Filing form type (e.g., '10-K', '8-K')")
    filing_date: date = Field(..., description="Date the filing was submitted")
    reporting_date: date | None = Field(None, description="Period of report")
    primary_document: str | None = Field(None, description="Primary document filename")
    description: str | None = Field(None, description="Filing description")

    model_config = ConfigDict(validate_assignment=True)


class EdgarFinancials(BaseModel):
    """Standardized financial data extracted from XBRL filings.

    Pulled from the EDGAR companyfacts API for a given CIK.
    """

    cik: str = Field(..., description="Central Index Key")
    fiscal_year: int = Field(..., description="Fiscal year")
    fiscal_period: str = Field(default="FY", description="Fiscal period (FY, Q1-Q4)")

    revenue: float | None = Field(None, description="Total revenue (USD)")
    net_income: float | None = Field(None, description="Net income (USD)")
    total_assets: float | None = Field(None, description="Total assets (USD)")
    total_liabilities: float | None = Field(None, description="Total liabilities (USD)")
    rd_expense: float | None = Field(None, description="Research & development expense (USD)")
    operating_income: float | None = Field(None, description="Operating income (USD)")
    cash_and_equivalents: float | None = Field(None, description="Cash and equivalents (USD)")

    filing_date: date | None = Field(None, description="Date of the source filing")

    model_config = ConfigDict(validate_assignment=True)


class EdgarMAEvent(BaseModel):
    """M&A event detected from an 8-K filing.

    Extracted from Item 1.01 (material agreements) and Item 2.01 (acquisitions)
    in 8-K filings.
    """

    cik: str = Field(..., description="CIK of the filing entity")
    filing_date: date = Field(..., description="8-K filing date")
    accession_number: str = Field(..., description="SEC accession number")
    event_type: MAAcquisitionType = Field(
        default=MAAcquisitionType.UNKNOWN, description="Type of M&A event"
    )
    items_reported: list[str] = Field(
        default_factory=list, description="8-K items reported (e.g., ['1.01', '2.01'])"
    )
    description: str | None = Field(None, description="Extracted event description")

    model_config = ConfigDict(validate_assignment=True)


class CompanyEdgarProfile(BaseModel):
    """Aggregated SEC EDGAR profile for an SBIR company.

    This is the enrichment output that gets merged into the company record.
    """

    # Identifiers
    company_name: str = Field(..., description="SBIR company name (source)")
    company_uei: str | None = Field(None, description="UEI used for linking")

    # EDGAR match
    cik: str | None = Field(None, description="Matched CIK, None if not public")
    is_publicly_traded: bool = Field(
        default=False, description="Whether a public filing match was found"
    )
    match_confidence: float = Field(
        default=0.0, ge=0.0, le=1.0, description="CIK match confidence"
    )
    match_method: str | None = Field(None, description="CIK resolution method")
    ticker: str | None = Field(None, description="Stock ticker if matched")
    sic_code: str | None = Field(None, description="SIC code from EDGAR")

    # Latest financials (from most recent 10-K/10-Q)
    latest_revenue: float | None = Field(None, description="Most recent revenue (USD)")
    latest_rd_expense: float | None = Field(None, description="Most recent R&D expense (USD)")
    latest_total_assets: float | None = Field(None, description="Most recent total assets (USD)")
    latest_net_income: float | None = Field(None, description="Most recent net income (USD)")
    financials_as_of: date | None = Field(None, description="Date of latest financial data")

    # M&A signals
    ma_event_count: int = Field(default=0, description="Number of detected M&A events")
    latest_ma_event_date: date | None = Field(None, description="Most recent M&A event date")

    # Filing activity
    total_filings: int = Field(default=0, description="Total number of filings found")
    latest_filing_date: date | None = Field(None, description="Most recent filing date")

    # Metadata
    enriched_at: datetime | None = Field(None, description="When enrichment was performed")

    @field_validator("match_confidence")
    @classmethod
    def validate_confidence(cls, v: float) -> float:
        if not (0.0 <= v <= 1.0):
            raise ValueError("Match confidence must be between 0.0 and 1.0")
        return v

    model_config = ConfigDict(validate_assignment=True)
