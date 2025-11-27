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
from dagster import Definitions

# Set environment variable to skip heavy assets
os.environ["DAGSTER_LOAD_HEAVY_ASSETS"] = "false"

# Import only essential lightweight assets explicitly
# These are the core SBIR data ingestion assets
from src.assets.sbir_ingestion import (
    raw_sbir_awards,
    validated_sbir_awards,
    sbir_validation_report,
)

# Create minimal definitions with just core SBIR ingestion
defs = Definitions(
    assets=[
        raw_sbir_awards,
        validated_sbir_awards,
        sbir_validation_report,
    ],
    jobs=[],
    schedules=[],
    sensors=[],
)
