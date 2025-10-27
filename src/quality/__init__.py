"""Quality validators and helpers for SBIR ETL.

This package exposes validators and helpers for USPTO data quality checks.
Currently includes:
- ValidatorResult: dataclass holding results
- validate_rf_id_uniqueness: file-based rf_id uniqueness validator
- validate_rf_id_uniqueness_from_iterator: iterator-based validator
- iter_rows_from_path: streaming row iterator for supported file types
- main_validate_rf_id_uniqueness: convenience entrypoint for quick runs
"""

from .uspto_validators import (
    ValidatorResult,
    validate_rf_id_uniqueness,
    validate_rf_id_uniqueness_from_iterator,
    validate_referential_integrity,
    validate_field_completeness,
    validate_date_fields,
    validate_duplicate_records,
    iter_rows_from_path,
    main_validate_rf_id_uniqueness,
    USPTOValidationConfig,
    USPTODataQualityValidator,
)

__all__ = [
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
]
