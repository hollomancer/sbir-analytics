"""Pydantic models for researcher data."""

from pydantic import BaseModel, Field


class Researcher(BaseModel):
    """Researcher/Principal Investigator data model."""

    # Identifying fields
    name: str = Field(..., description="Researcher full name")
    email: str | None = Field(None, description="Email address")
    phone: str | None = Field(None, description="Phone number")

    # Affiliation
    institution: str | None = Field(None, description="Academic/research institution")
    department: str | None = Field(None, description="Department within institution")

    # Professional information
    title: str | None = Field(None, description="Professional title")
    expertise: str | None = Field(None, description="Research expertise/keywords")

    # Biographical information
    bio: str | None = Field(None, description="Researcher biography")
    website: str | None = Field(None, description="Personal/academic website")

    # Social/Professional links
    orcid: str | None = Field(None, description="ORCID identifier")
    linkedin: str | None = Field(None, description="LinkedIn profile URL")
    google_scholar: str | None = Field(None, description="Google Scholar profile URL")

    class Config:
        """Pydantic configuration."""

        validate_assignment = True


class RawResearcher(BaseModel):
    """Raw researcher data before validation."""

    name: str | None = None
    email: str | None = None
    phone: str | None = None
    institution: str | None = None
    department: str | None = None
    title: str | None = None
    expertise: str | None = None

    class Config:
        """Pydantic configuration."""

        validate_assignment = True
