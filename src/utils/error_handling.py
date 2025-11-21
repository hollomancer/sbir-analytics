"""Standardized error handling utilities for consistent error management.

This module provides utilities for:
- Context-aware error logging
- Retry logic with backoff
- Asset error handling patterns
"""

from __future__ import annotations

import time
from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar

from loguru import logger


T = TypeVar("T")


def log_and_raise(
    error: Exception,
    context: str | None = None,
    additional_info: dict[str, Any] | None = None,
    reraise: bool = True,
) -> None:
    """Log an error with context and optionally re-raise it.

    Args:
        error: Exception to log
        context: Optional context string (e.g., "asset_name", "chunk_processing")
        additional_info: Optional dictionary with additional context
        reraise: If True, re-raise the exception after logging
    """
    context_str = f"[{context}] " if context else ""
    info_str = ""
    if additional_info:
        info_parts = [f"{k}={v}" for k, v in additional_info.items()]
        info_str = f" ({', '.join(info_parts)})"

    logger.error(f"{context_str}Error: {error}{info_str}", exc_info=True)

    if reraise:
        raise


def handle_asset_error(
    error: Exception,
    asset_name: str,
    context: Any | None = None,
    return_placeholder: bool = False,
    placeholder_value: Any = None,
) -> Any:
    """Handle errors in Dagster assets with standardized logging.

    Args:
        error: Exception that occurred
        asset_name: Name of the asset where error occurred
        context: Optional Dagster AssetExecutionContext for logging
        return_placeholder: If True, return placeholder value instead of raising
        placeholder_value: Value to return if return_placeholder is True

    Returns:
        placeholder_value if return_placeholder is True, otherwise raises

    Raises:
        The original exception if return_placeholder is False
    """
    # Log to context if available
    if context and hasattr(context, "log"):
        context.log.error(f"Error in asset {asset_name}: {error}", exc_info=True)
    else:
        logger.error(f"Error in asset {asset_name}: {error}", exc_info=True)

    if return_placeholder:
        logger.warning(f"Returning placeholder value for asset {asset_name}")
        return placeholder_value

    raise


def retry_with_backoff(
    max_retries: int = 3,
    initial_delay: float = 1.0,
    backoff_factor: float = 2.0,
    max_delay: float = 60.0,
    exceptions: tuple[type[Exception], ...] = (Exception,),
    on_retry: Callable[[Exception, int], None] | None = None,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorator for retrying functions with exponential backoff.

    Args:
        max_retries: Maximum number of retry attempts
        initial_delay: Initial delay in seconds before first retry
        backoff_factor: Multiplier for delay between retries
        max_delay: Maximum delay in seconds between retries
        exceptions: Tuple of exception types to catch and retry on
        on_retry: Optional callback function called on each retry (exception, attempt_num)

    Returns:
        Decorated function with retry logic
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            delay = initial_delay
            last_exception = None

            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e

                    if attempt < max_retries:
                        if on_retry:
                            on_retry(e, attempt + 1)
                        else:
                            logger.warning(
                                f"Retry {attempt + 1}/{max_retries} for {func.__name__} after {delay:.1f}s: {e}"
                            )

                        time.sleep(delay)
                        delay = min(delay * backoff_factor, max_delay)
                    else:
                        logger.error(f"Max retries ({max_retries}) exceeded for {func.__name__}")
                        raise

            # Should never reach here, but type checker needs it
            assert last_exception is not None
            raise last_exception

        return wrapper

    return decorator


def safe_execute(
    func: Callable[..., T],
    *args: Any,
    default: T | None = None,
    context: str | None = None,
    **kwargs: Any,
) -> T | None:
    """Safely execute a function, returning default value on error.

    Args:
        func: Function to execute
        *args: Positional arguments for function
        default: Default value to return on error (None if not provided)
        context: Optional context string for logging
        **kwargs: Keyword arguments for function

    Returns:
        Function result or default value on error
    """
    try:
        return func(*args, **kwargs)
    except Exception as e:
        context_str = f"[{context}] " if context else ""
        logger.warning(f"{context_str}Error executing {func.__name__}: {e}")
        return default
