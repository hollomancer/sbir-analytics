from __future__ import annotations

from typing import Any


"""
Pydantic models for USPTO patent data used by the SBIR ETL transition pipeline.

This module defines structured, validated data models for patent-related records
commonly encountered in USPTO datasets: documents, assignments, assignors,
assignees, and conveyances.

Models include:
- PatentDocument
- PatentAssignee
- PatentAssignor
- PatentConveyance
- PatentAssignment

Validators:
- Parse and normalize ISO-like date strings into datetime.date
- Normalize document numbers and identifiers
- Basic sanity checks for required fields and lengths
"""

import re
from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, Field, field_validator


# ---- Utilities ----
# Use centralized date parsing utility
from src.utils.date_utils import parse_date as _parse_date


def _normalize_identifier(val: str | None) -> str | None:
    if val is None:
        return None
    v = str(val).strip()
    if v == "":
        return None
    # Remove common punctuation and whitespace collapse
    v = re.sub(r"[^\w\-]", "", v).upper()
    return v


def _normalize_name(name: str | None) -> str | None:
    if name is None:
        return None
    n = " ".join(str(name).strip().split())
    # Replace multiple punctuation variants with single spaces for matching purposes
    n = re.sub(r"[,/&\.]+", " ", n)
    # Strip any trailing/leading spaces created by the substitution
    return n.strip()


# ---- Enums ----
class ConveyanceType(str, Enum):
    ASSIGNMENT = "assignment"
    LICENSE = "license"
    SECURITY_INTEREST = "security_interest"
    MERGER = "merger"
    OTHER = "other"


# ---- Models ----
class PatentDocument(BaseModel):
    """
    Represents a patent document record and common identifiers.
    """

    rf_id: str | None = Field(None, description="Repository-specific record identifier")
    application_number: str | None = Field(None, description="Application number (raw)")
    publication_number: str | None = Field(None, description="Publication number (raw)")
    grant_number: str | None = Field(None, description="Grant / patent number (raw)")
    filing_date: date | None = Field(None, description="Application filing date")
    publication_date: date | None = Field(None, description="Publication date")
    grant_date: date | None = Field(None, description="Grant/issue date")
    language: str | None = Field(None, description="Language code")
    title: str | None = Field(None, description="Title text")
    abstract: str | None = Field(None, description="Abstract text")
    raw: dict[str, object] = Field(default_factory=dict, description="Original raw row / metadata")

    @field_validator("application_number", mode="before")
    @classmethod
    def _norm_application_number(cls, v):
        return _normalize_identifier(v)

    @field_validator("publication_number", mode="before")
    @classmethod
    def _norm_publication_number(cls, v):
        return _normalize_identifier(v)

    @field_validator("grant_number", mode="before")
    @classmethod
    def _norm_grant_number(cls, v):
        return _normalize_identifier(v)

    @field_validator("filing_date", "publication_date", "grant_date", mode="before")
    @classmethod
    def _coerce_dates(cls, v):
        if v is None or v == "":
            return None
        return _parse_date(v)


class PatentAssignee(BaseModel):
    """
    Company or entity that is listed as an assignee on a patent assignment.
    """

    rf_id: str | None = Field(None, description="Record identifier (if applicable)")
    name: str = Field(..., description="Assignee name")
    street: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None
    country: str | None = None
    uei: str | None = Field(None, description="Enterprise identifier (UEI) if available")
    cage: str | None = Field(None, description="CAGE code if available")
    duns: str | None = Field(None, description="DUNS number if available")
    metadata: dict[str, object] = Field(default_factory=dict)

    @field_validator("name", mode="before")
    @classmethod
    def _validate_name(cls, v):
        if not v or not str(v).strip():
            raise ValueError("Assignee name must be non-empty")
        # Preserve original name but normalize whitespace
        return " ".join(str(v).strip().split())

    @field_validator("postal_code", mode="before")
    @classmethod
    def _coerce_postal_code(cls, v):
        """Coerce numeric postal codes to strings (pandas often reads them as int)."""
        if v is None or v == "":
            return None
        return str(v)

    @field_validator("uei", "cage", "duns", mode="before")
    @classmethod
    def _normalize_ids(cls, v):
        return _normalize_identifier(v)


class PatentAssignor(BaseModel):
    """
    Entity or person assigning rights (may overlap with assignee fields).
    """

    rf_id: str | None = None
    name: str | None = None
    execution_date: date | None = None
    acknowledgment_date: date | None = None
    metadata: dict[str, object] = Field(default_factory=dict)

    @field_validator("name", mode="before")
    @classmethod
    def _normalize_name(cls, v):
        if v is None:
            return None
        return _normalize_name(v)

    @field_validator("execution_date", "acknowledgment_date", mode="before")
    @classmethod
    def _parse_dates(cls, v):
        if v is None or v == "":
            return None
        return _parse_date(v)


class PatentConveyance(BaseModel):
    """
    Conveyance details describing the transfer of rights (assignment, license etc.)
    """

    rf_id: str | None = None
    conveyance_type: ConveyanceType = Field(
        ConveyanceType.ASSIGNMENT, description="Type of conveyance"
    )
    description: str | None = Field(None, description="Original conveyance text/freeform")
    employer_assign: bool | None = Field(
        None, description="True if conveyance indicates employer-assignment (work-for-hire)"
    )
    recorded_date: date | None = None
    metadata: dict[str, object] = Field(default_factory=dict)

    @field_validator("recorded_date", mode="before")
    @classmethod
    def _parse_recorded_date(cls, v):
        if v is None or v == "":
            return None
        return _parse_date(v)


class PatentAssignment(BaseModel):
    """
    A unified representation of an assignment record connecting assignor, assignee, conveyance and document.
    """

    rf_id: str | None = Field(None, description="Repository-specific record id")
    file_id: str | None = Field(None, description="File identifier linking related rows")
    document: PatentDocument | None = None
    conveyance: PatentConveyance | None = None
    assignee: PatentAssignee | None = None
    assignor: PatentAssignor | None = None

    # Important dates
    execution_date: date | None = None
    recorded_date: date | None = None

    # Additional extracted / normalized fields
    normalized_assignee_name: str | None = Field(
        None, description="Normalized assignee name for matching"
    )
    normalized_assignor_name: str | None = Field(
        None, description="Normalized assignor name for matching"
    )
    metadata: dict[str, object] = Field(default_factory=dict)

    @field_validator("execution_date", "recorded_date", mode="before")
    @classmethod
    def _parse_any_dates(cls, v):
        if v is None or v == "":
            return None
        return _parse_date(v)

    @field_validator("normalized_assignee_name", "normalized_assignor_name", mode="before")
    @classmethod
    def _norm_names(cls, v):
        if v is None:
            return None
        return _normalize_name(v)

    def summarize(self) -> dict[str, object]:
        """Return a compact summary useful for reports / ingestion checks."""
        return {
            "rf_id": self.rf_id,
            "file_id": self.file_id,
            "document_grant": self.document.grant_number if self.document else None,
            "assignee": self.assignee.name if self.assignee else None,
            "assignor": self.assignor.name if self.assignor else None,
            "conveyance_type": self.conveyance.conveyance_type if self.conveyance else None,
            "execution_date": self.execution_date.isoformat() if self.execution_date else None,
            "recorded_date": self.recorded_date.isoformat() if self.recorded_date else None,
        }


__all__ = [
    "PatentDocument",
    "PatentAssignee",
    "PatentAssignor",
    "PatentConveyance",
    "PatentAssignment",
]
