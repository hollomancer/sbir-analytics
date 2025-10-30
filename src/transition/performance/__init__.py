"""Performance optimization utilities for transition detection pipeline.

This module provides tools for:
- DuckDB-based contract analytics (handling 6.7M+ contracts efficiently)
- Vendor-based contract filtering to reduce dataset size
- Optimized vendor cross-walk with indexed lookups
- Caching of vendor resolutions
- Performance profiling and monitoring
"""

from __future__ import annotations

__all__ = [
    "ContractAnalytics",
    "VendorFilteredContracts",
    "PerformanceProfiler",
]
