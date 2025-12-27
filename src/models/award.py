"""Pydantic models for SBIR award data."""

from datetime import date
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)


class Award(BaseModel):
    """Unified SBIR/STTR award data model.

    Supports both general SBIR award data and SBIR.gov CSV format.

    Features:
    - Company identifiers (UEI, DUNS, CAGE)
    - Contact & personnel (contact, PI, research institution)
    - Timeline fields (proposal/award/contract dates)
    - Tracking fields (agency tracking, solicitation)
    - Business classification flags and company metadata
    - USAspending enrichment fields
    - Field aliases support both naming conventions (prefixed and SBIR.gov format)

    Field aliases (SBIR.gov CSV format -> consolidated format):
    - company -> company_name
    - uei -> company_uei
    - duns -> company_duns
    - address1/address2 -> company_address
    - city -> company_city
    - state -> company_state
    - zip -> company_zip
    - hubzone_owned -> is_hubzone
    - woman_owned -> is_woman_owned
    - socially_and_economically_disadvantaged -> is_socially_disadvantaged
    - number_employees -> number_of_employees
    - pi_name -> principal_investigator
    - ri_name -> research_institution
    """

    # Required fields (consolidated from both models)
    award_id: str = Field(..., description="Unique award identifier")
    company_name: str = Field(..., description="Company receiving the award", alias="company")
    award_amount: float = Field(..., description="Award amount in USD")
    award_date: date | None = Field(None, description="Date award was made")
    program: str | None = Field(None, description="SBIR or STTR program (lenient validator)")

    # Optional metadata fields
    phase: str | None = Field(None, description="Phase I, II, or III")
    agency: str | None = Field(None, description="Federal agency")
    branch: str | None = Field(None, description="Agency branch")
    contract: str | None = Field(None, description="Contract number")
    abstract: str | None = Field(None, description="Project abstract")
    keywords: str | None = Field(None, description="Project keywords")
    award_title: str | None = Field(None, description="Award / project title")

    # Identifier fields (with aliases for SBIR.gov format)
    company_uei: str | None = Field(None, description="Unique Entity Identifier (UEI)", alias="uei")
    company_duns: str | None = Field(None, description="DUNS number from SAM.gov", alias="duns")
    company_cage: str | None = Field(None, description="CAGE code from SAM.gov")

    # Company address / location (with aliases for SBIR.gov format)
    company_address: str | None = Field(None, description="Company address from SAM.gov")
    address1: str | None = Field(None, description="Primary address line (SBIR.gov format)")
    address2: str | None = Field(None, description="Secondary address line (SBIR.gov format)")
    company_city: str | None = Field(None, description="Company city from SAM.gov", alias="city")
    company_state: str | None = Field(None, description="Company state from SAM.gov", alias="state")
    company_zip: str | None = Field(None, description="Company ZIP code from SAM.gov", alias="zip")

    # Congressional district (enriched data)
    congressional_district: str | None = Field(
        None, description="Congressional district code (e.g., 'CA-12', 'NY-14')"
    )
    district_number: str | None = Field(
        None, description="District number only (e.g., '12', '14', 'AL' for at-large)"
    )
    congressional_district_confidence: float | None = Field(
        None, ge=0.0, le=1.0, description="Confidence score for district assignment (0.0-1.0)"
    )
    congressional_district_method: str | None = Field(
        None, description="Method used to resolve district (e.g., 'zip_crosswalk', 'census_api')"
    )

    # Contact / personnel (with aliases for SBIR.gov format)
    contact_name: str | None = Field(None, description="Primary contact name")
    contact_title: str | None = Field(None, description="Contact title/position (SBIR.gov format)")
    contact_email: str | None = Field(None, description="Primary contact email")
    contact_phone: str | None = Field(None, description="Primary contact phone")
    principal_investigator: str | None = Field(
        None, description="Principal Investigator", alias="pi_name"
    )
    pi_title: str | None = Field(None, description="PI title/position (SBIR.gov format)")
    pi_phone: str | None = Field(None, description="PI phone number (SBIR.gov format)")
    pi_email: str | None = Field(None, description="PI email address (SBIR.gov format)")
    research_institution: str | None = Field(
        None, description="Research institution or PI affiliation", alias="ri_name"
    )
    ri_poc_name: str | None = Field(
        None, description="Research Institution POC name (SBIR.gov format)", alias="ri_poc_name"
    )
    ri_poc_phone: str | None = Field(
        None, description="Research Institution POC phone (SBIR.gov format)", alias="ri_poc_phone"
    )

    # Timeline fields (with aliases for SBIR.gov format)
    proposal_award_date: date | None = Field(None, description="Proposal or award decision date")
    contract_start_date: date | None = Field(None, description="Contract start date")
    contract_end_date: date | None = Field(None, description="Contract end date")
    solicitation_date: date | None = Field(
        None, description="Solicitation / solicitation release date"
    )
    solicitation_close_date: date | None = Field(
        None, description="Solicitation closing date (SBIR.gov format)"
    )
    proposal_receipt_date: date | None = Field(
        None, description="Date proposal was received (SBIR.gov format)"
    )
    date_of_notification: date | None = Field(
        None, description="Date company was notified (SBIR.gov format)"
    )

    # Tracking fields (with aliases for SBIR.gov format)
    agency_tracking_number: str | None = Field(None, description="Agency tracking number")
    solicitation_number: str | None = Field(None, description="Solicitation number")
    solicitation_year: int | None = Field(
        None, description="Year of solicitation (SBIR.gov format)", ge=1983, le=2026
    )
    topic_code: str | None = Field(
        None, description="Topic code from solicitation (SBIR.gov format)"
    )

    # Business classification flags (with aliases for SBIR.gov format)
    is_hubzone: bool | None = Field(None, description="HUBZone designation", alias="hubzone_owned")
    is_woman_owned: bool | None = Field(
        None, description="Woman-owned business flag", alias="woman_owned"
    )
    is_socially_disadvantaged: bool | None = Field(
        None,
        description="Socially/economically disadvantaged flag",
        alias="socially_and_economically_disadvantaged",
    )

    # Company metadata (with aliases for SBIR.gov format)
    number_of_employees: int | None = Field(
        None, description="Number of employees", alias="number_employees"
    )
    company_website: str | None = Field(None, description="Company website URL")

    # USAspending enrichment
    usaspending_id: str | None = Field(None, description="USAspending.gov award ID")
    fiscal_year: int | None = Field(None, description="Fiscal year of award")

    # Additional tracking / metadata
    award_year: int | None = Field(None, description="Award year as integer")

    # --- Validators ---

    @field_validator("award_amount", mode="before")
    @classmethod
    def validate_award_amount(cls: Any, v) -> float:
        """Coerce award_amount from string to float (if needed) and validate it's non-negative.

        Accepts numeric strings like "1,234.56" and bare numbers.
        Allows zero amounts for cancelled/placeholder awards.
        """
        if v is None or v == "":
            raise ValueError("Award amount must be provided and numeric")
        # If provided as a string, try to coerce to float
        if isinstance(v, str):
            try:
                v = float(v.replace(",", "").strip())
            except Exception:
                raise ValueError("Award amount must be a number")
        try:
            v_float = float(v)
        except Exception:
            raise ValueError("Award amount must be a number")
        if v_float < 0:
            raise ValueError("Award amount must be non-negative")
        return v_float

    @field_validator("program")
    @classmethod
    def validate_program(cls, v: str) -> str | None:
        """Validate program is SBIR or STTR and normalize to uppercase.

        Lenient: Attempts to extract SBIR or STTR from variations like
        "SBIR/STTR", "SBIR-Phase I", etc. Returns None for invalid values
        rather than rejecting the entire record.
        """
        from loguru import logger

        if v is None:
            return v  # type: ignore[unreachable]

        # Normalize to uppercase and strip whitespace
        normalized = str(v).upper().strip()

        # Exact match (most common case)
        if normalized in ["SBIR", "STTR"]:
            return normalized

        # Try to extract SBIR or STTR from variations
        # Handle cases like "SBIR/STTR", "SBIR-Phase I", "STTR Phase II"
        if "SBIR" in normalized:
            logger.warning(
                f"Program field '{v}' contains SBIR but not exact match - normalizing to SBIR"
            )
            return "SBIR"
        if "STTR" in normalized:
            logger.warning(
                f"Program field '{v}' contains STTR but not exact match - normalizing to STTR"
            )
            return "STTR"

        # Invalid value - return None (lenient)
        logger.warning(
            f"Program field '{v}' is not SBIR or STTR - setting to None to preserve record"
        )
        return None

    @field_validator("phase")
    @classmethod
    def validate_phase(cls, v: str | None) -> str | None:
        """Validate phase if provided. Normalize to roman I/II/III.

        Accepts both "Phase I" format (SBIR.gov) and "I" format (consolidated).

        Lenient: Attempts to normalize numeric phases (1, 2, 3, 4) and handle
        variations. Returns None for invalid values rather than rejecting the
        entire record.
        """
        from loguru import logger

        if v is None:
            return v
        sv = str(v).strip()
        # Handle "Phase I", "Phase II", "Phase III" format
        if sv.upper().startswith("PHASE "):
            sv = sv.upper().replace("PHASE ", "")
        sv = sv.upper()

        # Exact match (most common case)
        if sv in ["I", "II", "III"]:
            return sv

        # Try to normalize numeric phases to roman numerals
        phase_map = {"1": "I", "2": "II", "3": "III", "4": "III"}  # Phase IV -> Phase III
        if sv in phase_map:
            normalized = phase_map[sv]
            if sv == "4":
                logger.warning(f"Phase field '{v}' is Phase IV (not standard) - normalizing to III")
            return normalized

        # Handle IV as Phase III (non-standard but occurs in data)
        if sv == "IV":
            logger.warning(f"Phase field '{v}' is Phase IV (not standard) - normalizing to III")
            return "III"

        # Invalid value - return None (lenient)
        logger.warning(f"Phase field '{v}' is not I/II/III - setting to None to preserve record")
        return None

    @field_validator("fiscal_year")
    @classmethod
    def validate_fiscal_year(cls, v: int | None) -> int | None:
        """Validate fiscal year range.

        Lenient: Accepts out-of-range years with a warning rather than
        rejecting the entire record. This preserves historical or future-dated
        awards.
        """
        from loguru import logger

        if v is not None and (v < 1983 or v > 2050):
            logger.warning(
                f"Fiscal year {v} is out of typical range (1983-2050) - accepting anyway to preserve record"
            )
        return v

    @field_validator("award_year")
    @classmethod
    def validate_award_year_matches_date(cls: Any, v: int | None, info: Any) -> int | None:
        """Prioritize award_date year over award_year field. Auto-correct if mismatch.

        If award_date exists, its year takes priority:
        - If award_year is None, populate it from award_date.year
        - If award_year differs from award_date.year, auto-correct to award_date.year
        If award_date doesn't exist, award_year is used as-is (fallback).
        """
        award_date_val = info.data.get("award_date") if hasattr(info, "data") else None
        if award_date_val and isinstance(award_date_val, date):
            # award_date is the source of truth - always use its year
            return award_date_val.year
        # No award_date available, use award_year as fallback
        return v

    @field_validator("company_uei")
    @classmethod
    def validate_company_uei(cls, v: str | None) -> str | None:
        """Normalize and validate UEI if provided.

        This validator strips any non-alphanumeric characters (hyphens, spaces,
        etc.) from the input. If the result is exactly 12 characters, returns
        the uppercased UEI. Otherwise, returns None (lenient - accept bad data
        rather than rejecting the entire record).
        """
        if v is None:
            return v
        if not isinstance(v, str):
            return None  # Lenient: return None for non-string
        # Remove non-alphanumeric characters commonly present in raw input (spaces, hyphens)
        cleaned = "".join(ch for ch in v if ch.isalnum()).strip()
        if len(cleaned) != 12:
            # Lenient: return None instead of raising exception
            return None
        return cleaned.upper()

    @field_validator("company_duns")
    @classmethod
    def validate_company_duns(cls, v: str | None) -> str | None:
        """Normalize and validate DUNS if provided.

        Returns 9-digit DUNS if valid, None if invalid (lenient - accept bad
        data rather than rejecting the entire record).
        """
        if v is None:
            return v
        if not isinstance(v, str):
            return None  # Lenient: return None for non-string
        digits = "".join(ch for ch in v if ch.isdigit())
        if len(digits) != 9:
            # Lenient: return None instead of raising exception
            return None
        return digits

    @field_validator("company_state")
    @classmethod
    def validate_company_state(cls, v: str | None) -> str | None:
        """Normalize state code to uppercase 2-letter code.

        Returns uppercased 2-letter code if valid, None if invalid (lenient -
        accept bad data rather than rejecting the entire record).
        """
        if v is None:
            return v
        if not isinstance(v, str):
            return None  # Lenient: return None for non-string
        code = v.strip().upper()
        if len(code) != 2:
            # Lenient: return None instead of raising exception
            return None
        return code

    @field_validator("company_zip")
    @classmethod
    def validate_company_zip(cls, v: str | None) -> str | None:
        """Normalize ZIP to digits and validate 5 or 9 digits.

        Returns digits-only ZIP if valid (5 or 9 digits), None if invalid
        (lenient - accept bad data rather than rejecting the entire record).
        """
        if v is None:
            return v
        if not isinstance(v, str):
            return None  # Lenient: return None for non-string
        digits = "".join(ch for ch in v if ch.isdigit())
        if len(digits) not in (5, 9):
            # Lenient: return None instead of raising exception
            return None
        return digits

    @field_validator("number_of_employees", mode="before")
    @classmethod
    def validate_number_of_employees(cls: Any, v) -> int | None:
        """Allow number_of_employees to be provided as a string; coerce to int and validate non-negative.

        Lenient: Accepts floats (rounds to nearest int), extracts digits from
        text like "approx 500", and returns None for invalid values rather than
        rejecting the entire record.
        """
        from loguru import logger

        if v is None or v == "":
            return None

        # Accept numeric strings like "1,234"
        if isinstance(v, str):
            # Try to extract digits from the string
            cleaned = v.replace(",", "").strip()
            try:
                # Try parsing as float first (handles "123.5")
                float_val = float(cleaned)
                if float_val < 0:
                    logger.warning(f"Number of employees '{v}' is negative - setting to None")
                    return None
                # Round to nearest int
                int_val = round(float_val)
                if abs(float_val - int_val) > 0.01:  # If it's not close to an integer
                    logger.warning(f"Number of employees '{v}' is a float - rounding to {int_val}")
                return int_val
            except ValueError:
                # Try extracting just the digits (handles "approx 500")
                digits = "".join(ch for ch in cleaned if ch.isdigit())
                if digits:
                    logger.warning(
                        f"Number of employees '{v}' is not pure numeric - extracting {digits}"
                    )
                    return int(digits)
                # Can't parse - return None (lenient)
                logger.warning(
                    f"Number of employees '{v}' cannot be parsed - setting to None to preserve record"
                )
                return None

        # Handle float values
        if isinstance(v, float):
            if v < 0:
                logger.warning(f"Number of employees {v} is negative - setting to None")
                return None
            int_val = round(v)
            if abs(v - int_val) > 0.01:
                logger.warning(f"Number of employees {v} is a float - rounding to {int_val}")
            return int_val

        # Handle int values
        if isinstance(v, int):
            if v < 0:
                logger.warning(f"Number of employees {v} is negative - setting to None")
                return None
            return v

        # Unknown type - return None (lenient)
        logger.warning(
            f"Number of employees has unexpected type {type(v)} - setting to None to preserve record"
        )
        return None

    @field_validator("award_date")
    @classmethod
    def validate_award_date_not_future(cls: Any, v: date) -> date:
        """Validate that award_date is not in the future.

        Awards should not be dated in the future. This catches data entry errors
        or placeholder dates that should be cleaned.

        Note: This is now lenient - it accepts future dates with a warning logged
        rather than rejecting the record.
        """
        from datetime import date as date_cls

        from loguru import logger

        today = date_cls.today()
        if v > today:
            # Lenient: log warning but accept the date
            logger.warning(f"Award date is in the future: {v} (today: {today})")
        return v

    @field_validator("proposal_award_date")
    @classmethod
    def validate_proposal_date_order(cls: Any, v: date | None, info: Any) -> date | None:
        """If proposal_award_date and award_date present, ensure proposal came before award.

        Proposal dates should precede or match award dates - it doesn't make sense
        for a proposal to be dated after the award decision.

        Note: This is now lenient - it accepts reversed dates with a warning logged
        rather than rejecting the record.
        """
        if v is None:
            return v
        from loguru import logger

        award_date_val = info.data.get("award_date") if hasattr(info, "data") else None
        if award_date_val and isinstance(award_date_val, date):
            # Proposal should be before or on the same day as award
            if v > award_date_val:
                # Lenient: log warning but accept the date
                logger.warning(f"Proposal date ({v}) is after award date ({award_date_val})")
        return v

    @field_validator("contract_start_date")
    @classmethod
    def validate_contract_start_not_future(cls: Any, v: date | None) -> date | None:
        """Validate that contract_start_date is not unreasonably far in the future.

        Note: This is now lenient - it accepts far-future dates with a warning logged
        rather than rejecting the record.
        """
        if v is None:
            return v
        from datetime import date as date_cls

        from loguru import logger

        today = date_cls.today()
        # Allow up to 2 years in the future for planned contracts
        max_future_date = date_cls(today.year + 2, today.month, today.day)
        if v > max_future_date:
            # Lenient: log warning but accept the date
            logger.warning(
                f"Contract start date ({v}) is far in future (max expected: {max_future_date})"
            )
        return v

    @field_validator("contract_end_date")
    @classmethod
    def validate_date_order(cls: Any, v: date | None, info: Any) -> date | None:
        """Validate contract end date consistency with start and proposal dates.

        Checks:
        1. End date >= start date (if both present)
        2. End date >= proposal/award date (if both present)

        Note: This is now lenient - it accepts invalid date orders with a warning logged
        rather than rejecting the record.
        """
        if v is None:
            return v
        from loguru import logger

        # Check against contract_start_date if present
        start = info.data.get("contract_start_date") if hasattr(info, "data") else None
        if start and isinstance(start, date) and v < start:
            # Lenient: log warning but accept the date
            logger.warning(f"Contract end date ({v}) is before start date ({start})")

        # Check against proposal_award_date if present
        proposal = info.data.get("proposal_award_date") if hasattr(info, "data") else None
        if proposal and isinstance(proposal, date) and v < proposal:
            # Lenient: log warning but accept the date
            logger.warning(f"Contract end date ({v}) is before proposal date ({proposal})")

        return v

    @model_validator(mode="after")
    def populate_award_year_from_date(self) -> "Award":
        """Populate award_year from award_date if not already set.

        This runs after all field validation and ensures award_year is always
        populated when award_date is available. Uses object.__setattr__ to
        bypass validate_assignment and avoid re-triggering field validators.
        """
        if self.award_year is None and self.award_date:
            object.__setattr__(self, "award_year", self.award_date.year)
        return self

    model_config = ConfigDict(
        validate_assignment=True,
        populate_by_name=True,  # Allow both field names and aliases
        str_strip_whitespace=True,
    )

    @field_serializer(
        "award_date",
        "proposal_award_date",
        "contract_start_date",
        "contract_end_date",
        "solicitation_date",
        "solicitation_close_date",
        "proposal_receipt_date",
        "date_of_notification",
        when_used="json",
    )
    def serialize_date(self, v: date | None) -> str | None:
        """Serialize date fields to ISO format."""
        return v.isoformat() if v else None

    @classmethod
    def from_sbir_csv(cls, data: dict) -> "Award":
        """Create Award from SBIR.gov CSV format data.

        Handles field name mapping from SBIR.gov CSV format to consolidated Award model.
        If award_id is not provided, generates it from agency_tracking_number and contract.
        """
        # Map SBIR.gov CSV field names to Award model fields
        mapped_data = {}
        field_mapping = {
            "company_name": "company_name",  # Direct mapping for normalized column
            "company": "company_name",  # Fallback for original CSV format
            "uei": "company_uei",
            "duns": "company_duns",
            "address1": "address1",
            "address2": "address2",
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

        for sbir_key, award_key in field_mapping.items():
            if sbir_key in data:
                mapped_data[award_key] = data[sbir_key]

        # Copy fields that are the same in both formats
        for key in [
            "award_id",  # Add award_id to direct copy fields
            "award_title",
            "abstract",
            "agency",
            "branch",
            "phase",
            "program",
            "award_amount",
            "award_date",  # Add award_date to list of copied fields
            "award_year",
            "proposal_award_date",
            "contract_end_date",
            "contract",
            "agency_tracking_number",
            "solicitation_number",
            "contact_name",
            "contact_title",
            "contact_phone",
            "contact_email",
            "pi_title",
            "pi_phone",
            "pi_email",
            "ri_poc_name",
            "ri_poc_phone",
            "solicitation_close_date",
            "proposal_receipt_date",
            "date_of_notification",
            "solicitation_year",
            "topic_code",
            "company_website",
            "address1",
            "address2",
        ]:
            if key in data:
                mapped_data[key] = data[key]

        # Combine address1 and address2 into company_address if company_address not provided
        if "company_address" not in mapped_data and (
            "address1" in mapped_data or "address2" in mapped_data
        ):
            addr_parts = [mapped_data.get("address1"), mapped_data.get("address2")]
            addr_parts_filtered: list[str] = [str(p) for p in addr_parts if p]
            if addr_parts_filtered:
                mapped_data["company_address"] = ", ".join(addr_parts_filtered)

        # Generate award_id if not provided
        if "award_id" not in mapped_data and "award_id" not in data:
            tracking = mapped_data.get("agency_tracking_number") or data.get(
                "agency_tracking_number", ""
            )
            contract = mapped_data.get("contract") or data.get("contract", "")
            if tracking and contract:
                mapped_data["award_id"] = f"{tracking}_{contract}"
            elif tracking:
                mapped_data["award_id"] = tracking
            elif contract:
                mapped_data["award_id"] = contract
            else:
                # Fallback: generate from agency and award_year if available
                agency = mapped_data.get("agency") or data.get("agency", "UNKNOWN")
                year = mapped_data.get("award_year") or data.get("award_year", "")
                mapped_data["award_id"] = f"{agency}_{year}_UNKNOWN"

        # Handle award_date - if not provided, use proposal_award_date
        if "award_date" not in mapped_data and "award_date" not in data:
            proposal_date = mapped_data.get("proposal_award_date")
            if proposal_date:
                mapped_data["award_date"] = proposal_date
            else:
                # Try to infer from award_year
                award_year = mapped_data.get("award_year")
                if award_year:
                    from datetime import date as date_cls

                    mapped_data["award_date"] = date_cls(award_year, 1, 1)

        return cls(**mapped_data)


class RawAward(BaseModel):
    """Raw award data before validation/transformation.

    This model represents the raw input shape (e.g., CSV rows) where many fields
    are optional and dates are often strings. Consumers should transform/parse
    RawAward into validated `Award` instances as part of ingestion.
    """

    # Raw fields (all optional)
    award_id: str | None = None
    company_name: str | None = None
    award_title: str | None = None
    # Accept numeric strings in raw input (e.g., "1,234.56") — coercion happens in to_award()
    award_amount: str | float | None = None
    award_date: str | None = None  # Raw string date, to be parsed
    award_year: int | None = None
    program: str | None = None
    phase: str | None = None
    agency: str | None = None
    branch: str | None = None
    contract: str | None = None
    abstract: str | None = None
    keywords: str | None = None

    # Identifiers
    company_uei: str | None = None
    company_duns: str | None = None
    company_cage: str | None = None

    # Address / contact
    company_address: str | None = None
    company_city: str | None = None
    company_state: str | None = None
    company_zip: str | None = None
    contact_name: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None
    principal_investigator: str | None = None
    research_institution: str | None = None

    # Timeline (strings in raw)
    proposal_award_date: str | None = None
    contract_start_date: str | None = None
    contract_end_date: str | None = None
    solicitation_date: str | None = None

    # Business classifications
    is_hubzone: bool | None = None
    is_woman_owned: bool | None = None
    is_socially_disadvantaged: bool | None = None

    # Company metadata
    # Accept numeric strings for number_of_employees (e.g., "1,234") — coercion happens in to_award()
    number_of_employees: str | int | None = None
    company_website: str | None = None

    def to_award(self) -> "Award":
        """Convert this RawAward into a validated Award instance.

        Parsing/coercion rules applied:
        - Date strings are parsed into date objects for award_date,
          proposal_award_date, contract_start_date, contract_end_date, solicitation_date.
          Parsing order:
            1) ISO-format via datetime.fromisoformat (handles YYYY-MM-DD and ISO with time)
            2) YYYY-MM-DD via strptime
            3) Common US formats: MM/DD/YYYY, MM-DD-YYYY, MM/DD/YY
        - Numeric-ish strings for award_amount and number_of_employees are coerced.
        - ZIP strings are cleaned to digits only.
        - If parsing fails for a numeric required field, a ValueError is raised.
        """
        # Use pydantic model_dump to get a plain dict of values (pydantic v2)
        data = self.model_dump()

        # Parse dates using centralized utility
        from src.utils.common.date_utils import parse_date

        date_fields = [
            "award_date",
            "proposal_award_date",
            "contract_start_date",
            "contract_end_date",
            "solicitation_date",
        ]
        for f in date_fields:
            val = data.get(f)
            if val is not None:
                parsed = parse_date(val, strict=False)
                data[f] = parsed

        # Coerce award_amount if provided as string
        aa = data.get("award_amount")
        if isinstance(aa, str):
            try:
                data["award_amount"] = float(aa.replace(",", "").strip())
            except Exception:
                raise ValueError("award_amount must be numeric")

        # Coerce number_of_employees if string
        noe = data.get("number_of_employees")
        if isinstance(noe, str):
            try:
                data["number_of_employees"] = int(noe.replace(",", "").strip())
            except Exception:
                data["number_of_employees"] = None

        # Normalize ZIP to digits
        z = data.get("company_zip")
        if isinstance(z, str):
            digits = "".join(ch for ch in z if ch.isdigit())
            data["company_zip"] = digits if digits else None

        # Construct and return validated Award (let pydantic validators run)
        return Award(**data)

    model_config = ConfigDict(validate_assignment=True)
