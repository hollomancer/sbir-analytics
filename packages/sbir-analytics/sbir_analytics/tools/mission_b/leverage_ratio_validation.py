"""Independent validation, sensitivity, review, and gating for leverage ratios."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from itertools import product
from collections.abc import Iterable

import numpy as np
import pandas as pd

from .leverage_ratio import LeverageConfig, compute_leverage_ratio, prepare_obligations


@dataclass(frozen=True)
class ValidationThresholds:
    reconciliation_tolerance: float = 0.01
    minimum_match_quality_coverage: float = 0.8
    required_dimensions: tuple[str, ...] = ("company", "agency", "cohort", "headline")


@dataclass(frozen=True)
class ValidationCheck:
    name: str
    passed: bool
    observed: float | int | str
    expected: float | int | str
    detail: str


def validate_run(
    source: pd.DataFrame,
    outputs: dict[str, pd.DataFrame],
    config: LeverageConfig,
    thresholds: ValidationThresholds = ValidationThresholds(),
) -> list[ValidationCheck]:
    """Recompute invariants from source rows rather than trusting primary outputs."""
    prepared = prepare_obligations(source, config)
    headline = outputs.get("headline", pd.DataFrame())
    reported_num = float(headline["non_sbir_obligations"].sum()) if not headline.empty else np.nan
    reported_den = float(headline["sbir_sttr_obligations"].sum()) if not headline.empty else np.nan
    source_num = float(prepared.loc[prepared["numerator_eligible"], "analysis_amount"].sum())
    source_den = float(prepared.loc[prepared["denominator_eligible"], "analysis_amount"].sum())
    recon_error = max(abs(reported_num - source_num), abs(reported_den - source_den))

    sbir_in_numerator = int(
        (prepared["numerator_eligible"] & (prepared["is_sbir"] | prepared["is_sttr"])).sum()
    )
    duplicate_count = int(prepared["obligation_id"].duplicated(keep=False).sum())
    negative_source = float(prepared.loc[prepared["analysis_amount"] < 0, "analysis_amount"].sum())
    expected_negative = negative_source if config.include_negative_obligations else 0.0
    reported_total = reported_num + reported_den
    positive_total = float(prepared.loc[prepared["analysis_amount"] >= 0, "analysis_amount"].sum())
    negative_effect = reported_total - positive_total

    stable_errors: list[float] = []
    for dimension in ("company", "agency", "cohort"):
        aggregate = outputs.get(dimension, pd.DataFrame())
        aggregate_num = float(aggregate.get("non_sbir_obligations", pd.Series(dtype=float)).sum())
        aggregate_den = float(aggregate.get("sbir_sttr_obligations", pd.Series(dtype=float)).sum())
        stable_errors.extend([abs(aggregate_num - reported_num), abs(aggregate_den - reported_den)])
    stable_error = max(stable_errors)

    matched_at_threshold = source["canonical_company_id"].notna() & (
        source["match_confidence"] >= config.match_confidence_threshold
    )
    match_coverage = float(matched_at_threshold.sum() / max(len(source), 1))

    invalid_ratios = 0
    for output in outputs.values():
        ratio = output.get("leverage_ratio", pd.Series(dtype=float))
        denominator = output.get("sbir_sttr_obligations", pd.Series(dtype=float))
        invalid_ratios += int((ratio.isna() & (denominator > 0)).sum() + np.isinf(ratio).sum())

    checks = [
        ValidationCheck(
            "source_reconciliation",
            recon_error <= thresholds.reconciliation_tolerance,
            recon_error,
            thresholds.reconciliation_tolerance,
            "Headline numerator and denominator reconcile independently to filtered source records.",
        ),
        ValidationCheck(
            "no_sbir_in_non_sbir_numerator",
            sbir_in_numerator == 0,
            sbir_in_numerator,
            0,
            "SBIR and STTR flags are excluded from the non-SBIR numerator.",
        ),
        ValidationCheck(
            "no_duplicate_obligations_after_matching",
            duplicate_count == 0,
            duplicate_count,
            0,
            "Obligation IDs must remain unique after entity matching.",
        ),
        ValidationCheck(
            "deobligations_handled_as_configured",
            abs(negative_effect - expected_negative) <= thresholds.reconciliation_tolerance,
            negative_effect,
            expected_negative,
            "Negative obligations are retained or excluded according to the scenario.",
        ),
        ValidationCheck(
            "stable_aggregation_across_dimensions",
            stable_error <= thresholds.reconciliation_tolerance,
            stable_error,
            thresholds.reconciliation_tolerance,
            "Company, agency, and cohort totals each roll up exactly to headline totals.",
        ),
        ValidationCheck(
            "match_quality_coverage",
            match_coverage >= thresholds.minimum_match_quality_coverage,
            match_coverage,
            thresholds.minimum_match_quality_coverage,
            "Share of entity-linked source rows meeting the configured confidence threshold.",
        ),
        ValidationCheck(
            "required_output_dimensions",
            set(thresholds.required_dimensions).issubset(outputs),
            ",".join(sorted(outputs)),
            ",".join(thresholds.required_dimensions),
            "Required user-facing aggregation dimensions are present.",
        ),
        ValidationCheck(
            "no_unexplained_invalid_ratios",
            invalid_ratios == 0,
            invalid_ratios,
            0,
            "NaN is allowed only when the denominator is non-positive; infinity is never allowed.",
        ),
    ]
    return checks


def enforce_report_gate(checks: Iterable[ValidationCheck]) -> None:
    """Fail an asset/report refresh when any accepted-quality threshold is missed."""
    failures = [check for check in checks if not check.passed]
    if failures:
        details = "; ".join(
            f"{c.name}: observed={c.observed}, expected={c.expected}" for c in failures
        )
        raise ValueError(f"Leverage-ratio quality gate failed: {details}")


def run_sensitivity_analysis(
    source: pd.DataFrame,
    *,
    match_thresholds: Iterable[float] = (0.7, 0.8, 0.9),
    analysis_windows: Iterable[tuple[int | None, int | None]] = ((None, None), (2012, 2020)),
    inflation_adjusted: Iterable[bool] = (False, True),
    include_negative_obligations: Iterable[bool] = (True, False),
    sttr_treatments: Iterable[str] = ("include", "exclude"),
) -> pd.DataFrame:
    """Expose every methodology combination and its headline result."""
    rows: list[dict[str, object]] = []
    for threshold, window, real, negatives, sttr in product(
        match_thresholds,
        analysis_windows,
        inflation_adjusted,
        include_negative_obligations,
        sttr_treatments,
    ):
        config = LeverageConfig(threshold, window[0], window[1], real, negatives, sttr)  # type: ignore[arg-type]
        headline = compute_leverage_ratio(source, config)["headline"].iloc[0].to_dict()
        rows.append({**asdict(config), **headline})
    return pd.DataFrame(rows)


def sensitivity_summary(scenarios: pd.DataFrame) -> pd.DataFrame:
    """Report headline ranges overall and by each methodological choice."""
    dimensions = [
        "match_confidence_threshold",
        "start_fiscal_year",
        "end_fiscal_year",
        "inflation_adjusted",
        "include_negative_obligations",
        "sttr_treatment",
    ]
    rows = [
        {
            "choice": "all_scenarios",
            "value": "all",
            "ratio_min": scenarios["leverage_ratio"].min(),
            "ratio_max": scenarios["leverage_ratio"].max(),
            "scenario_count": len(scenarios),
        }
    ]
    for dimension in dimensions:
        for value, group in scenarios.groupby(dimension, dropna=False):
            rows.append(
                {
                    "choice": dimension,
                    "value": str(value),
                    "ratio_min": group["leverage_ratio"].min(),
                    "ratio_max": group["leverage_ratio"].max(),
                    "scenario_count": len(group),
                }
            )
    return pd.DataFrame(rows)


def build_stratified_review_sample(
    source: pd.DataFrame,
    company_results: pd.DataFrame,
    *,
    per_stratum: int = 5,
) -> pd.DataFrame:
    """Create deterministic high/low-leverage manual-review records with evidence references."""
    valid = company_results.dropna(subset=["leverage_ratio"]).sort_values(
        ["leverage_ratio", "canonical_company_id"]
    )
    low = valid.head(per_stratum).assign(review_stratum="low_leverage")
    high = valid.tail(per_stratum).assign(review_stratum="high_leverage")
    sample = pd.concat([low, high]).drop_duplicates("canonical_company_id")
    evidence = (
        source.groupby("canonical_company_id")["obligation_id"]
        .agg(lambda values: ",".join(map(str, sorted(set(values)))))
        .rename("evidence_obligation_ids")
    )
    sample = sample.merge(evidence, on="canonical_company_id", how="left")
    sample["review_status"] = "pending"
    sample["reviewer"] = ""
    sample["review_notes"] = ""
    sample["entity_match_confirmed"] = pd.NA
    sample["sbir_classification_confirmed"] = pd.NA
    sample["review_evidence_reference"] = sample["evidence_obligation_ids"].map(
        lambda ids: f"obligation_ids:{ids}"
    )
    return sample
