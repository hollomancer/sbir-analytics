"""Pydantic models for patent data."""

from datetime import date
from typing import List, Optional

from pydantic import BaseModel, Field, validator


class Patent(BaseModel):
    """Patent data model."""

    # Core patent information
    patent_number: str = Field(..., description="Patent number")
    title: str = Field(..., description="Patent title")
    abstract: Optional[str] = Field(None, description="Patent abstract")

    # Filing and grant dates
    filing_date: Optional[date] = Field(None, description="Filing date")
    grant_date: Optional[date] = Field(None, description="Grant date")
    publication_date: Optional[date] = Field(None, description="Publication date")

    # Inventor information
    inventors: List[str] = Field(default_factory=list, description="List of inventor names")
    assignee: Optional[str] = Field(None, description="Patent assignee")

    # Classification
    uspc_class: Optional[str] = Field(None, description="US Patent Classification")
    cpc_class: Optional[str] = Field(None, description="Cooperative Patent Classification")

    # Status and type
    status: Optional[str] = Field(None, description="Patent status")
    patent_type: Optional[str] = Field(None, description="Type of patent")

    # Links and references
    application_number: Optional[str] = Field(None, description="Application number")
    related_patents: List[str] = Field(default_factory=list, description="Related patent numbers")

    # SBIR connection
    sbir_award_id: Optional[str] = Field(None, description="Associated SBIR award ID")

    @validator("patent_number")
    def validate_patent_number(cls, v):
        """Validate patent number format."""
        if v:
            # Remove any non-alphanumeric characters for validation
            clean_number = ''.join(c for c in v if c.isalnum())
            if len(clean_number) < 6:
                raise ValueError("Patent number too short")
        return v

    @validator("inventors")
    def validate_inventors(cls, v):
        """Validate inventors list."""
        if v and len(v) == 0:
            raise ValueError("Inventors list cannot be empty if provided")
        return v

    class Config:
        """Pydantic configuration."""
        validate_assignment = True
        json_encoders = {
            date: lambda v: v.isoformat()
        }


class RawPatent(BaseModel):
    """Raw patent data before validation."""

    patent_number: Optional[str] = None
    title: Optional[str] = None
    abstract: Optional[str] = None
    filing_date: Optional[str] = None  # Raw string date
    grant_date: Optional[str] = None
    publication_date: Optional[str] = None
    inventors: Optional[List[str]] = None
    assignee: Optional[str] = None
    uspc_class: Optional[str] = None
    cpc_class: Optional[str] = None

    class Config:
        """Pydantic configuration."""
        validate_assignment = True


class PatentCitation(BaseModel):
    """Patent citation relationship."""

    citing_patent: str = Field(..., description="Patent making the citation")
    cited_patent: str = Field(..., description="Patent being cited")
    citation_type: str = Field(..., description="Type of citation")
    citation_date: Optional[date] = Field(None, description="Date of citation")

    class Config:
        """Pydantic configuration."""
        validate_assignment = True
        json_encoders = {
            date: lambda v: v.isoformat()
        }