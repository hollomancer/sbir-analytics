"""Primary federal-to-SBIR leverage-ratio computation.

Validation, sensitivity analysis, and report gates intentionally live in
``leverage_ratio_validation`` so the primary calculation remains small and auditable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd


STTRTreatment = Literal["include", "exclude"]


@dataclass(frozen=True)
class LeverageConfig:
    """Method choices that define one reproducible leverage-ratio run."""

    match_confidence_threshold: float = 0.8
    start_fiscal_year: int | None = None
    end_fiscal_year: int | None = None
    inflation_adjusted: bool = False
    include_negative_obligations: bool = True
    sttr_treatment: STTRTreatment = "include"

    @property
    def scenario_id(self) -> str:
        window = f"{self.start_fiscal_year or 'all'}-{self.end_fiscal_year or 'all'}"
        dollars = "real" if self.inflation_adjusted else "nominal"
        negatives = "with-neg" if self.include_negative_obligations else "no-neg"
        return (
            f"match-{self.match_confidence_threshold:g}__window-{window}__{dollars}__"
            f"{negatives}__sttr-{self.sttr_treatment}"
        )


REQUIRED_SOURCE_COLUMNS = {
    "obligation_id",
    "canonical_company_id",
    "agency",
    "fiscal_year",
    "obligation_amount",
    "is_sbir",
    "is_sttr",
    "match_confidence",
}


def prepare_obligations(source: pd.DataFrame, config: LeverageConfig) -> pd.DataFrame:
    """Apply the stated methodology without silently deduplicating source records."""
    missing = REQUIRED_SOURCE_COLUMNS - set(source.columns)
    if missing:
        raise ValueError(f"Missing required leverage source columns: {sorted(missing)}")

    frame = source.copy()
    frame["obligation_amount"] = pd.to_numeric(frame["obligation_amount"], errors="coerce")
    frame = frame[frame["match_confidence"] >= config.match_confidence_threshold]
    if config.start_fiscal_year is not None:
        frame = frame[frame["fiscal_year"] >= config.start_fiscal_year]
    if config.end_fiscal_year is not None:
        frame = frame[frame["fiscal_year"] <= config.end_fiscal_year]
    if not config.include_negative_obligations:
        frame = frame[frame["obligation_amount"] >= 0]
    if config.sttr_treatment == "exclude":
        frame = frame[~frame["is_sttr"].fillna(False).astype(bool)]

    if config.inflation_adjusted:
        if "inflation_factor" not in frame:
            raise ValueError("inflation_factor is required for inflation-adjusted runs")
        frame["analysis_amount"] = frame["obligation_amount"] * frame["inflation_factor"]
    else:
        frame["analysis_amount"] = frame["obligation_amount"]

    is_sbir = frame["is_sbir"].fillna(False).astype(bool)
    is_sttr = frame["is_sttr"].fillna(False).astype(bool)
    frame["is_sbir"] = is_sbir
    frame["is_sttr"] = is_sttr
    frame["denominator_eligible"] = is_sbir | (is_sttr & (config.sttr_treatment == "include"))
    # STTR is never allowed to leak into non-SBIR, even when excluded from the denominator.
    frame["numerator_eligible"] = ~(is_sbir | is_sttr)
    return frame


def _aggregate(frame: pd.DataFrame, dimensions: list[str]) -> pd.DataFrame:
    work = frame.assign(
        numerator_amount=frame["analysis_amount"].where(frame["numerator_eligible"], 0.0),
        denominator_amount=frame["analysis_amount"].where(frame["denominator_eligible"], 0.0),
    )
    grouped = work.groupby(dimensions, dropna=False, as_index=False).agg(
        non_sbir_obligations=("numerator_amount", "sum"),
        sbir_sttr_obligations=("denominator_amount", "sum"),
        obligation_count=("obligation_id", "count"),
    )
    grouped["leverage_ratio"] = np.where(
        grouped["sbir_sttr_obligations"] > 0,
        grouped["non_sbir_obligations"] / grouped["sbir_sttr_obligations"],
        np.nan,
    )
    return grouped


def compute_leverage_ratio(
    source: pd.DataFrame, config: LeverageConfig = LeverageConfig()
) -> dict[str, pd.DataFrame]:
    """Compute company, agency, cohort, and headline aggregates for one configuration."""
    frame = prepare_obligations(source, config)
    if "cohort_year" not in frame:
        frame["cohort_year"] = frame.groupby("canonical_company_id")["fiscal_year"].transform("min")
    outputs = {
        "company": _aggregate(frame, ["canonical_company_id"]),
        "agency": _aggregate(frame, ["agency"]),
        "cohort": _aggregate(frame, ["cohort_year"]),
    }
    headline_source = frame.assign(headline="all")
    outputs["headline"] = _aggregate(headline_source, ["headline"])
    for output in outputs.values():
        output["scenario_id"] = config.scenario_id
    return outputs
