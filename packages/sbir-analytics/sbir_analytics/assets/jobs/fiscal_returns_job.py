"""Fiscal returns analysis job definitions for Dagster.

Epistemic tier: exploratory. This job wires the exploratory fiscal
estimation assets; outputs are non-citable.
"""

from .. import fiscal_assets as _fiscal_assets  # noqa: F401 - validate definitions at import time
from .job_registry import JobSpec, build_job_from_spec


EPISTEMIC_TIER = "exploratory"


fiscal_returns_mvp_job = build_job_from_spec(
    JobSpec(
        name="fiscal_returns_mvp_job",
        description="Fiscal returns MVP pipeline: data prep → economic modeling → tax calculation → ROI summary",
        asset_keys=(
            "fiscal_naics_enriched_awards",
            "fiscal_prepared_sbir_awards",
            "inflation_adjusted_awards",
            "bea_mapped_sbir_awards",
            "economic_shocks",
            "economic_impacts",
            "tax_base_components",
            "federal_tax_estimates",
            "fiscal_return_summary",
        ),
    )
)

fiscal_returns_full_job = build_job_from_spec(
    JobSpec(
        name="fiscal_returns_full_job",
        description="Complete fiscal returns analysis pipeline with sensitivity analysis and uncertainty quantification",
        asset_groups=(
            "fiscal_data_prep",
            "economic_modeling",
            "tax_calculation",
            "sensitivity_analysis",
        ),
    )
)

fiscal_returns_analysis_job = fiscal_returns_full_job
