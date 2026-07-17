"""Dagster definitions for SBIR ETL pipeline."""

import logging
import os

from dagster import (
    AssetSelection,
    Definitions,
    DefaultScheduleStatus,
    JobDefinition,
    ScheduleDefinition,
    SensorDefinition,
    define_asset_job,
    load_asset_checks_from_modules,
    load_assets_from_modules,
)
from dagster._core.definitions.unresolved_asset_job_definition import (
    UnresolvedAssetJobDefinition,
)
from dagster._core.errors import DagsterInvalidSubsetError

from . import assets as assets_pkg


LOG = logging.getLogger(__name__)
DiscoveredJob = JobDefinition | UnresolvedAssetJobDefinition


def _schedule_status(env_var: str, *, default_running: bool) -> DefaultScheduleStatus:
    """Resolve a schedule's default status from an environment toggle.

    Server deployments gate schedules off by default so the always-on stack
    never launches expensive materializations without an explicit opt-in.
    """
    raw = os.getenv(env_var, "true" if default_running else "false").strip().lower()
    enabled = raw in ("true", "1", "yes", "on")
    return DefaultScheduleStatus.RUNNING if enabled else DefaultScheduleStatus.STOPPED


# Load all assets and checks from modules
asset_modules = assets_pkg.iter_asset_modules()
all_assets = load_assets_from_modules(asset_modules)
all_asset_checks = load_asset_checks_from_modules(asset_modules)


def _discover_jobs() -> dict[str, DiscoveredJob]:
    """Discover job definitions exposed under src.assets.jobs."""

    jobs: dict[str, DiscoveredJob] = {}
    load_heavy = assets_pkg.should_load_heavy_assets()
    for job in assets_pkg.iter_public_jobs():
        if not load_heavy and isinstance(job, UnresolvedAssetJobDefinition):
            try:
                job.selection.resolve(all_assets)
            except DagsterInvalidSubsetError as exc:
                LOG.info("Skipping job %s because its assets are not loaded: %s", job.name, exc)
                continue
        jobs[job.name] = job
    return jobs


def _discover_sensors() -> list[SensorDefinition]:
    """Discover sensors exposed under src.assets.sensors."""

    return list(assets_pkg.iter_public_sensors())


auto_jobs = _discover_jobs()


def _get_job(name: str) -> DiscoveredJob | None:
    """Retrieve a named job or return None if it is missing."""
    return auto_jobs.get(name)


# Try to get CET jobs (may not be available if heavy assets are skipped)
cet_full_pipeline_job = _get_job("cet_full_pipeline_job")

# Define a job that materializes all assets
etl_job = define_asset_job(
    name="sbir_analytics_job",
    selection=AssetSelection.all(),
    description="Complete SBIR ETL pipeline execution",
)

# Define a schedule to run the job daily.
#
# The heavy daily all-assets schedule is gated so the always-on server profile
# does not launch it automatically. It defaults to RUNNING (unchanged behavior
# for dev/local) unless SBIR_ETL__DAGSTER__SCHEDULES__DAILY_ALL_ASSETS_ENABLED
# is set to a falsey value (the server template sets it to "false").
daily_schedule = ScheduleDefinition(
    job=etl_job,
    cron_schedule=os.getenv(
        "SBIR_ETL__DAGSTER__SCHEDULES__ETL_JOB", "0 2 * * *"
    ),  # Default 02:00 UTC; override via SBIR_ETL__DAGSTER__SCHEDULES__ETL_JOB
    name="daily_sbir_analytics",
    description="Daily SBIR ETL pipeline execution",
    default_status=_schedule_status(
        "SBIR_ETL__DAGSTER__SCHEDULES__DAILY_ALL_ASSETS_ENABLED",
        default_running=True,
    ),
)

# Opt-in weekly core refresh for the server profile. It materializes the core
# (non-heavy) assets currently loaded — heavy ML/fiscal/NLP modules are excluded
# via DAGSTER_LOAD_HEAVY_ASSETS=false on the server. It stays STOPPED until an
# operator confirms a manual run succeeds and flips the env toggle on.
core_refresh_job = define_asset_job(
    name="core_refresh_job",
    selection=AssetSelection.all(),
    description="Weekly refresh of core (non-heavy) SBIR assets",
)

weekly_core_refresh_schedule = ScheduleDefinition(
    job=core_refresh_job,
    cron_schedule=os.getenv(
        "SBIR_ETL__DAGSTER__SCHEDULES__WEEKLY_CORE_REFRESH_JOB", "0 3 * * 0"
    ),  # Default Sundays 03:00 UTC
    name="weekly_core_refresh",
    description="Weekly core asset refresh (server profile; disabled by default)",
    default_status=_schedule_status(
        "SBIR_ETL__DAGSTER__SCHEDULES__WEEKLY_CORE_REFRESH_ENABLED",
        default_running=False,
    ),
)

# Define CET drift job only if ML assets are available
cet_drift_job = None
# Check if the drift detection asset exists before creating job
drift_asset_exists = any(
    hasattr(asset, "key") and asset.key.path == ["ml", "validated_cet_drift_detection"]
    for asset in all_assets
)
if drift_asset_exists:
    cet_drift_job = define_asset_job(
        name="cet_drift_job",
        selection=AssetSelection.keys(["ml", "validated_cet_drift_detection"]),
        description="Run CET drift detection asset",
    )

# Create schedules only for available jobs
schedules = [daily_schedule, weekly_core_refresh_schedule]

if cet_full_pipeline_job is not None:
    cet_full_pipeline_schedule = ScheduleDefinition(
        job=cet_full_pipeline_job,
        cron_schedule=os.getenv("SBIR_ETL__DAGSTER__SCHEDULES__CET_FULL_PIPELINE_JOB", "0 2 * * *"),
        name="daily_cet_full_pipeline",
        description="Daily CET full pipeline end-to-end execution",
    )
    schedules.append(cet_full_pipeline_schedule)

if cet_drift_job is not None:
    cet_drift_schedule = ScheduleDefinition(
        job=cet_drift_job,
        cron_schedule=os.getenv("SBIR_ETL__DAGSTER__SCHEDULES__CET_DRIFT_JOB", "0 6 * * *"),
        name="daily_cet_drift_detection",
        description="Daily CET drift detection and alerting",
    )
    schedules.append(cet_drift_schedule)

# Load sensors automatically
all_sensors = _discover_sensors()

# Aggregate jobs for repository registration
job_definitions: list[DiscoveredJob] = [etl_job, core_refresh_job]
# Add conditional jobs if they exist
if cet_drift_job is not None:
    job_definitions.append(cet_drift_job)

# Add auto-discovered jobs that aren't already in the list
job_definitions.extend(job for job in auto_jobs.values() if job not in job_definitions)

# Create the definitions object
defs = Definitions(
    assets=all_assets,
    asset_checks=all_asset_checks,
    jobs=job_definitions,
    schedules=schedules,  # Use conditional schedules list
    sensors=all_sensors,
)
