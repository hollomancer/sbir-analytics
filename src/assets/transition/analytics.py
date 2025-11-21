"""Transition analytics assets.

This module contains:
- transformed_transition_analytics: Compute transition analytics and insights
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .utils import (
    MetadataValue,
    Output,
    _ensure_parent_dir,
    _env_float,
    asset,
    now_utc_iso,
    write_json,
)


@asset(
    name="transformed_transition_analytics",
    group_name="transformation",
    compute_kind="pandas",
    description=(
        "Compute dual-perspective transition analytics (award/company rates, phase, agency) "
        "and emit a checks JSON for gating."
    ),
)
def transformed_transition_analytics(
    context,
    enriched_sbir_awards: pd.DataFrame,
    transformed_transition_scores: pd.DataFrame,
    validated_contracts_sample: pd.DataFrame | None = None,
) -> Output[str]:
    """
    Analyze transition candidates and awards to produce summary KPIs:
    - Award-level transition rate
    - Company-level transition rate
    - Phase effectiveness (I vs II)
    - By-agency transition rates
    - Optional: avg time-to-transition by agency (when dates are available)

    Writes:
      - data/processed/transition_analytics.json (summary)
      - data/processed/transition_analytics.checks.json (checks)
    """
    # Lazy import to keep module import-safe
    from src.transition.analysis.analytics import TransitionAnalytics  # noqa: WPS433

    score_threshold = _env_float("SBIR_ETL__TRANSITION__ANALYTICS__SCORE_THRESHOLD", 0.60)
    analytics = TransitionAnalytics(score_threshold=score_threshold)

    # Compute summary (contracts optional for time-to-transition metrics)
    summary = analytics.summarize(
        awards_df=enriched_sbir_awards,
        transitions_df=transformed_transition_scores,
        contracts_df=validated_contracts_sample,
    )

    # Persist summary JSON
    out_path = Path("data/processed/transition_analytics.json")
    _ensure_parent_dir(out_path)
    write_json(out_path, summary)

    # Build and write checks JSON
    award_rate = summary.get("award_transition_rate") or {}  # {"numerator","denominator","rate"}
    company_rate = summary.get("company_transition_rate") or {}
    checks = {
        "ok": True,
        "generated_at": now_utc_iso(),
        "score_threshold": float(score_threshold),
        "award_transition_rate": award_rate,
        "company_transition_rate": company_rate,
        "counts": {
            "total_awards": int(award_rate.get("denominator") or 0),
            "transitioned_awards": int(award_rate.get("numerator") or 0),
            "total_companies": int(company_rate.get("denominator") or 0),
            "companies_transitioned": int(company_rate.get("numerator") or 0),
        },
    }
    checks_path = out_path.with_suffix(".checks.json")
    write_json(checks_path, checks)

    meta = {
        "summary_path": str(out_path),
        "checks_path": str(checks_path),
        "award_transition_rate": MetadataValue.json(award_rate),
        "company_transition_rate": MetadataValue.json(company_rate),
    }
    context.log.info("Computed transition_analytics", extra=meta)
    return Output(str(out_path), metadata=meta)  # type: ignore[arg-type]


# -----------------------------
# Asset checks (import-safe shims)
# -----------------------------
