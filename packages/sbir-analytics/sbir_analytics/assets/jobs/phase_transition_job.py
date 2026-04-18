"""Phase II -> Phase III transition latency job.

Materializes the four phase_transition assets in dependency order:
phase_ii -> phase_iii -> pairs -> survival.

Upstream dependencies (``raw_contracts``, ``enriched_sbir_awards``) are not
included in this job — they are large, long-running SBIR-wide ingestion
assets, so operators run them separately via ``sbir_weekly_refresh_job``
and this job only computes the transition-latency marts.
"""

from .job_registry import JobSpec, build_job_from_spec


phase_transition_latency_job = build_job_from_spec(
    JobSpec(
        name="phase_transition_latency_job",
        description=(
            "Compute Phase II -> Phase III transition latency: unified Phase II "
            "awards, Phase III contracts, matched pairs, and KM-ready survival "
            "frame. Assumes raw_contracts / enriched_sbir_awards are already "
            "materialized."
        ),
        asset_keys=(
            "validated_phase_ii_awards",
            "validated_phase_iii_contracts",
            "transformed_phase_ii_iii_pairs",
            "transformed_phase_transition_survival",
        ),
    )
)
