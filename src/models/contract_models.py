from __future__ import annotations

from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, field_validator
from datetime import date, datetime


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

    vendor_id: Optional[str] = Field(
        None, description="Canonical vendor ID (e.g., company node id or UEI)."
    )
    method: str = Field(
        ..., description="How the match was determined ('uei', 'cage', 'duns', 'name_fuzzy', ...)."
    )
    score: float = Field(0.0, ge=0.0, le=1.0, description="Confidence score for the vendor match.")
    matched_name: Optional[str] = Field(None, description="Matched vendor canonical name.")
    matched_uei: Optional[str] = Field(None, description="Matched vendor UEI.")
    matched_cage: Optional[str] = Field(None, description="Matched vendor CAGE code.")
    matched_duns: Optional[str] = Field(None, description="Matched vendor DUNS number.")
    metadata: Dict[str, object] = Field(
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

    name: Optional[str] = Field(None, description="Party name.")
    uei: Optional[str] = Field(None, description="Unique Entity ID.")
    cage_code: Optional[str] = Field(None, description="CAGE code.")
    duns_number: Optional[str] = Field(None, description="DUNS number.")
    address: Optional[str] = Field(None, description="Full address.")
    city: Optional[str] = Field(None, description="City.")
    state: Optional[str] = Field(None, description="State/province.")
    zip_code: Optional[str] = Field(None, description="ZIP/postal code.")
    country: Optional[str] = Field(None, description="Country code.")


class ContractValue(BaseModel):
    """Contract value and obligation information."""

    obligated_amount: Optional[float] = Field(None, ge=0.0, description="Total obligated amount.")
    current_value: Optional[float] = Field(None, ge=0.0, description="Current contract value.")
    potential_value: Optional[float] = Field(None, ge=0.0, description="Maximum potential value.")
    base_and_all_options_value: Optional[float] = Field(
        None, ge=0.0, description="Base plus all options value."
    )
    currency: str = Field("USD", description="Currency code.")


class ContractPeriod(BaseModel):
    """Contract period and performance dates."""

    signed_date: Optional[date] = Field(None, description="Date contract was signed.")
    effective_date: Optional[date] = Field(None, description="Effective date of contract.")
    current_end_date: Optional[date] = Field(None, description="Current end date.")
    ultimate_completion_date: Optional[date] = Field(None, description="Ultimate completion date.")
    last_date_to_order: Optional[date] = Field(None, description="Last date to order.")

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
        if v is None:
            return None
        if isinstance(v, (date, datetime)):
            return v.date() if isinstance(v, datetime) else v
        # Attempt ISO parse
        try:
            return date.fromisoformat(str(v))
        except Exception:
            raise ValueError("Dates must be ISO-formatted strings or date objects")


class ContractDescription(BaseModel):
    """Contract description and classification information."""

    description: Optional[str] = Field(None, description="Contract description text.")
    naics_code: Optional[str] = Field(None, description="NAICS code.")
    naics_description: Optional[str] = Field(None, description="NAICS description.")
    product_or_service_code: Optional[str] = Field(None, description="PSC code.")
    product_or_service_description: Optional[str] = Field(None, description="PSC description.")
    principal_naics_code: Optional[str] = Field(None, description="Principal NAICS code.")


class FederalContract(BaseModel):
    """Comprehensive model for federal contract data used in transition detection."""

    # Primary identifiers
    contract_id: str = Field(..., description="Primary contract identifier (PIID).")
    piid: Optional[str] = Field(None, description="Procurement Instrument ID.")
    modification_number: Optional[str] = Field(None, description="Modification number.")
    transaction_number: Optional[int] = Field(None, description="Transaction number.")

    # Agency information
    agency_code: Optional[str] = Field(None, description="Agency code (e.g., '9700' for DOD).")
    agency_name: Optional[str] = Field(None, description="Agency name.")
    department_code: Optional[str] = Field(None, description="Department code.")
    department_name: Optional[str] = Field(None, description="Department name.")
    contracting_office_code: Optional[str] = Field(None, description="Contracting office code.")
    contracting_office_name: Optional[str] = Field(None, description="Contracting office name.")
    funding_agency_code: Optional[str] = Field(None, description="Funding agency code.")
    funding_agency_name: Optional[str] = Field(None, description="Funding agency name.")

    # Vendor information
    vendor: ContractParty = Field(..., description="Vendor/contractor information.")
    contracting_officer: Optional[ContractParty] = Field(
        None, description="Contracting officer information."
    )

    # Contract details
    status: ContractStatus = Field(ContractStatus.ACTIVE, description="Contract status.")
    competition_type: CompetitionType = Field(
        CompetitionType.OTHER, description="Competition type."
    )
    extent_competed: Optional[str] = Field(None, description="Extent competed.")
    solicitation_procedures: Optional[str] = Field(None, description="Solicitation procedures.")
    evaluator: Optional[str] = Field(None, description="Evaluator (e.g., 'HUBZone', 'SDB').")

    # Contract type and vehicle
    contract_type: Optional[str] = Field(
        None, description="Type of contract (e.g., 'IDIQ', 'BPA')."
    )
    idv_type: Optional[str] = Field(None, description="Indefinite Delivery Vehicle type.")
    multiple_or_single_award_idv: Optional[str] = Field(
        None, description="Multiple or single award IDV."
    )
    cost_or_pricing_data: Optional[str] = Field(None, description="Cost or pricing data.")
    commercial_item_acquisition_procedures: Optional[str] = Field(
        None, description="Commercial item acquisition procedures."
    )
    commercial_item_test_program: Optional[str] = Field(
        None, description="Commercial item test program."
    )
    consolidated_contract: Optional[str] = Field(None, description="Consolidated contract flag.")
    contingency_humanitarian_or_peacekeeping_operation: Optional[str] = Field(
        None, description="Contingency/humanitarian/peacekeeping operation."
    )
    contract_bundling: Optional[str] = Field(None, description="Contract bundling.")
    contract_financing: Optional[str] = Field(None, description="Contract financing.")
    contracting_officers_determination_of_business_size: Optional[str] = Field(
        None, description="CO determination of business size."
    )
    country_of_origin: Optional[str] = Field(None, description="Country of origin.")
    davis_bacon_act: Optional[str] = Field(None, description="Davis-Bacon Act applicability.")
    evaluated_preference: Optional[str] = Field(None, description="Evaluated preference.")
    fed_biz_opps: Optional[str] = Field(None, description="FedBizOpps publication.")
    foreign_funding: Optional[str] = Field(None, description="Foreign funding.")
    gfe_gfp: Optional[str] = Field(None, description="Government Furnished Equipment/Property.")
    information_technology_commercial_item_category: Optional[str] = Field(
        None, description="IT commercial item category."
    )
    interagency_contracting_authority: Optional[str] = Field(
        None, description="Interagency contracting authority."
    )
    local_area_set_aside: Optional[str] = Field(None, description="Local area set-aside.")
    major_program: Optional[str] = Field(None, description="Major program.")
    purchase_card_as_payment_method: Optional[str] = Field(
        None, description="Purchase card as payment method."
    )
    multi_year_contract: Optional[str] = Field(None, description="Multi-year contract.")
    national_interest_action: Optional[str] = Field(None, description="National interest action.")
    number_of_actions: Optional[int] = Field(None, description="Number of actions.")
    number_of_offers_received: Optional[int] = Field(None, description="Number of offers received.")
    other_than_full_and_open_competition: Optional[str] = Field(
        None, description="Other than full and open competition."
    )
    performance_based_service_acquisition: Optional[str] = Field(
        None, description="Performance-based service acquisition."
    )
    place_of_manufacture: Optional[str] = Field(None, description="Place of manufacture.")
    place_of_performance_city: Optional[str] = Field(None, description="Place of performance city.")
    place_of_performance_country: Optional[str] = Field(
        None, description="Place of performance country."
    )
    place_of_performance_state: Optional[str] = Field(
        None, description="Place of performance state."
    )
    place_of_performance_zip: Optional[str] = Field(None, description="Place of performance ZIP.")
    price_evaluation_adjustment_preference_percent_difference: Optional[float] = Field(
        None, description="Price evaluation adjustment preference percent difference."
    )
    program_acronym: Optional[str] = Field(None, description="Program acronym.")
    reason_for_modification: Optional[str] = Field(None, description="Reason for modification.")
    recurring_data: Optional[str] = Field(None, description="Recurring data.")
    research: Optional[str] = Field(None, description="Research contract.")
    sea_transportation: Optional[str] = Field(None, description="Sea transportation.")
    service_contract_act: Optional[str] = Field(None, description="Service Contract Act.")
    small_business_competitiveness_demonstration_program: Optional[str] = Field(
        None, description="Small Business Competitiveness Demonstration Program."
    )
    solicitation_id: Optional[str] = Field(None, description="Solicitation ID.")
    subcontracting_plan: Optional[str] = Field(None, description="Subcontracting plan.")
    type_of_contract_pricing: Optional[str] = Field(None, description="Type of contract pricing.")
    type_of_idc: Optional[str] = Field(None, description="Type of IDC.")
    walsh_healey_act: Optional[str] = Field(None, description="Walsh-Healey Act.")

    # Financial information
    value: ContractValue = Field(..., description="Contract value information.")
    period: ContractPeriod = Field(..., description="Contract period information.")

    # Classification and description
    description_info: ContractDescription = Field(
        ..., description="Contract description and classification."
    )

    # Transition detection fields
    matched_vendor: Optional[VendorMatch] = Field(
        None, description="Result of vendor matching to SBIR companies."
    )
    transition_candidate_score: Optional[float] = Field(
        None, ge=0.0, le=1.0, description="Score indicating potential for SBIR transition."
    )

    # Metadata
    source: str = Field("usaspending", description="Data source (usaspending, fpds, etc.).")
    last_modified: Optional[datetime] = Field(None, description="Last modification timestamp.")
    created_at: datetime = Field(
        default_factory=datetime.utcnow, description="Record creation timestamp."
    )
    metadata: Dict[str, object] = Field(default_factory=dict, description="Additional metadata.")

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

    contracts: List[FederalContract] = Field(
        default_factory=list, description="List of contracts in batch."
    )
    batch_id: str = Field(..., description="Unique batch identifier.")
    source: str = Field(..., description="Data source for this batch.")
    created_at: datetime = Field(
        default_factory=datetime.utcnow, description="Batch creation timestamp."
    )
    metadata: Dict[str, object] = Field(default_factory=dict, description="Batch metadata.")

    def add_contract(self, contract: FederalContract) -> None:
        """Add a contract to the batch."""
        self.contracts.append(contract)

    def __len__(self) -> int:
        """Return number of contracts in batch."""
        return len(self.contracts)


class ContractSearchResult(BaseModel):
    """Result of searching for contracts related to an award."""

    award_id: str = Field(..., description="Award ID that was searched for.")
    contracts: List[FederalContract] = Field(
        default_factory=list, description="Matching contracts found."
    )
    search_criteria: Dict[str, object] = Field(
        default_factory=dict, description="Search criteria used."
    )
    search_timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="When search was performed."
    )
    total_candidates: int = Field(0, description="Total candidate contracts examined.")
    metadata: Dict[str, object] = Field(default_factory=dict, description="Search metadata.")


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
