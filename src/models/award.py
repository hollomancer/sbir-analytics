"""Pydantic models for SBIR award data."""

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator, ConfigDict


class Award(BaseModel):
    """SBIR/STTR award data model."""

    # Required fields
    award_id: str = Field(..., description="Unique award identifier")
    company_name: str = Field(..., description="Company receiving the award")
    award_amount: float = Field(..., description="Award amount in USD")
    award_date: date = Field(..., description="Date award was made")
    program: str = Field(..., description="SBIR or STTR program")

    # Optional fields
    phase: str | None = Field(None, description="Phase I, II, or III")
    agency: str | None = Field(None, description="Federal agency")
    branch: str | None = Field(None, description="Agency branch")
    contract: str | None = Field(None, description="Contract number")
    abstract: str | None = Field(None, description="Project abstract")
    keywords: str | None = Field(None, description="Project keywords")

    # Enrichment fields (populated later)
    company_duns: str | None = Field(None, description="DUNS number from SAM.gov")
    company_cage: str | None = Field(None, description="CAGE code from SAM.gov")
    company_address: str | None = Field(None, description="Company address from SAM.gov")
    company_city: str | None = Field(None, description="Company city from SAM.gov")
    company_state: str | None = Field(None, description="Company state from SAM.gov")
    company_zip: str | None = Field(None, description="Company ZIP code from SAM.gov")

    # USAspending enrichment
    usaspending_id: str | None = Field(None, description="USAspending.gov award ID")
    fiscal_year: int | None = Field(None, description="Fiscal year of award")

    @validator("award_amount")
    def validate_award_amount(cls, v):
        """Validate award amount is positive."""
        if v <= 0:
            raise ValueError("Award amount must be positive")
        return v

    @validator("program")
    def validate_program(cls, v):
        """Validate program is SBIR or STTR."""
        if v.upper() not in ["SBIR", "STTR"]:
            raise ValueError("Program must be SBIR or STTR")
        return v.upper()

    @validator("phase")
    def validate_phase(cls, v):
        """Validate phase if provided."""
        if v is not None and v.upper() not in ["I", "II", "III"]:
            raise ValueError("Phase must be I, II, or III")
        return v.upper() if v else v

    @validator("fiscal_year")
    def validate_fiscal_year(cls, v):
        """Validate fiscal year range."""
        if v is not None and (v < 1983 or v > 2030):
            raise ValueError("Fiscal year must be between 1983 and 2030")
        return v

    class Config:
        """Pydantic configuration."""

        validate_assignment = True
        json_encoders = {date: lambda v: v.isoformat()}


class RawAward(BaseModel):
    """Raw award data before validation/transformation."""

    # All fields are optional for raw data
    award_id: str | None = None
    company_name: str | None = None
    award_amount: float | None = None
    award_date: str | None = None  # Raw string date
    program: str | None = None
    phase: str | None = None
    agency: str | None = None
    branch: str | None = None
    contract: str | None = None
    abstract: str | None = None
    keywords: str | None = None

    class Config:
        """Pydantic configuration."""

        validate_assignment = True
