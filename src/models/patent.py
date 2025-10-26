"""Pydantic models for patent data."""

from datetime import date

from pydantic import BaseModel, Field, field_validator, ConfigDict


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

    model_config = ConfigDict(
        validate_assignment=True, json_encoders={date: lambda v: v.isoformat()}
    )


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

    model_config = ConfigDict(
        validate_assignment=True, json_encoders={date: lambda v: v.isoformat()}
    )


class PatentCitation(BaseModel):
    """Patent citation relationship."""

    citing_patent: str = Field(..., description="Patent making the citation")
    cited_patent: str = Field(..., description="Patent being cited")
    citation_type: str = Field(..., description="Type of citation")
    citation_date: date | None = Field(None, description="Date of citation")

    model_config = ConfigDict(
        validate_assignment=True, json_encoders={date: lambda v: v.isoformat()}
    )
