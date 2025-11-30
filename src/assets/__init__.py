"""Helpers for discovering SBIR ETL asset modules and Dagster registrations."""

from __future__ import annotations

import importlib
import logging
import os
import pkgutil
from collections.abc import Iterator, Sequence
from functools import lru_cache
from types import ModuleType
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from dagster import JobDefinition, SensorDefinition

LOG = logging.getLogger(__name__)


# Heavy modules that can be skipped in resource-constrained environments
HEAVY_ASSET_MODULES = {
    "src.assets.fiscal_assets",  # R dependencies, economic modeling
    "src.assets.paecter.embeddings",  # Sentence transformers, ML models
    "src.assets.paecter.similarity",  # Large-scale similarity computation
    "src.assets.ml.cet_training",  # scikit-learn, model training
    "src.assets.ml.cet_inference",  # Model inference
    "src.assets.ml.cet_drift_detection",  # Statistical analysis
    "src.assets.uspto.ai_extraction",  # spaCy, NLP processing
}


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


def _should_load_heavy_assets() -> bool:
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
    load_heavy = _should_load_heavy_assets()

    modules: list[ModuleType] = []
    for module_name in _asset_module_names():
        # Skip heavy modules if configured
        if not load_heavy and module_name in HEAVY_ASSET_MODULES:
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
]
