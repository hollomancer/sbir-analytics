"""Asset discovery utilities for SBIR ETL.

This package previously exposed a large lazy-import registry for all Dagster assets.
That approach required manual updates whenever a new asset module was added or renamed.
The helpers below provide automatic discovery for assets, asset checks, jobs, and sensors
so callers (primarily the Dagster repository definitions) can keep themselves in sync
with the actual package layout.
"""

from __future__ import annotations

import importlib
import logging
import pkgutil
from functools import lru_cache
from types import ModuleType
from typing import Iterable, Iterator, Sequence

LOG = logging.getLogger(__name__)


def _iter_package_modules(
    package: ModuleType,
    *,
    skip_prefixes: Sequence[str] = (),
) -> Iterator[str]:
    """Yield fully-qualified module names contained within a package."""

    prefix = package.__name__ + "."
    for module_info in pkgutil.walk_packages(package.__path__, prefix=prefix):
        if any(module_info.name.startswith(skip) for skip in skip_prefixes):
            continue
        yield module_info.name


def _safe_import(module_name: str) -> ModuleType | None:
    """Import a module and swallow errors with a log entry.

    Dagster repository loading should be resilient even if a subset of modules fails to import.
    """
    try:
        return importlib.import_module(module_name)
    except Exception as exc:  # pragma: no cover - defensive logging
        LOG.warning("Failed to import module %s: %s", module_name, exc)
        return None


@lru_cache(maxsize=1)
def _asset_module_names() -> tuple[str, ...]:
    """Cached tuple of module names that contain Dagster assets."""

    package = importlib.import_module(__name__)
    skip = (
        f"{__name__}.jobs",
        f"{__name__}.sensors",
    )
    return tuple(_iter_package_modules(package, skip_prefixes=skip))


def iter_asset_modules() -> list[ModuleType]:
    """Return all asset modules discovered under src.assets (excluding jobs/sensors)."""

    modules: list[ModuleType] = []
    for module_name in _asset_module_names():
        module = _safe_import(module_name)
        if module:
            modules.append(module)
    return modules


@lru_cache(maxsize=1)
def _job_module_names() -> tuple[str, ...]:
    """Return fully-qualified module names for job definitions."""

    package = importlib.import_module(f"{__name__}.jobs")
    return tuple(_iter_package_modules(package))


def iter_job_modules() -> list[ModuleType]:
    """Import and return modules that define Dagster jobs."""

    modules: list[ModuleType] = []
    for module_name in _job_module_names():
        module = _safe_import(module_name)
        if module:
            modules.append(module)
    return modules


@lru_cache(maxsize=1)
def _sensor_module_names() -> tuple[str, ...]:
    """Return module names for Dagster sensors."""

    try:
        package = importlib.import_module(f"{__name__}.sensors")
    except ModuleNotFoundError:
        return ()
    return tuple(_iter_package_modules(package))


def iter_sensor_modules() -> list[ModuleType]:
    """Import and return modules that define Dagster sensors."""

    modules: list[ModuleType] = []
    for module_name in _sensor_module_names():
        module = _safe_import(module_name)
        if module:
            modules.append(module)
    return modules


def iter_public_jobs() -> list["JobDefinition"]:
    """Return Dagster JobDefinitions discovered in job modules."""

    from dagster import JobDefinition  # Imported lazily to keep module import-safe

    jobs: list[JobDefinition] = []
    for module in iter_job_modules():
        for value in vars(module).values():
            if isinstance(value, JobDefinition):
                jobs.append(value)
    return jobs


def iter_public_sensors() -> list["SensorDefinition"]:
    """Return Dagster SensorDefinitions discovered in sensor modules."""

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
]
