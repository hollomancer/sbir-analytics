"""Central exception hierarchy for SBIR ETL pipeline.

All custom exceptions inherit from SBIRETLError which provides structured
error context (component, operation, details, retryable flag, error code).

Hierarchy:
    SBIRETLError (base)
    ├── ExtractionError
    ├── ValidationError
    ├── EnrichmentError
    │   └── APIError
    │       └── RateLimitError
    ├── TransformationError
    │   └── CETClassificationError
    ├── ConfigurationError
    ├── FileSystemError
    └── DependencyError
        └── RFunctionError
"""

from __future__ import annotations

from enum import IntEnum
from typing import Any


class ErrorCode(IntEnum):
    """Numeric error codes for programmatic handling."""

    # Configuration (1xxx)
    CONFIG_LOAD_FAILED = 1001
    CONFIG_VALIDATION_FAILED = 1002
    CONFIG_MISSING_REQUIRED = 1003

    # Data quality (2xxx)
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

    # File I/O (4xxx)
    FILE_NOT_FOUND = 4001
    FILE_READ_FAILED = 4002
    FILE_WRITE_FAILED = 4003

    # Pipeline stages (5xxx)
    EXTRACTION_FAILED = 5001
    ENRICHMENT_FAILED = 5002
    TRANSFORMATION_FAILED = 5003
    LOADING_FAILED = 5004


class SBIRETLError(Exception):
    """Base exception for all SBIR ETL pipeline errors."""

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
        self.message = message
        self.component = component or self.__class__.__module__
        self.operation = operation
        self.details = details or {}
        self.retryable = retryable
        self.status_code = status_code
        self.cause = cause

        parts = [message]
        if component:
            parts.append(f"[component={component}]")
        if operation:
            parts.append(f"[operation={operation}]")
        if status_code:
            parts.append(f"[code={status_code}]")
        super().__init__(" ".join(parts))

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for logging/serialization."""
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


# -- Pipeline stage exceptions -----------------------------------------------


class ExtractionError(SBIRETLError):
    """Data extraction from source failed."""

    def __init__(self, message: str, **kwargs: Any):
        super().__init__(
            message,
            status_code=kwargs.pop("status_code", ErrorCode.EXTRACTION_FAILED),
            **kwargs,
        )


class ValidationError(SBIRETLError):
    """Data validation failed. Not retryable by default."""

    def __init__(self, message: str, **kwargs: Any):
        super().__init__(
            message,
            status_code=kwargs.pop("status_code", ErrorCode.VALIDATION_FAILED),
            retryable=False,
            **kwargs,
        )


class EnrichmentError(SBIRETLError):
    """Data enrichment failed."""

    def __init__(self, message: str, **kwargs: Any):
        super().__init__(
            message,
            status_code=kwargs.pop("status_code", ErrorCode.ENRICHMENT_FAILED),
            **kwargs,
        )


class TransformationError(SBIRETLError):
    """Data transformation failed."""

    def __init__(self, message: str, **kwargs: Any):
        super().__init__(
            message,
            status_code=kwargs.pop("status_code", ErrorCode.TRANSFORMATION_FAILED),
            **kwargs,
        )


# -- Component-specific exceptions -------------------------------------------


class APIError(EnrichmentError):
    """External API call failed. Auto-marks 5xx/408/429 as retryable."""

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
        if "retryable" not in kwargs and http_status:
            kwargs["retryable"] = http_status in [408, 429, 500, 502, 503, 504]
        component = kwargs.pop("component", f"api.{api_name}" if api_name else "api")
        super().__init__(
            message,
            component=component,
            details=details,
            status_code=kwargs.pop("status_code", ErrorCode.API_REQUEST_FAILED),
            **kwargs,
        )


class RateLimitError(APIError):
    """API rate limit exceeded. Always retryable."""

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
    """Configuration loading or validation failed. Not retryable."""

    def __init__(self, message: str, config_key: str | None = None, **kwargs: Any):
        details = kwargs.pop("details", {})
        if config_key:
            details["config_key"] = config_key
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
    """File I/O operation failed."""

    def __init__(self, message: str, file_path: str | None = None, **kwargs: Any):
        details = kwargs.pop("details", {})
        if file_path:
            details["file_path"] = file_path
        component = kwargs.pop("component", "filesystem")
        super().__init__(
            message,
            component=component,
            details=details,
            status_code=kwargs.pop("status_code", ErrorCode.FILE_READ_FAILED),
            **kwargs,
        )


class CETClassificationError(TransformationError):
    """CET classification failed."""

    def __init__(self, message: str, **kwargs: Any):
        component = kwargs.pop("component", "cet_classification")
        super().__init__(message, component=component, **kwargs)


class DependencyError(SBIRETLError):
    """Missing or incompatible external dependency. Not retryable."""

    def __init__(self, message: str, dependency_name: str | None = None, **kwargs: Any):
        details = kwargs.pop("details", {})
        if dependency_name:
            details["dependency_name"] = dependency_name
        component = kwargs.pop("component", "dependencies")
        super().__init__(
            message,
            component=component,
            details=details,
            retryable=False,
            **kwargs,
        )


class RFunctionError(DependencyError):
    """R function call failed."""

    def __init__(self, message: str, function_name: str | None = None, **kwargs: Any):
        details = kwargs.pop("details", {})
        if function_name:
            details["function_name"] = function_name
        component = kwargs.pop("component", "r_interface")
        super().__init__(
            message,
            dependency_name="R",
            component=component,
            details=details,
            status_code=ErrorCode.R_FUNCTION_FAILED,
            **kwargs,
        )
