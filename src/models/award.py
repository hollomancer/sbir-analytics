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

    # Identifier fields (may be present in raw input)
    company_uei: str | None = Field(None, description="Unique Entity Identifier (UEI)")

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

    @field_validator("award_amount")
    @classmethod
    def validate_award_amount(cls, v: float) -> float:
        """Validate award amount is positive."""
        if v <= 0:
            raise ValueError("Award amount must be positive")
        return v

    @field_validator("program")
    @classmethod
    def validate_program(cls, v: str) -> str:
        """Validate program is SBIR or STTR."""
        if v.upper() not in ["SBIR", "STTR"]:
            raise ValueError("Program must be SBIR or STTR")
        return v.upper()

    @field_validator("phase")
    @classmethod
    def validate_phase(cls, v: str | None) -> str | None:
        """Validate phase if provided."""
        if v is not None and v.upper() not in ["I", "II", "III"]:
            raise ValueError("Phase must be I, II, or III")
        return v.upper() if v else v

    @field_validator("fiscal_year")
    @classmethod
    def validate_fiscal_year(cls, v: int | None) -> int | None:
        """Validate fiscal year range."""
        if v is not None and (v < 1983 or v > 2030):
            raise ValueError("Fiscal year must be between 1983 and 2030")
        return v

    @field_validator("company_uei")
    @classmethod
    def validate_company_uei(cls, v: str | None) -> str | None:
        """Validate UEI if provided: expected to be 12 alphanumeric characters."""
        if v is None:
            return v
        if not isinstance(v, str):
            raise ValueError("Company UEI must be a string")
        cleaned = v.strip()
        if len(cleaned) != 12 or not cleaned.isalnum():
            raise ValueError("Company UEI must be a 12-character alphanumeric string")
        return cleaned.upper()

    @field_validator("company_duns")
    @classmethod
    def validate_company_duns(cls, v: str | None) -> str | None:
        """Normalize and validate DUNS if provided: must contain 9 digits."""
        if v is None:
            return v
        if not isinstance(v, str):
            raise ValueError("DUNS must be provided as a string")
        digits = "".join(ch for ch in v if ch.isdigit())
        if len(digits) != 9:
            raise ValueError("DUNS must contain exactly 9 digits")
        return digits

    model_config = ConfigDict(
        validate_assignment=True, json_encoders={date: lambda v: v.isoformat()}
    )


class RawAward(BaseModel):
    """Raw award data before validation/transformation."""

    # All fields are optional for raw data
    award_id: str | None = None
    company_name: str | None = None
    company_uei: str | None = None
    company_duns: str | None = None
    award_amount: float | None = None
    award_date: str | None = None  # Raw string date
    program: str | None = None
    phase: str | None = None
    agency: str | None = None
    branch: str | None = None
    contract: str | None = None
    abstract: str | None = None
    keywords: str | None = None

    model_config = ConfigDict(validate_assignment=True)
