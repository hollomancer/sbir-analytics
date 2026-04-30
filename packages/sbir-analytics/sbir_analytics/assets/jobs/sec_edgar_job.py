"""Dagster job for SEC EDGAR enrichment pipeline.

Chains: validated_sbir_awards → sec_edgar_enriched_companies → neo4j_sec_edgar_enrichment

This job is opt-in (SEC EDGAR enrichment is disabled by default).
Enable via: SBIR_ETL__ENRICHMENT_REFRESH__SEC_EDGAR__ENABLED=true
"""

from __future__ import annotations

from dagster import JobDefinition, in_process_executor
from dagster._core.definitions.unresolved_asset_job_definition import (
    UnresolvedAssetJobDefinition,
)


try:
    from ..sbir_ingestion import validated_sbir_awards
    from ..sec_edgar_enrichment import neo4j_sec_edgar_enrichment, sec_edgar_enriched_companies
except Exception:  # pragma: no cover - handles optional Dagster deps
    validated_sbir_awards = None  # type: ignore
    sec_edgar_enriched_companies = None  # type: ignore
    neo4j_sec_edgar_enrichment = None  # type: ignore

from .job_registry import JobSpec, build_job_from_spec_with_executor, build_placeholder_job


def _build_job() -> JobDefinition | UnresolvedAssetJobDefinition:
    assets = [
        validated_sbir_awards,
        sec_edgar_enriched_companies,
        neo4j_sec_edgar_enrichment,
    ]
    if any(asset is None for asset in assets):  # type: ignore[arg-type]
        return build_placeholder_job(
            name="sec_edgar_pipeline_job",
            description="Placeholder job (SEC EDGAR assets unavailable at import time).",
        )

    return build_job_from_spec_with_executor(
        JobSpec(
            name="sec_edgar_pipeline_job",
            description=(
                "SEC EDGAR enrichment pipeline: resolve SBIR companies to SEC filings, "
                "extract financials and M&A signals, load into Neo4j"
            ),
            assets=assets,  # type: ignore[arg-type]
        ),
        executor=in_process_executor,
    )


sec_edgar_pipeline_job = _build_job()

__all__ = ["sec_edgar_pipeline_job"]
