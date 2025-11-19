"""Helpers for discovering SBIR ETL asset modules and Dagster registrations."""

from __future__ import annotations

import importlib
import logging
import pkgutil
from functools import lru_cache
from types import ModuleType
from typing import Iterator, Sequence

LOG = logging.getLogger(__name__)


def _iter_modules(
    package: ModuleType,
    *,
    skip_prefixes: Sequence[str] = (),
) -> Iterator[str]:
    """Yield fully qualified module names for a package tree."""

    prefix = package.__name__ + "."
    for module_info in pkgutil.walk_packages(package.__path__, prefix=prefix):
        if any(module_info.name.startswith(skip) for skip in skip_prefixes):
            continue
        yield module_info.name


def _safe_import(module_name: str) -> ModuleType | None:
    """Import a module, logging and skipping failures."""

    try:
        return importlib.import_module(module_name)
    except Exception as exc:  # pragma: no cover - defensive
        LOG.warning("Failed to import %s: %s", module_name, exc)
        return None


@lru_cache(maxsize=1)
def _asset_module_names() -> tuple[str, ...]:
    package = importlib.import_module(__name__)
    skip = (
        f"{__name__}.jobs",
        f"{__name__}.sensors",
    )
    return tuple(_iter_modules(package, skip_prefixes=skip))


def iter_asset_modules() -> list[ModuleType]:
    """Return all asset modules (excluding jobs/sensors)."""

    modules: list[ModuleType] = []
    for module_name in _asset_module_names():
        module = _safe_import(module_name)
        if module:
            modules.append(module)
    return modules


@lru_cache(maxsize=1)
def _job_module_names() -> tuple[str, ...]:
    package = importlib.import_module(f"{__name__}.jobs")
    return tuple(_iter_modules(package))


def iter_job_modules() -> list[ModuleType]:
    modules: list[ModuleType] = []
    for module_name in _job_module_names():
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


def iter_public_jobs() -> list["JobDefinition"]:
    from dagster import JobDefinition  # Imported lazily

    jobs: list[JobDefinition] = []
    for module in iter_job_modules():
        for value in vars(module).values():
            if isinstance(value, JobDefinition):
                jobs.append(value)
    return jobs


def iter_public_sensors() -> list["SensorDefinition"]:
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
