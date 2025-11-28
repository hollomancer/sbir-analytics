from __future__ import annotations

from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, Field, field_validator


class CompetitionType(str, Enum):
    """Competition types for federal contracts."""

    SOLE_SOURCE = "sole_source"
    LIMITED = "limited"
    FULL_AND_OPEN = "full_and_open"
    SET_ASIDE = "set_aside"
    OTHER = "other"


class ContractStatus(str, Enum):
    """Contract status enumeration."""

    ACTIVE = "active"
    COMPLETED = "completed"
    TERMINATED = "terminated"
    CANCELLED = "cancelled"
    PENDING = "pending"


class VendorMatch(BaseModel):
    """Result of vendor/company resolution for a contract."""

    vendor_id: str | None = Field(
        None, description="Canonical vendor ID (e.g., company node id or UEI)."
    )
    method: str = Field(
        ..., description="How the match was determined ('uei', 'cage', 'duns', 'name_fuzzy', ...)."
    )
    score: float = Field(0.0, ge=0.0, le=1.0, description="Confidence score for the vendor match.")
    matched_name: str | None = Field(None, description="Matched vendor canonical name.")
    matched_uei: str | None = Field(None, description="Matched vendor UEI.")
    matched_cage: str | None = Field(None, description="Matched vendor CAGE code.")
    matched_duns: str | None = Field(None, description="Matched vendor DUNS number.")
    metadata: dict[str, object] = Field(
        default_factory=dict, description="Additional match metadata."
    )

    @field_validator("method")
    @classmethod
    def validate_method(cls, v):
        valid_methods = ["uei", "cage", "duns", "name_fuzzy", "address_match", "manual"]
        if v not in valid_methods:
            raise ValueError(f"method must be one of {valid_methods}")
        return v


class ContractParty(BaseModel):
    """Information about a party to the contract (vendor, contracting officer, etc.)."""

    name: str | None = Field(None, description="Party name.")
    uei: str | None = Field(None, description="Unique Entity ID.")
    cage_code: str | None = Field(None, description="CAGE code.")
    duns_number: str | None = Field(None, description="DUNS number.")
    address: str | None = Field(None, description="Full address.")
    city: str | None = Field(None, description="City.")
    state: str | None = Field(None, description="State/province.")
    zip_code: str | None = Field(None, description="ZIP/postal code.")
    country: str | None = Field(None, description="Country code.")


class ContractValue(BaseModel):
    """Contract value and obligation information."""

    obligated_amount: float | None = Field(None, ge=0.0, description="Total obligated amount.")
    current_value: float | None = Field(None, ge=0.0, description="Current contract value.")
    potential_value: float | None = Field(None, ge=0.0, description="Maximum potential value.")
    base_and_all_options_value: float | None = Field(
        None, ge=0.0, description="Base plus all options value."
    )
    currency: str = Field("USD", description="Currency code.")


class ContractPeriod(BaseModel):
    """Contract period and performance dates."""

    signed_date: date | None = Field(None, description="Date contract was signed.")
    effective_date: date | None = Field(None, description="Effective date of contract.")
    current_end_date: date | None = Field(None, description="Current end date.")
    ultimate_completion_date: date | None = Field(None, description="Ultimate completion date.")
    last_date_to_order: date | None = Field(None, description="Last date to order.")

    @field_validator(
        "signed_date",
        "effective_date",
        "current_end_date",
        "ultimate_completion_date",
        "last_date_to_order",
        mode="before",
    )
    @classmethod
    def parse_dates(cls, v):
        from src.utils.common.date_utils import parse_date

        result = parse_date(v, strict=True)
        if result is None:
            return None
        return result


class ContractDescription(BaseModel):
    """Contract description and classification information."""

    description: str | None = Field(None, description="Contract description text.")
    naics_code: str | None = Field(None, description="NAICS code.")
    naics_description: str | None = Field(None, description="NAICS description.")
    product_or_service_code: str | None = Field(None, description="PSC code.")
    product_or_service_description: str | None = Field(None, description="PSC description.")
    principal_naics_code: str | None = Field(None, description="Principal NAICS code.")


class FederalContract(BaseModel):
    """Comprehensive model for federal contract data used in transition detection."""

    # Primary identifiers
    contract_id: str = Field(..., description="Primary contract identifier (PIID).")
    piid: str | None = Field(None, description="Procurement Instrument ID.")
    modification_number: str | None = Field(None, description="Modification number.")
    transaction_number: int | None = Field(None, description="Transaction number.")

    # Agency information
    agency_code: str | None = Field(None, description="Agency code (e.g., '9700' for DOD).")
    agency_name: str | None = Field(None, description="Agency name.")
    department_code: str | None = Field(None, description="Department code.")
    department_name: str | None = Field(None, description="Department name.")
    contracting_office_code: str | None = Field(None, description="Contracting office code.")
    contracting_office_name: str | None = Field(None, description="Contracting office name.")
    funding_agency_code: str | None = Field(None, description="Funding agency code.")
    funding_agency_name: str | None = Field(None, description="Funding agency name.")

    # Vendor information
    vendor: ContractParty = Field(..., description="Vendor/contractor information.")
    contracting_officer: ContractParty | None = Field(
        None, description="Contracting officer information."
    )

    # Contract details
    status: ContractStatus = Field(ContractStatus.ACTIVE, description="Contract status.")
    competition_type: CompetitionType = Field(
        CompetitionType.OTHER, description="Competition type."
    )
    extent_competed: str | None = Field(None, description="Extent competed.")
    solicitation_procedures: str | None = Field(None, description="Solicitation procedures.")
    evaluator: str | None = Field(None, description="Evaluator (e.g., 'HUBZone', 'SDB').")

    # Contract type and vehicle
    contract_type: str | None = Field(None, description="Type of contract (e.g., 'IDIQ', 'BPA').")
    idv_type: str | None = Field(None, description="Indefinite Delivery Vehicle type.")
    multiple_or_single_award_idv: str | None = Field(
        None, description="Multiple or single award IDV."
    )
    cost_or_pricing_data: str | None = Field(None, description="Cost or pricing data.")
    commercial_item_acquisition_procedures: str | None = Field(
        None, description="Commercial item acquisition procedures."
    )
    commercial_item_test_program: str | None = Field(
        None, description="Commercial item test program."
    )
    consolidated_contract: str | None = Field(None, description="Consolidated contract flag.")
    contingency_humanitarian_or_peacekeeping_operation: str | None = Field(
        None, description="Contingency/humanitarian/peacekeeping operation."
    )
    contract_bundling: str | None = Field(None, description="Contract bundling.")
    contract_financing: str | None = Field(None, description="Contract financing.")
    contracting_officers_determination_of_business_size: str | None = Field(
        None, description="CO determination of business size."
    )
    country_of_origin: str | None = Field(None, description="Country of origin.")
    davis_bacon_act: str | None = Field(None, description="Davis-Bacon Act applicability.")
    evaluated_preference: str | None = Field(None, description="Evaluated preference.")
    fed_biz_opps: str | None = Field(None, description="FedBizOpps publication.")
    foreign_funding: str | None = Field(None, description="Foreign funding.")
    gfe_gfp: str | None = Field(None, description="Government Furnished Equipment/Property.")
    information_technology_commercial_item_category: str | None = Field(
        None, description="IT commercial item category."
    )
    interagency_contracting_authority: str | None = Field(
        None, description="Interagency contracting authority."
    )
    local_area_set_aside: str | None = Field(None, description="Local area set-aside.")
    major_program: str | None = Field(None, description="Major program.")
    purchase_card_as_payment_method: str | None = Field(
        None, description="Purchase card as payment method."
    )
    multi_year_contract: str | None = Field(None, description="Multi-year contract.")
    national_interest_action: str | None = Field(None, description="National interest action.")
    number_of_actions: int | None = Field(None, description="Number of actions.")
    number_of_offers_received: int | None = Field(None, description="Number of offers received.")
    other_than_full_and_open_competition: str | None = Field(
        None, description="Other than full and open competition."
    )
    performance_based_service_acquisition: str | None = Field(
        None, description="Performance-based service acquisition."
    )
    place_of_manufacture: str | None = Field(None, description="Place of manufacture.")
    place_of_performance_city: str | None = Field(None, description="Place of performance city.")
    place_of_performance_country: str | None = Field(
        None, description="Place of performance country."
    )
    place_of_performance_state: str | None = Field(None, description="Place of performance state.")
    place_of_performance_zip: str | None = Field(None, description="Place of performance ZIP.")
    price_evaluation_adjustment_preference_percent_difference: float | None = Field(
        None, description="Price evaluation adjustment preference percent difference."
    )
    program_acronym: str | None = Field(None, description="Program acronym.")
    reason_for_modification: str | None = Field(None, description="Reason for modification.")
    recurring_data: str | None = Field(None, description="Recurring data.")
    research: str | None = Field(None, description="Research contract.")
    sea_transportation: str | None = Field(None, description="Sea transportation.")
    service_contract_act: str | None = Field(None, description="Service Contract Act.")
    small_business_competitiveness_demonstration_program: str | None = Field(
        None, description="Small Business Competitiveness Demonstration Program."
    )
    solicitation_id: str | None = Field(None, description="Solicitation ID.")
    subcontracting_plan: str | None = Field(None, description="Subcontracting plan.")
    type_of_contract_pricing: str | None = Field(None, description="Type of contract pricing.")
    type_of_idc: str | None = Field(None, description="Type of IDC.")
    walsh_healey_act: str | None = Field(None, description="Walsh-Healey Act.")

    # Financial information
    value: ContractValue = Field(..., description="Contract value information.")
    period: ContractPeriod = Field(..., description="Contract period information.")

    # Classification and description
    description_info: ContractDescription = Field(
        ..., description="Contract description and classification."
    )

    # Transition detection fields
    matched_vendor: VendorMatch | None = Field(
        None, description="Result of vendor matching to SBIR companies."
    )
    transition_candidate_score: float | None = Field(
        None, ge=0.0, le=1.0, description="Score indicating potential for SBIR transition."
    )

    # Metadata
    source: str = Field("usaspending", description="Data source (usaspending, fpds, etc.).")
    last_modified: datetime | None = Field(None, description="Last modification timestamp.")
    created_at: datetime = Field(
        default_factory=datetime.utcnow, description="Record creation timestamp."
    )
    metadata: dict[str, object] = Field(default_factory=dict, description="Additional metadata.")

    @field_validator("contract_id")
    @classmethod
    def validate_contract_id(cls, v):
        if not v or not v.strip():
            raise ValueError("contract_id cannot be empty")
        return v.strip()

    @field_validator("agency_code")
    @classmethod
    def validate_agency_code(cls, v):
        if v is not None and len(str(v)) != 4:
            raise ValueError("agency_code should be 4 digits")
        return v


class ContractBatch(BaseModel):
    """Batch of contracts for processing."""

    contracts: list[FederalContract] = Field(
        default_factory=list, description="List of contracts in batch."
    )
    batch_id: str = Field(..., description="Unique batch identifier.")
    source: str = Field(..., description="Data source for this batch.")
    created_at: datetime = Field(
        default_factory=datetime.utcnow, description="Batch creation timestamp."
    )
    metadata: dict[str, object] = Field(default_factory=dict, description="Batch metadata.")

    def add_contract(self, contract: FederalContract) -> None:
        """Add a contract to the batch."""
        self.contracts.append(contract)

    def __len__(self) -> int:
        """Return number of contracts in batch."""
        return len(self.contracts)


class ContractSearchResult(BaseModel):
    """Result of searching for contracts related to an award."""

    award_id: str = Field(..., description="Award ID that was searched for.")
    contracts: list[FederalContract] = Field(
        default_factory=list, description="Matching contracts found."
    )
    search_criteria: dict[str, object] = Field(
        default_factory=dict, description="Search criteria used."
    )
    search_timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="When search was performed."
    )
    total_candidates: int = Field(0, description="Total candidate contracts examined.")
    metadata: dict[str, object] = Field(default_factory=dict, description="Search metadata.")


__all__ = [
    "CompetitionType",
    "ContractStatus",
    "VendorMatch",
    "ContractParty",
    "ContractValue",
    "ContractPeriod",
    "ContractDescription",
    "FederalContract",
    "ContractBatch",
    "ContractSearchResult",
]
