"""Fiscal returns analysis job definitions for Dagster."""

from .job_registry import JobSpec, build_job_from_spec, build_placeholder_job

# Check if fiscal assets module is available
try:
    from .. import fiscal_assets  # noqa: F401 - imported to check availability

    fiscal_assets_available = True
except Exception:  # pragma: no cover - handles optional dependencies
    fiscal_assets_available = False


if fiscal_assets_available:
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
else:
    # Create placeholder jobs when fiscal assets aren't available
    fiscal_returns_mvp_job = build_placeholder_job(
        name="fiscal_returns_mvp_job",
        description="Placeholder job (fiscal assets unavailable at import time).",
    )

    fiscal_returns_full_job = build_placeholder_job(
        name="fiscal_returns_full_job",
        description="Placeholder job (fiscal assets unavailable at import time).",
    )

fiscal_returns_analysis_job = fiscal_returns_full_job
