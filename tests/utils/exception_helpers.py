"""Test utilities for exception handling.

This module provides helper functions for testing exceptions in the SBIR ETL
pipeline, making it easier to verify exception structure, context, and behavior.
"""

from typing import Any

from src.exceptions import SBIRETLError


def assert_exception_structure(
    exc: SBIRETLError,
    expected_message: str | None = None,
    expected_component: str | None = None,
    expected_operation: str | None = None,
    expected_retryable: bool | None = None,
    expected_status_code: int | None = None,
) -> None:
    """Assert exception has expected structure.

    Args:
        exc: Exception to validate
        expected_message: Expected error message (substring match)
        expected_component: Expected component identifier
        expected_operation: Expected operation name
        expected_retryable: Expected retryable flag
        expected_status_code: Expected status code

    Example:
        try:
            raise_some_error()
        except SBIRETLError as e:
            assert_exception_structure(
                e,
                expected_message="Failed to load",
                expected_component="loader.neo4j",
                expected_retryable=True
            )
    """
    # Verify it's a proper SBIR ETL exception
    assert isinstance(exc, SBIRETLError), f"Expected SBIRETLError, got {type(exc)}"

    # Check message (substring match for flexibility)
    if expected_message is not None:
        assert expected_message in exc.message, (
            f"Expected message to contain '{expected_message}', got '{exc.message}'"
        )

    # Check component
    if expected_component is not None:
        assert exc.component == expected_component, (
            f"Expected component '{expected_component}', got '{exc.component}'"
        )

    # Check operation
    if expected_operation is not None:
        assert exc.operation == expected_operation, (
            f"Expected operation '{expected_operation}', got '{exc.operation}'"
        )

    # Check retryable flag
    if expected_retryable is not None:
        assert exc.retryable == expected_retryable, (
            f"Expected retryable={expected_retryable}, got {exc.retryable}"
        )

    # Check status code
    if expected_status_code is not None:
        assert exc.status_code is not None, "Expected status_code to be set"
        assert exc.status_code.value == expected_status_code, (
            f"Expected status_code={expected_status_code}, got {exc.status_code.value}"
        )

    # All exceptions should be serializable
    assert isinstance(exc.to_dict(), dict), "Exception should be serializable"
    assert "error_type" in exc.to_dict(), "Serialized exception should have error_type"
    assert "message" in exc.to_dict(), "Serialized exception should have message"


def assert_raises_with_context(
    exception_class: type[SBIRETLError],
    callable_obj: Any,
    expected_component: str | None = None,
    expected_operation: str | None = None,
    expected_details_keys: list[str] | None = None,
) -> SBIRETLError:
    """Assert callable raises exception with expected context.

    Args:
        exception_class: Expected exception class
        callable_obj: Callable that should raise the exception
        expected_component: Expected component in exception
        expected_operation: Expected operation in exception
        expected_details_keys: Expected keys in details dict

    Returns:
        The raised exception for further inspection

    Example:
        exc = assert_raises_with_context(
            ConfigurationError,
            lambda: load_config("invalid.yaml"),
            expected_component="config",
            expected_details_keys=["file_path"]
        )
        assert exc.details["file_path"] == "invalid.yaml"
    """
    try:
        callable_obj()
        raise AssertionError(f"Expected {exception_class.__name__} but nothing was raised")
    except exception_class as e:
        # Verify component if specified
        if expected_component is not None:
            assert e.component == expected_component, (
                f"Expected component '{expected_component}', got '{e.component}'"
            )

        # Verify operation if specified
        if expected_operation is not None:
            assert e.operation == expected_operation, (
                f"Expected operation '{expected_operation}', got '{e.operation}'"
            )

        # Verify details keys if specified
        if expected_details_keys is not None:
            for key in expected_details_keys:
                assert key in e.details, (
                    f"Expected key '{key}' in details, got keys: {list(e.details.keys())}"
                )

        return e
    except Exception as e:
        raise AssertionError(f"Expected {exception_class.__name__} but got {type(e).__name__}: {e}")


def assert_exception_details(
    exc: SBIRETLError,
    expected_details: dict[str, Any],
) -> None:
    """Assert exception has expected details.

    Args:
        exc: Exception to validate
        expected_details: Dictionary of expected key-value pairs in details

    Example:
        try:
            validate_data(df)
        except ValidationError as e:
            assert_exception_details(e, {
                "missing_columns": ["state", "amount"],
                "total_rows": 100
            })
    """
    for key, expected_value in expected_details.items():
        assert key in exc.details, (
            f"Expected key '{key}' in details, got keys: {list(exc.details.keys())}"
        )
        actual_value = exc.details[key]
        assert actual_value == expected_value, (
            f"Expected details['{key}'] = {expected_value}, got {actual_value}"
        )


def assert_exception_serialization(exc: SBIRETLError) -> dict[str, Any]:
    """Assert exception can be serialized and verify structure.

    Args:
        exc: Exception to serialize

    Returns:
        Serialized exception dictionary

    Example:
        exc = ConfigurationError("Test")
        data = assert_exception_serialization(exc)
        assert data["error_type"] == "ConfigurationError"
    """
    data = exc.to_dict()

    # Verify required keys
    required_keys = ["error_type", "message", "component", "retryable"]
    for key in required_keys:
        assert key in data, f"Serialized exception missing required key: {key}"

    # Verify types
    assert isinstance(data["error_type"], str)
    assert isinstance(data["message"], str)
    assert isinstance(data["retryable"], bool)

    return data


def assert_retryable_exception(exc: SBIRETLError) -> None:
    """Assert exception is retryable.

    Args:
        exc: Exception to check

    Example:
        try:
            api_call()
        except APIError as e:
            assert_retryable_exception(e)
    """
    assert exc.retryable is True, (
        f"Expected exception to be retryable, but retryable={exc.retryable}"
    )


def assert_non_retryable_exception(exc: SBIRETLError) -> None:
    """Assert exception is not retryable.

    Args:
        exc: Exception to check

    Example:
        try:
            validate_config()
        except ConfigurationError as e:
            assert_non_retryable_exception(e)
    """
    assert exc.retryable is False, (
        f"Expected exception to be non-retryable, but retryable={exc.retryable}"
    )


def create_test_exception(
    exception_class: type[SBIRETLError],
    message: str = "Test error",
    **kwargs: Any,
) -> SBIRETLError:
    """Create a test exception with sensible defaults.

    Args:
        exception_class: Exception class to instantiate
        message: Error message
        **kwargs: Additional arguments for exception constructor

    Returns:
        Exception instance

    Example:
        exc = create_test_exception(
            APIError,
            "API failed",
            api_name="test_api",
            http_status=503
        )
    """
    # Provide default component if not specified
    if "component" not in kwargs:
        kwargs["component"] = "test.component"

    # Provide default operation if not specified
    if "operation" not in kwargs:
        kwargs["operation"] = "test_operation"

    return exception_class(message, **kwargs)
