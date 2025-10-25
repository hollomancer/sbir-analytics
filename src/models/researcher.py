"""Pydantic models for researcher data."""

from typing import Optional

from pydantic import BaseModel, Field


class Researcher(BaseModel):
    """Researcher/Principal Investigator data model."""

    # Identifying fields
    name: str = Field(..., description="Researcher full name")
    email: Optional[str] = Field(None, description="Email address")
    phone: Optional[str] = Field(None, description="Phone number")

    # Affiliation
    institution: Optional[str] = Field(None, description="Academic/research institution")
    department: Optional[str] = Field(None, description="Department within institution")

    # Professional information
    title: Optional[str] = Field(None, description="Professional title")
    expertise: Optional[str] = Field(None, description="Research expertise/keywords")

    # Biographical information
    bio: Optional[str] = Field(None, description="Researcher biography")
    website: Optional[str] = Field(None, description="Personal/academic website")

    # Social/Professional links
    orcid: Optional[str] = Field(None, description="ORCID identifier")
    linkedin: Optional[str] = Field(None, description="LinkedIn profile URL")
    google_scholar: Optional[str] = Field(None, description="Google Scholar profile URL")

    class Config:
        """Pydantic configuration."""
        validate_assignment = True


class RawResearcher(BaseModel):
    """Raw researcher data before validation."""

    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    institution: Optional[str] = None
    department: Optional[str] = None
    title: Optional[str] = None
    expertise: Optional[str] = None

    class Config:
        """Pydantic configuration."""
        validate_assignment = True