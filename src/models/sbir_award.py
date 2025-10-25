"""Pydantic model for SBIR award data from SBIR.gov CSV."""

from datetime import date
from typing import Optional

from pydantic import BaseModel, Field, field_validator, ConfigDict


class SbirAward(BaseModel):
    """
    Complete SBIR/STTR award data model matching SBIR.gov CSV format.

    Represents a single SBIR or STTR award with 42 fields including company
    identification, award details, timeline, personnel, and business classifications.
    """

    # Company Identification (7 fields)
    company: str = Field(..., description="Company name receiving the award")
    address1: Optional[str] = Field(None, description="Primary address line")
    address2: Optional[str] = Field(None, description="Secondary address line")
    city: Optional[str] = Field(None, description="City")
    state: Optional[str] = Field(None, description="State (2-letter code)")
    zip: Optional[str] = Field(None, description="ZIP code (5 or 9 digits)")
    company_website: Optional[str] = Field(None, description="Company website URL")
    number_employees: Optional[int] = Field(None, description="Number of employees")

    # Award Details (7 fields)
    award_title: str = Field(..., description="Title of the award project")
    abstract: Optional[str] = Field(None, description="Project abstract/description")
    agency: str = Field(..., description="Federal agency (NSF, DOD, DOE, HHS, NASA, etc.)")
    branch: Optional[str] = Field(None, description="Agency branch/division")
    phase: str = Field(..., description="Phase I, Phase II, or Phase III")
    program: str = Field(..., description="SBIR or STTR")
    topic_code: Optional[str] = Field(None, description="Topic code from solicitation")

    # Financial (2 fields)
    award_amount: float = Field(..., description="Award amount in USD", gt=0)
    award_year: int = Field(..., description="Year of award", ge=1983, le=2026)

    # Timeline/Dates (5 fields)
    proposal_award_date: Optional[date] = Field(None, description="Date proposal was awarded")
    contract_end_date: Optional[date] = Field(None, description="Contract end date")
    solicitation_close_date: Optional[date] = Field(None, description="Solicitation closing date")
    proposal_receipt_date: Optional[date] = Field(None, description="Date proposal was received")
    date_of_notification: Optional[date] = Field(None, description="Date company was notified")

    # Tracking/Identifiers (4 fields)
    agency_tracking_number: str = Field(..., description="Agency's internal tracking number")
    contract: str = Field(..., description="Contract number/ID")
    solicitation_number: Optional[str] = Field(None, description="Solicitation number")
    solicitation_year: Optional[int] = Field(
        None, description="Year of solicitation", ge=1983, le=2026
    )

    # Company Identifiers (2 fields)
    uei: Optional[str] = Field(None, description="Unique Entity Identifier (12 alphanumeric)")
    duns: Optional[str] = Field(None, description="DUNS number (9 digits)")

    # Business Classifications (3 fields)
    hubzone_owned: Optional[bool] = Field(None, description="HUBZone owned business")
    socially_and_economically_disadvantaged: Optional[bool] = Field(
        None, description="Socially and economically disadvantaged business"
    )
    woman_owned: Optional[bool] = Field(None, description="Woman-owned business")

    # Contact Person (4 fields)
    contact_name: Optional[str] = Field(None, description="Primary contact name")
    contact_title: Optional[str] = Field(None, description="Contact title/position")
    contact_phone: Optional[str] = Field(None, description="Contact phone number")
    contact_email: Optional[str] = Field(None, description="Contact email address")

    # Principal Investigator (4 fields)
    pi_name: Optional[str] = Field(None, description="Principal Investigator name")
    pi_title: Optional[str] = Field(None, description="PI title/position")
    pi_phone: Optional[str] = Field(None, description="PI phone number")
    pi_email: Optional[str] = Field(None, description="PI email address")

    # Research Institution (3 fields)
    ri_name: Optional[str] = Field(None, description="Research Institution name")
    ri_poc_name: Optional[str] = Field(None, description="RI Point of Contact name")
    ri_poc_phone: Optional[str] = Field(None, description="RI POC phone number")

    # Validators
    @field_validator("phase")
    @classmethod
    def validate_phase(cls, v: str) -> str:
        """Validate phase is one of the allowed values."""
        if v not in ["Phase I", "Phase II", "Phase III"]:
            raise ValueError(f"Phase must be 'Phase I', 'Phase II', or 'Phase III', got '{v}'")
        return v

    @field_validator("program")
    @classmethod
    def validate_program(cls, v: str) -> str:
        """Validate program is SBIR or STTR."""
        if v.upper() not in ["SBIR", "STTR"]:
            raise ValueError(f"Program must be 'SBIR' or 'STTR', got '{v}'")
        return v.upper()

    @field_validator("state")
    @classmethod
    def validate_state(cls, v: Optional[str]) -> Optional[str]:
        """Validate state is 2-letter code if provided."""
        if v and len(v) != 2:
            raise ValueError(f"State must be 2-letter code, got '{v}'")
        return v.upper() if v else v

    @field_validator("zip")
    @classmethod
    def validate_zip(cls, v: Optional[str]) -> Optional[str]:
        """Validate ZIP code format if provided."""
        if v and not (len(v) == 5 or len(v) == 10):  # 5 digits or ZIP+4 (12345-6789)
            raise ValueError(f"ZIP must be 5 or 10 characters (ZIP+4), got '{v}'")
        return v

    @field_validator("uei")
    @classmethod
    def validate_uei(cls, v: Optional[str]) -> Optional[str]:
        """Validate UEI format if provided (12 alphanumeric characters)."""
        if v and len(v) != 12:
            raise ValueError(f"UEI must be 12 characters, got '{v}' ({len(v)} chars)")
        return v.upper() if v else v

    @field_validator("duns")
    @classmethod
    def validate_duns(cls, v: Optional[str]) -> Optional[str]:
        """Validate DUNS format if provided (9 digits)."""
        if v and (len(v) != 9 or not v.isdigit()):
            raise ValueError(f"DUNS must be 9 digits, got '{v}'")
        return v

    @field_validator("contract_end_date")
    @classmethod
    def validate_contract_end_date(cls, v: Optional[date], info) -> Optional[date]:
        """Validate contract end date is after award date if both present."""
        if v and "proposal_award_date" in info.data:
            award_date = info.data["proposal_award_date"]
            if award_date and v < award_date:
                raise ValueError(
                    f"Contract end date ({v}) cannot be before award date ({award_date})"
                )
        return v

    model_config = ConfigDict(
        validate_assignment=True,
        str_strip_whitespace=True,
        json_encoders={date: lambda v: v.isoformat()},
    )


def parse_bool_from_csv(value: Optional[str]) -> Optional[bool]:
    """Parse boolean values from CSV (Y/N or True/False)."""
    if not value or value.strip() == "":
        return None
    value_upper = value.strip().upper()
    if value_upper in ["Y", "YES", "TRUE", "1"]:
        return True
    if value_upper in ["N", "NO", "FALSE", "0"]:
        return False
    return None


def parse_date_from_csv(value: Optional[str]) -> Optional[date]:
    """Parse date from CSV string (YYYY-MM-DD format)."""
    if not value or value.strip() == "":
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        # Try alternative formats
        from dateutil import parser

        try:
            return parser.parse(value.strip()).date()
        except Exception:
            return None


def parse_int_from_csv(value: Optional[str]) -> Optional[int]:
    """Parse integer from CSV, returning None for empty strings."""
    if not value or value.strip() == "":
        return None
    try:
        return int(float(value.strip()))  # Handle "123.0" format
    except ValueError:
        return None


def parse_float_from_csv(value: Optional[str]) -> Optional[float]:
    """Parse float from CSV, returning None for empty strings."""
    if not value or value.strip() == "":
        return None
    try:
        return float(value.strip())
    except ValueError:
        return None
