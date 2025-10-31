# sbir-etl/src/assets/jobs/cet_pipeline_job.py
"""
Dagster job that orchestrates the full CET flow end-to-end:

Pipeline (intended order; actual execution enforced by asset dependencies):
  1) cet_taxonomy                    — produce CET taxonomy artifact
  2) cet_award_classifications       — classify awards using CET classifier (with evidence)
  3) cet_company_profiles            — aggregate award-level CETs into company profiles
  4) neo4j_cetarea_nodes             — upsert CETArea nodes into Neo4j
  5) neo4j_award_cet_enrichment      — MERGE award-level CET enrichment properties
  6) neo4j_company_cet_enrichment    — MERGE company-level CET enrichment properties
  7) neo4j_award_cet_relationships   — create (Award)-[:APPLICABLE_TO]->(CETArea)
  8) neo4j_company_cet_relationships — create (Company)-[:SPECIALIZES_IN]->(CETArea)

Notes:
- Execution order is captured by the asset dependencies defined in their modules.
- This job simply composes the assets into a single materialization target.
- Provide runtime configuration via Dagster run config for paths, batch sizes, etc.
"""

from dagster import AssetSelection, define_asset_job

# Import CET production assets
try:
    from src.assets.cet_assets import (  # type: ignore
        cet_award_classifications,
        cet_company_profiles,
        cet_taxonomy,
    )
except Exception:  # pragma: no cover - defensive import for repository load-time
    cet_taxonomy = None  # type: ignore
    cet_award_classifications = None  # type: ignore
    cet_company_profiles = None  # type: ignore

# Import CET Neo4j loading/enrichment assets (consolidated)
try:
    from src.assets.cet_assets import (  # type: ignore
        neo4j_award_cet_enrichment,
        neo4j_award_cet_relationships,
        neo4j_cetarea_nodes,
        neo4j_company_cet_enrichment,
        neo4j_company_cet_relationships,
    )
except Exception:  # pragma: no cover - defensive import for repository load-time
    neo4j_cetarea_nodes = None  # type: ignore
    neo4j_award_cet_enrichment = None  # type: ignore
    neo4j_company_cet_enrichment = None  # type: ignore
    neo4j_award_cet_relationships = None  # type: ignore
    neo4j_company_cet_relationships = None  # type: ignore


# Compose the CET end-to-end job if all assets are importable; otherwise expose a placeholder job
if (
    cet_taxonomy is not None
    and cet_award_classifications is not None
    and cet_company_profiles is not None
    and neo4j_cetarea_nodes is not None
    and neo4j_award_cet_enrichment is not None
    and neo4j_company_cet_enrichment is not None
    and neo4j_award_cet_relationships is not None
    and neo4j_company_cet_relationships is not None
):
    cet_full_pipeline_job = define_asset_job(
        name="cet_full_pipeline_job",
        selection=AssetSelection.keys(
            cet_taxonomy.key,  # type: ignore[attr-defined]
            cet_award_classifications.key,  # type: ignore[attr-defined]
            cet_company_profiles.key,  # type: ignore[attr-defined]
            neo4j_cetarea_nodes.key,  # type: ignore[attr-defined]
            neo4j_award_cet_enrichment.key,  # type: ignore[attr-defined]
            neo4j_company_cet_enrichment.key,  # type: ignore[attr-defined]
            neo4j_award_cet_relationships.key,  # type: ignore[attr-defined]
            neo4j_company_cet_relationships.key,  # type: ignore[attr-defined]
        ),
        description=(
            "Materialize the CET pipeline end-to-end: taxonomy -> award classification -> "
            "company aggregation -> Neo4j nodes/enrichment -> relationships."
        ),
    )
else:
    cet_full_pipeline_job = define_asset_job(
        name="cet_full_pipeline_job_placeholder",
        selection=AssetSelection.keys(),
        description="Placeholder job (CET assets unavailable at import time).",
    )


__all__ = ["cet_full_pipeline_job"]
