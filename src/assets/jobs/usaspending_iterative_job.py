"""Dagster job definitions for USAspending iterative enrichment.

Phase 1: USAspending API only. Generic multi-source orchestrator will be created in Phase 2+.
"""

from dagster import AssetSelection, define_asset_job

# Define USAspending iterative enrichment job
usaspending_iterative_enrichment_job = define_asset_job(
    name="usaspending_iterative_enrichment_job",
    selection=AssetSelection.keys(
        "usaspending_freshness_ledger",
        "stale_usaspending_awards",
    ),
    description="USAspending iterative enrichment refresh: identify and refresh stale awards",
    config={
        "ops": {
            "usaspending_refresh_batch": {
                "config": {
                    "source": "usaspending",
                    "force": False,
                }
            }
        }
    },
)

