"""Dagster definitions for SBIR ETL pipeline."""

from dagster import (
    AssetSelection,
    Definitions,
    ScheduleDefinition,
    define_asset_job,
    load_asset_checks_from_modules,
    load_assets_from_modules,
)

from . import assets
from .assets import (
    sbir_ingestion,
    usaspending_ingestion,
    sbir_usaspending_enrichment,
    uspto_assets,
    uspto_validation_assets,
    uspto_transformation_assets,
)
from .assets.jobs.cet_pipeline_job import cet_full_pipeline_job

# Load all assets and checks from modules
all_assets = load_assets_from_modules(
    [
        assets,
        sbir_ingestion,
        usaspending_ingestion,
        sbir_usaspending_enrichment,
        uspto_assets,
        uspto_validation_assets,
        uspto_transformation_assets,
    ]
)
all_asset_checks = load_asset_checks_from_modules(
    [sbir_ingestion, uspto_assets, uspto_validation_assets, uspto_transformation_assets]
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
    cron_schedule="0 2 * * *",  # Run at 2 AM daily
    name="daily_sbir_etl",
    description="Daily SBIR ETL pipeline execution",
)

# Create the definitions object
defs = Definitions(
    assets=all_assets,
    asset_checks=all_asset_checks,
    jobs=[sbir_ingestion_job, etl_job, cet_full_pipeline_job],
    schedules=[daily_schedule],
)
