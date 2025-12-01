"""Minimal Dagster definitions for serverless deployment.

This module loads only essential assets explicitly to avoid the overhead
of auto-discovering and importing 55+ asset modules. For full pipeline
capabilities, use src.definitions_core in hybrid deployments.

Why minimal?
- Auto-discovery loads 55+ Python files at startup (7+ minute timeout)
- Serverless has strict startup time limits
- This loads only critical SBIR ingestion assets for fast startup
"""

import os

# CRITICAL: Set this BEFORE any src imports to prevent heavy modules from loading
os.environ["DAGSTER_LOAD_HEAVY_ASSETS"] = "false"

from dagster import Definitions, define_asset_job, load_assets_from_modules

# Import only the specific lightweight module we need
from src.assets import sbir_ingestion
from src.assets.sensors.s3_data_sensor import s3_sbir_data_sensor

# Load assets from the sbir_ingestion module
all_assets = load_assets_from_modules([sbir_ingestion])

# Define the sbir_ingestion_job for the sensor to target
sbir_ingestion_job = define_asset_job(
    name="sbir_ingestion_job",
    selection="*",  # All assets in this minimal deployment
    description="SBIR data ingestion and validation pipeline",
)

# Create minimal definitions with core SBIR ingestion + S3 sensor
defs = Definitions(
    assets=all_assets,
    jobs=[sbir_ingestion_job],
    schedules=[],
    sensors=[s3_sbir_data_sensor],
)
