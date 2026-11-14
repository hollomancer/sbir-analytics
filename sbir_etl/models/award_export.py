"""Versioned semantic declarations for the SBIR.gov award export.

Epistemic tier: primitives. These names describe source rows and time fields;
they do not define award identity or report empirical findings.
"""

import json
import re
from datetime import datetime
from enum import StrEnum
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


EPISTEMIC_TIER = "primitives"


class AwardGrain(StrEnum):
    """Named, immutable row-grain declarations.

    ``EXPORT_ROW_V1`` is one physical data record after CSV parsing and before
    deduplication, canonical-ID construction, or grouping. It is not an award
    identity.
    """

    EXPORT_ROW_V1 = "export-row-v1"


class FiscalYearBasis(StrEnum):
    """Named, immutable fiscal-year field declarations."""

    AWARD_YEAR_FIELD_V1 = "award-year-field-v1"

    @property
    def field_name(self) -> str:
        """Return the exact export field used by this basis."""

        return "Award Year"

    def parse(self, value: Any, *, row_location: str | int) -> int | None:
        """Parse this basis from one source value without date fallbacks."""

        if value is None:
            return None
        if isinstance(value, bool):
            self._raise_invalid(value, row_location=row_location)
        if isinstance(value, int):
            return value

        text = value if isinstance(value, str) else str(value)
        stripped = text.strip()
        if not stripped:
            return None
        if re.fullmatch(r"[+-]?[0-9]+", stripped) is None:
            self._raise_invalid(value, row_location=row_location)
        return int(stripped)

    def _raise_invalid(self, value: Any, *, row_location: str | int) -> None:
        location = f"row {row_location}" if isinstance(row_location, int) else row_location
        raise ValueError(f"{self.field_name} at {location} must be an integer; got {value!r}")


class AwardExportSourceMetadata(BaseModel):
    """Pinned identity and capture context for one SBIR.gov export."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int = Field(default=1, strict=True, ge=1, le=1)
    source_url: str
    retrieved_at: datetime
    upstream_published_at: datetime | None = None
    upstream_date_unknown_reason: str | None = None
    upstream_object_version: str | None = None
    sha256: str
    size_bytes: int = Field(strict=True, ge=0)
    row_count: int = Field(strict=True, ge=0)
    column_count: int = Field(strict=True, ge=1)
    ordered_schema_sha256: str
    retrieval_tool: str
    retrieval_tool_version: str
    operator_identity: str
    access_license_note: str
    award_grain: AwardGrain = AwardGrain.EXPORT_ROW_V1

    @field_validator(
        "source_url",
        "upstream_date_unknown_reason",
        "upstream_object_version",
        "retrieval_tool",
        "retrieval_tool_version",
        "operator_identity",
        "access_license_note",
    )
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        """Reject blank metadata while preserving absent optional fields."""

        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("metadata text fields must not be blank")
        return stripped

    @field_validator("source_url")
    @classmethod
    def require_http_source(cls, value: str) -> str:
        """Require a complete HTTP(S) source identity."""

        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("source_url must be an absolute HTTP(S) URL")
        return value

    @field_validator("sha256", "ordered_schema_sha256")
    @classmethod
    def require_sha256(cls, value: str) -> str:
        """Normalize and validate one full SHA-256 digest."""

        normalized = value.lower()
        if re.fullmatch(r"[0-9a-f]{64}", normalized) is None:
            raise ValueError("SHA-256 values must contain 64 hexadecimal characters")
        return normalized

    @field_validator("retrieved_at", "upstream_published_at")
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        """Reject local timestamps whose instant cannot be reconstructed."""

        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("source timestamps must include a timezone")
        return value

    @model_validator(mode="after")
    def require_upstream_date_or_reason(self) -> "AwardExportSourceMetadata":
        """Make an absent upstream publication date an explicit assertion."""

        known = self.upstream_published_at is not None
        explained = self.upstream_date_unknown_reason is not None
        if known == explained:
            raise ValueError(
                "provide exactly one of upstream_published_at or upstream_date_unknown_reason"
            )
        return self

    def to_json(self) -> str:
        """Return stable, newline-terminated JSON without adding run time state."""

        return json.dumps(self.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"


__all__ = [
    "AwardExportSourceMetadata",
    "AwardGrain",
    "EPISTEMIC_TIER",
    "FiscalYearBasis",
]
