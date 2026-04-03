"""Pydantic model for SBIR/STTR solicitation topics."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator


class Solicitation(BaseModel):
    """SBIR/STTR solicitation topic.

    Represents a single topic within a solicitation cycle.  Topics contain
    the government's research need description (500-3000 words of technical
    prose) which is the highest-value text for LightRAG entity extraction.

    Data sources:
        - SBIR.gov API (``/solicitations`` endpoint)
        - SBIR.gov bulk downloads (``https://www.sbir.gov/data-resources``)
    """

    model_config = ConfigDict(
        str_strip_whitespace=True,
        populate_by_name=True,
    )

    # Required fields
    topic_code: str = Field(..., description="Topic identifier (e.g., 'AF231-001')")
    solicitation_number: str = Field(
        ..., description="Parent solicitation number (e.g., 'SBIR-2023.1')"
    )
    title: str = Field(..., description="Topic title")

    # Optional fields
    description: str | None = Field(None, description="Full topic description (500-3000 words)")
    agency: str | None = Field(None, description="Issuing agency (e.g., 'DOD', 'DOE')")
    branch: str | None = Field(None, description="Agency branch (e.g., 'Air Force', 'Navy')")
    program: str | None = Field(None, description="SBIR or STTR")
    open_date: date | None = Field(None, description="Solicitation open date")
    close_date: date | None = Field(None, description="Solicitation close date")
    year: int | None = Field(None, description="Solicitation year")

    @field_validator("program", mode="before")
    @classmethod
    def _normalize_program(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = str(v).strip().upper()
        if v in ("SBIR", "STTR"):
            return v
        return v or None

    @field_serializer("open_date", "close_date")
    def _serialize_date(self, v: date | None) -> str | None:
        return v.isoformat() if v else None
