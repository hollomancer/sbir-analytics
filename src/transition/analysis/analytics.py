# mypy: ignore-errors
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportMissingTypeStubs=false, reportDeprecatedType=false, reportGeneralTypeIssues=false
"""
Transition Analytics: dual-perspective (award- and company-level) KPIs and breakdowns.

This module provides Pandas-based analytics over transition detection outputs to compute:
- Award-level transition rate (fraction of awards that transitioned)
- Company-level transition rate (fraction of companies with ≥1 transitioned award)
- Phase effectiveness (Phase I vs Phase II transition rates)
- By-agency transition rates and counts
- Optional: average time-to-transition by agency (when dates are available)

Inputs (expected minimum columns):
- awards_df:
    - award_id (str)
    - Company or company (str) [for fallback company ID]
    - UEI or uei (str) [preferred company ID]
    - Duns or duns (str) [fallback company ID]
    - Phase or phase (str like "I" / "II")
    - Agency or awarding_agency_name or awarding_agency_code
    - award_date or completion_date (date-like, optional for time-to-transition)
- transitions_df:
    - award_id (str)
    - score (float 0-1)
    - contract_id (str, optional for time-to-transition)
- contracts_df (optional for time-to-transition):
    - contract_id (str)
    - action_date or start_date (date-like)

All computations gracefully degrade when optional fields are missing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd


def _norm_str(v: Any) -> str:
    try:
        s = str(v).strip()
        return s
    except Exception:
        return ""


def _first_col(df: pd.DataFrame, candidates: list[str]) -> str | None:
    for c in candidates:
        if c in df.columns:
            return c
    # try case-insensitive
    lower_map = {c.lower(): c for c in df.columns}
    for c in candidates:
        if c.lower() in lower_map:
            return lower_map[c.lower()]
    return None


def _company_id_series(awards_df: pd.DataFrame) -> pd.Series:
    """
    Construct a canonical company_id with priority UEI > DUNS > normalized Company name.
    """
    uei_col = _first_col(awards_df, ["UEI", "uei"])
    duns_col = _first_col(awards_df, ["Duns", "duns"])
    name_col = _first_col(awards_df, ["Company", "company", "vendor_name", "Vendor", "Name"])

    uei = (
        awards_df[uei_col].astype(str).str.strip() if uei_col else pd.Series([""] * len(awards_df))
    )
    duns = (
        awards_df[duns_col].astype(str).str.strip()
        if duns_col
        else pd.Series([""] * len(awards_df))
    )
    names = (
        awards_df[name_col].astype(str).str.strip().str.lower()
        if name_col
        else pd.Series([""] * len(awards_df))
    )

    # Build canonical id with prefixes to avoid collisions between ID systems
    company_id = pd.Series([""] * len(awards_df), index=awards_df.index, dtype="object")
    if uei_col:
        # Check for valid UEI values (not empty, not "None", not "nan")
        uei_valid = (uei != "") & (~uei.isin(["None", "nan", "NaN"]))
        company_id = company_id.mask(uei_valid, "uei:" + uei)
    if duns_col:
        # Check for valid DUNS values (not empty, not "None", not "nan")
        duns_valid = (duns != "") & (~duns.isin(["None", "nan", "NaN"]))
        company_id = company_id.mask((~company_id.astype(bool)) & duns_valid, "duns:" + duns)
    if name_col:
        # Check for valid name values (not empty, not "None", not "nan")
        names_valid = (names != "") & (~names.isin(["None", "nan", "NaN"]))
        company_id = company_id.mask((~company_id.astype(bool)) & names_valid, "name:" + names)

    # Last resort: row index as id to avoid empties
    company_id = company_id.where(company_id.astype(bool), "row:" + awards_df.index.astype(str))
    return company_id


def _award_id_col(df: pd.DataFrame) -> str:
    c = _first_col(df, ["award_id", "Award ID", "id", "award"])
    if not c:
        raise ValueError("awards_df must contain an award_id-like column")
    return c


def _transition_award_id_col(df: pd.DataFrame) -> str:
    c = _first_col(df, ["award_id", "award", "Award ID"])
    if not c:
        raise ValueError("transitions_df must contain an award_id column")
    return c


def _contract_id_col(df: pd.DataFrame) -> str | None:
    return _first_col(df, ["contract_id", "piid", "PIID"])


def _agency_col(df: pd.DataFrame) -> str | None:
    return _first_col(
        df, ["Agency", "agency", "awarding_agency_name", "awarding_agency_code", "Agency Code"]
    )


def _phase_col(df: pd.DataFrame) -> str | None:
    return _first_col(df, ["Phase", "phase", "Award Phase"])


def _award_date_col(df: pd.DataFrame) -> str | None:
    return _first_col(
        df,
        [
            "completion_date",
            "award_completion_date",
            "award_date",
            "project_start_date",
            "Start Date",
            "start_date",
        ],
    )


def _contract_date_col(df: pd.DataFrame) -> str | None:
    return _first_col(df, ["action_date", "start_date", "period_of_performance_start_date"])


@dataclass
class RateResult:
    numerator: int
    denominator: int
    rate: float

    def to_dict(self) -> dict[str, Any]:
        return {"numerator": self.numerator, "denominator": self.denominator, "rate": self.rate}


class TransitionAnalytics:
    """
    Pandas-based analytics over transition candidates.

    Typical usage:
        analytics = TransitionAnalytics(score_threshold=0.60)
        award_rate = analytics.compute_award_transition_rate(awards_df, transitions_df)
        company_rate = analytics.compute_company_transition_rate(awards_df, transitions_df)
        phase_df = analytics.compute_phase_effectiveness(awards_df, transitions_df)
        agency_df = analytics.compute_by_agency(awards_df, transitions_df)
    """

    def __init__(self, score_threshold: float = 0.60):
        self.score_threshold = float(score_threshold)

    def _transitioned_award_ids(self, transitions_df: pd.DataFrame) -> pd.Series:
        if transitions_df.empty:
            return pd.Series([], dtype="object")
        aid_col = _transition_award_id_col(transitions_df)
        # Filter by score threshold and deduplicate awards
        df = transitions_df.copy()
        if "score" in df.columns:
            df = df[pd.to_numeric(df["score"], errors="coerce").fillna(0.0) >= self.score_threshold]
        return df[aid_col].dropna().astype(str).drop_duplicates()

    # -----------------------
    # Award-level KPI
    # -----------------------
    def compute_award_transition_rate(
        self,
        awards_df: pd.DataFrame,
        transitions_df: pd.DataFrame,
    ) -> RateResult:
        """
        Fraction of unique awards with ≥1 transition (score ≥ threshold).
        """
        if awards_df.empty:
            return RateResult(0, 0, 0.0)
        aid_col = _award_id_col(awards_df)
        all_awards = awards_df[aid_col].dropna().astype(str).drop_duplicates()
        transitioned = self._transitioned_award_ids(transitions_df)
        num = int(all_awards.isin(set(transitioned)).sum())
        den = int(len(all_awards))
        rate = float(num / den) if den > 0 else 0.0
        return RateResult(num, den, rate)

    # -----------------------
    # Company-level KPI
    # -----------------------
    def compute_company_transition_rate(
        self,
        awards_df: pd.DataFrame,
        transitions_df: pd.DataFrame,
    ) -> tuple[RateResult, pd.DataFrame]:
        """
        Fraction of unique companies with ≥1 transitioned award.

        Returns:
            (RateResult, per_company DataFrame with columns:
                company_id, total_awards, transitioned_awards, transitioned (bool))
        """
        if awards_df.empty:
            return RateResult(0, 0, 0.0), pd.DataFrame(
                columns=["company_id", "total_awards", "transitioned_awards", "transitioned"]
            )

        aid_col = _award_id_col(awards_df)
        awards = awards_df.copy()
        awards["company_id"] = _company_id_series(awards_df).astype(str)

        # per-company counts
        per_company_counts = (
            awards.groupby("company_id")[aid_col].nunique().rename("total_awards").reset_index()
        )

        # awards that transitioned
        transitioned_awards = set(self._transitioned_award_ids(transitions_df).tolist())
        awards["transitioned"] = awards[aid_col].astype(str).isin(transitioned_awards)
        per_company_trans = (
            awards.groupby("company_id")["transitioned"].sum().rename("transitioned_awards")
        ).reset_index()

        result = per_company_counts.merge(per_company_trans, on="company_id", how="left").fillna(0)
        result["transitioned_awards"] = result["transitioned_awards"].astype(int)
        result["transitioned"] = result["transitioned_awards"] > 0

        num = int(result["transitioned"].sum())
        den = int(result["company_id"].nunique())
        rate = float(num / den) if den > 0 else 0.0

        return RateResult(num, den, rate), result.sort_values(
            ["transitioned", "total_awards"], ascending=[False, False]
        )

    # -----------------------
    # Phase effectiveness
    # -----------------------
    def compute_phase_effectiveness(
        self,
        awards_df: pd.DataFrame,
        transitions_df: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        Transition rate by award phase (e.g., Phase I vs Phase II).

        Returns:
            DataFrame with columns: phase, total_awards, transitioned_awards, rate
        """
        phase_c = _phase_col(awards_df)
        if awards_df.empty or not phase_c:
            # No phase column; return empty
            return pd.DataFrame(columns=["phase", "total_awards", "transitioned_awards", "rate"])

        aid_col = _award_id_col(awards_df)
        df = awards_df[[aid_col, phase_c]].copy()
        df["phase"] = df[phase_c].astype(str).str.strip().str.upper().str.replace("PHASE ", "")

        transitioned_awards = set(self._transitioned_award_ids(transitions_df).tolist())
        df["transitioned"] = df[aid_col].astype(str).isin(transitioned_awards)

        # Aggregate per phase
        grouped = df.groupby("phase").agg(
            total_awards=(aid_col, "nunique"),
            transitioned_awards=("transitioned", "sum"),
        )
        grouped["rate"] = grouped["transitioned_awards"] / grouped["total_awards"].clip(lower=1)
        return grouped.reset_index().sort_values("phase")

    # -----------------------
    # Agency breakdown
    # -----------------------
    def compute_by_agency(
        self,
        awards_df: pd.DataFrame,
        transitions_df: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        Transition rate by agency (code or name).

        Returns:
            DataFrame with columns: agency, total_awards, transitioned_awards, rate
        """
        agency_c = _agency_col(awards_df)
        if awards_df.empty or not agency_c:
            return pd.DataFrame(columns=["agency", "total_awards", "transitioned_awards", "rate"])

        aid_col = _award_id_col(awards_df)
        df = awards_df[[aid_col, agency_c]].copy()
        df["agency"] = df[agency_c].apply(_norm_str).str.upper()

        transitioned_awards = set(self._transitioned_award_ids(transitions_df).tolist())
        df["transitioned"] = df[aid_col].astype(str).isin(transitioned_awards)

        grouped = df.groupby("agency").agg(
            total_awards=(aid_col, "nunique"),
            transitioned_awards=("transitioned", "sum"),
        )
        grouped["rate"] = grouped["transitioned_awards"] / grouped["total_awards"].clip(lower=1)
        return grouped.reset_index().sort_values(["rate", "total_awards"], ascending=[False, False])

    # -----------------------
    # Avg time-to-transition (optional)
    # -----------------------
    def compute_avg_time_to_transition_by_agency(
        self,
        awards_df: pd.DataFrame,
        transitions_df: pd.DataFrame,
        contracts_df: pd.DataFrame | None = None,
    ) -> pd.DataFrame:
        """
        Compute average time from award_date/completion_date to contract action_date, grouped by agency.

        Requirements:
            - awards_df must contain award_id, agency, and a date column (award_date or completion_date)
            - transitions_df must contain award_id and contract_id
            - contracts_df must contain contract_id and action_date/start_date

        Returns:
            DataFrame with columns: agency, n, avg_days, p50_days, p90_days
            Empty DataFrame when required columns are missing.
        """
        if contracts_df is None or awards_df.empty or transitions_df.empty:
            return pd.DataFrame(columns=["agency", "n", "avg_days", "p50_days", "p90_days"])

        aid_col_awards = _award_id_col(awards_df)
        aid_col_trans = _transition_award_id_col(transitions_df)
        agency_c = _agency_col(awards_df)
        a_date_c = _award_date_col(awards_df)
        c_id_c = _contract_id_col(transitions_df)
        c_date_c = _contract_date_col(contracts_df)

        needed = [agency_c, a_date_c, c_id_c, c_date_c]
        if any(c is None for c in needed):
            return pd.DataFrame(columns=["agency", "n", "avg_days", "p50_days", "p90_days"])

        # Filter transitions to ≥ threshold
        tdf = transitions_df.copy()
        if "score" in tdf.columns:
            tdf = tdf[
                pd.to_numeric(tdf["score"], errors="coerce").fillna(0.0) >= self.score_threshold
            ]

        # Join awards -> transitions -> contracts
        a = awards_df[[aid_col_awards, agency_c, a_date_c]].copy()
        a[a_date_c] = pd.to_datetime(a[a_date_c], errors="coerce")
        c = contracts_df[[c_id_c, c_date_c]].copy()
        c[c_date_c] = pd.to_datetime(c[c_date_c], errors="coerce")

        at = tdf[[aid_col_trans, c_id_c]].dropna().drop_duplicates()
        merged = (
            at.merge(a, left_on=aid_col_trans, right_on=aid_col_awards, how="left")
            .merge(c, on=c_id_c, how="left")
            .dropna(subset=[a_date_c, c_date_c])
        )
        if merged.empty:
            return pd.DataFrame(columns=["agency", "n", "avg_days", "p50_days", "p90_days"])

        # Compute delta days
        merged["days"] = (merged[c_date_c] - merged[a_date_c]).dt.days

        # Keep only non-negative (contract after or on award date)
        merged = merged[merged["days"] >= 0].copy()
        if merged.empty:
            return pd.DataFrame(columns=["agency", "n", "avg_days", "p50_days", "p90_days"])

        grouped = merged.groupby(agency_c)["days"]
        out = pd.DataFrame(
            {
                "n": grouped.count(),
                "avg_days": grouped.mean().round(1),
                "p50_days": grouped.quantile(0.5).round(1),
                "p90_days": grouped.quantile(0.9).round(1),
            }
        ).reset_index()
        out.rename(columns={agency_c: "agency"}, inplace=True)
        return out.sort_values(["n", "avg_days"], ascending=[False, True])

    # -----------------------
    # High-level summary
    # -----------------------
    def summarize(
        self,
        awards_df: pd.DataFrame,
        transitions_df: pd.DataFrame,
        contracts_df: pd.DataFrame | None = None,
    ) -> dict[str, Any]:
        """
        Produce a compact metrics summary dict (JSON-serializable), excluding large tables.
        """
        award_rate = self.compute_award_transition_rate(awards_df, transitions_df)
        company_rate, _ = self.compute_company_transition_rate(awards_df, transitions_df)

        summary: dict[str, Any] = {
            "score_threshold": self.score_threshold,
            "award_transition_rate": award_rate.to_dict(),
            "company_transition_rate": company_rate.to_dict(),
        }

        # Include small aggregates
        phase_df = self.compute_phase_effectiveness(awards_df, transitions_df)
        if not phase_df.empty:
            summary["phase_effectiveness"] = phase_df.to_dict(orient="records")

        agency_df = self.compute_by_agency(awards_df, transitions_df)
        top_agencies = agency_df.head(10) if not agency_df.empty else pd.DataFrame()
        if not top_agencies.empty:
            summary["top_agencies"] = top_agencies.to_dict(orient="records")

        # Optional: time-to-transition aggregates (limited payload)
        if contracts_df is not None:
            ttt_agency = self.compute_avg_time_to_transition_by_agency(
                awards_df, transitions_df, contracts_df
            )
            summary["avg_time_to_transition_by_agency"] = (
                ttt_agency.head(10).to_dict(orient="records") if not ttt_agency.empty else []
            )
        else:
            summary["avg_time_to_transition_by_agency"] = []

        # CET-related metrics (empty lists if not available)
        summary["cet_area_transition_rates"] = []
        summary["avg_time_to_transition_by_cet_area"] = []
        summary["patent_backed_rates_by_cet_area"] = []

        return summary

    # -----------------------
    # CET-related methods
    # -----------------------

    def compute_transition_rates_by_cet_area(
        self,
        awards_df: pd.DataFrame,
        transitions_df: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        Compute transition rates grouped by CET area.

        Returns DataFrame with columns: cet_area, total_awards, transitioned_awards, rate
        """
        # Check if cet_area column exists
        cet_col = _first_col(awards_df, ["cet_area", "CET_area", "cet"])
        if not cet_col:
            return pd.DataFrame(columns=["cet_area", "total_awards", "transitioned_awards", "rate"])

        # Get award_id column
        award_id_col = _first_col(awards_df, ["award_id", "Award_id", "id"])
        if not award_id_col:
            return pd.DataFrame(columns=["cet_area", "total_awards", "transitioned_awards", "rate"])

        # Filter transitions by score threshold
        trans_award_id_col = _first_col(transitions_df, ["award_id", "Award_id", "id"])
        if not trans_award_id_col:
            return pd.DataFrame(columns=["cet_area", "total_awards", "transitioned_awards", "rate"])

        qualified = transitions_df[transitions_df["score"] >= self.score_threshold]
        transitioned_award_ids = set(qualified[trans_award_id_col].unique())

        # Group by CET area
        results = []
        for cet_area in awards_df[cet_col].unique():
            cet_awards = awards_df[awards_df[cet_col] == cet_area]
            total = len(cet_awards)
            transitioned = len(cet_awards[cet_awards[award_id_col].isin(transitioned_award_ids)])
            rate = transitioned / total if total > 0 else 0.0

            results.append(
                {
                    "cet_area": cet_area,
                    "total_awards": total,
                    "transitioned_awards": transitioned,
                    "rate": rate,
                }
            )

        return pd.DataFrame(results)

    def compute_avg_time_to_transition_by_cet_area(
        self,
        awards_df: pd.DataFrame,
        transitions_df: pd.DataFrame,
        contracts_df: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        Compute average time to transition grouped by CET area.

        Returns DataFrame with columns: cet_area, avg_days_to_transition, count
        """
        # Check if required columns exist
        cet_col = _first_col(awards_df, ["cet_area", "CET_area", "cet"])
        award_date_col = _first_col(awards_df, ["completion_date", "award_date", "date"])
        contract_date_col = _first_col(contracts_df, ["action_date", "start_date", "date"])

        if not all([cet_col, award_date_col, contract_date_col]):
            return pd.DataFrame(columns=["cet_area", "avg_days_to_transition", "count"])

        # Merge data
        award_id_col = _first_col(awards_df, ["award_id", "Award_id", "id"])
        trans_award_id_col = _first_col(transitions_df, ["award_id", "Award_id", "id"])
        contract_id_col = _first_col(contracts_df, ["contract_id", "Contract_id", "id"])
        trans_contract_id_col = _first_col(transitions_df, ["contract_id", "Contract_id", "id"])

        if not all([award_id_col, trans_award_id_col, contract_id_col, trans_contract_id_col]):
            return pd.DataFrame(columns=["cet_area", "avg_days_to_transition", "count"])

        # Filter by score threshold
        qualified = transitions_df[transitions_df["score"] >= self.score_threshold]

        # Merge to get dates
        merged = qualified.merge(
            awards_df[[award_id_col, cet_col, award_date_col]],
            left_on=trans_award_id_col,
            right_on=award_id_col,
            how="left",
        ).merge(
            contracts_df[[contract_id_col, contract_date_col]],
            left_on=trans_contract_id_col,
            right_on=contract_id_col,
            how="left",
        )

        # Calculate days to transition
        merged["days_to_transition"] = (
            pd.to_datetime(merged[contract_date_col]) - pd.to_datetime(merged[award_date_col])
        ).dt.days

        # Group by CET area
        result = (
            merged.groupby(cet_col)["days_to_transition"]
            .agg(["mean", "count"])
            .reset_index()
            .rename(columns={cet_col: "cet_area", "mean": "avg_days_to_transition"})
        )

        return result

    def compute_patent_backed_transition_rates_by_cet_area(
        self,
        awards_df: pd.DataFrame,
        transitions_df: pd.DataFrame,
        patents_df: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        Compute patent-backed transition rates grouped by CET area.

        Returns DataFrame with columns: cet_area, total_transitions, patent_backed, rate
        """
        # Check if required columns exist
        cet_col = _first_col(awards_df, ["cet_area", "CET_area", "cet"])
        if not cet_col:
            return pd.DataFrame(columns=["cet_area", "total_transitions", "patent_backed", "rate"])

        award_id_col = _first_col(awards_df, ["award_id", "Award_id", "id"])
        trans_award_id_col = _first_col(transitions_df, ["award_id", "Award_id", "id"])
        patent_award_id_col = _first_col(patents_df, ["award_id", "Award_id", "id"])

        if not all([award_id_col, trans_award_id_col, patent_award_id_col]):
            return pd.DataFrame(columns=["cet_area", "total_transitions", "patent_backed", "rate"])

        # Filter by score threshold
        qualified = transitions_df[transitions_df["score"] >= self.score_threshold]

        # Get patent-backed award IDs
        patent_backed_ids = set(patents_df[patent_award_id_col].unique())

        # Merge transitions with awards to get CET areas
        merged = qualified.merge(
            awards_df[[award_id_col, cet_col]],
            left_on=trans_award_id_col,
            right_on=award_id_col,
            how="left",
        )

        # Group by CET area
        results = []
        for cet_area in merged[cet_col].unique():
            cet_transitions = merged[merged[cet_col] == cet_area]
            total = len(cet_transitions)
            patent_backed = len(
                cet_transitions[cet_transitions[trans_award_id_col].isin(patent_backed_ids)]
            )
            rate = patent_backed / total if total > 0 else 0.0

            results.append(
                {
                    "cet_area": cet_area,
                    "total_transitions": total,
                    "patent_backed": patent_backed,
                    "rate": rate,
                }
            )

        return pd.DataFrame(results)


__all__ = ["TransitionAnalytics", "RateResult"]
