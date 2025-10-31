"""Pydantic models for SBIR award data."""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


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
    award_date: date = Field(..., description="Date award was made")
    program: str = Field(..., description="SBIR or STTR program")

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

    # Contact / personnel (with aliases for SBIR.gov format)
    contact_name: str | None = Field(None, description="Primary contact name")
    contact_title: str | None = Field(None, description="Contact title/position (SBIR.gov format)")
    contact_email: str | None = Field(None, description="Primary contact email")
    contact_phone: str | None = Field(None, description="Primary contact phone")
    principal_investigator: str | None = Field(None, description="Principal Investigator", alias="pi_name")
    pi_title: str | None = Field(None, description="PI title/position (SBIR.gov format)")
    pi_phone: str | None = Field(None, description="PI phone number (SBIR.gov format)")
    pi_email: str | None = Field(None, description="PI email address (SBIR.gov format)")
    research_institution: str | None = Field(
        None, description="Research institution or PI affiliation", alias="ri_name"
    )
    ri_poc_name: str | None = Field(None, description="Research Institution POC name (SBIR.gov format)", alias="ri_poc_name")
    ri_poc_phone: str | None = Field(None, description="Research Institution POC phone (SBIR.gov format)", alias="ri_poc_phone")

    # Timeline fields (with aliases for SBIR.gov format)
    proposal_award_date: date | None = Field(None, description="Proposal or award decision date")
    contract_start_date: date | None = Field(None, description="Contract start date")
    contract_end_date: date | None = Field(None, description="Contract end date")
    solicitation_date: date | None = Field(
        None, description="Solicitation / solicitation release date"
    )
    solicitation_close_date: date | None = Field(None, description="Solicitation closing date (SBIR.gov format)")
    proposal_receipt_date: date | None = Field(None, description="Date proposal was received (SBIR.gov format)")
    date_of_notification: date | None = Field(None, description="Date company was notified (SBIR.gov format)")

    # Tracking fields (with aliases for SBIR.gov format)
    agency_tracking_number: str | None = Field(None, description="Agency tracking number")
    solicitation_number: str | None = Field(None, description="Solicitation number")
    solicitation_year: int | None = Field(None, description="Year of solicitation (SBIR.gov format)", ge=1983, le=2026)
    topic_code: str | None = Field(None, description="Topic code from solicitation (SBIR.gov format)")

    # Business classification flags (with aliases for SBIR.gov format)
    is_hubzone: bool | None = Field(None, description="HUBZone designation", alias="hubzone_owned")
    is_woman_owned: bool | None = Field(None, description="Woman-owned business flag", alias="woman_owned")
    is_socially_disadvantaged: bool | None = Field(
        None, description="Socially/economically disadvantaged flag", alias="socially_and_economically_disadvantaged"
    )

    # Company metadata (with aliases for SBIR.gov format)
    number_of_employees: int | None = Field(None, description="Number of employees", alias="number_employees")
    company_website: str | None = Field(None, description="Company website URL")

    # USAspending enrichment
    usaspending_id: str | None = Field(None, description="USAspending.gov award ID")
    fiscal_year: int | None = Field(None, description="Fiscal year of award")

    # Additional tracking / metadata
    award_year: int | None = Field(None, description="Award year as integer")

    # --- Validators ---

    @field_validator("award_amount", mode="before")
    @classmethod
    def validate_award_amount(cls, v) -> float:
        """Coerce award_amount from string to float (if needed) and validate it's positive.

        Accepts numeric strings like "1,234.56" and bare numbers.
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
        if v_float <= 0:
            raise ValueError("Award amount must be positive")
        return v_float

    @field_validator("program")
    @classmethod
    def validate_program(cls, v: str) -> str:
        """Validate program is SBIR or STTR and normalize to uppercase."""
        if v is None:
            return v
        if v.upper() not in ["SBIR", "STTR"]:
            raise ValueError("Program must be SBIR or STTR")
        return v.upper()

    @field_validator("phase")
    @classmethod
    def validate_phase(cls, v: str | None) -> str | None:
        """Validate phase if provided. Normalize to roman I/II/III.
        
        Accepts both "Phase I" format (SBIR.gov) and "I" format (consolidated).
        """
        if v is None:
            return v
        sv = str(v).strip()
        # Handle "Phase I", "Phase II", "Phase III" format
        if sv.upper().startswith("PHASE "):
            sv = sv.upper().replace("PHASE ", "")
        sv = sv.upper()
        if sv not in ["I", "II", "III"]:
            raise ValueError("Phase must be I, II, or III (or Phase I, Phase II, Phase III)")
        return sv

    @field_validator("fiscal_year")
    @classmethod
    def validate_fiscal_year(cls, v: int | None) -> int | None:
        """Validate fiscal year range."""
        if v is not None and (v < 1983 or v > 2050):
            raise ValueError("Fiscal year must be between 1983 and 2050")
        return v

    @field_validator("award_year")
    @classmethod
    def validate_award_year_matches_date(cls, v: int | None, info) -> int | None:
        """If award_year provided, ensure it matches award_date year when award_date exists."""
        if v is None:
            return v
        award_date_val = info.data.get("award_date") if hasattr(info, "data") else None
        if award_date_val and isinstance(award_date_val, date):
            if v != award_date_val.year:
                raise ValueError("award_year must match award_date year")
        return v

    @field_validator("company_uei")
    @classmethod
    def validate_company_uei(cls, v: str | None) -> str | None:
        """Normalize and validate UEI if provided.

        This validator strips any non-alphanumeric characters (hyphens, spaces,
        etc.) from the input and then expects the remaining characters to be a
        12-character alphanumeric UEI. The returned value is uppercased.
        """
        if v is None:
            return v
        if not isinstance(v, str):
            raise ValueError("Company UEI must be a string")
        # Remove non-alphanumeric characters commonly present in raw input (spaces, hyphens)
        cleaned = "".join(ch for ch in v if ch.isalnum()).strip()
        if len(cleaned) != 12:
            raise ValueError(
                "Company UEI must be a 12-character alphanumeric string after removing separators"
            )
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

    @field_validator("company_state")
    @classmethod
    def validate_company_state(cls, v: str | None) -> str | None:
        """Normalize state code to uppercase 2-letter code."""
        if v is None:
            return v
        if not isinstance(v, str):
            raise ValueError("State must be a string")
        code = v.strip().upper()
        if len(code) != 2:
            raise ValueError("State code must be 2 letters")
        return code

    @field_validator("company_zip")
    @classmethod
    def validate_company_zip(cls, v: str | None) -> str | None:
        """Normalize ZIP to digits and validate 5 or 9 digits."""
        if v is None:
            return v
        if not isinstance(v, str):
            raise ValueError("ZIP must be a string")
        digits = "".join(ch for ch in v if ch.isdigit())
        if len(digits) not in (5, 9):
            raise ValueError("ZIP code must be 5 or 9 digits")
        return digits

    @field_validator("number_of_employees", mode="before")
    @classmethod
    def validate_number_of_employees(cls, v) -> int | None:
        """Allow number_of_employees to be provided as a string; coerce to int and validate non-negative."""
        if v is None or v == "":
            return None
        # Accept numeric strings like "1,234"
        if isinstance(v, str):
            try:
                v = int(v.replace(",", "").strip())
            except Exception:
                raise ValueError("Number of employees must be an integer")
        if not isinstance(v, int):
            raise ValueError("Number of employees must be an integer")
        if v < 0:
            raise ValueError("Number of employees must be non-negative")
        return v

    @field_validator("contract_end_date")
    @classmethod
    def validate_date_order(cls, v: date | None, info) -> date | None:
        """If contract_end_date and proposal_award_date present, ensure consistency."""
        if v is None:
            return v
        start = info.data.get("proposal_award_date") if hasattr(info, "data") else None
        if start and isinstance(start, date) and v < start:
            raise ValueError("contract_end_date must be on or after proposal_award_date")
        return v

    model_config = ConfigDict(
        validate_assignment=True,
        populate_by_name=True,  # Allow both field names and aliases
        str_strip_whitespace=True,
        json_encoders={date: lambda v: v.isoformat()}
    )

    @classmethod
    def from_sbir_csv(cls, data: dict) -> "Award":
        """Create Award from SBIR.gov CSV format data.

        Handles field name mapping from SBIR.gov CSV format to consolidated Award model.
        If award_id is not provided, generates it from agency_tracking_number and contract.
        """
        # Map SBIR.gov CSV field names to Award model fields
        mapped_data = {}
        field_mapping = {
            "company": "company_name",
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
        for key in ["award_title", "abstract", "agency", "branch", "phase", "program",
                    "award_amount", "award_year", "proposal_award_date", "contract_end_date",
                    "contract", "agency_tracking_number", "solicitation_number",
                    "contact_name", "contact_title", "contact_phone", "contact_email",
                    "pi_title", "pi_phone", "pi_email", "ri_poc_name", "ri_poc_phone",
                    "solicitation_close_date", "proposal_receipt_date", "date_of_notification",
                    "solicitation_year", "topic_code", "company_website", "address1", "address2"]:
            if key in data:
                mapped_data[key] = data[key]

        # Combine address1 and address2 into company_address if company_address not provided
        if "company_address" not in mapped_data and ("address1" in mapped_data or "address2" in mapped_data):
            addr_parts = [mapped_data.get("address1"), mapped_data.get("address2")]
            addr_parts = [p for p in addr_parts if p]
            if addr_parts:
                mapped_data["company_address"] = ", ".join(addr_parts)

        # Generate award_id if not provided
        if "award_id" not in mapped_data and "award_id" not in data:
            tracking = mapped_data.get("agency_tracking_number") or data.get("agency_tracking_number", "")
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

        # Parse dates (attempt ISO first, then YYYY-MM-DD, then common US formats)
        date_fields = [
            "award_date",
            "proposal_award_date",
            "contract_start_date",
            "contract_end_date",
            "solicitation_date",
        ]
        us_formats = ("%m/%d/%Y", "%m-%d-%Y", "%m/%d/%y")
        for f in date_fields:
            val = data.get(f)
            if isinstance(val, str):
                parsed = None
                s = val.strip()
                # Try ISO first (handles 'YYYY-MM-DD' and ISO datetimes)
                try:
                    parsed = datetime.fromisoformat(s).date()
                except Exception:
                    # Try explicit YYYY-MM-DD
                    try:
                        parsed = datetime.strptime(s, "%Y-%m-%d").date()
                    except Exception:
                        # Try common US formats
                        for fmt in us_formats:
                            try:
                                parsed = datetime.strptime(s, fmt).date()
                                break
                            except Exception:
                                parsed = None
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
