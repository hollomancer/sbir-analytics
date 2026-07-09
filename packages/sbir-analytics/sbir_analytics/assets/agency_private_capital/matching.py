"""Coarsened-exact matching for Phase 2 private-capital controls."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd


MATCH_COLUMNS = ("vintage_year", "industry_group", "state")


@dataclass(frozen=True)
class CohortMatcher:
    """Match each treated agency Form D firm to up to `controls_per_treated` controls."""

    controls_per_treated: int = 3
    match_columns: tuple[str, ...] = MATCH_COLUMNS

    def match(self, treated: pd.DataFrame, controls: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
        if treated.empty or controls.empty:
            return _pairs_frame([]), self._balance(treated, controls, matched_treated=set())

        control_buckets: dict[tuple[Any, ...], list[dict]] = {}
        for _, row in controls.sort_values(["form_d_cik"]).iterrows():
            key = tuple(row.get(col) for col in self.match_columns)
            control_buckets.setdefault(key, []).append(row.to_dict())

        pairs: list[dict[str, Any]] = []
        matched_treated: set[str] = set()
        for _, treated_row in treated.sort_values(["company_key"]).iterrows():
            key = tuple(treated_row.get(col) for col in self.match_columns)
            candidates = control_buckets.get(key, [])[: self.controls_per_treated]
            if not candidates:
                continue
            matched_treated.add(str(treated_row.get("company_key")))
            for control_row in candidates:
                pairs.append(
                    {
                        "treated_company_name": treated_row.get("company_name"),
                        "treated_company_key": treated_row.get("company_key"),
                        "treated_form_d_cik": treated_row.get("form_d_cik"),
                        "control_issuer_name": control_row.get("issuer_name"),
                        "control_issuer_key": control_row.get("issuer_key"),
                        "control_form_d_cik": control_row.get("form_d_cik"),
                        "vintage_year": treated_row.get("vintage_year"),
                        "industry_group": treated_row.get("industry_group"),
                        "state": treated_row.get("state"),
                        "treated_total_form_d_raised": treated_row.get("total_form_d_raised"),
                        "control_total_form_d_raised": control_row.get("total_form_d_raised"),
                    }
                )
        return _pairs_frame(pairs), self._balance(treated, controls, matched_treated=matched_treated)

    def _balance(
        self,
        treated: pd.DataFrame,
        controls: pd.DataFrame,
        *,
        matched_treated: set[str],
    ) -> dict:
        strata = []
        if not treated.empty:
            treated_counts = (
                treated.groupby(list(self.match_columns), dropna=False)
                .size()
                .reset_index(name="treated_count")
            )
        else:
            treated_counts = pd.DataFrame(columns=[*self.match_columns, "treated_count"])
        if not controls.empty:
            control_counts = (
                controls.groupby(list(self.match_columns), dropna=False)
                .size()
                .reset_index(name="control_count")
            )
        else:
            control_counts = pd.DataFrame(columns=[*self.match_columns, "control_count"])
        merged = treated_counts.merge(
            control_counts, on=list(self.match_columns), how="outer"
        ).fillna(0)
        for _, row in merged.iterrows():
            strata.append(
                {
                    **{col: row[col] for col in self.match_columns},
                    "treated_count": int(row["treated_count"]),
                    "control_count": int(row["control_count"]),
                }
            )
        n_treated = int(len(treated))
        return {
            "match_columns": list(self.match_columns),
            "controls_per_treated": self.controls_per_treated,
            "treated_count": n_treated,
            "control_count": int(len(controls)),
            "matched_treated_count": len(matched_treated),
            "unmatched_treated_count": n_treated - len(matched_treated),
            "match_rate": (len(matched_treated) / n_treated) if n_treated else 0.0,
            "strata": strata,
        }


def _pairs_frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    return pd.DataFrame(
        rows,
        columns=[
            "treated_company_name",
            "treated_company_key",
            "treated_form_d_cik",
            "control_issuer_name",
            "control_issuer_key",
            "control_form_d_cik",
            "vintage_year",
            "industry_group",
            "state",
            "treated_total_form_d_raised",
            "control_total_form_d_raised",
        ],
    )
