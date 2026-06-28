"""Pydantic models for SBIR award data."""

from datetime import UTC, date, datetime
from typing import Any

from loguru import logger
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)

from sbir_etl.utils.date_utils import parse_date

_PHASE_NORMALIZE = {
    "I": "I",
    "II": "II",
    "III": "III",
    "1": "I",
    "2": "II",
    "3": "III",
    "4": "III",  # Phase IV — non-standard, fold into III with a warning.
    "IV": "III",
}


def _clean_digits(v: Any, *, allowed_lengths: tuple[int, ...]) -> str | None:
    """Extract digits from `v`; return them only if length matches one of `allowed_lengths`."""
    if v is None:
        return None
    if isinstance(v, float) and v.is_integer():
        v = str(int(v))
    if not isinstance(v, str):
        return None
    digits = "".join(ch for ch in v if ch.isdigit())
    return digits if len(digits) in allowed_lengths else None


class Award(BaseModel):
    """Unified SBIR/STTR award data model.

    Supports both general SBIR award data and SBIR.gov CSV format with field
    aliases. Validators are lenient — bad fields generally become None rather
    than rejecting the whole record.

    Field aliases (SBIR.gov CSV → consolidated):
        company → company_name; uei → company_uei; duns → company_duns;
        city → company_city; state → company_state; zip → company_zip;
        hubzone_owned → is_hubzone; woman_owned → is_woman_owned;
        socially_and_economically_disadvantaged → is_socially_disadvantaged;
        number_employees → number_of_employees; pi_name → principal_investigator;
        ri_name → research_institution.
    """

    # Required fields
    award_id: str = Field(..., description="Unique award identifier")
    company_name: str = Field(..., description="Company receiving the award", alias="company")
    award_amount: float | None = Field(None, description="Award amount in USD")
    award_date: date | None = Field(None, description="Date award was made")
    program: str | None = Field(None, description="SBIR or STTR program (lenient validator)")

    # Optional metadata
    phase: str | None = Field(None, description="Phase I, II, or III")
    agency: str | None = Field(None, description="Federal agency")
    branch: str | None = Field(None, description="Agency branch")
    contract: str | None = Field(None, description="Contract number")
    abstract: str | None = Field(None, description="Project abstract")
    keywords: str | None = Field(None, description="Project keywords")
    award_title: str | None = Field(None, description="Award / project title")

    # Identifier fields
    company_uei: str | None = Field(None, description="Unique Entity Identifier (UEI)", alias="uei")
    company_duns: str | None = Field(None, description="DUNS number from SAM.gov", alias="duns")
    company_cage: str | None = Field(None, description="CAGE code from SAM.gov")

    # Company address
    company_address: str | None = Field(None, description="Company address from SAM.gov")
    address1: str | None = Field(None, description="Primary address line (SBIR.gov format)")
    address2: str | None = Field(None, description="Secondary address line (SBIR.gov format)")
    company_city: str | None = Field(None, description="Company city from SAM.gov", alias="city")
    company_state: str | None = Field(None, description="Company state from SAM.gov", alias="state")
    company_zip: str | None = Field(None, description="Company ZIP code from SAM.gov", alias="zip")

    # Congressional district (enriched)
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

    # Contact / personnel
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
        None, description="Research Institution POC name (SBIR.gov format)"
    )
    ri_poc_phone: str | None = Field(
        None, description="Research Institution POC phone (SBIR.gov format)"
    )

    # Timeline
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

    # Tracking
    agency_tracking_number: str | None = Field(None, description="Agency tracking number")
    solicitation_number: str | None = Field(None, description="Solicitation number")
    solicitation_year: int | None = Field(
        None, description="Year of solicitation (SBIR.gov format)", ge=1983, le=2026
    )
    topic_code: str | None = Field(
        None, description="Topic code from solicitation (SBIR.gov format)"
    )

    # Business classification flags
    is_hubzone: bool | None = Field(None, description="HUBZone designation", alias="hubzone_owned")
    is_woman_owned: bool | None = Field(
        None, description="Woman-owned business flag", alias="woman_owned"
    )
    is_socially_disadvantaged: bool | None = Field(
        None,
        description="Socially/economically disadvantaged flag",
        alias="socially_and_economically_disadvantaged",
    )

    # Company metadata
    number_of_employees: int | None = Field(
        None, description="Number of employees", alias="number_employees"
    )
    company_website: str | None = Field(None, description="Company website URL")

    # USAspending enrichment
    usaspending_id: str | None = Field(None, description="USAspending.gov award ID")
    fiscal_year: int | None = Field(None, description="Fiscal year of award")

    # Additional tracking / metadata
    award_year: int | None = Field(None, description="Award year as integer")

    # Data source provenance
    data_source: str | None = Field(
        None, description="Original data source system (e.g., 'sbir.gov', 'usaspending', 'sam.gov')"
    )
    data_source_url: str | None = Field(
        None, description="URL or path of the source file (e.g., S3 URI, local CSV path)"
    )
    ingested_at: datetime | None = Field(
        None, description="UTC timestamp when this record was ingested into the pipeline"
    )

    model_config = ConfigDict(
        validate_assignment=True,
        populate_by_name=True,  # Allow both field names and aliases
        str_strip_whitespace=True,
    )

    # --- Validators ---

    @field_validator("ingested_at", mode="before")
    @classmethod
    def validate_ingested_at_utc(cls, v: Any) -> datetime | None:
        """Coerce ingested_at to timezone-aware UTC; naive datetimes are assumed UTC."""
        if v is None or not isinstance(v, datetime):
            return v
        return v.replace(tzinfo=UTC) if v.tzinfo is None else v.astimezone(UTC)

    @field_validator("award_amount", mode="before")
    @classmethod
    def validate_award_amount(cls, v: Any) -> float | None:
        """Coerce to float; accept numeric strings with commas. Lenient: bad → None."""
        if v is None or v == "":
            return None
        if isinstance(v, str):
            try:
                v = float(v.replace(",", "").strip())
            except Exception:
                return None
        try:
            f = float(v)
        except Exception:
            return None
        return f if f >= 0 else None

    @field_validator("award_date", mode="before")
    @classmethod
    def validate_award_date(cls, v: Any) -> date | None:
        """Parse award_date strings; lenient on format failures."""
        result = parse_date(v)
        return result.date() if isinstance(result, datetime) else result

    @field_validator("program")
    @classmethod
    def validate_program(cls, v: str | None) -> str | None:
        """Validate program is SBIR or STTR; extract from variations like 'SBIR/STTR'."""
        if v is None:
            return v
        normalized = str(v).upper().strip()
        if normalized in ("SBIR", "STTR"):
            return normalized
        for prog in ("SBIR", "STTR"):
            if prog in normalized:
                logger.warning(
                    f"Program field '{v}' contains {prog} but not exact match — normalizing to {prog}"
                )
                return prog
        logger.warning(
            f"Program field '{v}' is not SBIR or STTR — setting to None to preserve record"
        )
        return None

    @field_validator("phase")
    @classmethod
    def validate_phase(cls, v: str | None) -> str | None:
        """Validate phase if provided; normalize to roman I/II/III (lenient)."""
        if v is None:
            return v
        sv = str(v).strip().upper().removeprefix("PHASE ").strip()
        if normalized := _PHASE_NORMALIZE.get(sv):
            if sv in ("4", "IV"):
                logger.warning(f"Phase field '{v}' is Phase IV (not standard) — normalizing to III")
            return normalized
        logger.warning(f"Phase field '{v}' is not I/II/III — setting to None to preserve record")
        return None

    @field_validator("fiscal_year")
    @classmethod
    def validate_fiscal_year(cls, v: int | None) -> int | None:
        """Validate fiscal year range (lenient — warn but accept out-of-range)."""
        if v is not None and not (1983 <= v <= 2050):
            logger.warning(
                f"Fiscal year {v} is out of typical range (1983-2050) — accepting anyway"
            )
        return v

    @field_validator("award_year")
    @classmethod
    def validate_award_year_matches_date(cls, v: int | None, info: Any) -> int | None:
        """If award_date is set, its year wins; otherwise use award_year as-is."""
        award_date_val = info.data.get("award_date") if hasattr(info, "data") else None
        if isinstance(award_date_val, date):
            return award_date_val.year
        return v

    @field_validator("company_uei")
    @classmethod
    def validate_company_uei(cls, v: str | None) -> str | None:
        """Strip non-alphanumeric chars; keep only 12-char UEIs (uppercased)."""
        if v is None:
            return v
        if not isinstance(v, str):
            return None
        cleaned = "".join(ch for ch in v if ch.isalnum()).strip()
        return cleaned.upper() if len(cleaned) == 12 else None

    @field_validator("company_duns", mode="before")
    @classmethod
    def validate_company_duns(cls, v: Any) -> str | None:
        """Coerce DUNS to 9 digits; lenient on non-string or wrong-length values."""
        return _clean_digits(v if not isinstance(v, int) else str(v), allowed_lengths=(9,))

    @field_validator("company_state")
    @classmethod
    def validate_company_state(cls, v: str | None) -> str | None:
        """Normalize state code to uppercase 2-letter code; lenient otherwise."""
        if v is None:
            return v
        if not isinstance(v, str):
            return None
        code = v.strip().upper()
        return code if len(code) == 2 else None

    @field_validator("company_zip")
    @classmethod
    def validate_company_zip(cls, v: str | None) -> str | None:
        """Normalize ZIP to digits; keep only 5- or 9-digit ZIPs."""
        return _clean_digits(v, allowed_lengths=(5, 9))

    @field_validator("number_of_employees", mode="before")
    @classmethod
    def validate_number_of_employees(cls, v: Any) -> int | None:
        """Coerce employee count to non-negative int; lenient on commas, floats, and 'approx 500'."""
        if v is None or v == "":
            return None

        # Try direct numeric coercion (handles int, float, "1,234", "123.5").
        if isinstance(v, str):
            cleaned = v.replace(",", "").strip()
            try:
                f = float(cleaned)
            except ValueError:
                # Last-ditch: extract digits from text like "approx 500".
                digits = "".join(ch for ch in cleaned if ch.isdigit())
                if digits:
                    logger.warning(
                        f"Number of employees '{v}' is not pure numeric — extracting {digits}"
                    )
                    return int(digits)
                logger.warning(f"Number of employees '{v}' cannot be parsed — setting to None")
                return None
        elif isinstance(v, (int, float)):
            f = float(v)
        else:
            logger.warning(f"Number of employees has unexpected type {type(v)} — setting to None")
            return None

        if f < 0:
            logger.warning(f"Number of employees {v} is negative — setting to None")
            return None
        rounded = round(f)
        if abs(f - rounded) > 0.01:
            logger.warning(f"Number of employees {v} is a float — rounding to {rounded}")
        return rounded

    @field_validator("award_date")
    @classmethod
    def validate_award_date_not_future(cls, v: date | None) -> date | None:
        """Warn (but accept) if award_date is in the future."""
        if v is not None and v > date.today():
            logger.warning(f"Award date is in the future: {v} (today: {date.today()})")
        return v

    @field_validator("proposal_award_date")
    @classmethod
    def validate_proposal_date_order(cls, v: date | None, info: Any) -> date | None:
        """Warn (but accept) if proposal_award_date is after award_date."""
        if v is None:
            return v
        award_date_val = info.data.get("award_date") if hasattr(info, "data") else None
        if isinstance(award_date_val, date) and v > award_date_val:
            logger.warning(f"Proposal date ({v}) is after award date ({award_date_val})")
        return v

    @field_validator("contract_start_date")
    @classmethod
    def validate_contract_start_not_future(cls, v: date | None) -> date | None:
        """Warn (but accept) contract_start_date > 2 years in the future."""
        if v is None:
            return v
        today = date.today()
        max_future = date(today.year + 2, today.month, today.day)
        if v > max_future:
            logger.warning(
                f"Contract start date ({v}) is far in future (max expected: {max_future})"
            )
        return v

    @field_validator("contract_end_date")
    @classmethod
    def validate_date_order(cls, v: date | None, info: Any) -> date | None:
        """Warn (but accept) when contract_end_date precedes start or proposal dates."""
        if v is None:
            return v
        data = info.data if hasattr(info, "data") else {}
        for label in ("contract_start_date", "proposal_award_date"):
            other = data.get(label)
            if isinstance(other, date) and v < other:
                logger.warning(f"Contract end date ({v}) is before {label} ({other})")
        return v

    @model_validator(mode="after")
    def populate_award_year_from_date(self) -> "Award":
        """Backfill award_year from award_date when missing."""
        if self.award_year is None and self.award_date:
            object.__setattr__(self, "award_year", self.award_date.year)
        return self

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
        """Create an Award from SBIR.gov CSV format data.

        Maps CSV column names to model fields, derives `award_id` from
        agency_tracking_number / contract / agency+year if not provided,
        and falls back award_date → proposal_award_date → Jan 1 of award_year.
        """
        # SBIR.gov column name → model field name (only entries that differ).
        field_mapping = {
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

        # Fields that pass through unchanged when present in `data`.
        direct_copy_keys = frozenset(
            {
                "award_id",
                "award_title",
                "abstract",
                "agency",
                "branch",
                "phase",
                "program",
                "award_amount",
                "award_date",
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
                "company_name",
                "address1",
                "address2",
            }
        )

        mapped: dict[str, Any] = {}
        for sbir_key, award_key in field_mapping.items():
            if sbir_key in data:
                mapped[award_key] = data[sbir_key]
        for key in direct_copy_keys:
            if key in data:
                mapped[key] = data[key]

        # Combine address1/address2 into company_address if needed.
        if "company_address" not in mapped:
            addr_parts = [str(p) for p in (mapped.get("address1"), mapped.get("address2")) if p]
            if addr_parts:
                mapped["company_address"] = ", ".join(addr_parts)

        # Synthesize award_id when missing.
        if "award_id" not in mapped:
            tracking = mapped.get("agency_tracking_number") or data.get(
                "agency_tracking_number", ""
            )
            contract = mapped.get("contract") or data.get("contract", "")
            if tracking and contract:
                mapped["award_id"] = f"{tracking}_{contract}"
            elif tracking or contract:
                mapped["award_id"] = tracking or contract
            else:
                agency = mapped.get("agency") or data.get("agency", "UNKNOWN")
                year = mapped.get("award_year") or data.get("award_year", "")
                mapped["award_id"] = f"{agency}_{year}_UNKNOWN"

        # Fall back award_date → proposal_award_date → Jan 1 of award_year.
        if "award_date" not in mapped:
            if proposal_date := mapped.get("proposal_award_date"):
                mapped["award_date"] = proposal_date
            elif award_year := mapped.get("award_year"):
                mapped["award_date"] = date(award_year, 1, 1)

        return cls(**mapped)


class RawAward(BaseModel):
    """Raw award data before validation/transformation.

    Represents the raw input shape (e.g., CSV rows) where most fields are
    optional and dates are often strings. Consumers should call `to_award()`
    to parse/validate into a final `Award` instance.
    """

    award_id: str | None = None
    company_name: str | None = None
    award_title: str | None = None
    award_amount: str | float | None = None
    award_date: str | None = None
    award_year: int | None = None
    program: str | None = None
    phase: str | None = None
    agency: str | None = None
    branch: str | None = None
    contract: str | None = None
    abstract: str | None = None
    keywords: str | None = None

    company_uei: str | None = None
    company_duns: str | None = None
    company_cage: str | None = None

    company_address: str | None = None
    company_city: str | None = None
    company_state: str | None = None
    company_zip: str | None = None
    contact_name: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None
    principal_investigator: str | None = None
    research_institution: str | None = None

    proposal_award_date: str | None = None
    contract_start_date: str | None = None
    contract_end_date: str | None = None
    solicitation_date: str | None = None

    is_hubzone: bool | None = None
    is_woman_owned: bool | None = None
    is_socially_disadvantaged: bool | None = None

    number_of_employees: str | int | None = None
    company_website: str | None = None

    data_source: str | None = None
    data_source_url: str | None = None
    ingested_at: datetime | None = None

    model_config = ConfigDict(validate_assignment=True)

    def to_award(self) -> "Award":
        """Parse this RawAward and return a validated Award instance."""
        from sbir_etl.utils.date_utils import parse_date

        data = self.model_dump()

        for f in (
            "award_date",
            "proposal_award_date",
            "contract_start_date",
            "contract_end_date",
            "solicitation_date",
        ):
            if (val := data.get(f)) is not None:
                data[f] = parse_date(val, strict=False)

        aa = data.get("award_amount")
        if isinstance(aa, str):
            try:
                data["award_amount"] = float(aa.replace(",", "").strip())
            except Exception as e:
                raise ValueError("award_amount must be numeric") from e

        noe = data.get("number_of_employees")
        if isinstance(noe, str):
            try:
                data["number_of_employees"] = int(noe.replace(",", "").strip())
            except Exception:
                data["number_of_employees"] = None

        z = data.get("company_zip")
        if isinstance(z, str):
            digits = "".join(ch for ch in z if ch.isdigit())
            data["company_zip"] = digits or None

        return Award(**data)
