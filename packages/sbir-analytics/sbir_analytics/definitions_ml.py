"""Heavy ML and fiscal Dagster code-location entry point."""

from .definitions_factory import build_definitions


_bundle = build_definitions("heavy")

defs = _bundle.defs
asset_modules = _bundle.asset_modules
all_assets = _bundle.all_assets
all_asset_checks = _bundle.all_asset_checks
auto_jobs = _bundle.auto_jobs
all_sensors = _bundle.all_sensors
job_definitions = _bundle.job_definitions
schedules = _bundle.schedules
cet_full_pipeline_job = _bundle.cet_full_pipeline_job
fiscal_returns_mvp_job = auto_jobs.get("fiscal_returns_mvp_job")
modernbert_job = auto_jobs.get("modernbert_job")
uspto_ai_job = auto_jobs.get("uspto_ai_extraction_job")
