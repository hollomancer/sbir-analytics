"""Dagster definitions for SBIR ETL pipeline."""

import os

from dagster import (
    AssetSelection,
    Definitions,
    ScheduleDefinition,
    define_asset_job,
    load_asset_checks_from_modules,
    load_assets_from_modules,
    load_sensors_from_modules,
)

from . import assets
from .assets import (
    cet_assets,
    fiscal_assets,
    sbir_ingestion,
    sbir_usaspending_enrichment,
    transition_assets,
    usaspending_ingestion,
    usaspending_iterative_enrichment,
    uspto_assets,
)
from .assets.jobs.cet_pipeline_job import cet_full_pipeline_job
from .assets.jobs.transition_job import (
    transition_analytics_job,
    transition_full_job,
    transition_mvp_job,
)
from .assets.jobs.usaspending_iterative_job import usaspending_iterative_enrichment_job

# Load all assets and checks from modules
all_assets = load_assets_from_modules(
    [
        assets,
        fiscal_assets,
        sbir_ingestion,
        usaspending_ingestion,
        sbir_usaspending_enrichment,
        usaspending_iterative_enrichment,
        uspto_assets,
        cet_assets,
        transition_assets,
    ]
)
all_asset_checks = load_asset_checks_from_modules(
    [
        fiscal_assets,
        sbir_ingestion,
        usaspending_iterative_enrichment,
        uspto_assets,
        cet_assets,
        transition_assets,
    ]
)

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

# Load sensors
from .assets import sensors

all_sensors = load_sensors_from_modules([sensors])

# Create the definitions object
defs = Definitions(
    assets=all_assets,
    asset_checks=all_asset_checks,
    jobs=[
        sbir_ingestion_job,
        etl_job,
        cet_full_pipeline_job,
        cet_drift_job,
        transition_mvp_job,
        transition_full_job,
        transition_analytics_job,
        usaspending_iterative_enrichment_job,
    ],
    schedules=[daily_schedule, cet_full_pipeline_schedule, cet_drift_schedule],
    sensors=all_sensors,
)
