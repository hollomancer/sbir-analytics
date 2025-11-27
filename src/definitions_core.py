"""Dagster definitions for core SBIR ETL pipeline (serverless-compatible).

This module contains only lightweight assets suitable for Dagster Cloud Serverless:
- Data ingestion (SBIR, USAspending, USPTO)
- Data enrichment and validation
- Neo4j graph loading
- Transition analysis
- M&A detection

Heavy ML/fiscal assets are excluded and run in the ML location instead.
"""

import os

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


def _discover_jobs() -> dict[str, any]:
    """Discover job definitions exposed under src.assets.jobs."""
    return {job.name: job for job in assets_pkg.iter_public_jobs()}


def _discover_sensors() -> list[any]:
    """Discover sensors exposed under src.assets.sensors."""
    return list(assets_pkg.iter_public_sensors())


auto_jobs = _discover_jobs()

# Define SBIR ingestion job (core ETL)
sbir_ingestion_job = define_asset_job(
    name="sbir_ingestion_job",
    selection=AssetSelection.groups("sbir_ingestion"),
    description="Extract, validate, and prepare SBIR awards data",
)

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
job_definitions: list[any] = [
    sbir_ingestion_job,
    core_etl_job,
]
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
