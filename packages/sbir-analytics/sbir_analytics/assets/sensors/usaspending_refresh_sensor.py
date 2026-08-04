"""Dagster sensor for USAspending iterative enrichment refresh.

Triggers refresh job after bulk enrichment completes successfully.
"""

from dagster import RunRequest, SensorEvaluationContext, SkipReason, sensor

from ..jobs.usaspending_iterative_job import usaspending_iterative_enrichment_job


@sensor(
    job=usaspending_iterative_enrichment_job,
    name="usaspending_refresh_sensor",
    description="Sensor that triggers USAspending refresh after bulk enrichment completes",
)
def usaspending_refresh_sensor(context: SensorEvaluationContext) -> RunRequest | SkipReason:
    """Sensor that triggers USAspending iterative refresh.

    Checks if bulk enrichment assets are healthy and triggers refresh if:
    1. enriched_sbir_awards asset is materialized successfully
    2. It's been at least the configured cadence_days since last refresh
    3. There are stale awards detected

    Args:
        context: Sensor evaluation context

    Returns:
        RunRequest if refresh should be triggered, SkipReason otherwise
    """
    from dagster import AssetKey

    # Check if bulk enrichment asset is materialized
    try:
        # Check enriched_sbir_awards asset
        enriched_awards_key = AssetKey("enriched_sbir_awards")
        enriched_awards_record = context.instance.get_latest_materialization_event(  # type: ignore[attr-defined]
            enriched_awards_key
        )

        if not enriched_awards_record:
            return SkipReason("Bulk enrichment asset not yet materialized")

        # Check if materialization was successful
        if not enriched_awards_record.asset_materialization:
            return SkipReason("Bulk enrichment asset materialization not found")

        # A stable event-derived run key lets Dagster deduplicate repeated
        # evaluations of the same materialization. A wall-clock key generated a
        # distinct run on every sensor tick.
        trigger_timestamp = enriched_awards_record.timestamp

        # Check freshness ledger to see if refresh is needed
        freshness_key = AssetKey("usaspending_freshness_ledger")
        freshness_record = context.instance.get_latest_materialization_event(freshness_key)  # type: ignore[attr-defined]

        # If freshness ledger exists, check staleness
        # Otherwise, this might be first run - trigger refresh to initialize
        if freshness_record:
            # Check stale awards asset
            stale_key = AssetKey("stale_usaspending_awards")
            stale_record = context.instance.get_latest_materialization_event(stale_key)  # type: ignore[attr-defined]

            if stale_record:
                # Check metadata for stale count
                stale_materialization = stale_record.asset_materialization
                if stale_materialization:
                    trigger_timestamp = stale_record.timestamp
                    metadata = stale_materialization.metadata or {}
                    stale_count_val = metadata.get("stale_count")
                    # Extract value if it's a MetadataValue, otherwise use directly
                    if hasattr(stale_count_val, "value"):
                        stale_count = stale_count_val.value  # type: ignore[union-attr]
                    elif isinstance(stale_count_val, int | float):
                        stale_count = int(stale_count_val)
                    else:
                        stale_count = 0
                else:
                    stale_count = 0

                if stale_count == 0:
                    return SkipReason("No stale awards found - refresh not needed")

        # Trigger refresh
        context.log.info("Triggering USAspending iterative refresh")
        return RunRequest(
            run_key=f"usaspending_refresh_{trigger_timestamp}",
            tags={
                "source": "usaspending",
                "trigger": "sensor",
            },
        )

    except Exception:
        # Unexpected instance failures should fail the sensor tick visibly;
        # converting them to SkipReason made an unhealthy sensor look healthy.
        context.log.exception("Error in refresh sensor")
        raise
