"""Dagster job for SBIR weekly refresh pipeline."""

from __future__ import annotations

from dagster import JobDefinition, in_process_executor
from dagster._core.definitions.unresolved_asset_job_definition import (
    UnresolvedAssetJobDefinition,
)


from ..sam_gov_ingestion import raw_sam_gov_entities
from ..sbir_ingestion import raw_sbir_awards, sbir_validation_report, validated_sbir_awards
from ..sbir_usaspending_enrichment import enriched_sbir_awards
from ..usaspending_ingestion import raw_usaspending_recipients

from .job_registry import JobSpec, build_job_from_spec


def _build_job() -> JobDefinition | UnresolvedAssetJobDefinition:
    # Use in-process executor to avoid OOM on GitHub runners (7GB limit)
    return build_job_from_spec(
        JobSpec(
            name="sbir_weekly_refresh_job",
            description="Weekly SBIR data refresh: extract, validate, and enrich awards",
            assets=(
                raw_sbir_awards,
                validated_sbir_awards,
                sbir_validation_report,
                raw_usaspending_recipients,
                raw_sam_gov_entities,
                enriched_sbir_awards,
            ),
        ),
        executor=in_process_executor,
    )


sbir_weekly_refresh_job = _build_job()

__all__ = ["sbir_weekly_refresh_job"]
