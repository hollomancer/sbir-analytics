"""Behavioral contracts for the USAspending refresh sensor."""

from unittest.mock import Mock

import pytest
from dagster import (
    AssetKey,
    AssetMaterialization,
    DagsterInstance,
    RunRequest,
    SkipReason,
    build_sensor_context,
)

from sbir_analytics.assets.sensors.usaspending_refresh_sensor import (
    usaspending_refresh_sensor,
)


pytestmark = pytest.mark.fast


@pytest.fixture
def instance():
    with DagsterInstance.ephemeral() as ephemeral:
        yield ephemeral


def _materialize(instance, key: str, **metadata):
    instance.report_runless_asset_event(
        AssetMaterialization(asset_key=AssetKey(key), metadata=metadata)
    )


def test_skips_before_bulk_enrichment_is_materialized(instance):
    result = usaspending_refresh_sensor(build_sensor_context(instance=instance))

    assert isinstance(result, SkipReason)
    assert result.skip_message == "Bulk enrichment asset not yet materialized"


def test_skips_when_no_awards_are_stale(instance):
    _materialize(instance, "enriched_sbir_awards")
    _materialize(instance, "usaspending_freshness_ledger")
    _materialize(instance, "stale_usaspending_awards", stale_count=0)

    result = usaspending_refresh_sensor(build_sensor_context(instance=instance))

    assert isinstance(result, SkipReason)
    assert result.skip_message == "No stale awards found - refresh not needed"


def test_stale_materialization_produces_a_stable_deduplicating_run_key(instance):
    _materialize(instance, "enriched_sbir_awards")
    _materialize(instance, "usaspending_freshness_ledger")
    _materialize(instance, "stale_usaspending_awards", stale_count=3)
    context = build_sensor_context(instance=instance)
    stale_record = instance.get_latest_materialization_event(AssetKey("stale_usaspending_awards"))
    assert stale_record is not None

    first = usaspending_refresh_sensor(context)
    second = usaspending_refresh_sensor(context)

    assert isinstance(first, RunRequest)
    assert isinstance(second, RunRequest)
    assert first.run_key == second.run_key == f"usaspending_refresh_{stale_record.timestamp}"
    assert first.tags == {"source": "usaspending", "trigger": "sensor"}


def test_first_refresh_uses_enrichment_materialization_for_run_key(instance):
    _materialize(instance, "enriched_sbir_awards")
    enrichment_record = instance.get_latest_materialization_event(AssetKey("enriched_sbir_awards"))
    assert enrichment_record is not None

    result = usaspending_refresh_sensor(build_sensor_context(instance=instance))

    assert isinstance(result, RunRequest)
    assert result.run_key == f"usaspending_refresh_{enrichment_record.timestamp}"


def test_instance_errors_fail_the_sensor_tick(instance, monkeypatch):
    monkeypatch.setattr(
        instance,
        "get_latest_materialization_event",
        Mock(side_effect=RuntimeError("storage down")),
    )

    with pytest.raises(RuntimeError, match="storage down"):
        usaspending_refresh_sensor(build_sensor_context(instance=instance))
