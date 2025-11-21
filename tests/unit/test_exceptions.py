"""Unit tests for centralized exception module.

Tests cover:
- Base exception class functionality
- Exception hierarchy correctness
- Error code system
- Helper functions (wrap_exception, is_retryable, etc.)
- Serialization and context preservation
"""

import pytest


pytestmark = pytest.mark.fast

from src.exceptions import (
    APIError,
    CETClassificationError,
    ConfigurationError,
    DataQualityError,
    DependencyError,
    EnrichmentError,
    ErrorCode,
    ExtractionError,
    FileSystemError,
    FiscalAnalysisError,
    LoadError,
    Neo4jError,
    PatentProcessingError,
    RateLimitError,
    RFunctionError,
    SBIRETLError,
    TransformationError,
    TransitionDetectionError,
    ValidationError,
    get_error_code,
    is_retryable,
    wrap_exception,
)
from tests.utils.exception_helpers import (
    assert_exception_details,
    assert_exception_serialization,
    assert_exception_structure,
    assert_non_retryable_exception,
    assert_retryable_exception,
    create_test_exception,
)


pytestmark = pytest.mark.fast


class TestBaseException:
    """Tests for SBIRETLError base class."""

    def test_base_exception_minimal(self):
        """Test base exception with minimal arguments."""
        exc = SBIRETLError("Test error")

        assert exc.message == "Test error"
        assert exc.component is not None  # Should default to module name
        assert exc.operation is None
        assert exc.details == {}
        assert exc.retryable is False
        assert exc.status_code is None
        assert exc.cause is None

    def test_base_exception_full(self):
        """Test base exception with all arguments."""
        details = {"key": "value", "count": 42}
        cause = ValueError("Original error")

        exc = SBIRETLError(
            "Test error",
            component="test.component",
            operation="test_operation",
            details=details,
            retryable=True,
            status_code=ErrorCode.VALIDATION_FAILED,
            cause=cause,
        )

        assert exc.message == "Test error"
        assert exc.component == "test.component"
        assert exc.operation == "test_operation"
        assert exc.details == details
        assert exc.retryable is True
        assert exc.status_code == ErrorCode.VALIDATION_FAILED
        assert exc.cause is cause

    def test_base_exception_string_representation(self):
        """Test exception string includes context."""
        exc = SBIRETLError(
            "Test error",
            component="test.component",
            operation="test_op",
            status_code=ErrorCode.VALIDATION_FAILED,
        )

        exc_str = str(exc)
        assert "Test error" in exc_str
        assert "component=test.component" in exc_str
        assert "operation=test_op" in exc_str
        assert f"code={ErrorCode.VALIDATION_FAILED}" in exc_str

    def test_base_exception_serialization(self):
        """Test exception can be serialized to dict."""
        cause = ValueError("Original")
        exc = SBIRETLError(
            "Test error",
            component="test.component",
            operation="test_op",
            details={"key": "value"},
            retryable=True,
            status_code=ErrorCode.VALIDATION_FAILED,
            cause=cause,
        )

        data = exc.to_dict()

        assert data["error_type"] == "SBIRETLError"
        assert data["message"] == "Test error"
        assert data["component"] == "test.component"
        assert data["operation"] == "test_op"
        assert data["details"] == {"key": "value"}
        assert data["retryable"] is True
        assert data["status_code"] == ErrorCode.VALIDATION_FAILED.value
        assert "Original" in data["cause"]


class TestErrorCodes:
    """Tests for ErrorCode enum."""

    def test_error_code_values(self):
        """Test error codes have expected values."""
        # Configuration errors (1xxx)
        assert 1000 <= ErrorCode.CONFIG_LOAD_FAILED.value < 2000
        assert 1000 <= ErrorCode.CONFIG_VALIDATION_FAILED.value < 2000

        # Data quality errors (2xxx)
        assert 2000 <= ErrorCode.VALIDATION_FAILED.value < 3000
        assert 2000 <= ErrorCode.QUALITY_THRESHOLD_NOT_MET.value < 3000

        # External dependencies (3xxx)
        assert 3000 <= ErrorCode.NEO4J_QUERY_FAILED.value < 4000
        assert 3000 <= ErrorCode.API_REQUEST_FAILED.value < 4000
        assert 3000 <= ErrorCode.R_FUNCTION_FAILED.value < 4000

        # File I/O errors (4xxx)
        assert 4000 <= ErrorCode.FILE_NOT_FOUND.value < 5000

        # Pipeline stage errors (5xxx)
        assert 5000 <= ErrorCode.EXTRACTION_FAILED.value < 6000

    def test_error_codes_unique(self):
        """Test all error codes are unique."""
        codes = [code.value for code in ErrorCode]
        assert len(codes) == len(set(codes)), "Error codes must be unique"


class TestPipelineStageExceptions:
    """Tests for pipeline stage exceptions (Layer 1)."""

    def test_extraction_error(self):
        """Test ExtractionError."""
        exc = ExtractionError("Failed to extract data", component="extractor.sbir")

        assert_exception_structure(
            exc,
            expected_message="Failed to extract",
            expected_component="extractor.sbir",
            expected_status_code=ErrorCode.EXTRACTION_FAILED.value,
        )

    def test_validation_error(self):
        """Test ValidationError is not retryable by default."""
        exc = ValidationError("Schema validation failed")

        assert_exception_structure(exc, expected_retryable=False)
        assert exc.status_code == ErrorCode.VALIDATION_FAILED

    def test_enrichment_error(self):
        """Test EnrichmentError."""
        exc = EnrichmentError(
            "Enrichment failed",
            component="enricher.usaspending",
            details={"awards_failed": 10},
        )

        assert exc.status_code == ErrorCode.ENRICHMENT_FAILED
        assert exc.details["awards_failed"] == 10

    def test_transformation_error(self):
        """Test TransformationError."""
        exc = TransformationError("Calculation failed", operation="calculate_roi")

        assert exc.status_code == ErrorCode.TRANSFORMATION_FAILED
        assert exc.operation == "calculate_roi"

    def test_load_error(self):
        """Test LoadError."""
        exc = LoadError("Failed to load nodes", component="loader.neo4j")

        assert exc.status_code == ErrorCode.LOADING_FAILED
        assert exc.component == "loader.neo4j"


class TestComponentSpecificExceptions:
    """Tests for component-specific exceptions (Layer 2)."""

    def test_neo4j_error_with_query(self):
        """Test Neo4jError includes query in details."""
        query = "MERGE (a:Award {id: $id})"
        exc = Neo4jError("Query failed", query=query, operation="create_node")

        assert exc.component == "neo4j"
        assert exc.details["query"] == query
        assert exc.operation == "create_node"
        assert exc.status_code == ErrorCode.NEO4J_QUERY_FAILED

    def test_api_error_auto_retryable_5xx(self):
        """Test APIError is automatically retryable for 5xx status codes."""
        exc = APIError(
            "Server error",
            api_name="usaspending",
            endpoint="/v2/awards",
            http_status=503,
        )

        assert_retryable_exception(exc)
        assert exc.component == "api.usaspending"
        assert exc.details["endpoint"] == "/v2/awards"
        assert exc.details["http_status"] == 503

    def test_api_error_not_retryable_4xx(self):
        """Test APIError is not retryable for 4xx status codes."""
        exc = APIError(
            "Bad request",
            api_name="usaspending",
            http_status=400,
        )

        assert_non_retryable_exception(exc)

    def test_api_error_retryable_timeout(self):
        """Test APIError is retryable for timeout status."""
        exc = APIError(
            "Timeout",
            api_name="usaspending",
            http_status=408,
        )

        assert_retryable_exception(exc)

    def test_rate_limit_error_always_retryable(self):
        """Test RateLimitError is always retryable."""
        exc = RateLimitError(
            "Rate limit exceeded",
            api_name="usaspending",
            retry_after=60,
        )

        assert_retryable_exception(exc)
        assert exc.status_code == ErrorCode.API_RATE_LIMIT
        assert exc.details["retry_after_seconds"] == 60

    def test_configuration_error_not_retryable(self):
        """Test ConfigurationError is not retryable."""
        exc = ConfigurationError(
            "Missing config key",
            config_key="neo4j.uri",
        )

        assert_non_retryable_exception(exc)
        assert exc.component == "config"
        assert exc.details["config_key"] == "neo4j.uri"

    def test_filesystem_error_with_path(self):
        """Test FileSystemError includes file path."""
        exc = FileSystemError(
            "File not found",
            file_path="/data/awards.csv",
            operation="read_file",
        )

        assert exc.component == "filesystem"
        assert exc.details["file_path"] == "/data/awards.csv"
        assert exc.operation == "read_file"


class TestDomainSpecificExceptions:
    """Tests for domain-specific exceptions (Layer 3)."""

    def test_transition_detection_error(self):
        """Test TransitionDetectionError."""
        exc = TransitionDetectionError(
            "Failed to calculate score",
            operation="calculate_composite_score",
        )

        assert exc.component == "transition_detection"
        assert exc.operation == "calculate_composite_score"
        assert isinstance(exc, TransformationError)

    def test_fiscal_analysis_error(self):
        """Test FiscalAnalysisError."""
        exc = FiscalAnalysisError(
            "ROI calculation failed",
            operation="compute_npv",
        )

        assert exc.component == "fiscal_analysis"
        assert isinstance(exc, TransformationError)

    def test_cet_classification_error(self):
        """Test CETClassificationError."""
        exc = CETClassificationError(
            "Classification failed",
            operation="predict_cet_areas",
            details={"award_id": "SBIR-2020-001"},
        )

        assert exc.component == "cet_classification"
        assert exc.details["award_id"] == "SBIR-2020-001"

    def test_patent_processing_error(self):
        """Test PatentProcessingError."""
        exc = PatentProcessingError(
            "Failed to parse patent data",
            operation="parse_dta_file",
        )

        assert exc.component == "patent_processing"


class TestOperationalExceptions:
    """Tests for operational exceptions (Layer 4)."""

    def test_data_quality_error_with_threshold(self):
        """Test DataQualityError includes threshold info."""
        exc = DataQualityError(
            "Match rate below threshold",
            threshold=0.70,
            actual_value=0.58,
            component="enricher.usaspending",
        )

        assert_non_retryable_exception(exc)
        assert exc.details["threshold"] == 0.70
        assert exc.details["actual_value"] == 0.58
        assert exc.status_code == ErrorCode.QUALITY_THRESHOLD_NOT_MET

    def test_dependency_error_not_retryable(self):
        """Test DependencyError is not retryable."""
        exc = DependencyError(
            "Package not installed",
            dependency_name="neo4j",
            details={"install_command": "pip install neo4j"},
        )

        assert_non_retryable_exception(exc)
        assert exc.component == "dependencies"
        assert exc.details["dependency_name"] == "neo4j"

    def test_r_function_error(self):
        """Test RFunctionError."""
        exc = RFunctionError(
            "R function failed",
            function_name="calculate_impacts",
            details={"r_error": "invalid NAICS code"},
        )

        assert exc.component == "r_interface"
        assert exc.details["function_name"] == "calculate_impacts"
        assert exc.details["r_error"] == "invalid NAICS code"
        assert exc.status_code == ErrorCode.R_FUNCTION_FAILED


class TestHelperFunctions:
    """Tests for exception helper functions."""

    def test_wrap_exception_basic(self):
        """Test wrap_exception with basic usage."""
        original = ValueError("Invalid input")
        wrapped = wrap_exception(
            original,
            ValidationError,
            component="test.component",
        )

        assert isinstance(wrapped, ValidationError)
        assert wrapped.cause is original
        assert wrapped.component == "test.component"
        assert "Invalid input" in wrapped.message

    def test_wrap_exception_with_message_override(self):
        """Test wrap_exception with custom message."""
        original = ValueError("Original")
        wrapped = wrap_exception(
            original,
            ValidationError,
            message="Custom message",
            component="test",
        )

        assert wrapped.message == "Custom message"
        assert wrapped.cause is original

    def test_wrap_exception_preserves_context(self):
        """Test wrap_exception preserves additional context."""
        original = KeyError("missing_key")
        wrapped = wrap_exception(
            original,
            ValidationError,
            component="test",
            operation="validate_data",
            details={"key": "missing_key"},
        )

        assert wrapped.operation == "validate_data"
        assert wrapped.details["key"] == "missing_key"
        assert wrapped.cause is original

    def test_is_retryable_true(self):
        """Test is_retryable returns True for retryable exceptions."""
        exc = APIError("Error", http_status=503)  # 503 is retryable
        assert is_retryable(exc) is True

    def test_is_retryable_false(self):
        """Test is_retryable returns False for non-retryable exceptions."""
        exc = ConfigurationError("Error")
        assert is_retryable(exc) is False

    def test_is_retryable_generic_exception(self):
        """Test is_retryable returns False for generic exceptions."""
        exc = ValueError("Error")
        assert is_retryable(exc) is False

    def test_get_error_code_with_code(self):
        """Test get_error_code returns code value."""
        exc = ValidationError("Error")
        code = get_error_code(exc)
        assert code == ErrorCode.VALIDATION_FAILED.value

    def test_get_error_code_without_code(self):
        """Test get_error_code returns None for no code."""
        exc = SBIRETLError("Error")  # No status_code set
        code = get_error_code(exc)
        assert code is None

    def test_get_error_code_generic_exception(self):
        """Test get_error_code returns None for generic exceptions."""
        exc = ValueError("Error")
        code = get_error_code(exc)
        assert code is None


class TestExceptionInheritance:
    """Tests for exception hierarchy correctness."""

    def test_all_exceptions_inherit_from_base(self):
        """Test all custom exceptions inherit from SBIRETLError."""
        exception_classes = [
            ExtractionError,
            ValidationError,
            EnrichmentError,
            TransformationError,
            LoadError,
            Neo4jError,
            APIError,
            RateLimitError,
            ConfigurationError,
            FileSystemError,
            TransitionDetectionError,
            FiscalAnalysisError,
            CETClassificationError,
            PatentProcessingError,
            DataQualityError,
            DependencyError,
            RFunctionError,
        ]

        for exc_class in exception_classes:
            assert issubclass(exc_class, SBIRETLError), (
                f"{exc_class.__name__} should inherit from SBIRETLError"
            )

    def test_layer_2_inherits_from_layer_1(self):
        """Test layer 2 exceptions inherit from layer 1."""
        assert issubclass(Neo4jError, LoadError)
        assert issubclass(APIError, EnrichmentError)

    def test_layer_3_inherits_from_layer_1(self):
        """Test layer 3 exceptions inherit from layer 1."""
        assert issubclass(TransitionDetectionError, TransformationError)
        assert issubclass(FiscalAnalysisError, TransformationError)
        assert issubclass(CETClassificationError, TransformationError)

    def test_layer_4_inherits_correctly(self):
        """Test layer 4 exceptions inherit correctly."""
        assert issubclass(RateLimitError, APIError)
        assert issubclass(DataQualityError, ValidationError)
        assert issubclass(RFunctionError, DependencyError)


class TestExceptionTestHelpers:
    """Tests for the exception test helper utilities themselves."""

    def test_assert_exception_structure(self):
        """Test assert_exception_structure helper."""
        exc = create_test_exception(
            ConfigurationError,
            "Test error",
            component="test.component",
            operation="test_op",
        )

        # Should not raise
        assert_exception_structure(
            exc,
            expected_message="Test error",
            expected_component="test.component",
            expected_operation="test_op",
        )

    def test_assert_exception_details(self):
        """Test assert_exception_details helper."""
        exc = create_test_exception(
            ValidationError,
            "Error",
            details={"key1": "value1", "key2": 42},
        )

        # Should not raise
        assert_exception_details(exc, {"key1": "value1", "key2": 42})

    def test_assert_exception_serialization(self):
        """Test assert_exception_serialization helper."""
        exc = create_test_exception(ConfigurationError, "Test")

        data = assert_exception_serialization(exc)
        assert data["error_type"] == "ConfigurationError"
        assert data["message"] == "Test"

    def test_create_test_exception(self):
        """Test create_test_exception helper."""
        exc = create_test_exception(
            APIError,
            "Test error",
            api_name="test_api",
            http_status=500,
        )

        assert isinstance(exc, APIError)
        assert exc.message == "Test error"
        assert exc.component == "test.component"  # Default
        assert exc.operation == "test_operation"  # Default
