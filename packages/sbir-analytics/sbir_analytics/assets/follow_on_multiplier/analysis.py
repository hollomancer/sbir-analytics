"""Pure, deterministic follow-on funding multiplier calculations over canonical obligation rows.

The follow-on funding multiplier (sometimes called the *leverage ratio* in NASEM's reviews of
DoD SBIR) is the dollar of non-SBIR federal obligations per dollar of SBIR/STTR investment for
SBIR-recipient firms.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


CANONICAL_COLUMNS = (
    "obligation_id",
    "company_id",
    "agency",
    "fiscal_year",
    "obligation_amount",
    "is_sbir",
    "match_confidence",
    "cohort_year",
    "firm_size",
    "technology_area",
    "experience",
)


@dataclass(frozen=True)
class FollowOnMultiplierPolicy:
    """Explicit semantics for a follow-on funding multiplier run.

    Amounts are net obligations: negative transactions/de-obligations are retained.
    Multipliers with a non-positive SBIR denominator are undefined (``pd.NA``).
    """

    include_sttr: bool = True
    match_confidence_threshold: float = 0.80
    fiscal_year_start: int | None = None
    fiscal_year_end: int | None = None
    dollar_basis: str = "nominal"

    def __post_init__(self) -> None:
        if not 0 <= self.match_confidence_threshold <= 1:
            raise ValueError("match_confidence_threshold must be between 0 and 1")
        if self.dollar_basis not in {"nominal", "adjusted"}:
            raise ValueError("dollar_basis must be 'nominal' or 'adjusted'")


@dataclass(frozen=True)
class FollowOnMultiplierResult:
    company: pd.DataFrame
    agency: pd.DataFrame
    cohort: pd.DataFrame
    fiscal_year: pd.DataFrame
    quality: pd.DataFrame


def _as_bool(values: pd.Series) -> pd.Series:
    if pd.api.types.is_bool_dtype(values.dtype):
        return values.fillna(False).astype(bool)
    return values.astype(str).str.strip().str.lower().isin({"true", "1", "yes", "y"})


def _safe_ratio(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    return (numerator / denominator).where(denominator > 0, pd.NA).astype("Float64")


def _aggregate(rows: pd.DataFrame, dimensions: list[str]) -> pd.DataFrame:
    # ``rows`` arrives already filtered to ``accepted_match == True`` (see
    # calculate_follow_on_multipliers), so per-stratum ``matched_record_count`` would
    # always equal ``record_count`` and adds no information. Match-coverage stats
    # are surfaced at the run level via the ``quality`` DataFrame.
    columns = dimensions + [
        "sbir_funding_denominator",
        "non_sbir_obligations_numerator",
        "follow_on_multiplier",
        "record_count",
        "company_count",
        "mean_match_confidence",
        "min_match_confidence",
    ]
    if rows.empty:
        return pd.DataFrame(columns=columns)
    grouped = rows.groupby(dimensions, dropna=False, sort=True)
    output = grouped.agg(
        sbir_funding_denominator=("sbir_amount", "sum"),
        non_sbir_obligations_numerator=("non_sbir_amount", "sum"),
        record_count=("obligation_id", "count"),
        company_count=("company_id", "nunique"),
        mean_match_confidence=("match_confidence", "mean"),
        min_match_confidence=("match_confidence", "min"),
    ).reset_index()
    output["follow_on_multiplier"] = _safe_ratio(
        output["non_sbir_obligations_numerator"], output["sbir_funding_denominator"]
    )
    return output[columns]


def calculate_follow_on_multipliers(
    obligations: pd.DataFrame,
    *,
    policy: FollowOnMultiplierPolicy = FollowOnMultiplierPolicy(),
    adjustment_factors: pd.DataFrame | None = None,
) -> FollowOnMultiplierResult:
    """Calculate traceable company, agency, cohort, and fiscal-year follow-on funding multipliers.

    ``obligations`` must be canonical, transaction-level rows. Unmatched and low-confidence
    rows are retained in the quality table but excluded from multiplier calculations.
    """

    missing = sorted(set(CANONICAL_COLUMNS) - set(obligations.columns))
    if missing:
        raise ValueError(f"Missing canonical obligation columns: {', '.join(missing)}")
    rows = obligations.copy()
    rows["obligation_amount"] = pd.to_numeric(rows["obligation_amount"], errors="coerce").fillna(
        0.0
    )
    rows["match_confidence"] = pd.to_numeric(rows["match_confidence"], errors="coerce")
    rows["is_sbir"] = _as_bool(rows["is_sbir"])
    rows["fiscal_year"] = pd.to_numeric(rows["fiscal_year"], errors="coerce").astype("Int64")
    if policy.fiscal_year_start is not None:
        rows = rows[rows["fiscal_year"] >= policy.fiscal_year_start]
    if policy.fiscal_year_end is not None:
        rows = rows[rows["fiscal_year"] <= policy.fiscal_year_end]
    if not policy.include_sttr and "program" in rows:
        rows = rows[rows["program"].astype(str).str.upper() != "STTR"]

    rows["accepted_match"] = rows["company_id"].notna() & (
        rows["match_confidence"] >= policy.match_confidence_threshold
    )
    quality = pd.DataFrame(
        [
            {
                "input_record_count": int(len(rows)),
                "matched_record_count": int(rows["accepted_match"].sum()),
                "excluded_record_count": int((~rows["accepted_match"]).sum()),
                "matched_company_count": int(
                    rows.loc[rows["accepted_match"], "company_id"].nunique()
                ),
                "match_rate": float(rows["accepted_match"].mean()) if len(rows) else 0.0,
                "match_confidence_threshold": policy.match_confidence_threshold,
                "dollar_basis": policy.dollar_basis,
                "fiscal_year_start": policy.fiscal_year_start,
                "fiscal_year_end": policy.fiscal_year_end,
            }
        ]
    )
    rows = rows[rows["accepted_match"]].copy()
    # The agency multiplier is for that agency's SBIR/STTR-firm universe. Keep all of a
    # firm's transactions only when the firm has an accepted SBIR row at that agency.
    eligible_pairs = rows.loc[
        rows["is_sbir"].astype(bool), ["company_id", "agency"]
    ].drop_duplicates()
    rows = rows.merge(
        eligible_pairs.assign(_eligible=True), on=["company_id", "agency"], how="inner"
    )

    if policy.dollar_basis == "adjusted":
        if adjustment_factors is None or not {"fiscal_year", "adjustment_factor"}.issubset(
            adjustment_factors
        ):
            raise ValueError("adjusted dollar_basis requires fiscal_year/adjustment_factor data")
        rows = rows.merge(
            adjustment_factors[["fiscal_year", "adjustment_factor"]],
            on="fiscal_year",
            how="left",
            validate="many_to_one",
        )
        if rows["adjustment_factor"].isna().any():
            years = sorted(
                rows.loc[rows["adjustment_factor"].isna(), "fiscal_year"].dropna().unique()
            )
            raise ValueError(f"Missing adjustment factors for fiscal years: {years}")
        rows["obligation_amount"] *= rows["adjustment_factor"]

    rows["sbir_amount"] = rows["obligation_amount"].where(rows["is_sbir"].astype(bool), 0.0)
    rows["non_sbir_amount"] = rows["obligation_amount"].where(~rows["is_sbir"].astype(bool), 0.0)
    strata = ["company_id", "agency", "cohort_year", "firm_size", "technology_area", "experience"]
    company = _aggregate(rows, strata)
    return FollowOnMultiplierResult(
        company=company,
        agency=_aggregate(rows, ["agency"]),
        cohort=_aggregate(
            rows, ["agency", "cohort_year", "firm_size", "technology_area", "experience"]
        ),
        fiscal_year=_aggregate(rows, ["agency", "cohort_year", "fiscal_year"]),
        quality=quality,
    )
