"""Tests for automatic asset/job/sensor discovery helpers."""

import types

import pytest
from dagster import JobDefinition, SensorDefinition

from src import assets as assets_pkg


pytestmark = pytest.mark.fast


def test_iter_asset_modules_discovers_expected_packages():
    """Asset discovery should include core modules such as sbir_ingestion."""

    modules = assets_pkg.iter_asset_modules()
    assert modules, "Expected at least one asset module to be discovered"

    module_names = {module.__name__ for module in modules}
    assert "src.assets.sbir_ingestion" in module_names
    assert "src.assets.uspto.extraction" in module_names
    assert "src.assets.transition.detections" in module_names
    # Jobs/sensors should be excluded
    assert "src.assets.jobs.transition_job" not in module_names
    assert all(not name.startswith("src.assets.sensors") for name in module_names)


def test_iter_job_modules_discovers_job_packages():
    """Job discovery should import every module under src.assets.jobs."""

    modules = assets_pkg.iter_job_modules()
    assert modules, "Expected job modules to be discovered"
    assert all(isinstance(module, types.ModuleType) for module in modules), (
        "Discovery should return module objects"
    )

    module_names = {module.__name__ for module in modules}
    assert "src.assets.jobs.transition_job" in module_names
    assert "src.assets.jobs.fiscal_returns_job" in module_names


def test_iter_public_jobs_returns_job_definitions():
    """Public job iterator should yield Dagster JobDefinition objects."""
    from dagster._core.definitions.unresolved_asset_job_definition import (
        UnresolvedAssetJobDefinition,
    )

    jobs = assets_pkg.iter_public_jobs()
    assert jobs, "Auto-discovery should return registered jobs"
    assert all(isinstance(job, JobDefinition | UnresolvedAssetJobDefinition) for job in jobs)
    assert any(job.name == "transition_full_job" for job in jobs)


def test_iter_public_sensors_returns_sensor_definitions():
    """Sensors should be discovered automatically when defined."""

    sensors = assets_pkg.iter_public_sensors()
    assert all(isinstance(sensor, SensorDefinition) for sensor in sensors)
