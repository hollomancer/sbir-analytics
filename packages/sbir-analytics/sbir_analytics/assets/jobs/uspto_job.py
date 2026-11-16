# packages/sbir-analytics/sbir_analytics/assets/jobs/uspto_job.py
"""
Dagster job that composes the USPTO assets into a single materialization job.

This job materializes:
  - raw_uspto_assignments (discovers raw files and reads a preview)
  - validated_uspto_assignments (runs rf_id uniqueness and returns per-file summaries)

Asset checks associated with these assets (e.g., uspto_rf_id_asset_check) will be
registered by Dagster as part of the repository when the module defining them is
imported. When this job is materialized in a Dagster run that executes asset checks,
those checks will be evaluated against the materialized assets.

Usage:
  - Import the job into your Dagster repository (for example via a repository definition)
  - Run the job with dagster CLI or from the Dagster UI

Notes:
  - This file only defines a lightweight job composition for the USPTO assets.
  - Runtime configuration (such as the raw file directory) should be provided via
    Dagster run config or environment variables consumed by the assets.
"""

from sbir_analytics.assets.uspto import raw_uspto_assignments, validated_uspto_assignments

from .job_registry import JobSpec, build_job_from_spec


# The assets module also defines an asset_check `uspto_rf_id_asset_check` which
# will be attached to `validated_uspto_assignments` when the repository is loaded.
uspto_validation_job = build_job_from_spec(
    JobSpec(
        name="uspto_validation_job",
        description=(
            "Materialize USPTO assignment assets and run basic validators (rf_id uniqueness). "
            "This job is intended for CI and lightweight validation runs."
        ),
        assets=(
            raw_uspto_assignments,
            validated_uspto_assignments,
        ),
    )
)


# For convenience, expose a stable name that repository scaffolding can import.
__all__ = ["uspto_validation_job"]
