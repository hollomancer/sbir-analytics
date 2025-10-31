"""Transition detection job definitions for Dagster."""

from dagster import AssetSelection, define_asset_job

# Define transition MVP job (core transition detection chain)
transition_mvp_job = define_asset_job(
    name="transition_mvp_job",
    selection=AssetSelection.keys(
        "validated_contracts_sample",
        "enriched_vendor_resolution",
        "transformed_transition_scores",
        "transformed_transition_evidence",
    ),
    description="Transition detection MVP chain: contracts → vendor resolution → scoring → evidence",
)

# Define full transition pipeline job (includes analytics and Neo4j loading)
transition_full_job = define_asset_job(
    name="transition_full_job",
    selection=AssetSelection.keys(
        "validated_contracts_sample",
        "enriched_vendor_resolution",
        "transformed_transition_scores",
        "transformed_transition_evidence",
        "transformed_transition_detections",
        "transformed_transition_analytics",
        "loaded_transitions",
        "loaded_transition_relationships",
        "loaded_transition_profiles",
    ).with_checks(
        AssetSelection.checks_for_keys(
            "validated_contracts_sample",
            "enriched_vendor_resolution",
            "transformed_transition_scores",
            "transformed_transition_evidence",
            "transformed_transition_detections",
            "transformed_transition_analytics",
            "loaded_transitions",
            "loaded_transition_relationships",
        )
    ),
    description="Complete transition detection pipeline with analytics and Neo4j loading",
)

# Define transition analytics job (just the analytics components)
transition_analytics_job = define_asset_job(
    name="transition_analytics_job",
    selection=AssetSelection.keys(
        "transformed_transition_detections", "transformed_transition_analytics"
    ),
    description="Transition analytics: detections → dual-perspective analytics",
)
