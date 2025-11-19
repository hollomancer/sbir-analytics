"""Central exception hierarchy for SBIR ETL pipeline.

This module provides a comprehensive exception hierarchy for all pipeline stages,
components, and operations. All custom exceptions should inherit from SBIRETLError.

Exception Hierarchy:
    SBIRETLError (base)
    ├── ExtractionError
    ├── ValidationError
    │   └── DataQualityError
    ├── EnrichmentError
    │   └── APIError
    │       └── RateLimitError
    ├── TransformationError
    │   ├── TransitionDetectionError
    │   ├── FiscalAnalysisError
    │   ├── CETClassificationError
    │   └── PatentProcessingError
    ├── LoadError
    │   └── Neo4jError
    ├── ConfigurationError
    ├── FileSystemError
    └── DependencyError
        └── RFunctionError

Usage:
    from src.exceptions import EnrichmentError, APIError

    try:
        enrich_data()
    except APIError as e:
        logger.error(f"API failed: {e.message}", extra=e.to_dict())
        if e.retryable:
            retry_operation()

    # Wrap external exceptions
    try:
        response = httpx.get(url)
    except httpx.HTTPError as exc:
        raise wrap_exception(
            exc,
            APIError,
            api_name="usaspending",
            endpoint=url
        )
"""

from __future__ import annotations

from enum import IntEnum
from typing import Any


class ErrorCode(IntEnum):
    """Error codes for programmatic handling.

    Categories:
        1xxx - Configuration errors
        2xxx - Data quality/validation errors
        3xxx - External dependencies (Neo4j, APIs, R)
        4xxx - File I/O errors
        5xxx - Pipeline stage errors
    """

    # Configuration errors (1xxx)
    CONFIG_LOAD_FAILED = 1001
    CONFIG_VALIDATION_FAILED = 1002
    CONFIG_MISSING_REQUIRED = 1003

    # Data quality errors (2xxx)
    VALIDATION_FAILED = 2001
    QUALITY_THRESHOLD_NOT_MET = 2002
    SCHEMA_MISMATCH = 2003

    # External dependencies (3xxx)
    NEO4J_CONNECTION_FAILED = 3001
    NEO4J_QUERY_FAILED = 3002
    API_REQUEST_FAILED = 3101
    API_RATE_LIMIT = 3102
    API_AUTHENTICATION_FAILED = 3103
    R_PACKAGE_MISSING = 3201
    R_FUNCTION_FAILED = 3202

    # File I/O errors (4xxx)
    FILE_NOT_FOUND = 4001
    FILE_READ_FAILED = 4002
    FILE_WRITE_FAILED = 4003

    # Pipeline stage errors (5xxx)
    EXTRACTION_FAILED = 5001
    ENRICHMENT_FAILED = 5002
    TRANSFORMATION_FAILED = 5003
    LOADING_FAILED = 5004


class SBIRETLError(Exception):
    """Base exception for all SBIR ETL pipeline errors.

    This base class provides structured error information including component,
    operation context, retry guidance, and detailed metadata.

    Attributes:
        message: Human-readable error description
        component: Pipeline component (e.g., "enricher.usaspending")
        operation: Operation being performed (e.g., "fetch_award_data")
        details: Additional context as dictionary
        retryable: Whether operation can be retried
        status_code: Numeric error code from ErrorCode enum
        cause: Original exception if wrapping another error

    Example:
        raise SBIRETLError(
            "Failed to process data",
            component="enricher",
            operation="fetch_awards",
            details={"award_count": 100, "failed_count": 5},
            retryable=True,
            status_code=ErrorCode.ENRICHMENT_FAILED
        )
    """

    def __init__(
        self,
        message: str,
        component: str | None = None,
        operation: str | None = None,
        details: dict[str, Any] | None = None,
        retryable: bool = False,
        status_code: ErrorCode | None = None,
        cause: Exception | None = None,
    ):
        """Initialize SBIR ETL error.

        Args:
            message: Human-readable error description
            component: Pipeline component that raised the error
            operation: Operation being performed when error occurred
            details: Additional context as key-value pairs
            retryable: Whether the operation can be retried
            status_code: Numeric error code for programmatic handling
            cause: Original exception if this wraps another error
        """
        self.message = message
        self.component = component or self.__class__.__module__
        self.operation = operation
        self.details = details or {}
        self.retryable = retryable
        self.status_code = status_code
        self.cause = cause

        # Build comprehensive error message
        parts = [message]
        if component:
            parts.append(f"[component={component}]")
        if operation:
            parts.append(f"[operation={operation}]")
        if status_code:
            parts.append(f"[code={status_code}]")

        super().__init__(" ".join(parts))

    def to_dict(self) -> dict[str, Any]:
        """Convert exception to dictionary for logging/serialization.

        Returns:
            Dictionary with all exception attributes

        Example:
            {
                "error_type": "APIError",
                "message": "Request failed",
                "component": "api.usaspending",
                "operation": "fetch_award",
                "details": {"endpoint": "/v2/awards/123"},
                "retryable": true,
                "status_code": 3101,
                "cause": "HTTPError: 503 Service Unavailable"
            }
        """
        return {
            "error_type": self.__class__.__name__,
            "message": self.message,
            "component": self.component,
            "operation": self.operation,
            "details": self.details,
            "retryable": self.retryable,
            "status_code": self.status_code.value if self.status_code else None,
            "cause": str(self.cause) if self.cause else None,
        }


# ============================================================================
# PIPELINE STAGE EXCEPTIONS (Layer 1)
# ============================================================================


class ExtractionError(SBIRETLError):
    """Failed to extract data from source.

    Use this for failures during the extraction stage, such as:
    - Failed to download data files
    - Failed to connect to data source
    - Failed to parse raw data

    Example:
        raise ExtractionError(
            "Failed to download SBIR awards CSV",
            component="extractor.sbir_gov",
            details={"url": "https://sbir.gov/awards.csv"}
        )
    """

    def __init__(self, message: str, **kwargs: Any):
        super().__init__(
            message,
            status_code=kwargs.pop("status_code", ErrorCode.EXTRACTION_FAILED),
            **kwargs,
        )


class ValidationError(SBIRETLError):
    """Data validation failed.

    Use this for failures during the validation stage, such as:
    - Schema validation failures
    - Missing required fields
    - Invalid data types

    Note: This is not retryable by default as data issues must be fixed at source.

    Example:
        raise ValidationError(
            "Schema validation failed",
            component="validator.award",
            details={"missing_fields": ["award_id", "amount"]},
            retryable=False
        )
    """

    def __init__(self, message: str, **kwargs: Any):
        super().__init__(
            message,
            status_code=kwargs.pop("status_code", ErrorCode.VALIDATION_FAILED),
            retryable=False,
            **kwargs,
        )


class EnrichmentError(SBIRETLError):
    """Data enrichment failed.

    Use this for failures during the enrichment stage, such as:
    - External API calls failed
    - Fuzzy matching failed
    - Data augmentation failed

    Example:
        raise EnrichmentError(
            "Failed to enrich awards with USAspending data",
            component="enricher.usaspending",
            details={"awards_attempted": 100, "awards_failed": 15}
        )
    """

    def __init__(self, message: str, **kwargs: Any):
        super().__init__(
            message,
            status_code=kwargs.pop("status_code", ErrorCode.ENRICHMENT_FAILED),
            **kwargs,
        )


class TransformationError(SBIRETLError):
    """Data transformation failed.

    Use this for failures during the transformation stage, such as:
    - Business logic errors
    - Calculation failures
    - Data aggregation failures

    Example:
        raise TransformationError(
            "Failed to calculate fiscal ROI",
            component="transformer.fiscal",
            operation="calculate_roi"
        )
    """

    def __init__(self, message: str, **kwargs: Any):
        super().__init__(
            message,
            status_code=kwargs.pop("status_code", ErrorCode.TRANSFORMATION_FAILED),
            **kwargs,
        )


class LoadError(SBIRETLError):
    """Data loading failed.

    Use this for failures during the loading stage, such as:
    - Database connection failures
    - Insert/update failures
    - Constraint violations

    Example:
        raise LoadError(
            "Failed to load awards into Neo4j",
            component="loader.neo4j",
            details={"nodes_attempted": 1000, "nodes_failed": 3}
        )
    """

    def __init__(self, message: str, **kwargs: Any):
        super().__init__(
            message,
            status_code=kwargs.pop("status_code", ErrorCode.LOADING_FAILED),
            **kwargs,
        )


# ============================================================================
# COMPONENT-SPECIFIC EXCEPTIONS (Layer 2)
# ============================================================================


class Neo4jError(LoadError):
    """Neo4j database operation failed.

    Use this for all Neo4j-related errors, such as:
    - Connection failures
    - Query execution failures
    - Constraint violations
    - Transaction failures

    Example:
        raise Neo4jError(
            "Failed to create Award node",
            query="MERGE (a:Award {award_id: $id})",
            operation="create_node",
            details={"award_id": "SBIR-2020-001"},
            retryable=True
        )
    """

    def __init__(self, message: str, query: str | None = None, **kwargs: Any):
        details = kwargs.pop("details", {})
        if query:
            details["query"] = query

        # Use provided component or default to "neo4j"
        component = kwargs.pop("component", "neo4j")

        super().__init__(
            message,
            component=component,
            details=details,
            status_code=kwargs.pop("status_code", ErrorCode.NEO4J_QUERY_FAILED),
            **kwargs,
        )


class APIError(EnrichmentError):
    """External API call failed.

    Use this for all external API errors, such as:
    - HTTP request failures
    - API response errors
    - Authentication failures
    - Timeout errors

    Automatically marks 5xx errors as retryable.

    Example:
        raise APIError(
            "USAspending API request failed",
            api_name="usaspending",
            endpoint="/v2/awards/123",
            http_status=503,
            retryable=True
        )
    """

    def __init__(
        self,
        message: str,
        api_name: str | None = None,
        endpoint: str | None = None,
        http_status: int | None = None,
        **kwargs: Any,
    ):
        details = kwargs.pop("details", {})
        if endpoint:
            details["endpoint"] = endpoint
        if http_status:
            details["http_status"] = http_status

        # Automatically determine retryable based on HTTP status
        # 408 Timeout, 429 Rate Limit, 5xx Server Errors are retryable
        if "retryable" not in kwargs and http_status:
            kwargs["retryable"] = http_status in [408, 429, 500, 502, 503, 504]

        # Use provided component or construct from api_name
        component = kwargs.pop("component", f"api.{api_name}" if api_name else "api")

        super().__init__(
            message,
            component=component,
            details=details,
            status_code=kwargs.pop("status_code", ErrorCode.API_REQUEST_FAILED),
            **kwargs,
        )


class RateLimitError(APIError):
    """API rate limit exceeded.

    Always retryable. Includes retry_after information when available.

    Example:
        raise RateLimitError(
            "USAspending API rate limit exceeded",
            api_name="usaspending",
            retry_after=60,
            details={"requests_made": 120, "limit": 120}
        )
    """

    def __init__(self, message: str, retry_after: int | None = None, **kwargs: Any):
        details = kwargs.pop("details", {})
        if retry_after:
            details["retry_after_seconds"] = retry_after

        super().__init__(
            message,
            details=details,
            status_code=ErrorCode.API_RATE_LIMIT,
            retryable=True,
            **kwargs,
        )


class ConfigurationError(SBIRETLError):
    """Configuration loading or validation failed.

    Not retryable as configuration issues must be fixed manually.

    Use this for:
    - Missing configuration files
    - Invalid configuration values
    - Missing required configuration keys
    - Configuration schema validation failures

    Example:
        raise ConfigurationError(
            "Missing required Neo4j URI configuration",
            config_key="neo4j.uri",
            details={"config_file": "config/base.yaml"}
        )
    """

    def __init__(self, message: str, config_key: str | None = None, **kwargs: Any):
        details = kwargs.pop("details", {})
        if config_key:
            details["config_key"] = config_key

        # Use provided component or default to "config"
        component = kwargs.pop("component", "config")

        super().__init__(
            message,
            component=component,
            details=details,
            status_code=kwargs.pop("status_code", ErrorCode.CONFIG_VALIDATION_FAILED),
            retryable=False,
            **kwargs,
        )


class FileSystemError(SBIRETLError):
    """File I/O operation failed.

    Use this for all file system operations:
    - File not found
    - Permission denied
    - Disk full
    - Read/write failures

    Example:
        raise FileSystemError(
            "Failed to read awards CSV file",
            file_path="/data/raw/awards.csv",
            operation="read_file",
            cause=original_exception
        )
    """

    def __init__(self, message: str, file_path: str | None = None, **kwargs: Any):
        details = kwargs.pop("details", {})
        if file_path:
            details["file_path"] = file_path

        # Use provided component or default to "filesystem"
        component = kwargs.pop("component", "filesystem")

        super().__init__(
            message,
            component=component,
            details=details,
            status_code=kwargs.pop("status_code", ErrorCode.FILE_READ_FAILED),
            **kwargs,
        )


# ============================================================================
# DOMAIN-SPECIFIC EXCEPTIONS (Layer 3)
# ============================================================================


class TransitionDetectionError(TransformationError):
    """Transition detection pipeline failed.

    Use this for errors specific to the transition detection system.

    Example:
        raise TransitionDetectionError(
            "Failed to score transitions",
            operation="calculate_composite_score",
            details={"awards_processed": 1000, "failures": 5}
        )
    """

    def __init__(self, message: str, **kwargs: Any):
        # Use provided component or default to "transition_detection"
        component = kwargs.pop("component", "transition_detection")
        super().__init__(message, component=component, **kwargs)


class FiscalAnalysisError(TransformationError):
    """Fiscal returns analysis failed.

    Use this for errors specific to the fiscal analysis system.

    Example:
        raise FiscalAnalysisError(
            "Failed to calculate ROI",
            operation="compute_npv",
            details={"award_id": "SBIR-2020-001"}
        )
    """

    def __init__(self, message: str, **kwargs: Any):
        # Use provided component or default to "fiscal_analysis"
        component = kwargs.pop("component", "fiscal_analysis")
        super().__init__(message, component=component, **kwargs)


class CETClassificationError(TransformationError):
    """CET classification failed.

    Use this for errors specific to the CET classification system.

    Example:
        raise CETClassificationError(
            "Failed to classify award into CET areas",
            operation="predict_cet_areas",
            details={"award_id": "SBIR-2020-001", "title_length": 0}
        )
    """

    def __init__(self, message: str, **kwargs: Any):
        # Use provided component or default to "cet_classification"
        component = kwargs.pop("component", "cet_classification")
        super().__init__(message, component=component, **kwargs)


class PatentProcessingError(TransformationError):
    """USPTO patent processing failed.

    Use this for errors specific to patent processing.

    Example:
        raise PatentProcessingError(
            "Failed to parse patent assignment data",
            operation="parse_dta_file",
            details={"file_path": "/data/uspto/assignments.dta"}
        )
    """

    def __init__(self, message: str, **kwargs: Any):
        # Use provided component or default to "patent_processing"
        component = kwargs.pop("component", "patent_processing")
        super().__init__(message, component=component, **kwargs)


# ============================================================================
# OPERATIONAL EXCEPTIONS (Layer 4)
# ============================================================================


class DataQualityError(ValidationError):
    """Data quality threshold not met.

    Not retryable as data quality issues must be investigated and fixed.

    Example:
        raise DataQualityError(
            "Award match rate below threshold",
            threshold=0.70,
            actual_value=0.58,
            component="enricher.usaspending",
            details={"awards_processed": 10000, "matches": 5800}
        )
    """

    def __init__(
        self,
        message: str,
        threshold: float | None = None,
        actual_value: float | None = None,
        **kwargs: Any,
    ):
        details = kwargs.pop("details", {})
        if threshold is not None:
            details["threshold"] = threshold
        if actual_value is not None:
            details["actual_value"] = actual_value

        super().__init__(
            message,
            details=details,
            status_code=ErrorCode.QUALITY_THRESHOLD_NOT_MET,
            **kwargs,
        )


class DependencyError(SBIRETLError):
    """Missing or incompatible external dependency.

    Not retryable as dependencies must be installed manually.

    Use this for:
    - Missing Python packages
    - Missing R packages
    - Incompatible package versions
    - Missing system dependencies

    Example:
        raise DependencyError(
            "Required R package 'stateior' not installed",
            dependency_name="stateior",
            details={"install_command": "remotes::install_github('USEPA/stateior')"}
        )
    """

    def __init__(self, message: str, dependency_name: str | None = None, **kwargs: Any):
        details = kwargs.pop("details", {})
        if dependency_name:
            details["dependency_name"] = dependency_name

        # Use provided component or default to "dependencies"
        component = kwargs.pop("component", "dependencies")

        super().__init__(
            message,
            component=component,
            details=details,
            retryable=False,
            **kwargs,
        )


class RFunctionError(DependencyError):
    """R function call failed.

    Not retryable by default as R errors usually indicate logic issues.

    Example:
        raise RFunctionError(
            "R function 'calculate_impacts' failed",
            function_name="calculate_impacts",
            details={"error_message": "invalid NAICS code"}
        )
    """

    def __init__(self, message: str, function_name: str | None = None, **kwargs: Any):
        details = kwargs.pop("details", {})
        if function_name:
            details["function_name"] = function_name

        # Use provided component or default to "r_interface"
        component = kwargs.pop("component", "r_interface")

        super().__init__(
            message,
            dependency_name="R",
            component=component,
            details=details,
            status_code=ErrorCode.R_FUNCTION_FAILED,
            **kwargs,
        )


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def wrap_exception(
    original: Exception,
    error_class: type[SBIRETLError],
    message: str | None = None,
    **kwargs: Any,
) -> SBIRETLError:
    """Wrap a generic exception in a structured SBIR ETL exception.

    This is the recommended way to convert external library exceptions
    into the SBIR ETL exception hierarchy while preserving the original
    exception information.

    Args:
        original: Original exception to wrap
        error_class: SBIR ETL exception class to use
        message: Override message (defaults to original message)
        **kwargs: Additional arguments for exception constructor

    Returns:
        Instance of error_class with original exception as cause

    Example:
        try:
            response = httpx.get(url)
            response.raise_for_status()
        except httpx.HTTPError as e:
            raise wrap_exception(
                e,
                APIError,
                api_name="usaspending",
                endpoint=url,
                http_status=e.response.status_code
            )

        try:
            with open(file_path) as f:
                data = f.read()
        except IOError as e:
            raise wrap_exception(
                e,
                FileSystemError,
                file_path=file_path,
                operation="read_file"
            )
    """
    return error_class(message or str(original), cause=original, **kwargs)


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================


def is_retryable(exc: Exception) -> bool:
    """Check if an exception is retryable.

    Args:
        exc: Exception to check

    Returns:
        True if exception is retryable, False otherwise

    Example:
        try:
            process_data()
        except Exception as e:
            if is_retryable(e):
                retry_operation()
            else:
                raise
    """
    if isinstance(exc, SBIRETLError):
        return exc.retryable
    return False


def get_error_code(exc: Exception) -> int | None:
    """Get error code from exception if available.

    Args:
        exc: Exception to extract code from

    Returns:
        Error code integer or None

    Example:
        try:
            load_data()
        except Exception as e:
            code = get_error_code(e)
            if code == ErrorCode.NEO4J_CONNECTION_FAILED:
                reconnect_to_neo4j()
    """
    if isinstance(exc, SBIRETLError) and exc.status_code:
        return exc.status_code.value
    return None
