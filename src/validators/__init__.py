"""Data validation and quality checking module."""

# Re-export quality functions from the consolidated quality package for backward compatibility
from ..quality.checks import (
    check_completeness,
    check_uniqueness,
    check_value_ranges,
)
from .sbir_awards import validate_sbir_award_record, validate_sbir_awards

__all__ = [
    "check_completeness",
    "check_uniqueness",
    "check_value_ranges",
    "validate_sbir_awards",
    "validate_sbir_award_record",
]
