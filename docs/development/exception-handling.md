# Exception Handling Guide

**Type**: Reference
**Owner**: Engineering Team
**Last-Reviewed**: 2025-01-04
**Status**: Active

## Overview

The SBIR ETL pipeline uses a comprehensive, structured exception hierarchy to provide rich error context, enable intelligent retry logic, and facilitate debugging in production environments. All custom exceptions inherit from `SBIRETLError` and provide consistent metadata including component, operation, details, retry guidance, and error codes.

## Table of Contents

- [Exception Hierarchy](#exception-hierarchy)
- [Core Concepts](#core-concepts)
- [Usage Patterns](#usage-patterns)
- [Best Practices](#best-practices)
- [Testing Exceptions](#testing-exceptions)
- [Integration with Monitoring](#integration-with-monitoring)
- [Migration Guide](#migration-guide)

## Exception Hierarchy

### Full Hierarchy

```
SBIRETLError (base class - do not raise directly)
├── ExtractionError              # Stage 1: Data extraction failures
├── ValidationError              # Stage 2: Schema/quality validation failures
│   └── DataQualityError         # Quality thresholds not met
├── EnrichmentError              # Stage 3: Enrichment stage failures
│   └── APIError                 # External API failures
│       └── RateLimitError       # Rate limits exceeded
├── TransformationError          # Stage 4: Transformation stage failures
│   ├── TransitionDetectionError # Transition detection specific
│   ├── FiscalAnalysisError      # Fiscal analysis specific
│   ├── CETClassificationError   # CET classification specific
│   └── PatentProcessingError    # Patent processing specific
├── LoadError                    # Stage 5: Loading stage failures
│   └── Neo4jError               # Neo4j database operations
├── ConfigurationError           # Config loading/validation
├── FileSystemError              # File I/O operations
└── DependencyError              # Missing dependencies
    └── RFunctionError           # R function failures
```

### Error Code Ranges

All exceptions include optional numeric error codes for programmatic handling:

- **1xxx**: Configuration errors (`CONFIG_LOAD_FAILED`, `CONFIG_VALIDATION_FAILED`)
- **2xxx**: Data quality errors (`VALIDATION_FAILED`, `QUALITY_THRESHOLD_NOT_MET`)
- **3xxx**: External dependencies (`NEO4J_QUERY_FAILED`, `API_REQUEST_FAILED`, `R_FUNCTION_FAILED`)
- **4xxx**: File I/O errors (`FILE_NOT_FOUND`, `FILE_READ_FAILED`)
- **5xxx**: Pipeline stage errors (`EXTRACTION_FAILED`, `ENRICHMENT_FAILED`)

## Core Concepts

### Structured Context

Every exception includes standardized metadata:

```python
raise ValidationError(
    "Award amount must be positive",
    component="validators.sbir",        # Module/service identifier
    operation="validate_award",         # Function/method name
    details={                           # Contextual data dictionary
        "award_id": "A001",
        "amount": -1000,
        "expected": "> 0"
    }
)
```

### Retry Guidance

The `retryable` flag indicates whether the operation should be retried:

```python
# Transient error - should retry
raise APIError(
    "Connection timeout",
    api_name="usaspending",
    endpoint="/v2/awards/123",
    retryable=True  # Caller should retry
)

# Permanent error - don't retry
raise ValidationError(
    "Invalid award ID format",
    component="validators.sbir",
    operation="validate_award_id",
    retryable=False  # Won't succeed on retry
)
```

### Cause Chains

Preserve original exception context using the `cause` parameter:

```python
try:
    data = json.loads(raw_json)
except json.JSONDecodeError as e:
    raise ValidationError(
        "Invalid JSON in award data",
        component="extractors.sbir",
        operation="parse_award_json",
        details={"raw_json_preview": raw_json[:100]},
        cause=e  # Preserves original exception
    ) from e
```

## Usage Patterns

### Basic Exception Raising

```python
from src.exceptions import ValidationError, APIError, FileSystemError

# Input validation
if not award_id:
    raise ValidationError(
        "Award ID is required",
        component="validators.sbir",
        operation="validate_award",
        details={"provided_value": award_id}
    )

# Missing file
if not csv_path.exists():
    raise FileSystemError(
        f"CSV file not found: {csv_path}",
        file_path=str(csv_path),
        operation="import_csv",
        component="extractors.duckdb"
    )

# API failure
if response.status_code != 200:
    raise APIError(
        f"USAspending API returned {response.status_code}",
        api_name="usaspending",
        endpoint=endpoint,
        http_status=response.status_code,
        retryable=(response.status_code in [429, 500, 502, 503, 504])
    )
```

### Wrapping External Exceptions

Use `wrap_exception` to convert standard Python or library exceptions:

```python
from src.exceptions import wrap_exception, APIError, FileSystemError
import httpx

# Wrap HTTP errors
try:
    response = httpx.get(url)
    response.raise_for_status()
except httpx.HTTPError as e:
    raise wrap_exception(
        e, APIError,
        api_name="usaspending",
        endpoint=url,
        http_status=e.response.status_code if e.response else None
    )

# Wrap file I/O errors
try:
    with open(file_path) as f:
        data = f.read()
except IOError as e:
    raise wrap_exception(
        e, FileSystemError,
        file_path=file_path,
        operation="read_file"
    )
```

### Stage-Specific Exceptions

Use specific exception classes for each ETL stage:

```python
from src.exceptions import (
    ExtractionError,
    ValidationError,
    EnrichmentError,
    TransformationError,
    LoadError
)

# Stage 1: Extraction
if extraction_failed:
    raise ExtractionError(
        "Failed to extract SBIR awards from CSV",
        component="extractors.sbir",
        operation="extract_awards",
        details={"file_path": str(csv_path), "rows_processed": row_count}
    )

# Stage 2: Validation
if quality_score < threshold:
    raise DataQualityError(
        "Match rate below threshold",
        threshold=threshold,
        actual_value=quality_score,
        component="enrichers.usaspending",
        operation="enrich_awards"
    )

# Stage 3: Enrichment
if api_call_failed:
    raise EnrichmentError(
        "USAspending enrichment failed",
        component="enrichers.usaspending",
        operation="enrich_award_batch",
        details={"batch_size": len(batch), "failed_count": failed_count}
    )

# Stage 4: Transformation
if transition_detection_failed:
    raise TransitionDetectionError(
        "Failed to detect transitions",
        component="transformers.transition_detector",
        operation="detect_transitions",
        details={"awards_count": len(awards)}
    )

# Stage 5: Loading
if neo4j_write_failed:
    raise Neo4jError(
        "Failed to create award nodes",
        operation="create_award_nodes",
        query="MERGE (a:Award {award_id: $id})",
        details={"batch_size": len(batch)}
    )
```

## Best Practices

### 1. Always Provide Component and Operation

These fields are essential for debugging:

```python
# ✅ Good
raise ValidationError(
    "Missing required field",
    component="validators.sbir",
    operation="validate_completeness"
)

# ❌ Bad
raise ValidationError("Missing required field")
```

### 2. Include Actionable Details

Provide enough context to diagnose and fix the issue:

```python
# ✅ Good
raise ValidationError(
    "Missing required columns",
    component="validators.sbir",
    operation="validate_schema",
    details={
        "missing_columns": ["award_id", "amount"],
        "available_columns": list(df.columns)
    }
)

# ❌ Bad
raise ValidationError("Missing columns")
```

### 3. Use Specific Exception Classes

Prefer specific exceptions over generic ones:

```python
# ✅ Good
raise CETClassificationError(
    "Model must be trained before classification",
    component="ml.cet_classifier",
    operation="classify"
)

# ❌ Bad
raise RuntimeError("Model must be trained")
```

### 4. Document Exceptions in Docstrings

List all exceptions a function may raise:

```python
def enrich_awards(awards: pd.DataFrame) -> pd.DataFrame:
    """Enrich SBIR awards with USAspending data.

    Args:
        awards: DataFrame of SBIR awards

    Returns:
        Enriched awards DataFrame

    Raises:
        APIError: If USAspending API request fails
        DataQualityError: If match rate below threshold
        ConfigurationError: If API credentials missing
    """
    pass
```

### 5. Log Exceptions with Context

Use structured logging with exception metadata:

```python
from src.exceptions import APIError
import logging

logger = logging.getLogger(__name__)

try:
    enrich_data()
except APIError as e:
    logger.error(
        "Enrichment failed",
        extra=e.to_dict(),  # Includes all exception metadata
        exc_info=True
    )
    if e.retryable:
        retry_operation()
    else:
        raise
```

### 6. Set Retryable Flag Appropriately

Guide automated retry logic:

```python
# Transient errors (network, rate limits) - retryable
raise APIError(
    "Connection timeout",
    api_name="usaspending",
    retryable=True
)

# Permanent errors (validation, not found) - not retryable
raise ValidationError(
    "Invalid award ID format",
    retryable=False
)
```

## Testing Exceptions

### Unit Tests

Use the test utilities in `tests/utils/exception_helpers.py`:

```python
from src.exceptions import ValidationError
from tests.utils.exception_helpers import (
    assert_exception_structure,
    assert_raises_with_context
)

def test_validate_award_id():
    """Test that invalid award IDs raise ValidationError with proper context."""
    with assert_raises_with_context(
        ValidationError,
        component="validators.sbir",
        operation="validate_award_id",
        expected_details={"award_id": "INVALID"}
    ):
        validate_award_id("INVALID")
```

### Integration Tests

Test exception handling in real scenarios:

```python
def test_api_failure_handling(mock_api):
    """Test that API failures are properly wrapped."""
    mock_api.get.side_effect = httpx.HTTPError("Connection failed")

    with pytest.raises(APIError) as exc_info:
        fetch_award_data("A001")

    assert exc_info.value.api_name == "usaspending"
    assert exc_info.value.retryable is True
    assert exc_info.value.cause is not None
```

## Integration with Monitoring

### Dagster Integration

Exceptions integrate seamlessly with Dagster's error handling:

```python
from dagster import asset, AssetExecutionContext
from src.exceptions import EnrichmentError

@asset
def enriched_awards(context: AssetExecutionContext, raw_awards):
    """Enrich awards with USAspending data."""
    try:
        return enrich_awards_batch(raw_awards)
    except EnrichmentError as e:
        context.log.error(
            "Enrichment failed",
            extra=e.to_dict()
        )
        # Dagster will mark asset as failed and store error metadata
        raise
```

### Structured Logging

Exceptions serialize to JSON for structured logging systems:

```python
from src.exceptions import APIError

try:
    call_api()
except APIError as e:
    logger.error(
        "API call failed",
        extra={
            **e.to_dict(),
            "request_id": request_id,
            "user_id": user_id
        }
    )
```

Example JSON output:

```json
{
  "message": "API call failed",
  "exception_type": "APIError",
  "component": "enrichers.usaspending",
  "operation": "fetch_award",
  "api_name": "usaspending",
  "endpoint": "/v2/awards/123",
  "http_status": 503,
  "retryable": true,
  "error_code": 3001,
  "timestamp": "2025-01-04T12:34:56Z",
  "request_id": "req-123",
  "user_id": "user-456"
}
```

## Migration Guide

### Migrating from Generic Exceptions

Replace generic Python exceptions with structured SBIR exceptions:

```python
# Before
raise ValueError("Award amount must be positive")

# After
raise ValidationError(
    "Award amount must be positive",
    component="validators.sbir",
    operation="validate_award",
    details={"amount": amount, "min_value": 0}
)
```

```python
# Before
raise RuntimeError("pandas is required")

# After
raise DependencyError(
    "pandas is required for data processing",
    dependency_name="pandas",
    component="utils.data_processor",
    operation="process_dataframe",
    details={"install_command": "uv sync"}
)
```

```python
# Before
raise FileNotFoundError(f"File not found: {path}")

# After
raise FileSystemError(
    f"File not found: {path}",
    file_path=str(path),
    operation="load_csv",
    component="extractors.sbir"
)
```

### Pydantic Validators

Keep Pydantic field validators as `ValueError` (required by Pydantic):

```python
from pydantic import BaseModel, field_validator

class AwardConfig(BaseModel):
    threshold: float

    @field_validator("threshold")
    @classmethod
    def validate_threshold(cls, v):
        """Validate threshold is between 0 and 1."""
        if not (0.0 <= v <= 1.0):
            # Keep as ValueError for Pydantic compatibility
            raise ValueError("Threshold must be between 0.0 and 1.0")
        return v
```

For non-validator business logic, use structured exceptions:

```python
class AwardProcessor:
    def validate_award_data(self, award: dict) -> None:
        """Validate award data (not a Pydantic validator)."""
        if award["amount"] <= 0:
            # Use structured exception for business logic
            raise ValidationError(
                "Award amount must be positive",
                component="processors.award",
                operation="validate_award_data",
                details={"award_id": award["id"], "amount": award["amount"]}
            )
```

## Reference

### Exception Class Quick Reference

| Exception Class | Use For | Example |
|----------------|---------|---------|
| `ExtractionError` | Data extraction failures | CSV parsing, API data fetch |
| `ValidationError` | Input validation, schema checks | Missing fields, invalid formats |
| `DataQualityError` | Quality thresholds not met | Low match rates, completeness |
| `EnrichmentError` | Enrichment stage failures | API enrichment, fuzzy matching |
| `APIError` | External API failures | HTTP errors, timeouts |
| `RateLimitError` | Rate limits exceeded | 429 responses |
| `TransformationError` | Transformation failures | Data transformation, calculations |
| `TransitionDetectionError` | Transition detection | Signal extraction, scoring |
| `CETClassificationError` | CET classification | Model training, prediction |
| `LoadError` | Loading failures | Database writes, bulk inserts |
| `Neo4jError` | Neo4j operations | Query failures, connection issues |
| `ConfigurationError` | Config issues | Invalid config, missing keys |
| `FileSystemError` | File I/O | File not found, read/write errors |
| `DependencyError` | Missing dependencies | Import failures, missing packages |
| `RFunctionError` | R function failures | R package errors, execution failures |

### Common Patterns

```python
# Missing required field
raise ValidationError(
    "Missing required field",
    component="component_name",
    operation="operation_name",
    details={"field": field_name, "available_fields": list(data.keys())}
)

# API failure
raise APIError(
    "API request failed",
    api_name="api_name",
    endpoint=endpoint,
    http_status=status_code,
    retryable=(status_code in [429, 500, 502, 503, 504])
)

# Missing dependency
raise DependencyError(
    "Required package not installed",
    dependency_name="package_name",
    component="component_name",
    operation="operation_name",
    details={"install_command": "uv sync --extra xyz"}
)

# File not found
raise FileSystemError(
    "File not found",
    file_path=str(path),
    operation="operation_name",
    component="component_name"
)

# Quality threshold not met
raise DataQualityError(
    "Quality threshold not met",
    threshold=threshold,
    actual_value=actual_value,
    component="component_name",
    operation="operation_name"
)
```

## See Also

- [CONTRIBUTING.md](../../CONTRIBUTING.md#exception-handling) - Exception handling guidelines for contributors
- [src/exceptions.py](../../src/exceptions.py) - Exception class implementations
- [tests/unit/test_exceptions.py](../../tests/unit/test_exceptions.py) - Exception unit tests
- [tests/utils/exception_helpers.py](../../tests/utils/exception_helpers.py) - Test utilities
