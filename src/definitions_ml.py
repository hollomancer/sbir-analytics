"""Dagster definitions for ML and fiscal analysis pipeline (hybrid deployment).

This module contains only heavy ML and fiscal assets that require:
- scikit-learn (CET training, inference, drift detection)
- spaCy (USPTO AI extraction)
- sentence-transformers (PaECTER embeddings)
- R packages (fiscal impact analysis)

These run on your own compute (EC2, etc.) to avoid serverless timeouts.
"""

import os

from dagster import (
    Definitions,
    JobDefinition,
    ScheduleDefinition,
    load_asset_checks_from_modules,
    load_assets_from_modules,
)

# Force loading ALL assets in this location (including heavy ones)
os.environ["DAGSTER_LOAD_HEAVY_ASSETS"] = "true"

from . import assets as assets_pkg

# Load all assets and checks from modules
asset_modules = assets_pkg.iter_asset_modules()
all_assets = load_assets_from_modules(asset_modules)
all_asset_checks = load_asset_checks_from_modules(asset_modules)


def _discover_jobs() -> dict[str, JobDefinition]:
    """Discover job definitions exposed under src.assets.jobs."""
    return {job.name: job for job in assets_pkg.iter_public_jobs()}


def _discover_sensors() -> list[any]:
    """Discover sensors exposed under src.assets.sensors."""
    return list(assets_pkg.iter_public_sensors())


auto_jobs = _discover_jobs()


def _get_job(name: str) -> JobDefinition | None:
    """Retrieve a named job or return None if it is missing."""
    return auto_jobs.get(name)


# Get CET jobs (should be available since DAGSTER_LOAD_HEAVY_ASSETS=true)
cet_full_pipeline_job = _get_job("cet_full_pipeline_job")
fiscal_returns_mvp_job = _get_job("fiscal_returns_mvp_job")
paecter_job = _get_job("paecter_job")
uspto_ai_job = _get_job("uspto_ai_job")

# Create schedules for ML jobs
schedules = []

if cet_full_pipeline_job is not None:
    cet_full_pipeline_schedule = ScheduleDefinition(
        job=cet_full_pipeline_job,
        cron_schedule=os.getenv(
            "SBIR_ETL__DAGSTER__SCHEDULES__CET_FULL_PIPELINE_JOB", "0 3 * * *"
        ),
        name="daily_cet_full_pipeline",
        description="Daily CET ML pipeline end-to-end execution",
    )
    schedules.append(cet_full_pipeline_schedule)

if fiscal_returns_mvp_job is not None:
    fiscal_returns_schedule = ScheduleDefinition(
        job=fiscal_returns_mvp_job,
        cron_schedule=os.getenv(
            "SBIR_ETL__DAGSTER__SCHEDULES__FISCAL_RETURNS_JOB", "0 4 * * 1"
        ),  # Weekly on Monday
        name="weekly_fiscal_returns",
        description="Weekly fiscal returns analysis",
    )
    schedules.append(fiscal_returns_schedule)

# Load sensors
all_sensors = _discover_sensors()

# Aggregate ML jobs only
job_definitions: list[JobDefinition] = []
for job in auto_jobs.values():
    # Only include jobs that are ML/fiscal related
    if any(
        keyword in job.name.lower()
        for keyword in ["cet", "fiscal", "paecter", "uspto", "ml", "drift"]
    ):
        job_definitions.append(job)

# Create the definitions object
defs = Definitions(
    assets=all_assets,
    asset_checks=all_asset_checks,
    jobs=job_definitions,
    schedules=schedules,
    sensors=all_sensors,  # ML sensors if any
)
