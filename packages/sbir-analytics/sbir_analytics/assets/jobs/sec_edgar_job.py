"""Dagster job for SEC EDGAR enrichment pipeline.

Chains: validated_sbir_awards → sec_edgar_enriched_companies

This job is opt-in (SEC EDGAR enrichment is disabled by default).
Enable via: SBIR_ETL__ENRICHMENT_REFRESH__SEC_EDGAR__ENABLED=true
"""

from __future__ import annotations

from dagster import JobDefinition, in_process_executor
from dagster._core.definitions.unresolved_asset_job_definition import (
    UnresolvedAssetJobDefinition,
)


from ..sbir_ingestion import validated_sbir_awards
from ..sec_edgar_enrichment import sec_edgar_enriched_companies

from .job_registry import JobSpec, build_job_from_spec_with_executor


def _build_job() -> JobDefinition | UnresolvedAssetJobDefinition:
    return build_job_from_spec_with_executor(
        JobSpec(
            name="sec_edgar_pipeline_job",
            description=(
                "SEC EDGAR enrichment pipeline: resolve SBIR companies to SEC filings, "
                "then extract financials and M&A signals"
            ),
            assets=(validated_sbir_awards, sec_edgar_enriched_companies),
        ),
        executor=in_process_executor,
    )


sec_edgar_pipeline_job = _build_job()

__all__ = ["sec_edgar_pipeline_job"]
