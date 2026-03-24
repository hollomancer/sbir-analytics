"""Dagster job for SBIR weekly refresh pipeline."""

from __future__ import annotations

from dagster import JobDefinition, in_process_executor
from dagster._core.definitions.unresolved_asset_job_definition import (
    UnresolvedAssetJobDefinition,
)


try:
    from ..sbir_ingestion import raw_sbir_awards, sbir_validation_report, validated_sbir_awards
    from ..sbir_usaspending_enrichment import enriched_sbir_awards
    from ..sbir_neo4j_loading import neo4j_sbir_awards
    from ..usaspending_ingestion import raw_usaspending_recipients
    from ..sam_gov_ingestion import raw_sam_gov_entities
except Exception:  # pragma: no cover - handles optional Dagster deps
    raw_sbir_awards = None  # type: ignore
    validated_sbir_awards = None  # type: ignore
    sbir_validation_report = None  # type: ignore
    enriched_sbir_awards = None  # type: ignore
    neo4j_sbir_awards = None  # type: ignore
    raw_usaspending_recipients = None  # type: ignore
    raw_sam_gov_entities = None  # type: ignore

from .job_registry import JobSpec, build_job_from_spec_with_executor, build_placeholder_job


def _build_job() -> JobDefinition | UnresolvedAssetJobDefinition:
    assets = [
        raw_sbir_awards,
        validated_sbir_awards,
        sbir_validation_report,
        raw_usaspending_recipients,
        raw_sam_gov_entities,
        enriched_sbir_awards,
        neo4j_sbir_awards,
    ]
    if any(asset is None for asset in assets):  # type: ignore[arg-type]
        return build_placeholder_job(
            name="sbir_weekly_refresh_job",
            description="Placeholder job (SBIR assets unavailable at import time).",
        )

    # Use in-process executor to avoid OOM on GitHub runners (7GB limit)
    return build_job_from_spec_with_executor(
        JobSpec(
            name="sbir_weekly_refresh_job",
            description="Weekly SBIR data refresh: extract, validate, enrich, and load awards into Neo4j",
            assets=assets,  # type: ignore[arg-type]
        ),
        executor=in_process_executor,
    )


sbir_weekly_refresh_job = _build_job()

__all__ = ["sbir_weekly_refresh_job"]
