"""NASEM benchmark reconciliation for leverage-ratio results."""

from __future__ import annotations

import math

import pandas as pd

NASEM_DOD_BENCHMARK = 4.0

# Agency identifiers that should be treated as DOD for reconciliation purposes.
# Includes the USAspending agency code (9700), common name variants, and the
# top-level abbreviation. Match is case-insensitive against an uppercase string.
_DOD_NAME_PATTERN = (
    r"\bDOD\b"
    r"|\bDEPARTMENT OF DEFENSE\b"
    r"|\bDEPT(\.|\s)+OF\s+DEFENSE\b"
    r"|\bDEFENSE\s+DEPARTMENT\b"
)
_DOD_CODE_PATTERN = r"^9700$"


def _sum_dod_rows(agency_results: pd.DataFrame) -> tuple[float | None, int]:
    """Return (observed_ratio, n_dod_rows) by summing numerator/denominator across all
    DOD-matching rows. Avoids order-dependent ``iloc[0]`` selection and handles the case
    where DOD shows up under multiple codes/names in the same frame.
    """
    if agency_results.empty:
        return None, 0

    # Build a case-insensitive agency label for matching name variants.
    name_haystack = agency_results.get("agency", pd.Series(dtype=object)).astype(str).str.upper()

    # Code matching: 9700 is the USAspending agency code for DoD. Optional column.
    code_col = "agency_code" if "agency_code" in agency_results.columns else None
    code_match = (
        agency_results[code_col].astype(str).str.match(_DOD_CODE_PATTERN, na=False)
        if code_col
        else pd.Series(False, index=agency_results.index)
    )

    name_match = name_haystack.str.contains(_DOD_NAME_PATTERN, regex=True, na=False)
    is_dod = (name_match | code_match).fillna(False)

    dod_rows = agency_results.loc[is_dod]
    if dod_rows.empty:
        return None, 0

    # Sum numerator and denominator across all DOD-matching rows; compute ratio once.
    # Falls back to ``leverage_ratio`` column if numerator/denominator aren't surfaced
    # at the agency level (kept for backward compatibility with older fixtures).
    if {"non_sbir_amount", "sbir_amount"}.issubset(dod_rows.columns):
        num = float(dod_rows["non_sbir_amount"].fillna(0).sum())
        den = float(dod_rows["sbir_amount"].fillna(0).sum())
        if den <= 0:
            return None, int(len(dod_rows))
        return num / den, int(len(dod_rows))

    # Backward-compatible fallback: aggregate the per-row ratio when raw amounts
    # aren't present. Weights by amount when sbir_amount is available, otherwise
    # straight mean. This branch is least-correct but better than dod.iloc[0].
    if "sbir_amount" in dod_rows.columns and (dod_rows["sbir_amount"].fillna(0) > 0).any():
        weights = dod_rows["sbir_amount"].fillna(0).clip(lower=0)
        if weights.sum() <= 0:
            return None, int(len(dod_rows))
        weighted = (dod_rows["leverage_ratio"].fillna(0) * weights).sum() / weights.sum()
        return float(weighted), int(len(dod_rows))

    ratios = dod_rows["leverage_ratio"].dropna()
    if ratios.empty:
        return None, int(len(dod_rows))
    return float(ratios.mean()), int(len(dod_rows))


def reconcile_nasem(agency_results: pd.DataFrame, *, methodology: str) -> dict[str, object]:
    """Return a structured comparison that separates methods from implementation errors."""
    observed, n_dod_rows = _sum_dod_rows(agency_results)
    delta = None if observed is None else observed - NASEM_DOD_BENCHMARK
    return {
        "benchmark": NASEM_DOD_BENCHMARK,
        "observed": observed,
        "delta": delta,
        "methodology": methodology,
        "n_dod_rows_matched": n_dod_rows,
        "methodological_differences": [
            "Pipeline uses transaction-level net obligations, including de-obligations.",
            "Pipeline includes only entity matches at or above the configured confidence threshold.",
            "Pipeline cohort and fiscal-year windows are explicit run parameters.",
            "NASEM's published 4:1 benchmark is treated as a comparison point, not a test oracle.",
        ],
        "implementation_error": bool(observed is not None and (not math.isfinite(observed))),
        "interpretation": "Unavailable"
        if observed is None
        else f"Pipeline yields {observed:.2f}:1 versus NASEM 4:1; the {delta:+.2f} difference requires methodological reconciliation.",
    }


def _ratio_cell(value: object) -> str:
    """Render a ratio value as a markdown table cell, returning ``N/A`` for None/NaN."""
    if value is None:
        return "N/A"
    if isinstance(value, float) and not math.isfinite(value):
        return "N/A"
    if isinstance(value, (int, float)):
        return f"{float(value):.2f}:1"
    return str(value)


def _delta_cell(value: object) -> str:
    """Render a delta value as a markdown table cell with sign, ``N/A`` for None/NaN."""
    if value is None:
        return "N/A"
    if isinstance(value, float) and not math.isfinite(value):
        return "N/A"
    if isinstance(value, (int, float)):
        return f"{float(value):+.2f}"
    return str(value)


def reconciliation_markdown(report: dict[str, object]) -> str:
    differences = "\n".join(f"- {item}" for item in report["methodological_differences"])
    # Pre-format display cells so ``None``/NaN render as ``N/A`` rather than the
    # literal token ``None:1``.
    benchmark_cell = _ratio_cell(report["benchmark"])
    observed_cell = _ratio_cell(report["observed"])
    delta_cell = _delta_cell(report["delta"])
    return f"""# DOD Leverage Ratio Reproducibility Report

## Gate statement

{report["interpretation"]}

## Comparison

| Measure | Ratio |
|---|---:|
| NASEM benchmark | {benchmark_cell} |
| Pipeline result | {observed_cell} |
| Difference | {delta_cell} |

## Pipeline method

{report["methodology"]}

## Methodological differences

{differences}

## Implementation-error check

`implementation_error={str(report["implementation_error"]).lower()}`. A benchmark difference alone is not classified as an implementation error.
"""
