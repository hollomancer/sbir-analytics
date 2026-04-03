"""Backward-compatibility shim — re-exports from bea_io_functions.

The R/rpy2 StateIO wrappers have been replaced by pure-Python BEA API
functions.  This module exists solely so that existing import paths
continue to work.
"""

from .bea_io_functions import (  # noqa: F401
    apply_demand_shocks,
    calculate_employment_coefficients,
    calculate_employment_from_production,
    calculate_leontief_inverse,
    calculate_technical_coefficients,
    calculate_value_added_ratios,
)

__all__ = [
    "apply_demand_shocks",
    "calculate_employment_coefficients",
    "calculate_employment_from_production",
    "calculate_leontief_inverse",
    "calculate_technical_coefficients",
    "calculate_value_added_ratios",
]
