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

# Define SBIR ingestion job (just the ingestion assets)
sbir_ingestion_job = define_asset_job(
    name="sbir_ingestion_job",
    selection=AssetSelection.groups("sbir_ingestion"),
    description="Extract, validate, and prepare SBIR awards data",
)

# Define a job that materializes all assets
etl_job = define_asset_job(
    name="sbir_etl_job",
    selection=AssetSelection.all(),
    description="Complete SBIR ETL pipeline execution",
)

# Define a schedule to run the job daily
daily_schedule = ScheduleDefinition(
    job=etl_job,
    cron_schedule=os.getenv(
        "SBIR_ETL__DAGSTER__SCHEDULES__ETL_JOB", "0 2 * * *"
    ),  # Default 02:00 UTC; override via SBIR_ETL__DAGSTER__SCHEDULES__ETL_JOB
    name="daily_sbir_etl",
    description="Daily SBIR ETL pipeline execution",
)

# Define a small asset job to run the CET drift detection asset
cet_drift_job = define_asset_job(
    name="cet_drift_job",
    selection=AssetSelection.keys(["ml", "validated_cet_drift_detection"]),
    description="Run CET drift detection asset",
)

# Schedule CET full pipeline daily (02:00 UTC by default) and drift detection (06:00 UTC)
cet_full_pipeline_schedule = ScheduleDefinition(
    job=cet_full_pipeline_job,
    cron_schedule=os.getenv(
        "SBIR_ETL__DAGSTER__SCHEDULES__CET_FULL_PIPELINE_JOB", "0 2 * * *"
    ),  # Default 02:00 UTC; override via SBIR_ETL__DAGSTER__SCHEDULES__CET_FULL_PIPELINE_JOB
    name="daily_cet_full_pipeline",
    description="Daily CET full pipeline end-to-end execution",
)
cet_drift_schedule = ScheduleDefinition(
    job=cet_drift_job,
    cron_schedule=os.getenv(
        "SBIR_ETL__DAGSTER__SCHEDULES__CET_DRIFT_JOB", "0 6 * * *"
    ),  # Default 06:00 UTC; override via SBIR_ETL__DAGSTER__SCHEDULES__CET_DRIFT_JOB
    name="daily_cet_drift_detection",
    description="Daily CET drift detection and alerting",
)

def _job_lookup() -> dict[str, JobDefinition]:
    """Build a lookup table for auto-discovered jobs."""

    return {job.name: job for job in assets_pkg.iter_public_jobs()}


def _sensor_lookup() -> list[SensorDefinition]:
    """Return auto-discovered sensors."""

    return list(assets_pkg.iter_public_sensors())


auto_jobs = _job_lookup()

cet_full_pipeline_job = auto_jobs.get("cet_full_pipeline_job")
transition_mvp_job = auto_jobs.get("transition_mvp_job")
transition_full_job = auto_jobs.get("transition_full_job")
transition_analytics_job = auto_jobs.get("transition_analytics_job")
usaspending_iterative_enrichment_job = auto_jobs.get("usaspending_iterative_enrichment_job")
fiscal_returns_mvp_job = auto_jobs.get("fiscal_returns_mvp_job")
fiscal_returns_full_job = auto_jobs.get("fiscal_returns_full_job")

if cet_full_pipeline_job is None:
    raise RuntimeError("cet_full_pipeline_job not found during auto-discovery")

# Load sensors automatically
all_sensors = _sensor_lookup()

# Aggregate jobs for repository registration
job_definitions: list[JobDefinition] = [
    sbir_ingestion_job,
    etl_job,
    cet_drift_job,
]
job_definitions.extend(job for job in auto_jobs.values() if job not in job_definitions)

# Create the definitions object
defs = Definitions(
    assets=all_assets,
    asset_checks=all_asset_checks,
    jobs=job_definitions,
    schedules=[daily_schedule, cet_full_pipeline_schedule, cet_drift_schedule],
    sensors=all_sensors,
)
