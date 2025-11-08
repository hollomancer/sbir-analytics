"""Transition asset checks.

This module contains quality checks for transition assets:
- contracts_sample_quality_check
- vendor_resolution_quality_check
- transition_scores_quality_check
- transition_analytics_quality_check
- transition_evidence_quality_check
- transition_detections_quality_check
"""

from __future__ import annotations

import pandas as pd

from .utils import (
    AssetCheckResult,
    AssetCheckSeverity,
    _env_bool,
    _env_float,
    _env_int,
    asset_check,
)


@asset_check(
    asset="validated_contracts_sample",
    description="Contracts sample thresholds: action_date ≥ 0.90, any identifier ≥ 0.60, sample size within configured range",
)
def contracts_sample_quality_check(validated_contracts_sample: pd.DataFrame) -> AssetCheckResult:
    total = len(validated_contracts_sample)
    date_cov = float(validated_contracts_sample["action_date"].notna().mean()) if total > 0 else 0.0
    ident_cov = (
        float(
            (
                (validated_contracts_sample.get("vendor_uei", pd.Series(dtype=object)).notna())
                | (validated_contracts_sample.get("vendor_duns", pd.Series(dtype=object)).notna())
                | (validated_contracts_sample.get("piid", pd.Series(dtype=object)).notna())
                | (validated_contracts_sample.get("fain", pd.Series(dtype=object)).notna())
            ).mean()
        )
        if total > 0
        else 0.0
    )
    min_date_cov = _env_float("SBIR_ETL__TRANSITION__CONTRACTS__DATE_COVERAGE_MIN", 0.90)
    min_ident_cov = _env_float("SBIR_ETL__TRANSITION__CONTRACTS__IDENT_COVERAGE_MIN", 0.60)
    min_size = _env_int("SBIR_ETL__TRANSITION__CONTRACTS__SAMPLE_SIZE_MIN", 1000)
    max_size = _env_int("SBIR_ETL__TRANSITION__CONTRACTS__SAMPLE_SIZE_MAX", 10000)
    size_ok = (total >= min_size) and (total <= max_size)
    enforce_size = _env_bool("SBIR_ETL__TRANSITION__CONTRACTS__ENFORCE_SAMPLE_SIZE", False)
    passed = (
        (date_cov >= min_date_cov)
        and (ident_cov >= min_ident_cov)
        and (size_ok if enforce_size else True)
    )
    return AssetCheckResult(
        passed=passed,
        severity=AssetCheckSeverity.ERROR if not passed else AssetCheckSeverity.WARN,
        description=(
            f"{'✓' if passed else '✗'} contracts_sample quality: "
            f"action_date={date_cov:.2%} (min {min_date_cov:.2%}), "
            f"any_identifier={ident_cov:.2%} (min {min_ident_cov:.2%}), "
            f"sample_size={total} (min {min_size}, max {max_size})"
        ),
        metadata={
            "total_rows": total,
            "action_date_coverage": f"{date_cov:.2%}",
            "any_identifier_coverage": f"{ident_cov:.2%}",
            "sample_size": {
                "value": total,
                "min": min_size,
                "max": max_size,
                "in_range": size_ok,
            },
            "thresholds": {
                "action_date_min": f"{min_date_cov:.2%}",
                "any_identifier_min": f"{min_ident_cov:.2%}",
                "sample_size_min": int(min_size),
                "sample_size_max": int(max_size),
            },
        },
    )


@asset_check(
    asset="enriched_vendor_resolution",
    description="Vendor resolution rate meets minimum threshold (default 60%)",
)
def vendor_resolution_quality_check(enriched_vendor_resolution: pd.DataFrame) -> AssetCheckResult:
    total = len(enriched_vendor_resolution)
    res_rate = (
        float((enriched_vendor_resolution["match_method"] != "unresolved").mean())
        if total > 0
        else 0.0
    )
    min_rate = _env_float("SBIR_ETL__TRANSITION__VENDOR_RESOLUTION__MIN_RATE", 0.60)
    passed = res_rate >= min_rate
    return AssetCheckResult(
        passed=passed,
        severity=AssetCheckSeverity.ERROR if not passed else AssetCheckSeverity.WARN,
        description=(
            f"{'✓' if passed else '✗'} vendor_resolution: "
            f"resolution_rate={res_rate:.2%} (min {min_rate:.2%})"
        ),
        metadata={
            "total_contracts": total,
            "resolution_rate": f"{res_rate:.2%}",
            "threshold": f"{min_rate:.2%}",
            "by_method": enriched_vendor_resolution["match_method"]
            .value_counts(dropna=False)
            .to_dict()
            if total > 0
            else {},
        },
    )


@asset_check(
    asset="transformed_transition_scores",
    description="Transition scores quality: schema fields, score bounds [0,1], and non-empty signals",
)
def transition_scores_quality_check(
    transformed_transition_scores: pd.DataFrame,
) -> AssetCheckResult:
    required_cols = ["award_id", "contract_id", "score", "method", "signals", "computed_at"]
    missing = [c for c in required_cols if c not in transformed_transition_scores.columns]
    total = len(transformed_transition_scores)

    # Validate score bounds and signals presence
    invalid_scores = 0
    empty_signals = 0
    if total > 0 and "score" in transformed_transition_scores.columns:
        s = pd.to_numeric(transformed_transition_scores["score"], errors="coerce")
        invalid_scores = int(((s < 0) | (s > 1) | (s.isna())).sum())

    if total > 0 and "signals" in transformed_transition_scores.columns:

        def _is_empty_signals(v):
            if v is None:
                return True
            if isinstance(v, list | tuple | set):
                return len(v) == 0
            # Strings or other scalars: consider empty only if len == 0
            try:
                return len(v) == 0
            except Exception:
                return False

        empty_signals = int(transformed_transition_scores["signals"].apply(_is_empty_signals).sum())
    else:
        # If signals column is absent, treat as fully empty
        empty_signals = total

    passed = (len(missing) == 0) and (invalid_scores == 0) and (empty_signals == 0)

    return AssetCheckResult(
        passed=passed,
        severity=AssetCheckSeverity.ERROR if not passed else AssetCheckSeverity.WARN,
        description=(
            f"{'✓' if passed else '✗'} transition_scores_v1 quality: "
            f"missing={len(missing)}, invalid_scores={invalid_scores}, empty_signals={empty_signals}"
        ),
        metadata={
            "total_rows": total,
            "missing_columns": missing,
            "invalid_score_count": invalid_scores,
            "empty_signals_count": empty_signals,
            "columns_present": list(transformed_transition_scores.columns),
        },
    )


@asset_check(
    asset="transformed_transition_analytics",
    description="Sanity checks for transition analytics: positive denominators and 0≤rates≤1 (optional min-rate thresholds via env).",
)
def transition_analytics_quality_check(context) -> AssetCheckResult:
    """
    Validate transition_analytics KPIs using the emitted checks JSON.

    Gates:
      - award/company denominators > 0
      - 0 <= award/company rates <= 1
      - optional minimum thresholds via:
          SBIR_ETL__TRANSITION__ANALYTICS__MIN_AWARD_RATE (default 0.0)
          SBIR_ETL__TRANSITION__ANALYTICS__MIN_COMPANY_RATE (default 0.0)
    """
    import json as _json
    from pathlib import Path as _Path

    checks_path = _Path("data/processed/transition_analytics.checks.json")
    if not checks_path.exists():
        desc = "Missing transition_analytics.checks.json; analytics asset may not have run."
        context.log.error(desc)
        return AssetCheckResult(
            passed=False,
            severity=AssetCheckSeverity.ERROR,
            description=desc,
            metadata={"checks_path": str(checks_path), "reason": "missing_checks"},
        )

    try:
        payload = _json.loads(checks_path.read_text(encoding="utf-8"))
    except Exception as exc:
        desc = f"Failed to read analytics checks JSON: {exc}"
        context.log.error(desc)
        return AssetCheckResult(
            passed=False,
            severity=AssetCheckSeverity.ERROR,
            description=desc,
            metadata={"checks_path": str(checks_path), "reason": "read_error"},
        )

    award = payload.get("award_transition_rate") or {}
    company = payload.get("company_transition_rate") or {}

    def _safe_int(v, default=0):
        try:
            return int(v)
        except Exception:
            return default

    def _safe_float(v, default=0.0):
        try:
            return float(v)
        except Exception:
            return default

    a_num = _safe_int(award.get("numerator"))
    a_den = _safe_int(award.get("denominator"))
    a_rate = _safe_float(award.get("rate"))
    c_num = _safe_int(company.get("numerator"))
    c_den = _safe_int(company.get("denominator"))
    c_rate = _safe_float(company.get("rate"))

    # Basic sanity
    denom_ok = (a_den > 0) and (c_den > 0)
    rate_bounds_ok = (0.0 <= a_rate <= 1.0) and (0.0 <= c_rate <= 1.0)

    # Optional minimum thresholds
    min_award_rate = _env_float("SBIR_ETL__TRANSITION__ANALYTICS__MIN_AWARD_RATE", 0.0)
    min_company_rate = _env_float("SBIR_ETL__TRANSITION__ANALYTICS__MIN_COMPANY_RATE", 0.0)
    min_ok = (a_rate >= min_award_rate) and (c_rate >= min_company_rate)

    passed = denom_ok and rate_bounds_ok and min_ok

    return AssetCheckResult(
        passed=passed,
        severity=AssetCheckSeverity.ERROR if not passed else AssetCheckSeverity.WARN,
        description=(
            f"{'✓' if passed else '✗'} transition_analytics: "
            f"award_rate={a_rate:.2%} (den={a_den}, min {min_award_rate:.2%}), "
            f"company_rate={c_rate:.2%} (den={c_den}, min {min_company_rate:.2%})"
        ),
        metadata={
            "checks_path": str(checks_path),
            "award": {"num": a_num, "den": a_den, "rate": a_rate},
            "company": {"num": c_num, "den": c_den, "rate": c_rate},
            "thresholds": {
                "min_award_rate": min_award_rate,
                "min_company_rate": min_company_rate,
            },
            "sanity": {
                "denominators_positive": denom_ok,
                "rates_within_0_1": rate_bounds_ok,
            },
        },
    )


@asset_check(
    asset="transformed_transition_evidence",
    description="Evidence completeness for candidates with score ≥ configured threshold",
)
def transition_evidence_quality_check(context) -> AssetCheckResult:
    """
    Check evidence completeness by consuming the checks JSON emitted by transition_evidence_v1.

    Passes when all candidates with score >= threshold have an evidence row.
    """
    import json as _json
    from pathlib import Path as _Path

    checks_path = _Path("data/processed/transitions_evidence.checks.json")
    if not checks_path.exists():
        desc = "Missing transitions_evidence.checks.json; evidence asset may not have run."
        context.log.error(desc)
        return AssetCheckResult(
            passed=False,
            severity=AssetCheckSeverity.ERROR,
            description=desc,
            metadata={"checks_path": str(checks_path), "reason": "missing_checks"},
        )

    try:
        payload = _json.loads(checks_path.read_text(encoding="utf-8"))
    except Exception as exc:
        desc = f"Failed to read evidence checks JSON: {exc}"
        context.log.error(desc)
        return AssetCheckResult(
            passed=False,
            severity=AssetCheckSeverity.ERROR,
            description=desc,
            metadata={"checks_path": str(checks_path), "reason": "read_error"},
        )

    comp = payload.get("completeness", {}) or {}
    complete = bool(comp.get("complete", False))
    threshold = comp.get("threshold")
    num_above = comp.get("candidates_above_threshold")
    ev_rows = comp.get("evidence_rows_for_above_threshold")

    return AssetCheckResult(
        passed=complete,
        severity=AssetCheckSeverity.ERROR if not complete else AssetCheckSeverity.WARN,
        description=(
            f"{'✓' if complete else '✗'} evidence completeness: "
            f"{ev_rows}/{num_above} candidates at≥{threshold}"
        ),
        metadata={
            "checks_path": str(checks_path),
            "threshold": threshold,
            "candidates_above_threshold": num_above,
            "evidence_rows_for_above_threshold": ev_rows,
            "complete": complete,
        },
    )


@asset_check(
    asset="transformed_transition_detections",
    description=(
        "Transition detections quality: required columns present, score bounds [0,1], "
        "and minimum valid/high-confidence rates."
    ),
)
def transition_detections_quality_check(
    transition_detections: pd.DataFrame,
) -> AssetCheckResult:
    """
    Validate consolidated transition detections.

    Gates:
      - Required columns present: award_id, contract_id, score, method, computed_at
      - 0 <= score <= 1 and non-null
      - Valid row rate >= SBIR_ETL__TRANSITION__DETECTIONS__MIN_VALID_RATE (default: 0.99)
      - Optional high-confidence rate gate: share with score >= threshold
        is >= SBIR_ETL__TRANSITION__DETECTIONS__MIN_HIGHCONF_RATE (default: 0.0)
        where threshold = SBIR_ETL__TRANSITION__ANALYTICS__SCORE_THRESHOLD (default: 0.60)
    """
    # Required schema
    required_cols = ["award_id", "contract_id", "score", "method", "computed_at"]
    missing = [c for c in required_cols if c not in transition_detections.columns]
    total = int(len(transition_detections))

    # Score bounds and validity
    if total > 0 and "score" in transition_detections.columns:
        s = pd.to_numeric(transition_detections["score"], errors="coerce")
        out_of_bounds = int(((s < 0) | (s > 1) | (s.isna())).sum())
    else:
        # If empty or missing score column, treat all as out-of-bounds
        out_of_bounds = total

    # Valid row definition
    def _nonnull(col: str) -> pd.Series:
        return transition_detections.get(col, pd.Series(dtype=object)).notna()

    if total > 0:
        s = pd.to_numeric(
            transition_detections.get("score", pd.Series(dtype=float)), errors="coerce"
        )
        valid_mask = (
            _nonnull("award_id")
            & _nonnull("contract_id")
            & _nonnull("method")
            & s.notna()
            & (s >= 0)
            & (s <= 1)
        )
        valid_rate = float(valid_mask.mean())
    else:
        valid_rate = 0.0

    # High-confidence rate (optional gate)
    score_threshold = _env_float("SBIR_ETL__TRANSITION__ANALYTICS__SCORE_THRESHOLD", 0.60)
    if total > 0 and "score" in transition_detections.columns:
        s = pd.to_numeric(transition_detections["score"], errors="coerce").fillna(-1.0)
        highconf_rate = float((s >= score_threshold).mean())
    else:
        highconf_rate = 0.0

    # Thresholds
    min_valid_rate = _env_float("SBIR_ETL__TRANSITION__DETECTIONS__MIN_VALID_RATE", 0.99)
    min_highconf_rate = _env_float("SBIR_ETL__TRANSITION__DETECTIONS__MIN_HIGHCONF_RATE", 0.0)

    passed = (
        (len(missing) == 0)
        and (out_of_bounds == 0)
        and (valid_rate >= min_valid_rate)
        and (highconf_rate >= min_highconf_rate)
    )

    return AssetCheckResult(
        passed=passed,
        severity=AssetCheckSeverity.ERROR if not passed else AssetCheckSeverity.WARN,
        description=(
            f"{'✓' if passed else '✗'} transition_detections quality: "
            f"missing_cols={len(missing)}, score_out_of_bounds={out_of_bounds}, "
            f"valid_rate={valid_rate:.2%} (min {min_valid_rate:.2%}), "
            f"highconf_rate={highconf_rate:.2%} (min {min_highconf_rate:.2%}, "
            f"threshold {score_threshold:.2f})"
        ),
        metadata={
            "total_rows": total,
            "missing_columns": missing,
            "score_out_of_bounds": out_of_bounds,
            "rates": {
                "valid_rate": valid_rate,
                "min_valid_rate": min_valid_rate,
                "highconf_rate": highconf_rate,
                "min_highconf_rate": min_highconf_rate,
                "score_threshold": score_threshold,
            },
            "columns_present": list(transition_detections.columns),
        },
    )


