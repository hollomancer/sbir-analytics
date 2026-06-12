"""NASEM benchmark reconciliation for leverage-ratio results."""

from __future__ import annotations

import math

import pandas as pd

NASEM_DOD_BENCHMARK = 4.0


def reconcile_nasem(agency_results: pd.DataFrame, *, methodology: str) -> dict[str, object]:
    """Return a structured comparison that separates methods from implementation errors."""
    agency = agency_results["agency"].astype(str).str.upper()
    dod = agency_results[agency.str.contains(r"\bDOD\b|DEPARTMENT OF DEFENSE", regex=True)]
    observed = (
        None
        if dod.empty or pd.isna(dod.iloc[0]["leverage_ratio"])
        else float(dod.iloc[0]["leverage_ratio"])
    )
    delta = None if observed is None else observed - NASEM_DOD_BENCHMARK
    return {
        "benchmark": NASEM_DOD_BENCHMARK,
        "observed": observed,
        "delta": delta,
        "methodology": methodology,
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


def reconciliation_markdown(report: dict[str, object]) -> str:
    differences = "\n".join(f"- {item}" for item in report["methodological_differences"])
    return f"""# DOD Leverage Ratio Reproducibility Report

## Gate statement

{report["interpretation"]}

## Comparison

| Measure | Ratio |
|---|---:|
| NASEM benchmark | {report["benchmark"]}:1 |
| Pipeline result | {report["observed"]}:1 |
| Difference | {report["delta"]} |

## Pipeline method

{report["methodology"]}

## Methodological differences

{differences}

## Implementation-error check

`implementation_error={str(report["implementation_error"]).lower()}`. A benchmark difference alone is not classified as an implementation error.
"""
