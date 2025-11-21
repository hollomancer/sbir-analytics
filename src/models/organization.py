"""Pydantic models for unified Organization data."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Organization(BaseModel):
    """Unified organization model consolidating Company, PatentEntity, ResearchInstitution, and Agency.

    This model represents all organizational entities in the graph:
    - Companies (SBIR recipients, federal contractors)
    - Universities/Research Institutions
    - Government agencies (funding agencies)
    - Patent entities (companies, universities, government entities involved in patent assignments)
    """

    # Unified identifier
    organization_id: str = Field(..., description="Unique organization identifier")

    # Common properties
    name: str = Field(..., description="Organization name")
    normalized_name: str | None = Field(None, description="Normalized name for matching")
    address: str | None = Field(None, description="Street address")
    city: str | None = Field(None, description="City")
    state: str | None = Field(None, description="State or province code")
    postcode: str | None = Field(None, description="Postal/ZIP code")
    country: str | None = Field(None, description="Country code", default="US")

    # Entity classification
    organization_type: Literal["COMPANY", "UNIVERSITY", "GOVERNMENT", "AGENCY"] = Field(
        ..., description="Type of organization"
    )
    source_contexts: list[str] = Field(
        default_factory=list,
        description="Source contexts: SBIR, PATENT, RESEARCH, AGENCY",
    )

    # SBIR-specific (nullable)
    uei: str | None = Field(None, description="Unique Entity Identifier (SAM.gov)")
    cage: str | None = Field(None, description="CAGE code")
    duns: str | None = Field(None, description="DUNS number (9 digits)")
    business_size: str | None = Field(None, description="SMALL_BUSINESS or OTHER")
    company_id: str | None = Field(
        None, description="Legacy SBIR company_id for backward compatibility"
    )
    naics_primary: str | None = Field(None, description="Primary NAICS code")

    # Patent-specific (nullable)
    entity_id: str | None = Field(None, description="Legacy PatentEntity identifier")
    entity_category: str | None = Field(
        None, description="COMPANY, INDIVIDUAL, UNIVERSITY, GOVERNMENT (from patent context)"
    )
    num_assignments_as_assignee: int | None = Field(
        None, description="Number of assignments as assignee"
    )
    num_assignments_as_assignor: int | None = Field(
        None, description="Number of assignments as assignor"
    )
    num_patents_owned: int | None = Field(None, description="Number of patents owned")
    is_sbir_company: bool | None = Field(None, description="True if matches SBIR company")

    # Agency-specific (nullable)
    agency_code: str | None = Field(None, description="Agency code (e.g., '17' for DoD)")
    agency_name: str | None = Field(
        None, description="Full agency name (e.g., 'Department of Defense')"
    )
    sub_agency_code: str | None = Field(
        None, description="Sub-agency code (e.g., '5700' for Air Force)"
    )
    sub_agency_name: str | None = Field(None, description="Sub-agency name")

    # Transition metrics (nullable, computed from transitions)
    transition_total_awards: int | None = Field(
        None, ge=0, description="Total SBIR awards for this company"
    )
    transition_total_transitions: int | None = Field(
        None, ge=0, description="Total detected transitions"
    )
    transition_success_rate: float | None = Field(
        None, ge=0.0, le=1.0, description="Transition success rate (transitions / awards)"
    )
    transition_avg_likelihood_score: float | None = Field(
        None, ge=0.0, le=1.0, description="Average likelihood score across transitions"
    )
    transition_profile_updated_at: datetime | None = Field(
        None, description="When transition metrics were last updated"
    )

    # Metadata
    created_at: datetime | None = Field(
        default_factory=datetime.utcnow, description="Creation timestamp"
    )
    updated_at: datetime | None = Field(
        default_factory=datetime.utcnow, description="Last update timestamp"
    )

    @field_validator("duns")
    @classmethod
    def validate_duns(cls, v):
        """Validate DUNS number format."""
        if v is None:
            return v
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
        if len(v) != 5:
            raise ValueError("CAGE code must be 5 characters")
        return v.upper()

    @field_validator("uei")
    @classmethod
    def validate_uei(cls, v):
        """Normalize and validate UEI if provided."""
        if v is None:
            return v
        if not isinstance(v, str):
            return None
        cleaned = "".join(ch for ch in v if ch.isalnum()).strip()
        if len(cleaned) != 12:
            return None
        return cleaned.upper()

    @field_validator("source_contexts")
    @classmethod
    def validate_source_contexts(cls, v):
        """Ensure source_contexts is a list."""
        if isinstance(v, str):
            return [v]
        return v or []

    model_config = ConfigDict(validate_assignment=True)


class OrganizationMatch(BaseModel):
    """Result of organization matching/deduplication."""

    source_organization: Organization
    matched_organization: Organization
    confidence_score: float = Field(..., ge=0.0, le=1.0, description="Match confidence (0-1)")
    match_method: str = Field(..., description="Method used for matching")

    @field_validator("confidence_score")
    @classmethod
    def validate_confidence(cls, v):
        """Validate confidence score is between 0 and 1."""
        if not (0.0 <= v <= 1.0):
            raise ValueError("Confidence score must be between 0.0 and 1.0")
        return v
