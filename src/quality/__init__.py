"""Quality utilities for SBIR ETL.

This package provides comprehensive quality management utilities including:
- USPTO data validators and helpers
- Quality baseline management and regression detection
- Interactive quality dashboards and reporting
- General data quality checks and validation functions

Modules:
- uspto_validators: USPTO-specific data quality validation
- baseline: Quality baseline management for regression detection
- dashboard: Interactive quality dashboards and reporting
- checks: General data quality validation functions
"""

# USPTO validators
# Quality baseline management
from .baseline import BaselineComparison, QualityBaseline, QualityBaselineManager

# General quality checks
from .checks import check_completeness, check_uniqueness, check_value_ranges, validate_sbir_awards

# Quality dashboards
from .dashboard import DashboardMetrics, QualityDashboard
from .uspto_validators import (
    USPTODataQualityValidator,
    USPTOValidationConfig,
    ValidatorResult,
    iter_rows_from_path,
    main_validate_rf_id_uniqueness,
    validate_date_fields,
    validate_duplicate_records,
    validate_field_completeness,
    validate_referential_integrity,
    validate_rf_id_uniqueness,
    validate_rf_id_uniqueness_from_iterator,
)


__all__ = [
    # USPTO validators
    "ValidatorResult",
    "validate_rf_id_uniqueness",
    "validate_rf_id_uniqueness_from_iterator",
    "validate_referential_integrity",
    "validate_field_completeness",
    "validate_date_fields",
    "validate_duplicate_records",
    "iter_rows_from_path",
    "main_validate_rf_id_uniqueness",
    "USPTOValidationConfig",
    "USPTODataQualityValidator",
    # Quality baseline management
    "QualityBaseline",
    "BaselineComparison",
    "QualityBaselineManager",
    # Quality dashboards
    "DashboardMetrics",
    "QualityDashboard",
    # General quality checks
    "check_completeness",
    "check_uniqueness",
    "check_value_ranges",
    "validate_sbir_awards",
]
