"""Unit tests for centralized exception module."""

import pytest

pytestmark = pytest.mark.fast

from sbir_etl.exceptions import (
    APIError,
    CETClassificationError,
    ConfigurationError,
    DependencyError,
    EnrichmentError,
    ErrorCode,
    ExtractionError,
    FileSystemError,
    RateLimitError,
    RFunctionError,
    SBIRETLError,
    TransformationError,
    ValidationError,
)


class TestBaseException:
    def test_minimal(self):
        exc = SBIRETLError("Test error")
        assert exc.message == "Test error"
        assert exc.operation is None
        assert exc.details == {}
        assert exc.retryable is False
        assert exc.status_code is None
        assert exc.cause is None

    def test_full(self):
        cause = ValueError("Original error")
        exc = SBIRETLError(
            "Test error",
            component="test.component",
            operation="test_operation",
            details={"key": "value"},
            retryable=True,
            status_code=ErrorCode.VALIDATION_FAILED,
            cause=cause,
        )
        assert exc.component == "test.component"
        assert exc.operation == "test_operation"
        assert exc.retryable is True
        assert exc.status_code == ErrorCode.VALIDATION_FAILED
        assert exc.cause is cause

    def test_string_representation(self):
        exc = SBIRETLError(
            "Test error",
            component="test.component",
            status_code=ErrorCode.VALIDATION_FAILED,
        )
        exc_str = str(exc)
        assert "Test error" in exc_str
        assert "component=test.component" in exc_str

    def test_serialization(self):
        exc = SBIRETLError(
            "Test error",
            component="test.component",
            details={"key": "value"},
            retryable=True,
            status_code=ErrorCode.VALIDATION_FAILED,
            cause=ValueError("Original"),
        )
        data = exc.to_dict()
        assert data["error_type"] == "SBIRETLError"
        assert data["message"] == "Test error"
        assert data["retryable"] is True
        assert data["status_code"] == ErrorCode.VALIDATION_FAILED.value
        assert "Original" in data["cause"]


class TestErrorCodes:
    def test_code_ranges(self):
        assert 1000 <= ErrorCode.CONFIG_LOAD_FAILED.value < 2000
        assert 2000 <= ErrorCode.VALIDATION_FAILED.value < 3000
        assert 3000 <= ErrorCode.API_REQUEST_FAILED.value < 4000
        assert 4000 <= ErrorCode.FILE_NOT_FOUND.value < 5000
        assert 5000 <= ErrorCode.EXTRACTION_FAILED.value < 6000

    def test_codes_unique(self):
        codes = [code.value for code in ErrorCode]
        assert len(codes) == len(set(codes))


class TestPipelineStageExceptions:
    def test_extraction_error(self):
        exc = ExtractionError("Failed", component="extractor.sbir")
        assert exc.status_code == ErrorCode.EXTRACTION_FAILED
        assert exc.component == "extractor.sbir"

    def test_validation_error_not_retryable(self):
        exc = ValidationError("Schema failed")
        assert exc.retryable is False
        assert exc.status_code == ErrorCode.VALIDATION_FAILED

    def test_enrichment_error(self):
        exc = EnrichmentError("Failed", details={"awards_failed": 10})
        assert exc.status_code == ErrorCode.ENRICHMENT_FAILED
        assert exc.details["awards_failed"] == 10

    def test_transformation_error(self):
        exc = TransformationError("Failed", operation="calculate_roi")
        assert exc.status_code == ErrorCode.TRANSFORMATION_FAILED
        assert exc.operation == "calculate_roi"


class TestComponentExceptions:
    def test_api_error_auto_retryable_5xx(self):
        exc = APIError("Server error", api_name="usaspending", http_status=503)
        assert exc.retryable is True
        assert exc.component == "api.usaspending"
        assert exc.details["http_status"] == 503

    def test_api_error_not_retryable_4xx(self):
        exc = APIError("Bad request", http_status=400)
        assert exc.retryable is False

    def test_api_error_retryable_timeout(self):
        exc = APIError("Timeout", http_status=408)
        assert exc.retryable is True

    def test_rate_limit_always_retryable(self):
        exc = RateLimitError("Rate limit", retry_after=60)
        assert exc.retryable is True
        assert exc.status_code == ErrorCode.API_RATE_LIMIT
        assert exc.details["retry_after_seconds"] == 60

    def test_configuration_error_not_retryable(self):
        exc = ConfigurationError("Missing key", config_key="neo4j.uri")
        assert exc.retryable is False
        assert exc.details["config_key"] == "neo4j.uri"

    def test_filesystem_error(self):
        exc = FileSystemError("Not found", file_path="/data/awards.csv")
        assert exc.component == "filesystem"
        assert exc.details["file_path"] == "/data/awards.csv"

    def test_cet_classification_error(self):
        exc = CETClassificationError("Failed", details={"award_id": "A-1"})
        assert exc.component == "cet_classification"
        assert isinstance(exc, TransformationError)

    def test_dependency_error_not_retryable(self):
        exc = DependencyError("Not installed", dependency_name="neo4j")
        assert exc.retryable is False
        assert exc.details["dependency_name"] == "neo4j"

    def test_r_function_error(self):
        exc = RFunctionError("Failed", function_name="calculate_impacts")
        assert exc.component == "r_interface"
        assert exc.details["function_name"] == "calculate_impacts"
        assert exc.status_code == ErrorCode.R_FUNCTION_FAILED


class TestInheritance:
    def test_all_inherit_from_base(self):
        for cls in [
            ExtractionError, ValidationError, EnrichmentError,
            TransformationError, APIError, RateLimitError,
            ConfigurationError, FileSystemError, CETClassificationError,
            DependencyError, RFunctionError,
        ]:
            assert issubclass(cls, SBIRETLError), f"{cls.__name__} must inherit SBIRETLError"

    def test_subclass_chains(self):
        assert issubclass(APIError, EnrichmentError)
        assert issubclass(RateLimitError, APIError)
        assert issubclass(CETClassificationError, TransformationError)
        assert issubclass(RFunctionError, DependencyError)
