"""R helper utilities for safe function calling and data conversion."""

from __future__ import annotations

from typing import Any

from loguru import logger

from ..exceptions import DependencyError, RFunctionError, ValidationError  # Import from central exceptions


# Conditional rpy2 import
try:
    import rpy2.robjects as ro
    from rpy2.robjects.packages import importr

    RPY2_AVAILABLE = True
except ImportError:
    RPY2_AVAILABLE = False
    ro = None
    importr = None


def check_r_package(package_name: str) -> bool:
    """Check if an R package is installed and available.

    Args:
        package_name: Name of R package to check

    Returns:
        True if package is available, False otherwise
    """
    if not RPY2_AVAILABLE:
        return False

    try:
        package = importr(package_name)
        return package is not None
    except Exception as e:
        logger.debug(f"R package {package_name} not available: {e}")
        return False


def call_r_function(
    package: Any,
    function_name: str,
    *args: Any,
    **kwargs: Any,
) -> Any:
    """Safely call an R function with error handling.

    Args:
        package: R package object from importr()
        function_name: Name of R function to call
        *args: Positional arguments to pass to R function
        **kwargs: Keyword arguments to pass to R function

    Returns:
        R function result

    Raises:
        RFunctionError: If function call fails or package is unavailable
        RuntimeError: If rpy2 is not available
    """
    if not RPY2_AVAILABLE:
        raise DependencyError(
            "rpy2 is not installed. Install with: poetry install --extras r",
            dependency_name="rpy2",
            component="utils.r_helpers",
            details={"install_command": "poetry install --extras r"},
        )

    if package is None:
        raise RFunctionError(
            f"R package not loaded. Cannot call {function_name}.",
            function_name=function_name,
            operation="call_r_function",
        )

    try:
        # Get function from package
        r_func = getattr(package, function_name)

        # Call with arguments
        if args or kwargs:
            result = r_func(*args, **kwargs)
        else:
            result = r_func()

        return result

    except Exception as e:
        error_msg = str(e)
        logger.error(f"R function {function_name} failed: {error_msg}")

        # Try to extract R error message if available
        r_error = None
        if hasattr(e, "args") and len(e.args) > 0:
            r_error = str(e.args[0])

        details = {}
        if r_error:
            details["r_error"] = r_error
        if args:
            details["args_count"] = len(args)
        if kwargs:
            details["kwargs_keys"] = list(kwargs.keys())

        raise RFunctionError(
            f"R function {function_name} call failed: {error_msg}",
            function_name=function_name,
            operation="call_r_function",
            details=details,
            cause=e,
        ) from e


def validate_r_input(
    data: Any,
    required_columns: list[str] | None = None,
    min_rows: int = 1,
) -> None:
    """Validate data before passing to R.

    Args:
        data: Data to validate (DataFrame or dict-like)
        required_columns: List of required column names
        min_rows: Minimum number of rows required

    Raises:
        ValueError: If validation fails
    """
    if hasattr(data, "__len__") and len(data) < min_rows:
        raise ValidationError(
            f"Data must have at least {min_rows} row(s)",
            component="utils.r_helpers",
            operation="validate_r_input",
            details={"actual_rows": len(data), "min_rows": min_rows},
        )

    if required_columns:
        if hasattr(data, "columns"):
            missing = [col for col in required_columns if col not in data.columns]
            if missing:
                raise ValidationError(
                    f"Missing required columns: {missing}",
                    component="utils.r_helpers",
                    operation="validate_r_input",
                    details={
                        "missing_columns": missing,
                        "required_columns": required_columns,
                        "available_columns": list(data.columns),
                    },
                )
        elif hasattr(data, "keys"):
            # dict-like object
            missing = [col for col in required_columns if col not in data.keys()]
            if missing:
                raise ValidationError(
                    f"Missing required keys: {missing}",
                    component="utils.r_helpers",
                    operation="validate_r_input",
                    details={
                        "missing_keys": missing,
                        "required_keys": required_columns,
                        "available_keys": list(data.keys()),
                    },
                )


def extract_r_result(
    r_result: Any,
    expected_columns: list[str] | None = None,
) -> Any:
    """Extract and format R result consistently.

    Args:
        r_result: R result object (data.frame, list, etc.)
        expected_columns: List of expected column names (for validation)

    Returns:
        Formatted result (typically pandas DataFrame)

    Raises:
        ValueError: If result doesn't match expected structure
    """
    # Result extraction depends on actual R return type
    # This is a placeholder - actual implementation depends on StateIO API
    if r_result is None:
        raise ValidationError(
            "R function returned None",
            component="utils.r_helpers",
            operation="extract_r_result",
            details={"expected_type": "DataFrame or dict"},
        )

    # If r_result is already a DataFrame (converted by pandas2ri), return as-is
    # Otherwise, conversion happens in _convert_r_to_pandas

    if expected_columns and hasattr(r_result, "columns"):
        missing = [col for col in expected_columns if col not in r_result.columns]
        if missing:
            logger.warning(
                f"R result missing expected columns: {missing}. "
                f"Found columns: {list(r_result.columns)}"
            )

    return r_result


def safe_r_eval(r_code: str) -> Any:
    """Safely evaluate R code string.

    Args:
        r_code: R code to evaluate

    Returns:
        R evaluation result

    Raises:
        RFunctionError: If evaluation fails
    """
    if not RPY2_AVAILABLE:
        raise DependencyError(
            "rpy2 is not installed. Install with: poetry install --extras r",
            dependency_name="rpy2",
            component="utils.r_helpers",
            details={"install_command": "poetry install --extras r"},
        )

    try:
        result = ro.r(r_code)
        return result
    except Exception as e:
        error_msg = str(e)
        logger.error(f"R code evaluation failed: {error_msg}")
        raise RFunctionError(
            f"R code evaluation failed: {error_msg}",
            function_name="eval",
            operation="safe_r_eval",
            details={"r_code_preview": r_code[:100]},  # First 100 chars
            cause=e,
        ) from e


def get_r_package_version(package_name: str) -> str | None:
    """Get version string for an R package.

    Args:
        package_name: Name of R package

    Returns:
        Version string or None if package not found
    """
    if not RPY2_AVAILABLE:
        return None

    try:
        # Try to get package version via R
        version_code = f'packageVersion("{package_name}")'
        version_result = safe_r_eval(version_code)
        if version_result:
            return str(version_result[0])
    except Exception:
        logger.debug(f"Could not determine version for {package_name}")
        return None

    return None
