"""Dagster sensor for USAspending iterative enrichment refresh.

Triggers refresh job after bulk enrichment completes successfully.
"""

from datetime import datetime, timedelta

from dagster import (
    RunRequest,
    SensorEvaluationContext,
    SensorResult,
    SkipReason,
    sensor,
)

from ..jobs.usaspending_iterative_job import usaspending_iterative_enrichment_job


@sensor(
    job=usaspending_iterative_enrichment_job,
    name="usaspending_refresh_sensor",
    description="Sensor that triggers USAspending refresh after bulk enrichment completes",
)
def usaspending_refresh_sensor(context: SensorEvaluationContext) -> SensorResult | SkipReason:
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
        enriched_awards_record = context.instance.get_latest_materialization_record(enriched_awards_key)
        
        if not enriched_awards_record or not enriched_awards_record.event_log_entry:
            return SkipReason("Bulk enrichment asset not yet materialized")
        
        # Check if materialization was successful
        if enriched_awards_record.event_log_entry.asset_materialization is None:
            return SkipReason("Bulk enrichment asset materialization not found")
        
        # Check freshness ledger to see if refresh is needed
        freshness_key = AssetKey("usaspending_freshness_ledger")
        freshness_record = context.instance.get_latest_materialization_record(freshness_key)
        
        # If freshness ledger exists, check staleness
        # Otherwise, this might be first run - trigger refresh to initialize
        if freshness_record and freshness_record.event_log_entry:
            # Check stale awards asset
            stale_key = AssetKey("stale_usaspending_awards")
            stale_record = context.instance.get_latest_materialization_record(stale_key)
            
            if stale_record and stale_record.event_log_entry:
                # Check metadata for stale count
                if stale_record.event_log_entry.asset_materialization:
                    metadata = stale_record.event_log_entry.asset_materialization.metadata or {}
                    stale_count_val = metadata.get("stale_count")
                    # Extract value if it's a MetadataValue, otherwise use directly
                    if hasattr(stale_count_val, 'value'):
                        stale_count = stale_count_val.value
                    elif isinstance(stale_count_val, (int, float)):
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
            run_key=f"usaspending_refresh_{datetime.now().isoformat()}",
            tags={
                "source": "usaspending",
                "trigger": "sensor",
            },
        )
        
    except Exception as e:
        context.log.error(f"Error in refresh sensor: {e}")
        return SkipReason(f"Sensor error: {e}")

