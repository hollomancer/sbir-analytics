"""Outcome-metric calculator for the NSF SBIR cohort.

Computes per-stratum (vintage x phase) commercialization rates with Wilson-
score confidence intervals. Inputs are optional; when an upstream artifact
is missing the corresponding metric is reported as ``available=False`` and
all numeric fields are ``None`` so the downstream report can still render.

Metrics:
    - phase_i_to_ii_graduation: any company with a Phase I award in stratum
      that has a Phase II award (any year) in the NSF cohort.
    - phase_ii_to_federal_contract_transition: Phase II awards with at least
      one upstream transition score >= the configured threshold (consumes
      ``transformed_transition_scores`` produced by the existing detector;
      the >=85% precision benchmark is enforced upstream and not relaxed
      here).
    - five_year_survival_proxy: Phase II company appears as a recipient or
      vendor in any federal dataset >=5 years after Phase II award year.
    - patent_rate: NSF awardee linked to >=1 patent via PATLINK.
    - ma_exit_rate: NSF awardee appears in the M&A events JSONL (post-#286).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import pandas as pd


WILSON_Z_95 = 1.959963984540054


def wilson_interval(
    numerator: int, denominator: int, *, z: float = WILSON_Z_95
) -> dict[str, float]:
    """Wilson score confidence interval for a binomial proportion.

    Returns a dict with ``rate`` (point estimate), ``ci_low``, ``ci_high``,
    ``numerator`` and ``denominator``. When ``denominator`` is zero, the
    rate and bounds are returned as ``float('nan')`` so the caller can
    decide how to render an undefined cell.
    """

    n = int(denominator)
    k = int(numerator)
    if n <= 0:
        return {
            "rate": float("nan"),
            "ci_low": float("nan"),
            "ci_high": float("nan"),
            "numerator": k,
            "denominator": n,
        }
    if k < 0 or k > n:
        raise ValueError(f"numerator {k} out of range for denominator {n}")
    p = k / n
    z2 = z * z
    denom = 1 + z2 / n
    centre = (p + z2 / (2 * n)) / denom
    half = (z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n))) / denom
    return {
        "rate": p,
        "ci_low": max(0.0, centre - half),
        "ci_high": min(1.0, centre + half),
        "numerator": k,
        "denominator": n,
    }


def _company_key(row: pd.Series) -> str | None:
    for key in ("uei", "UEI"):
        v = row.get(key)
        if v is not None and not (isinstance(v, float) and pd.isna(v)) and str(v).strip():
            return f"uei:{str(v).strip().upper()}"
    for key in ("duns", "Duns"):
        v = row.get(key)
        if v is not None and not (isinstance(v, float) and pd.isna(v)) and str(v).strip():
            return f"duns:{str(v).strip()}"
    for key in ("company_name", "Company"):
        v = row.get(key)
        if v is not None and not (isinstance(v, float) and pd.isna(v)) and str(v).strip():
            return f"name:{str(v).strip().lower()}"
    return None


@dataclass
class OutcomeMetricsCalculator:
    """Compute per-stratum NSF SBIR cohort outcome rates with Wilson CIs.

    Args:
        transition_score_threshold: minimum upstream transition-score for a
            Phase II award to count as transitioned. Default 0.65 matches
            the ``likely`` confidence threshold in
            ``sbir_ml.transition.DEFAULTS``.
        survival_horizon_years: years after award_year to look for
            recipient/vendor activity. Default 5.
    """

    transition_score_threshold: float = 0.65
    survival_horizon_years: int = 5
    z: float = WILSON_Z_95

    transition_scores: pd.DataFrame | None = field(default=None)
    federal_activity_companies: set[str] | None = field(default=None)
    patent_award_ids: set[str] | None = field(default=None)
    ma_event_companies: set[str] | None = field(default=None)

    def compute(self, cohort: pd.DataFrame) -> pd.DataFrame:
        """Emit one row per (vintage_bucket, phase_label, metric) stratum."""

        if cohort.empty:
            return pd.DataFrame(
                columns=[
                    "vintage_bucket",
                    "phase_label",
                    "metric",
                    "numerator",
                    "denominator",
                    "rate",
                    "ci_low",
                    "ci_high",
                    "available",
                ]
            )

        records: list[dict[str, Any]] = []
        cohort = cohort.copy()
        cohort["_company_key"] = cohort.apply(_company_key, axis=1)

        # Phase I->II graduation: per-vintage
        phase_i = cohort[cohort["phase_label"] == "I"]
        phase_ii_companies = {
            ck for ck in cohort.loc[cohort["phase_label"] == "II", "_company_key"] if ck
        }
        for vintage, group in phase_i.groupby("vintage_bucket", dropna=False):
            keys = [k for k in group["_company_key"].tolist() if k]
            unique_keys = set(keys)
            graduated = unique_keys & phase_ii_companies
            records.append(
                self._make_row(
                    vintage,
                    "I",
                    "phase_i_to_ii_graduation",
                    numerator=len(graduated),
                    denominator=len(unique_keys),
                    available=True,
                )
            )

        # Phase II -> federal-contract transition
        phase_ii = cohort[cohort["phase_label"] == "II"].copy()
        transition_award_ids = self._transitioned_award_ids()
        for vintage, group in phase_ii.groupby("vintage_bucket", dropna=False):
            denom = len(group)
            if self.transition_scores is None:
                records.append(
                    self._make_row(
                        vintage,
                        "II",
                        "phase_ii_to_federal_contract_transition",
                        numerator=0,
                        denominator=denom,
                        available=False,
                    )
                )
                continue
            award_ids = set(group.get("award_id", pd.Series(dtype=object)).dropna().astype(str))
            transitioned = award_ids & transition_award_ids
            records.append(
                self._make_row(
                    vintage,
                    "II",
                    "phase_ii_to_federal_contract_transition",
                    numerator=len(transitioned),
                    denominator=denom,
                    available=True,
                )
            )

        # 5-year survival proxy (Phase II only)
        for vintage, group in phase_ii.groupby("vintage_bucket", dropna=False):
            denom = len(group)
            if self.federal_activity_companies is None:
                records.append(
                    self._make_row(
                        vintage,
                        "II",
                        "five_year_survival_proxy",
                        numerator=0,
                        denominator=denom,
                        available=False,
                    )
                )
                continue
            keys = {k for k in group["_company_key"].tolist() if k}
            survived = keys & self.federal_activity_companies
            records.append(
                self._make_row(
                    vintage,
                    "II",
                    "five_year_survival_proxy",
                    numerator=len(survived),
                    denominator=denom,
                    available=True,
                )
            )

        # Patent rate (per stratum, all phases)
        for (vintage, phase), group in cohort.groupby(
            ["vintage_bucket", "phase_label"], dropna=False
        ):
            denom = len(group)
            if self.patent_award_ids is None:
                records.append(
                    self._make_row(
                        vintage,
                        phase,
                        "patent_rate",
                        numerator=0,
                        denominator=denom,
                        available=False,
                    )
                )
                continue
            award_ids = set(group.get("award_id", pd.Series(dtype=object)).dropna().astype(str))
            patented = award_ids & self.patent_award_ids
            records.append(
                self._make_row(
                    vintage,
                    phase,
                    "patent_rate",
                    numerator=len(patented),
                    denominator=denom,
                    available=True,
                )
            )

        # M&A exit rate (per stratum, all phases)
        for (vintage, phase), group in cohort.groupby(
            ["vintage_bucket", "phase_label"], dropna=False
        ):
            denom_keys = {k for k in group["_company_key"].tolist() if k}
            denom = len(denom_keys)
            if self.ma_event_companies is None:
                records.append(
                    self._make_row(
                        vintage,
                        phase,
                        "ma_exit_rate",
                        numerator=0,
                        denominator=denom,
                        available=False,
                    )
                )
                continue
            exited = denom_keys & self.ma_event_companies
            records.append(
                self._make_row(
                    vintage,
                    phase,
                    "ma_exit_rate",
                    numerator=len(exited),
                    denominator=denom,
                    available=True,
                )
            )

        return pd.DataFrame.from_records(records)

    def _transitioned_award_ids(self) -> set[str]:
        if self.transition_scores is None or self.transition_scores.empty:
            return set()
        df = self.transition_scores
        score_col = "score" if "score" in df.columns else "likelihood_score"
        if score_col not in df.columns or "award_id" not in df.columns:
            return set()
        passed = df[df[score_col].astype(float) >= self.transition_score_threshold]
        return set(passed["award_id"].dropna().astype(str))

    def _make_row(
        self,
        vintage: object,
        phase: object,
        metric: str,
        *,
        numerator: int,
        denominator: int,
        available: bool,
    ) -> dict[str, Any]:
        if available and denominator > 0:
            wi = wilson_interval(numerator, denominator, z=self.z)
        else:
            wi = {
                "rate": float("nan"),
                "ci_low": float("nan"),
                "ci_high": float("nan"),
                "numerator": numerator,
                "denominator": denominator,
            }
        return {
            "vintage_bucket": vintage,
            "phase_label": phase,
            "metric": metric,
            "numerator": int(wi["numerator"]),
            "denominator": int(wi["denominator"]),
            "rate": wi["rate"],
            "ci_low": wi["ci_low"],
            "ci_high": wi["ci_high"],
            "available": bool(available),
        }
