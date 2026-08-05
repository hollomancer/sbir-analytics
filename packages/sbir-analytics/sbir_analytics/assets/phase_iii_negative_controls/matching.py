"""Deterministic exact matching and covariate-balance diagnostics."""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Any

import pandas as pd

from .covariates import MATCH_COVARIATES, CovariateInputError


BALANCE_FLAG = 0.1
CONTROLS_PER_TREATED = 3


def _require_matchable(frame: pd.DataFrame, *, label: str) -> pd.DataFrame:
    required = {"firm_id", "match_eligible", *MATCH_COVARIATES}
    if missing := sorted(required - set(frame.columns)):
        raise CovariateInputError(f"{label} is missing required columns: {missing}")
    if frame["firm_id"].astype(str).duplicated().any():
        raise CovariateInputError(f"{label}.firm_id must be unique")
    matchable = frame.loc[frame["match_eligible"].eq(True)].copy()  # noqa: E712
    if matchable.loc[:, list(MATCH_COVARIATES)].isna().any(axis=None):
        raise CovariateInputError(f"{label} marks a row match-eligible with a missing covariate")
    return matchable.sort_values("firm_id", kind="stable").reset_index(drop=True)


def exact_match_controls(
    treated: pd.DataFrame,
    controls: pd.DataFrame,
    *,
    controls_per_treated: int = CONTROLS_PER_TREATED,
) -> pd.DataFrame:
    """Match without replacement, maximizing one control before adding seconds or thirds."""

    if controls_per_treated != CONTROLS_PER_TREATED:
        raise CovariateInputError(
            f"the frozen design requires exactly up to {CONTROLS_PER_TREATED} controls"
        )
    treated_matchable = _require_matchable(treated, label="treated covariates")
    control_matchable = _require_matchable(controls, label="control covariates")
    buckets: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in control_matchable.itertuples(index=False):
        buckets[tuple(getattr(row, column) for column in MATCH_COVARIATES)].append(
            {
                "firm_id": row.firm_id,
                **{column: getattr(row, column) for column in MATCH_COVARIATES},
            }
        )

    treated_buckets: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in treated_matchable.itertuples(index=False):
        treated_buckets[tuple(getattr(row, column) for column in MATCH_COVARIATES)].append(
            {
                "firm_id": row.firm_id,
                **{column: getattr(row, column) for column in MATCH_COVARIATES},
            }
        )

    rows: list[dict[str, Any]] = []
    for stratum in sorted(treated_buckets, key=lambda value: tuple(map(str, value))):
        treated_rows = treated_buckets[stratum]
        control_rows = buckets.get(stratum, [])
        allocations: dict[str, list[dict[str, Any]]] = {row["firm_id"]: [] for row in treated_rows}
        control_index = 0
        for _slot in range(controls_per_treated):
            for treated_row in treated_rows:
                if control_index >= len(control_rows):
                    break
                allocations[treated_row["firm_id"]].append(control_rows[control_index])
                control_index += 1
            if control_index >= len(control_rows):
                break
        for treated_row in treated_rows:
            treated_id = treated_row["firm_id"]
            for slot, control_row in enumerate(allocations[treated_id], start=1):
                rows.append(
                    {
                        "treated_firm_id": treated_id,
                        "control_firm_id": control_row["firm_id"],
                        "control_slot": slot,
                        **{f"treated_{column}": treated_row[column] for column in MATCH_COVARIATES},
                        **{f"control_{column}": control_row[column] for column in MATCH_COVARIATES},
                    }
                )
    return pd.DataFrame.from_records(
        rows,
        columns=(
            "treated_firm_id",
            "control_firm_id",
            "control_slot",
            *(f"treated_{column}" for column in MATCH_COVARIATES),
            *(f"control_{column}" for column in MATCH_COVARIATES),
        ),
    )


def summarize_matching(treated: pd.DataFrame, pairs: pd.DataFrame) -> pd.DataFrame:
    """Return all four possible matched-control counts, including zero."""

    _require_matchable(treated, label="treated covariates")
    counts = pairs["treated_firm_id"].value_counts() if not pairs.empty else pd.Series(dtype=int)
    matchable_ids = set(treated.loc[treated["match_eligible"].eq(True), "firm_id"])  # noqa: E712
    return pd.DataFrame(
        {
            "matched_control_count": range(CONTROLS_PER_TREATED + 1),
            "treated_firms": [
                sum(int(counts.get(firm_id, 0)) == count for firm_id in matchable_ids)
                for count in range(CONTROLS_PER_TREATED + 1)
            ],
        }
    )


def _smd(treated: pd.Series, controls: pd.Series) -> float:
    treated_numeric: Any = pd.to_numeric(treated, errors="raise").astype(float)
    control_numeric: Any = pd.to_numeric(controls, errors="raise").astype(float)
    difference = float(treated_numeric.mean() - control_numeric.mean())
    pooled_variance = float((treated_numeric.var(ddof=1) + control_numeric.var(ddof=1)) / 2)
    if math.isclose(difference, 0.0, abs_tol=1e-15):
        return 0.0
    return (
        math.copysign(math.inf, difference)
        if pooled_variance <= 0
        else difference / math.sqrt(pooled_variance)
    )


def build_balance_table(pairs: pd.DataFrame) -> pd.DataFrame:
    """Report numeric and level-wise categorical SMDs on the matched pair expansion."""

    required = {
        "treated_firm_id",
        "control_firm_id",
        *(f"treated_{column}" for column in MATCH_COVARIATES),
        *(f"control_{column}" for column in MATCH_COVARIATES),
    }
    if missing := sorted(required - set(pairs.columns)):
        raise CovariateInputError(f"matched pairs are missing required columns: {missing}")
    if pairs.empty:
        return pd.DataFrame(
            columns=(
                "covariate",
                "level",
                "treated_value",
                "control_value",
                "standardized_mean_difference",
                "absolute_smd",
                "flagged_above_0_1",
            )
        )
    rows: list[dict[str, Any]] = []
    for covariate in MATCH_COVARIATES:
        if covariate == "first_contract_year":
            treated_values = pairs[f"treated_{covariate}"]
            control_values = pairs[f"control_{covariate}"]
            smd = _smd(treated_values, control_values)
            rows.append(
                {
                    "covariate": covariate,
                    "level": None,
                    "treated_value": float(treated_values.mean()),
                    "control_value": float(control_values.mean()),
                    "standardized_mean_difference": smd,
                    "absolute_smd": abs(smd),
                    "flagged_above_0_1": abs(smd) > BALANCE_FLAG,
                }
            )
            continue
        levels = sorted(
            set(pairs[f"treated_{covariate}"].astype(str))
            | set(pairs[f"control_{covariate}"].astype(str))
        )
        for level in levels:
            treated_indicator = pairs[f"treated_{covariate}"].astype(str).eq(level).astype(float)
            control_indicator = pairs[f"control_{covariate}"].astype(str).eq(level).astype(float)
            smd = _smd(treated_indicator, control_indicator)
            rows.append(
                {
                    "covariate": covariate,
                    "level": level,
                    "treated_value": float(treated_indicator.mean()),
                    "control_value": float(control_indicator.mean()),
                    "standardized_mean_difference": smd,
                    "absolute_smd": abs(smd),
                    "flagged_above_0_1": abs(smd) > BALANCE_FLAG,
                }
            )
    return pd.DataFrame.from_records(rows)


def require_covariate_balance(balance: pd.DataFrame) -> None:
    """Stop before outcomes when any pre-authorized balance flag is raised."""

    if "flagged_above_0_1" not in balance.columns:
        raise CovariateInputError("balance table is missing flagged_above_0_1")
    if balance.empty:
        raise CovariateInputError("no matched pairs are available for a balance assessment")
    if balance["flagged_above_0_1"].eq(True).any():  # noqa: E712
        raise CovariateInputError("matched covariate balance exceeds the approved 0.1 SMD flag")


__all__ = [
    "BALANCE_FLAG",
    "CONTROLS_PER_TREATED",
    "build_balance_table",
    "exact_match_controls",
    "require_covariate_balance",
    "summarize_matching",
]
