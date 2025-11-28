"""Minimal Dagster definitions for serverless deployment.

This module provides an empty Definitions object to ensure fast startup times
for Dagster Cloud serverless deployments.

Why empty?
- Even minimal asset imports (e.g., sbir_ingestion) pull in heavy dependencies
  like pandas, which can take 10+ minutes to load in serverless environments
- Serverless has strict startup time limits (615s timeout observed)
- This empty definitions file starts in <5 seconds
- For full pipeline capabilities, use src.definitions_core in hybrid deployments
  or self-hosted Dagster instances

IMPORTANT: This file intentionally contains NO asset imports to minimize
startup time. Asset imports trigger module-level imports of pandas, boto3,
and other heavy libraries that cause serverless timeouts.
"""

import os
from dagster import Definitions

# Set environment variable to skip heavy assets
os.environ["DAGSTER_LOAD_HEAVY_ASSETS"] = "false"

# Create empty definitions for ultra-fast serverless startup
# Assets, jobs, schedules, and sensors are managed in hybrid deployments
# or via GitHub Actions workflows (see .github/workflows/run-ml-jobs.yml)
defs = Definitions(
    assets=[],
    jobs=[],
    schedules=[],
    sensors=[],
)
