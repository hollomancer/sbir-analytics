"""Heavy ML and fiscal entry point for the primary Dagster definitions.

The separate heavy code location is retired. This module builds the primary
definitions with the heavy modules always loaded, so that
``-m sbir_analytics.definitions_ml`` commands find the CET, fiscal, ModernBERT,
and USPTO AI jobs even when ``DAGSTER_LOAD_HEAVY_ASSETS`` is false.
"""

from .definitions_factory import build_definitions


defs = build_definitions("heavy").defs

__all__ = ["defs"]
