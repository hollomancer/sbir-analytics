"""Alias for the primary Dagster code location.

The separate heavy ML and fiscal code location is retired. This module re-exports
the primary ``defs`` so that ``-m sbir_analytics.definitions_ml`` commands keep
working. Heavy jobs load only while ``DAGSTER_LOAD_HEAVY_ASSETS`` is true (the
default).
"""

from .definitions import defs


__all__ = ["defs"]
