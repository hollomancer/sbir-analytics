"""Dagster reporting asset for the leverage-ratio analysis."""

import json
from pathlib import Path

import pandas as pd
from dagster import AssetExecutionContext, Config, MetadataValue, Output, asset

from .analysis import LeverageRatioPolicy, calculate_leverage_ratios
from .integration import build_canonical_obligations
from .reconcile import reconcile_nasem, reconciliation_markdown


class LeverageRatioConfig(Config):
    match_confidence_threshold: float = 0.80
    fiscal_year_start: int | None = None
    fiscal_year_end: int | None = None
    include_sttr: bool = True
    dollar_basis: str = "nominal"
    adjustment_factors_path: str | None = None


@asset(
    group_name="leverage_ratio",
    compute_kind="pandas",
    description="Traceable SBIR/STTR leverage ratios from enriched SBIR and USAspending outputs.",
)
def leverage_ratio_analysis(
    context: AssetExecutionContext,
    config: LeverageRatioConfig,
    enriched_sbir_awards: pd.DataFrame,
    raw_usaspending_transactions: pd.DataFrame,
) -> Output[dict[str, pd.DataFrame]]:
    canonical = build_canonical_obligations(
        enriched_sbir_awards, enriched_sbir_awards, raw_usaspending_transactions
    )
    policy = LeverageRatioPolicy(
        include_sttr=config.include_sttr,
        match_confidence_threshold=config.match_confidence_threshold,
        fiscal_year_start=config.fiscal_year_start,
        fiscal_year_end=config.fiscal_year_end,
        dollar_basis=config.dollar_basis,
    )
    adjustment_factors = (
        pd.read_csv(config.adjustment_factors_path) if config.adjustment_factors_path else None
    )
    result = calculate_leverage_ratios(
        canonical, policy=policy, adjustment_factors=adjustment_factors
    )
    tables = {
        name: getattr(result, name)
        for name in ("company", "agency", "cohort", "fiscal_year", "quality")
    }
    output_dir = Path("data/processed/leverage_ratio")
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, table in tables.items():
        table.to_parquet(output_dir / f"{name}.parquet", index=False)
    method = f"Net USAspending obligations; threshold={config.match_confidence_threshold}; FY={config.fiscal_year_start or 'all'}-{config.fiscal_year_end or 'all'}; dollars={config.dollar_basis}; STTR included={config.include_sttr}."
    report = reconcile_nasem(result.agency, methodology=method)
    (output_dir / "nasem_reconciliation.json").write_text(json.dumps(report, indent=2))
    (output_dir / "nasem_reconciliation.md").write_text(reconciliation_markdown(report))
    return Output(
        tables,
        metadata={
            "agency_rows": len(result.agency),
            "company_rows": len(result.company),
            "quality": MetadataValue.json(result.quality.to_dict("records")[0]),
            "reconciliation": MetadataValue.json(report),
        },
    )
