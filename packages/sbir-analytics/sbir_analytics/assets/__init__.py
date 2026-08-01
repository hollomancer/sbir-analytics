"""Helpers for discovering SBIR ETL asset modules and Dagster registrations."""

from __future__ import annotations

import importlib
import logging
import os
from collections.abc import Iterator, Sequence
from functools import lru_cache
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from dagster import JobDefinition, SensorDefinition

LOG = logging.getLogger(__name__)


# Asset families excluded from resource-constrained environments. Prefixes are
# used because several families span packages rather than a single module.
HEAVY_ASSET_PREFIXES = (
    "sbir_analytics.assets.cet",
    "sbir_analytics.assets.fiscal_assets",
    "sbir_analytics.assets.sbir_fiscal_impacts",
    "sbir_analytics.assets.modernbert",
    "sbir_analytics.assets.uspto.ai_extraction",
)

# Jobs whose selections depend on one or more heavy asset modules above.  Job
# discovery must apply the same deployment gate as asset discovery; otherwise
# Dagster tries to resolve selections for assets that were intentionally left
# out of the server repository.
HEAVY_JOB_MODULES = {
    "sbir_analytics.assets.jobs.cet_pipeline_job",
    "sbir_analytics.assets.jobs.fiscal_returns_job",
    "sbir_analytics.assets.jobs.modernbert_job",
    "sbir_analytics.assets.jobs.uspto_ai_job",
}


def _iter_modules(
    package: ModuleType,
    *,
    skip_prefixes: Sequence[str] = (),
) -> Iterator[str]:
    """Yield fully qualified module names for a package tree."""

    module_names: set[str] = set()
    for package_path in package.__path__:
        root = Path(package_path)
        for module_path in root.rglob("*.py"):
            if module_path.name == "__init__.py":
                continue
            relative = module_path.relative_to(root).with_suffix("")
            module_name = f"{package.__name__}.{'.'.join(relative.parts)}"
            if any(module_name.startswith(skip) for skip in skip_prefixes):
                continue
            module_names.add(module_name)
    yield from sorted(module_names)


def _safe_import(module_name: str) -> ModuleType | None:
    """Import a module, logging and skipping failures."""

    try:
        return importlib.import_module(module_name)
    except Exception as exc:  # pragma: no cover - defensive
        LOG.warning("Failed to import %s: %s", module_name, exc)
        return None


def should_load_heavy_assets() -> bool:
    """Check if heavy assets should be loaded based on environment."""
    # Load heavy assets by default (local/hybrid), skip in serverless mode
    env_value = os.getenv("DAGSTER_LOAD_HEAVY_ASSETS", "true").lower()
    return env_value in ("true", "1", "yes")


@lru_cache(maxsize=1)
def _asset_module_names() -> tuple[str, ...]:
    package = importlib.import_module(__name__)
    skip = (
        f"{__name__}.jobs",
        f"{__name__}.sensors",
    )
    return tuple(_iter_modules(package, skip_prefixes=skip))


def iter_asset_modules() -> list[ModuleType]:
    """Return all asset modules (excluding jobs/sensors).

    Skips heavy asset modules in resource-constrained environments
    based on DAGSTER_LOAD_HEAVY_ASSETS environment variable.
    """
    load_heavy = should_load_heavy_assets()

    modules: list[ModuleType] = []
    for module_name in _asset_module_names():
        # Skip heavy modules if configured
        if not load_heavy and any(
            module_name == prefix or module_name.startswith(f"{prefix}.")
            for prefix in HEAVY_ASSET_PREFIXES
        ):
            LOG.info(
                "Skipping heavy asset module (DAGSTER_LOAD_HEAVY_ASSETS=false): %s", module_name
            )
            continue

        module = _safe_import(module_name)
        if module:
            modules.append(module)
    return modules


@lru_cache(maxsize=1)
def _job_module_names() -> tuple[str, ...]:
    package = importlib.import_module(f"{__name__}.jobs")
    return tuple(_iter_modules(package))


def iter_job_modules() -> list[ModuleType]:
    load_heavy = should_load_heavy_assets()
    modules: list[ModuleType] = []
    for module_name in _job_module_names():
        if not load_heavy and module_name in HEAVY_JOB_MODULES:
            LOG.info(
                "Skipping heavy job module (DAGSTER_LOAD_HEAVY_ASSETS=false): %s",
                module_name,
            )
            continue
        module = _safe_import(module_name)
        if module:
            modules.append(module)
    return modules


@lru_cache(maxsize=1)
def _sensor_module_names() -> tuple[str, ...]:
    try:
        package = importlib.import_module(f"{__name__}.sensors")
    except ModuleNotFoundError:
        return ()
    return tuple(_iter_modules(package))


def iter_sensor_modules() -> list[ModuleType]:
    modules: list[ModuleType] = []
    for module_name in _sensor_module_names():
        module = _safe_import(module_name)
        if module:
            modules.append(module)
    return modules


def iter_public_jobs() -> list[JobDefinition]:
    from dagster import JobDefinition  # Imported lazily
    from dagster._core.definitions.unresolved_asset_job_definition import (
        UnresolvedAssetJobDefinition,
    )

    jobs: list[JobDefinition] = []
    for module in iter_job_modules():
        for value in vars(module).values():
            if isinstance(value, JobDefinition | UnresolvedAssetJobDefinition):
                jobs.append(value)  # type: ignore[arg-type]
    return jobs


def iter_public_sensors() -> list[SensorDefinition]:
    from dagster import SensorDefinition  # Imported lazily

    sensors: list[SensorDefinition] = []
    for module in iter_sensor_modules():
        for value in vars(module).values():
            if isinstance(value, SensorDefinition):
                sensors.append(value)
    return sensors


__all__ = [
    "iter_asset_modules",
    "iter_job_modules",
    "iter_sensor_modules",
    "iter_public_jobs",
    "iter_public_sensors",
    "should_load_heavy_assets",
]
