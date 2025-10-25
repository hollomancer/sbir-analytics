"""Pydantic models for SBIR award data."""

from datetime import date
from typing import Optional

from pydantic import BaseModel, Field, validator


class Award(BaseModel):
    """SBIR/STTR award data model."""

    # Required fields
    award_id: str = Field(..., description="Unique award identifier")
    company_name: str = Field(..., description="Company receiving the award")
    award_amount: float = Field(..., description="Award amount in USD")
    award_date: date = Field(..., description="Date award was made")
    program: str = Field(..., description="SBIR or STTR program")

    # Optional fields
    phase: Optional[str] = Field(None, description="Phase I, II, or III")
    agency: Optional[str] = Field(None, description="Federal agency")
    branch: Optional[str] = Field(None, description="Agency branch")
    contract: Optional[str] = Field(None, description="Contract number")
    abstract: Optional[str] = Field(None, description="Project abstract")
    keywords: Optional[str] = Field(None, description="Project keywords")

    # Enrichment fields (populated later)
    company_duns: Optional[str] = Field(None, description="DUNS number from SAM.gov")
    company_cage: Optional[str] = Field(None, description="CAGE code from SAM.gov")
    company_address: Optional[str] = Field(None, description="Company address from SAM.gov")
    company_city: Optional[str] = Field(None, description="Company city from SAM.gov")
    company_state: Optional[str] = Field(None, description="Company state from SAM.gov")
    company_zip: Optional[str] = Field(None, description="Company ZIP code from SAM.gov")

    # USAspending enrichment
    usaspending_id: Optional[str] = Field(None, description="USAspending.gov award ID")
    fiscal_year: Optional[int] = Field(None, description="Fiscal year of award")

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
        json_encoders = {
            date: lambda v: v.isoformat()
        }


class RawAward(BaseModel):
    """Raw award data before validation/transformation."""

    # All fields are optional for raw data
    award_id: Optional[str] = None
    company_name: Optional[str] = None
    award_amount: Optional[float] = None
    award_date: Optional[str] = None  # Raw string date
    program: Optional[str] = None
    phase: Optional[str] = None
    agency: Optional[str] = None
    branch: Optional[str] = None
    contract: Optional[str] = None
    abstract: Optional[str] = None
    keywords: Optional[str] = None

    class Config:
        """Pydantic configuration."""
        validate_assignment = True