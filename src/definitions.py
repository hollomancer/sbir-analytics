"""Dagster definitions for SBIR ETL pipeline."""

from dagster import (
    AssetSelection,
    Definitions,
    ScheduleDefinition,
    define_asset_job,
    load_assets_from_modules,
)

from . import assets

# Load all assets from the assets module
all_assets = load_assets_from_modules([assets])

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
    jobs=[etl_job],
    schedules=[daily_schedule],
)
