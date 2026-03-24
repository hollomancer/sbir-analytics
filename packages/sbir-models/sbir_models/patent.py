"""Pydantic models for patent data."""

from datetime import date

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator


class Patent(BaseModel):
    """Patent data model."""

    # Core patent information
    patent_number: str = Field(..., description="Patent number")
    title: str = Field(..., description="Patent title")
    abstract: str | None = Field(None, description="Patent abstract")

    # Filing and grant dates
    filing_date: date | None = Field(None, description="Filing date")
    grant_date: date | None = Field(None, description="Grant date")
    publication_date: date | None = Field(None, description="Publication date")

    # Inventor information
    inventors: list[str] = Field(default_factory=list, description="List of inventor names")
    assignee: str | None = Field(None, description="Patent assignee")

    # Classification
    uspc_class: str | None = Field(None, description="US Patent Classification")
    cpc_class: str | None = Field(None, description="Cooperative Patent Classification")

    # Status and type
    status: str | None = Field(None, description="Patent status")
    patent_type: str | None = Field(None, description="Type of patent")

    # Links and references
    application_number: str | None = Field(None, description="Application number")
    related_patents: list[str] = Field(default_factory=list, description="Related patent numbers")

    # SBIR connection
    sbir_award_id: str | None = Field(None, description="Associated SBIR award ID")

    @field_validator("patent_number")
    @classmethod
    def validate_patent_number(cls, v):
        """Validate patent number format."""
        if v:
            # Remove any non-alphanumeric characters for validation
            clean_number = "".join(c for c in v if c.isalnum())
            if len(clean_number) < 6:
                raise ValueError("Patent number too short")
        return v

    @field_validator("inventors")
    @classmethod
    def validate_inventors(cls, v):
        """Validate inventors list.

        If an empty list is explicitly provided, treat it as invalid.
        Require at least one inventor when the field is present.
        """
        if isinstance(v, list) and len(v) == 0:
            raise ValueError("Inventors list cannot be empty")
        return v

    model_config = ConfigDict(validate_assignment=True)

    @field_serializer("filing_date", "grant_date", "publication_date", when_used="json")
    def serialize_date(self, v: date | None) -> str | None:
        """Serialize date to ISO format."""
        return v.isoformat() if v else None


class RawPatent(BaseModel):
    """Raw patent data before validation."""

    patent_number: str | None = None
    title: str | None = None
    abstract: str | None = None
    filing_date: str | None = None  # Raw string date
    grant_date: str | None = None
    publication_date: str | None = None
    inventors: list[str] | None = None
    assignee: str | None = None
    uspc_class: str | None = None
    cpc_class: str | None = None

    model_config = ConfigDict(validate_assignment=True)


class PatentCitation(BaseModel):
    """Patent citation relationship."""

    citing_patent: str = Field(..., description="Patent making the citation")
    cited_patent: str = Field(..., description="Patent being cited")
    citation_type: str = Field(..., description="Type of citation")
    citation_date: date | None = Field(None, description="Date of citation")

    model_config = ConfigDict(validate_assignment=True)

    @field_serializer("citation_date", when_used="json")
    def serialize_date(self, v: date | None) -> str | None:
        """Serialize date to ISO format."""
        return v.isoformat() if v else None


class PatentsViewPatent(BaseModel):
    """Patent data model from PatentsView API."""

    # Core patent information
    patent_number: str = Field(..., description="Patent number")
    patent_title: str | None = Field(None, description="Patent title")
    patent_date: date | None = Field(None, description="Patent date")

    # Assignee information
    assignee_organization: str | None = Field(None, description="Assignee organization name")
    assignee_id: str | None = Field(None, description="Assignee ID in PatentsView")

    # Filing and grant dates
    filing_date: date | None = Field(None, description="Filing date")
    grant_date: date | None = Field(None, description="Grant date")

    # Inventor information
    inventors: list[str] = Field(default_factory=list, description="List of inventor names")

    model_config = ConfigDict(validate_assignment=True)

    @field_serializer("patent_date", "filing_date", "grant_date", when_used="json")
    def serialize_date(self, v: date | None) -> str | None:
        """Serialize date to ISO format."""
        return v.isoformat() if v else None


class PatentAssignment(BaseModel):
    """Patent assignment/reassignment record."""

    patent_number: str = Field(..., description="Patent number")
    assignee: str | None = Field(None, description="Current assignee")
    assignor: str | None = Field(None, description="Previous assignee (assignor)")
    execution_date: date | None = Field(None, description="Assignment execution date")
    recorded_date: date | None = Field(None, description="Assignment recorded date")
    assignment_type: str | None = Field(
        None, description="Assignment type (e.g., ASSIGNMENT, LICENSE)"
    )

    model_config = ConfigDict(validate_assignment=True)

    @field_serializer("execution_date", "recorded_date", when_used="json")
    def serialize_date(self, v: date | None) -> str | None:
        """Serialize date to ISO format."""
        return v.isoformat() if v else None
