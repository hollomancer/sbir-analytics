"""Primary Dagster code-location entry point for the SBIR pipeline."""

from .definitions_factory import (
    _HOST_SCHEDULES as FACTORY_HOST_SCHEDULES,
    build_definitions,
    schedule_status,
)


_bundle = build_definitions("primary")
_HOST_SCHEDULES = FACTORY_HOST_SCHEDULES

# Keep the existing module-level operator and test surface stable.
defs = _bundle.defs
asset_modules = _bundle.asset_modules
all_assets = _bundle.all_assets
all_asset_checks = _bundle.all_asset_checks
auto_jobs = _bundle.auto_jobs
all_sensors = _bundle.all_sensors
job_definitions = _bundle.job_definitions
schedules = _bundle.schedules
source_download_schedules = _bundle.source_download_schedules
research_release_schedules = _bundle.research_release_schedules
_heavy_keys = _bundle.heavy_asset_keys
core_refresh_job = _bundle.core_refresh_job
cet_drift_job = _bundle.cet_drift_job
cet_full_pipeline_job = _bundle.cet_full_pipeline_job

# Backward-compatible private name used by focused schedule tests.
_schedule_status = schedule_status
