"""Pydantic schemas for data validation."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ValidationResult(BaseModel):
    """Result of a validation operation."""

    is_valid: bool
    field: str
    value: Any
    expected: Any
    message: str
    severity: str = "medium"

    model_config = ConfigDict(validate_assignment=True)


class CompletenessCheck(BaseModel):
    """Configuration for completeness validation."""

    required_fields: list[str] = Field(default_factory=list)
    threshold: float = Field(default=0.95, ge=0.0, le=1.0)

    @field_validator("threshold")
    @classmethod
    def validate_threshold(cls, v):
        """Validate threshold is between 0 and 1."""
        if not (0.0 <= v <= 1.0):
            raise ValueError("Threshold must be between 0.0 and 1.0")
        return v


class UniquenessCheck(BaseModel):
    """Configuration for uniqueness validation."""

    fields: list[str] = Field(default_factory=list)
    case_sensitive: bool = True


class ValueRangeCheck(BaseModel):
    """Configuration for value range validation."""

    field: str
    min_value: float | None = None
    max_value: float | None = None
    allowed_values: list[Any] | None = None

    @field_validator("allowed_values")
    @classmethod
    def validate_allowed_values(cls, v):
        """Validate allowed values is not empty if provided."""
        if v is not None and len(v) == 0:
            raise ValueError("allowed_values cannot be empty if provided")
        return v


class ValidationConfig(BaseModel):
    """Configuration for data validation."""

    completeness: dict[str, float] = Field(default_factory=dict)
    uniqueness: dict[str, float] = Field(default_factory=dict)
    value_ranges: dict[str, dict[str, Any]] = Field(default_factory=dict)

    model_config = ConfigDict(validate_assignment=True)
