# sbir-etl/src/assets/jobs/uspto_job.py
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

from dagster import AssetSelection, build_assets_job

# Import the USPTO asset definitions. These are expected to be defined in the
# package `src.assets.uspto_assets` as `raw_uspto_assignments` and
# `validated_uspto_assignments`.
#
# The assets module also defines an asset_check `uspto_rf_id_asset_check` which
# will be attached to `validated_uspto_assignments` when the repository is loaded.
try:
    from src.assets.uspto_assets import raw_uspto_assignments, validated_uspto_assignments
except Exception:  # pragma: no cover - defensive import for repository load-time
    # If assets cannot be imported (e.g., dependencies missing at import time),
    # set placeholders so the module still defines `uspto_validation_job` symbol.
    raw_uspto_assignments = None  # type: ignore
    validated_uspto_assignments = None  # type: ignore


# Build an assets job that materializes the USPTO extraction + validation flow.
# The job is named `uspto_validation_job` and only includes the two assets we care about.
# Downstream consumers (or CI) can call this job to materialize assets and evaluate checks.
if raw_uspto_assignments is not None and validated_uspto_assignments is not None:
    uspto_validation_job = build_assets_job(
        name="uspto_validation_job",
        assets=[raw_uspto_assignments, validated_uspto_assignments],
        selection=AssetSelection.keys(
            raw_uspto_assignments.key,
            validated_uspto_assignments.key,  # type: ignore[attr-defined]
        ),
        description=(
            "Materialize USPTO assignment assets and run basic validators (rf_id uniqueness). "
            "This job is intended for CI and lightweight validation runs."
        ),
    )
else:
    # Fallback placeholder job for environments where assets couldn't be imported.
    # This allows repository introspection without failing import in constrained environments.
    uspto_validation_job = build_assets_job(
        name="uspto_validation_job_placeholder",
        assets=[],
        description="Placeholder job (USPTO assets unavailable at import time).",
    )


# For convenience, expose a stable name that repository scaffolding can import.
__all__ = ["uspto_validation_job"]
