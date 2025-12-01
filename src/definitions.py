"""Dagster definitions for SBIR ETL pipeline."""

import os

from dagster import (
    AssetSelection,
    Definitions,
    JobDefinition,
    ScheduleDefinition,
    SensorDefinition,
    define_asset_job,
    load_asset_checks_from_modules,
    load_assets_from_modules,
)

from . import assets as assets_pkg


# Load all assets and checks from modules
asset_modules = assets_pkg.iter_asset_modules()
all_assets = load_assets_from_modules(asset_modules)
all_asset_checks = load_asset_checks_from_modules(asset_modules)


def _discover_jobs() -> dict[str, JobDefinition]:
    """Discover job definitions exposed under src.assets.jobs."""

    return {job.name: job for job in assets_pkg.iter_public_jobs()}


def _discover_sensors() -> list[SensorDefinition]:
    """Discover sensors exposed under src.assets.sensors."""

    return list(assets_pkg.iter_public_sensors())


auto_jobs = _discover_jobs()


def _get_job(name: str) -> JobDefinition | None:
    """Retrieve a named job or return None if it is missing."""
    return auto_jobs.get(name)


# Try to get CET jobs (may not be available if heavy assets are skipped)
cet_full_pipeline_job = _get_job("cet_full_pipeline_job")

# Define SBIR ingestion job (extraction + validation + enrichment)
sbir_ingestion_job = define_asset_job(
    name="sbir_ingestion_job",
    selection=AssetSelection.keys(
        "raw_sbir_awards",
        "validated_sbir_awards",
        "raw_usaspending_recipients",
        "enriched_sbir_awards",
    ),
    description="Extract, validate, and enrich SBIR awards data",
)

# Define a job that materializes all assets
etl_job = define_asset_job(
    name="sbir_analytics_job",
    selection=AssetSelection.all(),
    description="Complete SBIR ETL pipeline execution",
)

# Define a schedule to run the job daily
daily_schedule = ScheduleDefinition(
    job=etl_job,
    cron_schedule=os.getenv(
        "SBIR_ETL__DAGSTER__SCHEDULES__ETL_JOB", "0 2 * * *"
    ),  # Default 02:00 UTC; override via SBIR_ETL__DAGSTER__SCHEDULES__ETL_JOB
    name="daily_sbir_analytics",
    description="Daily SBIR ETL pipeline execution",
)

# Define CET drift job only if ML assets are available
cet_drift_job = None
# Check if the drift detection asset exists before creating job
drift_asset_exists = any(
    hasattr(asset, "key") and asset.key.path == ["ml", "validated_cet_drift_detection"]
    for asset in all_assets
)
if drift_asset_exists:
    cet_drift_job = define_asset_job(
        name="cet_drift_job",
        selection=AssetSelection.keys(["ml", "validated_cet_drift_detection"]),
        description="Run CET drift detection asset",
    )

# Create schedules only for available jobs
schedules = [daily_schedule]  # Always include daily schedule

if cet_full_pipeline_job is not None:
    cet_full_pipeline_schedule = ScheduleDefinition(
        job=cet_full_pipeline_job,
        cron_schedule=os.getenv("SBIR_ETL__DAGSTER__SCHEDULES__CET_FULL_PIPELINE_JOB", "0 2 * * *"),
        name="daily_cet_full_pipeline",
        description="Daily CET full pipeline end-to-end execution",
    )
    schedules.append(cet_full_pipeline_schedule)

if cet_drift_job is not None:
    cet_drift_schedule = ScheduleDefinition(
        job=cet_drift_job,
        cron_schedule=os.getenv("SBIR_ETL__DAGSTER__SCHEDULES__CET_DRIFT_JOB", "0 6 * * *"),
        name="daily_cet_drift_detection",
        description="Daily CET drift detection and alerting",
    )
    schedules.append(cet_drift_schedule)

# Load sensors automatically
all_sensors = _discover_sensors()

# Aggregate jobs for repository registration
job_definitions: list[JobDefinition] = [
    sbir_ingestion_job,  # type: ignore[list-item]
    etl_job,  # type: ignore[list-item]
]
# Add conditional jobs if they exist
if cet_drift_job is not None:
    job_definitions.append(cet_drift_job)  # type: ignore[arg-type]

# Add auto-discovered jobs that aren't already in the list
job_definitions.extend(job for job in auto_jobs.values() if job not in job_definitions)

# Create the definitions object
defs = Definitions(
    assets=all_assets,
    asset_checks=all_asset_checks,
    jobs=job_definitions,
    schedules=schedules,  # Use conditional schedules list
    sensors=all_sensors,
)
