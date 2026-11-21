"""Heavy ML and fiscal Dagster code-location entry point."""

from .definitions_factory import build_definitions


defs = build_definitions("heavy").defs
