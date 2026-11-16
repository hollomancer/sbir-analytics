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

from ..cet import (
    cet_taxonomy,
    enriched_cet_award_classifications,
    transformed_cet_company_profiles,
)

EPISTEMIC_TIER = "exploratory"


cet_full_pipeline_job = define_asset_job(
    name="cet_full_pipeline_job",
    selection=AssetSelection.keys(
        cet_taxonomy.key,
        enriched_cet_award_classifications.key,
        transformed_cet_company_profiles.key,
    ),
    description=(
        "Materialize the CET pipeline end-to-end: taxonomy -> award classification -> "
        "company aggregation."
    ),
)


__all__ = ["cet_full_pipeline_job"]
