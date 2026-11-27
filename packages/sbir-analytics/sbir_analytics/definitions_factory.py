"""Build the supported Dagster definition profiles from one registration path.

Epistemic tier: pipelines. This module registers operational assets without
changing their underlying evidence tier.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Sequence
from dataclasses import dataclass
from types import ModuleType
from typing import Any, Literal

from dagster import (
    AssetSelection,
    DefaultScheduleStatus,
    Definitions,
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

from sbir_etl.config.loader import env_bool

from . import assets as assets_pkg


LOG = logging.getLogger(__name__)
EPISTEMIC_TIER = "pipelines"
DefinitionProfile = Literal["primary", "heavy"]
DiscoveredJob = JobDefinition | UnresolvedAssetJobDefinition

_HOST_SCHEDULES = (
    (
        "sbir_awards_download_job",
        "weekly_sbir_awards_download",
        "0 9 * * 1",
        "SBIR awards download",
    ),
    (
        "sam_gov_download_job",
        "monthly_sam_gov_download",
        "0 3 15 * *",
        "SAM.gov entities download",
    ),
    (
        "usaspending_download_job",
        "monthly_usaspending_download",
        "0 2 6 * *",
        "USAspending dump download",
    ),
    (
        "uspto_download_job",
        "monthly_uspto_download",
        "0 9 1 * *",
        "USPTO datasets download",
    ),
    (
        "phase_transition_latency_job",
        "monthly_phase_transition",
        "0 14 1 * *",
        "Phase II->III transition latency analysis",
    ),
    (
        "weekly_awards_report_job",
        "weekly_awards_report",
        "0 12 * * 1",
        "Weekly SBIR awards report",
    ),
)


@dataclass(frozen=True)
class DefinitionBundle:
    """Definitions plus the registrations exposed for tests and operators."""

    defs: Definitions
    asset_modules: list[ModuleType]
    all_assets: Sequence[Any]
    all_asset_checks: Sequence[Any]
    auto_jobs: dict[str, DiscoveredJob]
    all_sensors: list[SensorDefinition]
    job_definitions: list[DiscoveredJob]
    schedules: list[ScheduleDefinition]
    source_download_schedules: list[ScheduleDefinition]
    research_release_schedules: list[ScheduleDefinition]
    heavy_asset_keys: set[Any]
    core_refresh_job: DiscoveredJob | None
    cet_drift_job: DiscoveredJob | None
    cet_full_pipeline_job: DiscoveredJob | None


def schedule_status(env_var: str, *, default_running: bool) -> DefaultScheduleStatus:
    """Resolve a schedule's default status from an environment toggle."""

    enabled = env_bool(env_var, default_running)
    return DefaultScheduleStatus.RUNNING if enabled else DefaultScheduleStatus.STOPPED


def _discover_jobs(*, load_heavy: bool, all_assets: Sequence[Any]) -> dict[str, DiscoveredJob]:
    jobs: dict[str, DiscoveredJob] = {}
    for job in assets_pkg.iter_public_jobs(load_heavy=load_heavy):
        if not load_heavy and isinstance(job, UnresolvedAssetJobDefinition):
            try:
                job.selection.resolve(all_assets)
            except DagsterInvalidSubsetError as exc:
                LOG.info("Skipping job %s because its assets are not loaded: %s", job.name, exc)
                continue
        jobs[job.name] = job
    return jobs


def _heavy_asset_keys(asset_modules: Sequence[ModuleType]) -> set[Any]:
    heavy_modules = [
        module
        for module in asset_modules
        if module.__name__.startswith(assets_pkg.HEAVY_ASSET_PREFIXES)
    ]
    if not heavy_modules:
        return set()
    return {asset.key for asset in load_assets_from_modules(heavy_modules) if hasattr(asset, "key")}


def _build_primary_bundle(*, load_heavy: bool) -> DefinitionBundle:
    asset_modules = assets_pkg.iter_asset_modules(load_heavy=load_heavy)
    all_assets = load_assets_from_modules(asset_modules)
    all_asset_checks = load_asset_checks_from_modules(asset_modules)
    auto_jobs = _discover_jobs(load_heavy=load_heavy, all_assets=all_assets)

    def get_job(name: str) -> DiscoveredJob | None:
        return auto_jobs.get(name)

    cet_full_pipeline_job = get_job("cet_full_pipeline_job")
    heavy_keys = _heavy_asset_keys(asset_modules)
    core_refresh_job = define_asset_job(
        name="core_refresh_job",
        selection=(
            AssetSelection.all() - AssetSelection.assets(*heavy_keys)
            if heavy_keys
            else AssetSelection.all()
        ),
        description="Weekly refresh of core (non-heavy) SBIR assets",
    )
    weekly_core_refresh_schedule = ScheduleDefinition(
        job=core_refresh_job,
        cron_schedule=os.getenv(
            "SBIR_ETL__DAGSTER__SCHEDULES__WEEKLY_CORE_REFRESH_JOB", "0 3 * * 0"
        ),
        name="weekly_core_refresh",
        description="Weekly core asset refresh (server profile; disabled by default)",
        default_status=schedule_status(
            "SBIR_ETL__DAGSTER__SCHEDULES__WEEKLY_CORE_REFRESH_ENABLED",
            default_running=False,
        ),
    )

    cet_drift_job = None
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

    source_download_schedules: list[ScheduleDefinition] = []
    for job_name, schedule_name, default_cron, label in _HOST_SCHEDULES:
        discovered = get_job(job_name)
        if discovered is None:
            LOG.warning("Job %s not discovered; skipping schedule", job_name)
            continue
        env_suffix = schedule_name.upper()
        source_download_schedules.append(
            ScheduleDefinition(
                job=discovered,
                cron_schedule=os.getenv(
                    f"SBIR_ETL__DAGSTER__SCHEDULES__{env_suffix}_CRON", default_cron
                ),
                name=schedule_name,
                description=f"Scheduled {label} on this host",
                default_status=schedule_status(
                    f"SBIR_ETL__DAGSTER__SCHEDULES__{env_suffix}_ENABLED",
                    default_running=False,
                ),
            )
        )

    research_release_schedules: list[ScheduleDefinition] = []
    lineage_job = get_job("nsf_defense_lineage_refresh_job")
    if lineage_job is None:
        LOG.warning("Job nsf_defense_lineage_refresh_job not discovered; skipping schedule")
    else:
        research_release_schedules.append(
            ScheduleDefinition(
                job=lineage_job,
                cron_schedule=os.getenv(
                    "SBIR_ETL__DAGSTER__SCHEDULES__MONTHLY_NSF_DEFENSE_LINEAGE_REFRESH_CRON",
                    "0 5 8 * *",
                ),
                name="monthly_nsf_defense_lineage_refresh",
                description="Scheduled NSF SBIR to DoD funding-lineage research release",
                default_status=schedule_status(
                    "SBIR_ETL__DAGSTER__SCHEDULES__MONTHLY_NSF_DEFENSE_LINEAGE_REFRESH_ENABLED",
                    default_running=False,
                ),
            )
        )

    schedules = [
        weekly_core_refresh_schedule,
        *source_download_schedules,
        *research_release_schedules,
    ]

    all_sensors = assets_pkg.iter_public_sensors()
    job_definitions: list[DiscoveredJob] = [core_refresh_job]
    if cet_drift_job is not None:
        job_definitions.append(cet_drift_job)
    job_definitions.extend(job for job in auto_jobs.values() if job not in job_definitions)

    defs = Definitions(
        assets=all_assets,
        asset_checks=all_asset_checks,
        jobs=job_definitions,
        schedules=schedules,
        sensors=all_sensors,
    )
    return DefinitionBundle(
        defs=defs,
        asset_modules=asset_modules,
        all_assets=all_assets,
        all_asset_checks=all_asset_checks,
        auto_jobs=auto_jobs,
        all_sensors=all_sensors,
        job_definitions=job_definitions,
        schedules=schedules,
        source_download_schedules=source_download_schedules,
        research_release_schedules=research_release_schedules,
        heavy_asset_keys=heavy_keys,
        core_refresh_job=core_refresh_job,
        cet_drift_job=cet_drift_job,
        cet_full_pipeline_job=cet_full_pipeline_job,
    )


def build_definitions(profile: DefinitionProfile) -> DefinitionBundle:
    """Build a supported Dagster code-location profile.

    ``primary`` honors ``DAGSTER_LOAD_HEAVY_ASSETS``. ``heavy`` builds the same
    definitions with the heavy modules always loaded.
    """

    if profile == "primary":
        return _build_primary_bundle(load_heavy=assets_pkg.should_load_heavy_assets())
    if profile == "heavy":
        return _build_primary_bundle(load_heavy=True)
    raise ValueError(f"Unknown Dagster definition profile: {profile!r}")
