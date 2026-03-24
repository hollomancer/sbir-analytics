"""Transition detection job definitions for Dagster."""

from .job_registry import JobSpec, build_job_from_spec


transition_mvp_job = build_job_from_spec(
    JobSpec(
        name="transition_mvp_job",
        description="Transition detection MVP chain: contracts → vendor resolution → scoring → evidence",
        asset_keys=(
            "validated_contracts_sample",
            "enriched_vendor_resolution",
            "transformed_transition_scores",
            "transformed_transition_evidence",
        ),
    )
)

transition_full_job = build_job_from_spec(
    JobSpec(
        name="transition_full_job",
        description="Complete transition detection pipeline with analytics and Neo4j loading",
        asset_keys=(
            "validated_contracts_sample",
            "enriched_vendor_resolution",
            "transformed_transition_scores",
            "transformed_transition_evidence",
            "transformed_transition_detections",
            "transformed_transition_analytics",
            "loaded_transitions",
            "loaded_transition_relationships",
            "loaded_transition_profiles",
        ),
    )
)

transition_analytics_job = build_job_from_spec(
    JobSpec(
        name="transition_analytics_job",
        description="Transition analytics: detections → dual-perspective analytics",
        asset_keys=(
            "transformed_transition_detections",
            "transformed_transition_analytics",
        ),
    )
)
