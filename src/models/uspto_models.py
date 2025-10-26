from __future__ import annotations

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

from datetime import date, datetime
from enum import Enum
import re
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, ValidationError, field_validator

# ---- Utilities ----
DATE_ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _parse_date(value) -> Optional[date]:
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        s = value.strip()
        # Accept ISO-like strings
        if DATE_ISO_RE.match(s):
            try:
                return date.fromisoformat(s)
            except ValueError:
                pass
        # Try other common formats
        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y/%m/%d"):
            try:
                return datetime.strptime(s, fmt).date()
            except ValueError:
                continue
    raise ValueError(f"Could not parse date from value: {value!r}")


def _normalize_identifier(val: Optional[str]) -> Optional[str]:
    if val is None:
        return None
    v = str(val).strip()
    if v == "":
        return None
    # Remove common punctuation and whitespace collapse
    v = re.sub(r"[^\w\-]", "", v).upper()
    return v


def _normalize_name(name: Optional[str]) -> Optional[str]:
    if name is None:
        return None
    n = " ".join(str(name).strip().split())
    # Replace multiple punctuation variants with single spaces for matching purposes
    n = re.sub(r"[,/&\.]+", " ", n)
    return n


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

    rf_id: Optional[str] = Field(None, description="Repository-specific record identifier")
    application_number: Optional[str] = Field(None, description="Application number (raw)")
    publication_number: Optional[str] = Field(None, description="Publication number (raw)")
    grant_number: Optional[str] = Field(None, description="Grant / patent number (raw)")
    filing_date: Optional[date] = Field(None, description="Application filing date")
    publication_date: Optional[date] = Field(None, description="Publication date")
    grant_date: Optional[date] = Field(None, description="Grant/issue date")
    language: Optional[str] = Field(None, description="Language code")
    title: Optional[str] = Field(None, description="Title text")
    abstract: Optional[str] = Field(None, description="Abstract text")
    raw: Dict[str, object] = Field(default_factory=dict, description="Original raw row / metadata")

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

    rf_id: Optional[str] = Field(None, description="Record identifier (if applicable)")
    name: str = Field(..., description="Assignee name")
    street: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    country: Optional[str] = None
    uei: Optional[str] = Field(None, description="Enterprise identifier (UEI) if available")
    cage: Optional[str] = Field(None, description="CAGE code if available")
    duns: Optional[str] = Field(None, description="DUNS number if available")
    metadata: Dict[str, object] = Field(default_factory=dict)

    @field_validator("name", mode="before")
    @classmethod
    def _normalize_name(cls, v):
        if not v or not str(v).strip():
            raise ValueError("Assignee name must be non-empty")
        return _normalize_name(v)

    @field_validator("uei", "cage", "duns", mode="before")
    @classmethod
    def _normalize_ids(cls, v):
        return _normalize_identifier(v)


class PatentAssignor(BaseModel):
    """
    Entity or person assigning rights (may overlap with assignee fields).
    """

    rf_id: Optional[str] = None
    name: Optional[str] = None
    execution_date: Optional[date] = None
    acknowledgment_date: Optional[date] = None
    metadata: Dict[str, object] = Field(default_factory=dict)

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

    rf_id: Optional[str] = None
    conveyance_type: ConveyanceType = Field(
        ConveyanceType.ASSIGNMENT, description="Type of conveyance"
    )
    description: Optional[str] = Field(None, description="Original conveyance text/freeform")
    employer_assign: Optional[bool] = Field(
        None, description="True if conveyance indicates employer-assignment (work-for-hire)"
    )
    recorded_date: Optional[date] = None
    metadata: Dict[str, object] = Field(default_factory=dict)

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

    rf_id: Optional[str] = Field(None, description="Repository-specific record id")
    file_id: Optional[str] = Field(None, description="File identifier linking related rows")
    document: Optional[PatentDocument] = None
    conveyance: Optional[PatentConveyance] = None
    assignee: Optional[PatentAssignee] = None
    assignor: Optional[PatentAssignor] = None

    # Important dates
    execution_date: Optional[date] = None
    recorded_date: Optional[date] = None

    # Additional extracted / normalized fields
    normalized_assignee_name: Optional[str] = Field(
        None, description="Normalized assignee name for matching"
    )
    normalized_assignor_name: Optional[str] = Field(
        None, description="Normalized assignor name for matching"
    )
    metadata: Dict[str, object] = Field(default_factory=dict)

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

    def summarize(self) -> Dict[str, object]:
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
