"""Pydantic model for SBIR award data from SBIR.gov CSV.

NOTE: This module provides SbirAward as a compatibility wrapper around the
consolidated Award model. New code should use Award.from_sbir_csv() or Award
directly with field aliases. SbirAward is maintained for backward compatibility.
"""

from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .award import Award


class SbirAward(BaseModel):
    """
    DEPRECATED: Use Award.from_sbir_csv() or Award with field aliases instead.
    
    Compatibility wrapper for SBIR.gov CSV format that uses the consolidated Award model.
    
    This class maintains backward compatibility with existing code that uses SbirAward.
    It converts SBIR.gov format fields to Award format internally.
    
    For new code, prefer:
        award = Award.from_sbir_csv(data)
    or:
        award = Award(**data, company="...")  # Uses alias="company"
    """

    _award: Award | None = None  # Internal consolidated Award instance

    def __init__(self, **data: Any) -> None:
        """Initialize SbirAward from SBIR.gov format data, converting to Award internally."""
        # Convert SBIR format to Award format
        award_data = Award.from_sbir_csv(data).model_dump()
        # Store as Award instance
        object.__setattr__(self, "_award", Award(**award_data))
        # For backward compatibility, allow attribute access via SBIR field names
        super().__init__(**{})  # Initialize with empty dict, we use _award internally

    def __getattribute__(self, name: str) -> Any:
        """Delegate attribute access to internal Award instance with SBIR field name mapping."""
        if name == "_award" or name.startswith("__") or name in ["model_dump", "model_dump_json", "model_validate"]:
            return super().__getattribute__(name)
        
        # Map SBIR field names to Award field names
        field_map = {
            "company": "company_name",
            "uei": "company_uei",
            "duns": "company_duns",
            "city": "company_city",
            "state": "company_state",
            "zip": "company_zip",
            "hubzone_owned": "is_hubzone",
            "woman_owned": "is_woman_owned",
            "socially_and_economically_disadvantaged": "is_socially_disadvantaged",
            "number_employees": "number_of_employees",
            "pi_name": "principal_investigator",
            "ri_name": "research_institution",
        }
        
        award_field = field_map.get(name, name)
        award = super().__getattribute__("_award")
        if award_field in award.model_fields:
            return getattr(award, award_field)
        # Fall back to Award attributes
        return getattr(award, name, None)

    def model_dump(self, **kwargs) -> dict[str, Any]:
        """Dump model as dict in SBIR.gov format."""
        award = self._award
        if award is None:
            return {}
        
        # Convert Award format back to SBIR format
        data = award.model_dump()
        reverse_map = {
            "company_name": "company",
            "company_uei": "uei",
            "company_duns": "duns",
            "company_city": "city",
            "company_state": "state",
            "company_zip": "zip",
            "is_hubzone": "hubzone_owned",
            "is_woman_owned": "woman_owned",
            "is_socially_disadvantaged": "socially_and_economically_disadvantaged",
            "number_of_employees": "number_employees",
            "principal_investigator": "pi_name",
            "research_institution": "ri_name",
        }
        
        sbir_data = {}
        for award_key, sbir_key in reverse_map.items():
            if award_key in data:
                sbir_data[sbir_key] = data[award_key]
        
        # Copy fields that are the same
        for key in ["award_title", "abstract", "agency", "branch", "phase", "program",
                    "award_amount", "award_year", "proposal_award_date", "contract_end_date",
                    "contract", "agency_tracking_number", "solicitation_number",
                    "contact_name", "contact_title", "contact_phone", "contact_email",
                    "pi_title", "pi_phone", "pi_email", "ri_poc_name", "ri_poc_phone",
                    "solicitation_close_date", "proposal_receipt_date", "date_of_notification",
                    "solicitation_year", "topic_code", "company_website", "address1", "address2"]:
            if key in data:
                sbir_data[key] = data[key]
        
        return sbir_data

    # Validators (delegated to Award, but kept for backward compatibility)
    model_config = ConfigDict(
        validate_assignment=True,
        str_strip_whitespace=True,
        json_encoders={date: lambda v: v.isoformat()},
        arbitrary_types_allowed=True,  # Allow Award type
    )


def parse_bool_from_csv(value: str | None) -> bool | None:
    """Parse boolean values from CSV (Y/N or True/False)."""
    if not value or value.strip() == "":
        return None
    value_upper = value.strip().upper()
    if value_upper in ["Y", "YES", "TRUE", "1"]:
        return True
    if value_upper in ["N", "NO", "FALSE", "0"]:
        return False
    return None


def parse_date_from_csv(value: str | None) -> date | None:
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


def parse_int_from_csv(value: str | None) -> int | None:
    """Parse integer from CSV, returning None for empty strings."""
    if not value or value.strip() == "":
        return None
    try:
        return int(float(value.strip()))  # Handle "123.0" format
    except ValueError:
        return None


def parse_float_from_csv(value: str | None) -> float | None:
    """Parse float from CSV, returning None for empty strings."""
    if not value or value.strip() == "":
        return None
    try:
        return float(value.strip())
    except ValueError:
        return None
