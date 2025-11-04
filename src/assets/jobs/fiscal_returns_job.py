"""Fiscal returns analysis job definitions for Dagster."""

from dagster import AssetSelection, define_asset_job


# Define fiscal returns MVP job (core pipeline without sensitivity analysis)
fiscal_returns_mvp_job = define_asset_job(
    name="fiscal_returns_mvp_job",
    selection=AssetSelection.keys(
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
    description="Fiscal returns MVP pipeline: data prep → economic modeling → tax calculation → ROI summary",
)

# Define full fiscal returns analysis job (includes sensitivity analysis)
fiscal_returns_full_job = define_asset_job(
    name="fiscal_returns_full_job",
    selection=AssetSelection.groups(
        "fiscal_data_prep",
        "economic_modeling",
        "tax_calculation",
        "sensitivity_analysis",
    ),
    description="Complete fiscal returns analysis pipeline with sensitivity analysis and uncertainty quantification",
)

# Define fiscal returns analysis job (alias for full job)
fiscal_returns_analysis_job = fiscal_returns_full_job
