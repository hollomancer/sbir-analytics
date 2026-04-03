"""Backward-compatibility shim — re-exports from bea_io_adapter.

The R/rpy2 StateIO implementation has been replaced by a pure-Python
BEA API client.  This module exists solely so that existing import
paths continue to work.
"""

from .bea_io_adapter import BEAIOAdapter as RStateIOAdapter  # noqa: F401
from .bea_io_adapter import BEAIOAdapter  # noqa: F401

# Legacy constant — always True now (no R dependency)
RPY2_AVAILABLE = True

__all__ = ["RStateIOAdapter", "BEAIOAdapter", "RPY2_AVAILABLE"]
