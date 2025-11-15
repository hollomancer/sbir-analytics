"""Pydantic models for unified Individual data."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Individual(BaseModel):
    """Unified individual model consolidating Researcher and PatentEntity (INDIVIDUAL).

    This model represents all individual persons in the graph:
    - Researchers/Principal Investigators (from SBIR awards)
    - Patent assignees/assignors (individuals from USPTO patent assignments)
    """

    # Unified identifier
    individual_id: str = Field(..., description="Unique individual identifier")

    # Common properties
    name: str = Field(..., description="Individual's full name")
    normalized_name: str | None = Field(None, description="Normalized name for matching")

    # Contact information
    email: str | None = Field(None, description="Email address")
    phone: str | None = Field(None, description="Phone number")

    # Address information (from patent assignments)
    address: str | None = Field(None, description="Street address")
    city: str | None = Field(None, description="City")
    state: str | None = Field(None, description="State or province code")
    postcode: str | None = Field(None, description="Postal/ZIP code")
    country: str | None = Field(None, description="Country code", default="US")

    # Entity classification
    individual_type: Literal["RESEARCHER", "PATENT_ASSIGNEE", "PATENT_ASSIGNOR"] = Field(
        ..., description="Type of individual"
    )
    source_contexts: list[str] = Field(
        default_factory=list,
        description="Source contexts: SBIR, PATENT",
    )

    # Researcher-specific (nullable)
    researcher_id: str | None = Field(None, description="Legacy Researcher identifier for backward compatibility")
    institution: str | None = Field(None, description="Academic/research institution")
    department: str | None = Field(None, description="Department within institution")
    title: str | None = Field(None, description="Professional title")
    expertise: str | None = Field(None, description="Research expertise/keywords")
    bio: str | None = Field(None, description="Researcher biography")
    website: str | None = Field(None, description="Personal/academic website")
    orcid: str | None = Field(None, description="ORCID identifier")
    linkedin: str | None = Field(None, description="LinkedIn profile URL")
    google_scholar: str | None = Field(None, description="Google Scholar profile URL")

    # Patent-specific (nullable)
    entity_id: str | None = Field(None, description="Legacy PatentEntity identifier")
    entity_type: str | None = Field(
        None, description="ASSIGNEE or ASSIGNOR (from patent context)"
    )
    num_assignments_as_assignee: int | None = Field(None, description="Number of assignments as assignee")
    num_assignments_as_assignor: int | None = Field(None, description="Number of assignments as assignor")

    # Metadata
    created_at: datetime | None = Field(default_factory=datetime.utcnow, description="Creation timestamp")
    updated_at: datetime | None = Field(default_factory=datetime.utcnow, description="Last update timestamp")

    @field_validator("email")
    @classmethod
    def validate_email(cls, v):
        """Basic email validation."""
        if v is None:
            return v
        if "@" not in v:
            return None  # Invalid email format
        return v.lower().strip()

    @field_validator("source_contexts")
    @classmethod
    def validate_source_contexts(cls, v):
        """Ensure source_contexts is a list."""
        if isinstance(v, str):
            return [v]
        return v or []

    model_config = ConfigDict(validate_assignment=True)


class IndividualMatch(BaseModel):
    """Result of individual matching/deduplication."""

    source_individual: Individual
    matched_individual: Individual
    confidence_score: float = Field(..., ge=0.0, le=1.0, description="Match confidence (0-1)")
    match_method: str = Field(..., description="Method used for matching")

    @field_validator("confidence_score")
    @classmethod
    def validate_confidence(cls, v):
        """Validate confidence score is between 0 and 1."""
        if not (0.0 <= v <= 1.0):
            raise ValueError("Confidence score must be between 0.0 and 1.0")
        return v

