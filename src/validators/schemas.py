"""Pydantic schemas for data validation."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, validator


class ValidationResult(BaseModel):
    """Result of a validation operation."""

    is_valid: bool
    field: str
    value: Any
    expected: Any
    message: str
    severity: str = "medium"

    class Config:
        """Pydantic configuration."""
        validate_assignment = True


class CompletenessCheck(BaseModel):
    """Configuration for completeness validation."""

    required_fields: List[str] = Field(default_factory=list)
    threshold: float = Field(default=0.95, ge=0.0, le=1.0)

    @validator("threshold")
    def validate_threshold(cls, v):
        """Validate threshold is between 0 and 1."""
        if not (0.0 <= v <= 1.0):
            raise ValueError("Threshold must be between 0.0 and 1.0")
        return v


class UniquenessCheck(BaseModel):
    """Configuration for uniqueness validation."""

    fields: List[str] = Field(default_factory=list)
    case_sensitive: bool = True


class ValueRangeCheck(BaseModel):
    """Configuration for value range validation."""

    field: str
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    allowed_values: Optional[List[Any]] = None

    @validator("allowed_values")
    def validate_allowed_values(cls, v):
        """Validate allowed values is not empty if provided."""
        if v is not None and len(v) == 0:
            raise ValueError("allowed_values cannot be empty if provided")
        return v


class ValidationConfig(BaseModel):
    """Configuration for data validation."""

    completeness: Dict[str, float] = Field(default_factory=dict)
    uniqueness: Dict[str, float] = Field(default_factory=dict)
    value_ranges: Dict[str, Dict[str, Any]] = Field(default_factory=dict)

    class Config:
        """Pydantic configuration."""
        validate_assignment = True