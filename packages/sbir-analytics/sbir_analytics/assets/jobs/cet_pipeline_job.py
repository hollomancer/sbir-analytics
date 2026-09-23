# packages/sbir-analytics/sbir_analytics/assets/jobs/cet_pipeline_job.py
"""
Dagster job that orchestrates the full CET flow end-to-end:

Pipeline (intended order; actual execution enforced by asset dependencies):
  1) cet_taxonomy                    — produce CET taxonomy artifact
  2) cet_award_classifications       — classify awards using CET classifier (with evidence)
  3) cet_company_profiles            — aggregate award-level CETs into company profiles

Notes:
- Execution order is captured by the asset dependencies defined in their modules.
- This job simply composes the assets into a single materialization target.
- Provide runtime configuration via Dagster run config for paths, batch sizes, etc.

Epistemic tier: exploratory. This job wires the exploratory CET
classification assets; outputs are non-citable.
"""

from dagster import AssetSelection, define_asset_job


# Import CET production assets
try:
    from ..cet import (
        cet_taxonomy,
        enriched_cet_award_classifications,
        transformed_cet_company_profiles,
    )

    # Create aliases for backward compatibility
    cet_award_classifications = enriched_cet_award_classifications
    cet_company_profiles = transformed_cet_company_profiles
except Exception:  # pragma: no cover - defensive import for repository load-time
    cet_taxonomy = None  # type: ignore
    cet_award_classifications = None  # type: ignore
    cet_company_profiles = None  # type: ignore

EPISTEMIC_TIER = "exploratory"


# Compose the CET end-to-end job if all assets are importable; otherwise expose a placeholder job
if (
    cet_taxonomy is not None
    and cet_award_classifications is not None
    and cet_company_profiles is not None
):
    cet_full_pipeline_job = define_asset_job(
        name="cet_full_pipeline_job",
        selection=AssetSelection.keys(
            cet_taxonomy.key,
            cet_award_classifications.key,
            cet_company_profiles.key,
        ),
        description=(
            "Materialize the CET pipeline end-to-end: taxonomy -> award classification -> "
            "company aggregation."
        ),
    )
else:
    # This branch is reachable when assets fail to import at module load time
    cet_full_pipeline_job = define_asset_job(  # type: ignore[unreachable]
        name="cet_full_pipeline_job",
        selection=AssetSelection.keys(),
        description="Placeholder job (CET assets unavailable at import time).",
    )


__all__ = ["cet_full_pipeline_job"]
