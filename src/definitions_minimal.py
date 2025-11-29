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

from dagster import Definitions, load_assets_from_modules

# Import only the specific lightweight module we need
from src.assets import sbir_ingestion

# Load assets from the sbir_ingestion module
all_assets = load_assets_from_modules([sbir_ingestion])

# Create minimal definitions with just core SBIR ingestion
defs = Definitions(
    assets=all_assets,
    jobs=[],
    schedules=[],
    sensors=[],
)
