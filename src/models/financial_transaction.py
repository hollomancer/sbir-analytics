"""Pydantic models for unified FinancialTransaction data."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class FinancialTransaction(BaseModel):
    """Unified financial transaction model consolidating Award and Contract.

    This model represents all financial transactions in the graph:
    - SBIR/STTR Awards (transaction_type: "AWARD")
    - Federal Contracts (transaction_type: "CONTRACT")
    """

    # Unified identifier
    transaction_id: str = Field(..., description="Unique transaction identifier")

    # Transaction classification
    transaction_type: Literal["AWARD", "CONTRACT"] = Field(
        ..., description="Type of transaction: AWARD or CONTRACT"
    )

    # Common properties
    agency: str | None = Field(None, description="Awarding agency code")
    agency_name: str | None = Field(None, description="Full agency name")
    sub_agency: str | None = Field(None, description="Sub-agency code")
    sub_agency_name: str | None = Field(None, description="Sub-agency name")

    # Recipient/Vendor information
    recipient_name: str | None = Field(None, description="Recipient/vendor company name")
    recipient_uei: str | None = Field(None, description="Recipient/vendor UEI")
    recipient_duns: str | None = Field(None, description="Recipient/vendor DUNS number")
    recipient_cage: str | None = Field(None, description="Recipient/vendor CAGE code")

    # Financial information
    amount: float = Field(..., description="Transaction amount in USD")
    base_and_all_options_value: float | None = Field(
        None, description="Total potential value including options (contracts)"
    )

    # Dates
    transaction_date: date = Field(..., description="Transaction date (award_date or action_date)")
    start_date: date | None = Field(None, description="Period of performance start")
    end_date: date | None = Field(None, description="Period of performance end")
    completion_date: date | None = Field(None, description="Completion date (awards)")

    # Description
    title: str | None = Field(None, description="Transaction title")
    description: str | None = Field(None, description="Transaction description/abstract")

    # Classification
    naics_code: str | None = Field(None, description="NAICS code")
    naics_description: str | None = Field(None, description="NAICS description")

    # Award-specific (nullable)
    award_id: str | None = Field(
        None, description="Legacy Award identifier for backward compatibility"
    )
    phase: str | None = Field(
        None, description="Award phase: PHASE_I, PHASE_II, PHASE_IIB, PHASE_III"
    )
    program: str | None = Field(None, description="Program type: SBIR or STTR")
    principal_investigator: str | None = Field(None, description="Principal Investigator name")
    research_institution: str | None = Field(None, description="Research institution")
    cet_area: str | None = Field(None, description="Critical Emerging Technology area")
    award_year: int | None = Field(None, description="Award year")
    fiscal_year: int | None = Field(None, description="Fiscal year")

    # Contract-specific (nullable)
    contract_id: str | None = Field(
        None, description="Legacy Contract identifier for backward compatibility"
    )
    piid: str | None = Field(None, description="Procurement Instrument Identifier")
    fain: str | None = Field(None, description="Federal Award Identification Number")
    competition_type: str | None = Field(
        None, description="Competition type: SOLE_SOURCE, LIMITED, FULL_AND_OPEN"
    )
    psc_code: str | None = Field(None, description="Product/Service Code")
    place_of_performance: str | None = Field(None, description="Place of performance location")
    contract_type: str | None = Field(None, description="Contract type code")
    parent_uei: str | None = Field(
        None, description="Parent organization UEI (for subsidiary relationships)"
    )

    # Metadata
    created_at: datetime | None = Field(
        default_factory=datetime.utcnow, description="Creation timestamp"
    )
    updated_at: datetime | None = Field(
        default_factory=datetime.utcnow, description="Last update timestamp"
    )

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v):
        """Validate amount is positive."""
        if v is None:
            raise ValueError("Amount must be provided")
        if isinstance(v, str):
            v = float(v.replace(",", "").strip())
        if float(v) <= 0:
            raise ValueError("Amount must be positive")
        return float(v)

    @field_validator("transaction_date")
    @classmethod
    def validate_transaction_date_not_future(cls, v: date) -> date:
        """Validate that transaction_date is not unreasonably far in the future."""
        from datetime import date as date_cls

        from loguru import logger

        today = date_cls.today()
        max_future_date = date_cls(today.year + 2, today.month, today.day)
        if v > max_future_date:
            logger.warning(
                f"Transaction date ({v}) is far in future (max expected: {max_future_date})"
            )
        return v

    @field_validator("recipient_uei")
    @classmethod
    def validate_recipient_uei(cls, v):
        """Normalize and validate UEI if provided."""
        if v is None:
            return v
        if not isinstance(v, str):
            return None
        cleaned = "".join(ch for ch in v if ch.isalnum()).strip()
        if len(cleaned) != 12:
            return None
        return cleaned.upper()

    @field_validator("parent_uei")
    @classmethod
    def validate_parent_uei(cls, v):
        """Normalize and validate parent UEI if provided."""
        if v is None:
            return v
        if not isinstance(v, str):
            return None
        cleaned = "".join(ch for ch in v if ch.isalnum()).strip()
        if len(cleaned) != 12:
            return None
        return cleaned.upper()

    model_config = ConfigDict(validate_assignment=True)
