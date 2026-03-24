"""Dagster definitions for core SBIR ETL pipeline.

This module contains core ETL assets:
- Data ingestion (SBIR, USAspending, USPTO)
- Data enrichment and validation
- Neo4j graph loading
- Transition analysis
- M&A detection

Heavy ML/fiscal assets are in definitions_ml.py and run via AWS Batch.
"""

import os
from typing import Any

from dagster import (
    AssetSelection,
    Definitions,
    ScheduleDefinition,
    define_asset_job,
    load_asset_checks_from_modules,
    load_assets_from_modules,
)

# Force skipping heavy assets in this location
os.environ["DAGSTER_LOAD_HEAVY_ASSETS"] = "false"

from . import assets as assets_pkg

# Load all assets and checks from modules (heavy ones will be skipped)
asset_modules = assets_pkg.iter_asset_modules()
all_assets = load_assets_from_modules(asset_modules)
all_asset_checks = load_asset_checks_from_modules(asset_modules)


def _discover_jobs() -> dict[str, Any]:
    """Discover job definitions exposed under src.assets.jobs."""
    return {job.name: job for job in assets_pkg.iter_public_jobs()}


def _discover_sensors() -> list[Any]:
    """Discover sensors exposed under src.assets.sensors."""
    return list(assets_pkg.iter_public_sensors())


def _get_job(job_name: str) -> Any:
    """Get a job by name from auto-discovered jobs."""
    return auto_jobs.get(job_name)


auto_jobs = _discover_jobs()

# Get the consolidated SBIR job (now includes enrichment)
sbir_weekly_refresh_job = _get_job("sbir_weekly_refresh_job")

# Define a job that materializes all core assets
core_etl_job = define_asset_job(
    name="sbir_core_etl_job",
    selection=AssetSelection.all(),
    description="Core SBIR ETL pipeline (lightweight assets only)",
)

# Daily schedule for core ETL
daily_schedule = ScheduleDefinition(
    job=core_etl_job,
    cron_schedule=os.getenv("SBIR_ETL__DAGSTER__SCHEDULES__CORE_ETL_JOB", "0 2 * * *"),
    name="daily_sbir_core_etl",
    description="Daily core SBIR ETL pipeline execution",
)

# Load sensors
all_sensors = _discover_sensors()

# Aggregate jobs
job_definitions: list[Any] = [
    core_etl_job,
]
# Add the consolidated SBIR job if available
if sbir_weekly_refresh_job is not None:
    job_definitions.append(sbir_weekly_refresh_job)
# Add auto-discovered jobs (ML jobs won't be discovered due to DAGSTER_LOAD_HEAVY_ASSETS=false)
job_definitions.extend(job for job in auto_jobs.values() if job not in job_definitions)

# Create the definitions object
defs = Definitions(
    assets=all_assets,
    asset_checks=all_asset_checks,
    jobs=job_definitions,
    schedules=[daily_schedule],
    sensors=all_sensors,
)
