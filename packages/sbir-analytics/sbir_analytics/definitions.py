"""Primary Dagster code-location entry point for the SBIR pipeline."""

from .definitions_factory import build_definitions


# Tests read the registrations (auto_jobs, schedules, sensors) from ``bundle``.
bundle = build_definitions("primary")
defs = bundle.defs
