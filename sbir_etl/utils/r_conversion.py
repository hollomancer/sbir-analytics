"""
Pandas ↔ R data.frame conversion utilities.

This module provides utilities for converting between pandas DataFrames
and R data.frames, with type preservation and error handling.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
from loguru import logger


# Conditional rpy2 import
try:
    import rpy2.robjects as ro
    from rpy2.robjects import pandas2ri

    RPY2_AVAILABLE = True
except ImportError:
    RPY2_AVAILABLE = False
    ro = None
    pandas2ri = None


def pandas_to_r(df: pd.DataFrame, activate_conversion: bool = True) -> Any:
    """Convert pandas DataFrame to R data.frame.

    Args:
        df: pandas DataFrame
        activate_conversion: Activate pandas2ri conversion (default: True)

    Returns:
        R data.frame object

    Raises:
        ImportError: If rpy2 is not installed
    """
    if not RPY2_AVAILABLE:
        raise ImportError("rpy2 is not installed. Install with: poetry install --extras r")

    if activate_conversion:
        pandas2ri.activate()

    try:
        r_df = pandas2ri.py2rpy(df)
        return r_df
    except Exception as e:
        logger.error(f"Failed to convert pandas DataFrame to R: {e}")
        raise


def r_to_pandas(r_df: Any, preserve_types: bool = True) -> pd.DataFrame:
    """Convert R data.frame to pandas DataFrame.

    Args:
        r_df: R data.frame object
        preserve_types: Attempt to preserve numeric types (default: True)

    Returns:
        pandas DataFrame

    Raises:
        ImportError: If rpy2 is not installed
    """
    if not RPY2_AVAILABLE:
        raise ImportError("rpy2 is not installed. Install with: poetry install --extras r")

    try:
        df = pandas2ri.rpy2py(r_df)

        if preserve_types:
            # Attempt to preserve numeric types
            for col in df.columns:
                if df[col].dtype == "object":
                    # Try to convert to numeric
                    try:
                        df[col] = pd.to_numeric(df[col], errors="coerce")  # type: ignore[call-overload]
                    except (ValueError, TypeError):
                        pass

        return df
    except Exception as e:
        logger.error(f"Failed to convert R data.frame to pandas: {e}")
        raise


def check_r_available() -> bool:
    """Check if rpy2 is available.

    Returns:
        True if rpy2 is installed and available
    """
    return RPY2_AVAILABLE
