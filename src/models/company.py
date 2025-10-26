"""Pydantic models for company data."""

from pydantic import BaseModel, Field, field_validator, ConfigDict


class Company(BaseModel):
    """Company data model with SAM.gov enrichment."""

    # Core identifying fields
    name: str = Field(..., description="Company name")
    duns: str | None = Field(None, description="DUNS number (9 digits)")
    cage: str | None = Field(None, description="CAGE code (5 characters)")

    # Address information
    address_line_1: str | None = Field(None, description="Street address line 1")
    address_line_2: str | None = Field(None, description="Street address line 2")
    city: str | None = Field(None, description="City")
    state: str | None = Field(None, description="State or province")
    zip_code: str | None = Field(None, description="ZIP or postal code")
    country: str | None = Field(None, description="Country code")

    # Business information
    business_type: str | None = Field(None, description="Type of business entity")
    naics_code: str | None = Field(None, description="NAICS code")
    naics_description: str | None = Field(None, description="NAICS description")

    # Contact information
    phone: str | None = Field(None, description="Phone number")
    email: str | None = Field(None, description="Email address")

    # Status and dates
    sam_registration_status: str | None = Field(None, description="SAM registration status")
    sam_exclusion_status: str | None = Field(None, description="SAM exclusion status")
    last_updated: str | None = Field(None, description="Last update date from SAM.gov")

    @field_validator("duns")
    @classmethod
    def validate_duns(cls, v):
        """Validate DUNS number format."""
        if v is None:
            return v
        # Remove any hyphens or spaces
        clean_duns = v.replace("-", "").replace(" ", "")
        if not clean_duns.isdigit() or len(clean_duns) != 9:
            raise ValueError("DUNS must be 9 digits")
        return clean_duns

    @field_validator("cage")
    @classmethod
    def validate_cage(cls, v):
        """Validate CAGE code format."""
        if v is None:
            return v
        # CAGE codes are typically 5 characters
        if len(v) != 5:
            raise ValueError("CAGE code must be 5 characters")
        return v.upper()

    @field_validator("zip_code")
    @classmethod
    def validate_zip_code(cls, v):
        """Validate ZIP code format."""
        if v is None:
            return v
        # Basic validation - should be numeric with optional hyphen
        clean_zip = v.replace("-", "").replace(" ", "")
        if not clean_zip.isdigit() or len(clean_zip) < 5:
            raise ValueError("Invalid ZIP code format")
        return v

    model_config = ConfigDict(validate_assignment=True)


class RawCompany(BaseModel):
    """Raw company data before validation/enrichment."""

    # All fields optional for raw data
    name: str | None = None
    duns: str | None = None
    cage: str | None = None
    address_line_1: str | None = None
    address_line_2: str | None = None
    city: str | None = None
    state: str | None = None
    zip_code: str | None = None
    country: str | None = None

    model_config = ConfigDict(validate_assignment=True)


class CompanyMatch(BaseModel):
    """Result of company matching/deduplication."""

    source_company: Company
    matched_company: Company
    confidence_score: float = Field(..., ge=0.0, le=1.0, description="Match confidence (0-1)")
    match_method: str = Field(..., description="Method used for matching")

    @field_validator("confidence_score")
    @classmethod
    def validate_confidence(cls, v):
        """Validate confidence score is between 0 and 1."""
        if not (0.0 <= v <= 1.0):
            raise ValueError("Confidence score must be between 0.0 and 1.0")
        return v
