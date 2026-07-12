"""Cohort construction for agency-vs-private-capital Phase 2."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from .cohort import AgencyCohortBuilder
from .form_d_inputs import normalize_name


def agency_leverage_cross_check(
    agency_code: str,
    awards: pd.DataFrame,
    treated: pd.DataFrame,
) -> dict[str, float | int | None | str]:
    """Compare matched Form D capital to the full agency SBIR award denominator."""

    agency_awards = AgencyCohortBuilder(agency_code=agency_code).build(awards)
    amount_col = "award_amount" if "award_amount" in agency_awards.columns else "Award Amount"
    agency_program_total = (
        float(agency_awards[amount_col].map(award_amount).sum())
        if amount_col in agency_awards.columns
        else 0.0
    )
    matched_sbir_total = _sum_numeric(treated, "agency_sbir_amount")
    matched_form_d_total = _sum_numeric(treated, "total_form_d_raised")
    return {
        "agency_code": agency_code,
        "agency_award_rows": int(len(agency_awards)),
        "matched_treated_firms": int(len(treated)),
        "agency_program_sbir_amount": agency_program_total,
        "matched_agency_sbir_amount": matched_sbir_total,
        "matched_form_d_raised": matched_form_d_total,
        "form_d_to_agency_program_ratio": _ratio(matched_form_d_total, agency_program_total),
        "form_d_to_matched_sbir_ratio": _ratio(matched_form_d_total, matched_sbir_total),
    }


def award_amount(value: object) -> float:
    """Parse SBIR award amount strings defensively."""

    if value is None or (isinstance(value, float) and pd.isna(value)):
        return 0.0
    try:
        return float(str(value).replace("$", "").replace(",", "").strip())
    except ValueError:
        return 0.0


def award_year(row: pd.Series) -> int | None:
    """Return award year from common normalized or SBIR.gov-style columns."""

    for key in ("award_year", "Award Year"):
        value = row.get(key)
        if value is not None and not (isinstance(value, float) and pd.isna(value)):
            try:
                return int(str(value).strip())
            except ValueError:
                pass
    for key in ("award_date", "Proposal Award Date"):
        value = row.get(key)
        if value is None or (isinstance(value, float) and pd.isna(value)):
            continue
        parsed = pd.to_datetime(value, errors="coerce")
        if pd.notna(parsed):
            return int(parsed.year)
    return None


def company_name(row: pd.Series) -> str:
    for key in ("company_name", "Company"):
        value = row.get(key)
        if value is not None and not (isinstance(value, float) and pd.isna(value)):
            return str(value).strip()
    return ""


def state_code(row: pd.Series) -> str:
    for key in ("state", "State"):
        value = row.get(key)
        if value is not None and not (isinstance(value, float) and pd.isna(value)):
            return str(value).strip().upper()[:2]
    return ""


@dataclass(frozen=True)
class AgencyAwardeeFilter:
    """Build the treated agency cohort intersected with high-tier Form D matches."""

    agency_code: str = "NSF"

    def build(self, awards: pd.DataFrame, form_d_matches: pd.DataFrame) -> pd.DataFrame:
        agency_awards = AgencyCohortBuilder(agency_code=self.agency_code).build(awards)
        if agency_awards.empty or form_d_matches.empty:
            return _treated_frame([])

        agency_awards = agency_awards.copy()
        agency_awards["company_key"] = agency_awards.apply(
            lambda row: normalize_name(company_name(row)), axis=1
        )
        agency_awards["_award_year"] = agency_awards.apply(award_year, axis=1)
        amount_col = "award_amount" if "award_amount" in agency_awards.columns else "Award Amount"
        if amount_col in agency_awards.columns:
            amount_values = agency_awards[amount_col]
        else:
            amount_values = pd.Series(0.0, index=agency_awards.index)
        agency_awards["_award_amount"] = amount_values.map(award_amount)
        agency_awards["_state"] = agency_awards.apply(state_code, axis=1)

        award_summary = (
            agency_awards.groupby("company_key", dropna=False)
            .agg(
                company_name=("company_name", "first")
                if "company_name" in agency_awards.columns
                else ("Company", "first"),
                agency_first_award_year=("_award_year", "min"),
                agency_sbir_amount=("_award_amount", "sum"),
                agency_award_count=("_award_amount", "size"),
                state=("_state", "first"),
            )
            .reset_index()
        )
        merged = award_summary.merge(
            form_d_matches,
            on="company_key",
            how="inner",
            suffixes=("_agency", "_form_d"),
        )
        if merged.empty:
            return _treated_frame([])

        rows: list[dict[str, Any]] = []
        for _, row in merged.iterrows():
            vintage_year = row.get("agency_first_award_year")
            rows.append(
                {
                    "cohort": "agency_sbir",
                    "company_name": row.get("company_name_agency") or row.get("company_name"),
                    "company_key": row["company_key"],
                    "form_d_cik": row["form_d_cik"],
                    "vintage_year": int(vintage_year) if pd.notna(vintage_year) else None,
                    "state": row.get("state_form_d") or row.get("state") or "",
                    "industry_group": row.get("industry_group") or "Unknown",
                    "first_form_d_year": row.get("first_form_d_year"),
                    "total_form_d_raised": row.get("total_form_d_raised", 0.0),
                    "agency_sbir_amount": row.get("agency_sbir_amount", 0.0),
                    "agency_award_count": row.get("agency_award_count", 0),
                }
            )
        return _treated_frame(rows)


@dataclass(frozen=True)
class PrivateCapitalControlCohortBuilder:
    """Build non-SBIR Form D controls from the broader Form D universe."""

    def build(self, form_d_universe: pd.DataFrame) -> pd.DataFrame:
        if form_d_universe.empty:
            return _control_frame([])
        rows: list[dict[str, Any]] = []
        for _, row in form_d_universe.iterrows():
            vintage_year = row.get("first_form_d_year")
            rows.append(
                {
                    "cohort": "form_d_control",
                    "issuer_name": row.get("issuer_name") or row.get("company_name"),
                    "issuer_key": row.get("issuer_key") or row.get("company_key"),
                    "form_d_cik": row.get("form_d_cik"),
                    "vintage_year": int(vintage_year) if pd.notna(vintage_year) else None,
                    "state": row.get("state") or "",
                    "industry_group": row.get("industry_group") or "Unknown",
                    "first_form_d_year": row.get("first_form_d_year"),
                    "total_form_d_raised": row.get("total_form_d_raised", 0.0),
                    "offering_count": row.get("offering_count", 0),
                }
            )
        return _control_frame(rows)


def _treated_frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    return pd.DataFrame(
        rows,
        columns=[
            "cohort",
            "company_name",
            "company_key",
            "form_d_cik",
            "vintage_year",
            "state",
            "industry_group",
            "first_form_d_year",
            "total_form_d_raised",
            "agency_sbir_amount",
            "agency_award_count",
        ],
    )


def _control_frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    return pd.DataFrame(
        rows,
        columns=[
            "cohort",
            "issuer_name",
            "issuer_key",
            "form_d_cik",
            "vintage_year",
            "state",
            "industry_group",
            "first_form_d_year",
            "total_form_d_raised",
            "offering_count",
        ],
    )


def _sum_numeric(frame: pd.DataFrame, column: str) -> float:
    if frame.empty or column not in frame.columns:
        return 0.0
    return float(pd.to_numeric(frame[column], errors="coerce").fillna(0).sum())


def _ratio(numerator: float, denominator: float) -> float | None:
    return numerator / denominator if denominator else None
