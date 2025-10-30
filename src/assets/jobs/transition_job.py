"""Transition detection job definitions for Dagster."""

from dagster import AssetSelection, define_asset_job

# Define transition MVP job (core transition detection chain)
transition_mvp_job = define_asset_job(
    name="transition_mvp_job",
    selection=AssetSelection.keys(
        "contracts_sample",
        "vendor_resolution", 
        "transition_scores_v1",
        "transition_evidence_v1"
    ),
    description="Transition detection MVP chain: contracts → vendor resolution → scoring → evidence",
)

# Define full transition pipeline job (includes analytics and Neo4j loading)
transition_full_job = define_asset_job(
    name="transition_full_job", 
    selection=AssetSelection.groups("transition"),
    description="Complete transition detection pipeline with analytics and Neo4j loading",
)

# Define transition analytics job (just the analytics components)
transition_analytics_job = define_asset_job(
    name="transition_analytics_job",
    selection=AssetSelection.keys(
        "transition_detections",
        "transition_analytics"
    ),
    description="Transition analytics: detections → dual-perspective analytics",
)