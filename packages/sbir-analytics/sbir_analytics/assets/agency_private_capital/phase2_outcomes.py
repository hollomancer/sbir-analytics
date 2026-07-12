"""Outcome calculations for matched agency-vs-Form-D control cohorts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from .outcomes import wilson_interval


def keys_from_ma_events(path: str | None) -> set[str] | None:
    """Load M&A event keys from JSONL, supporting company-name and CIK fields."""

    if not path:
        return None
    from pathlib import Path

    import json

    p = Path(path)
    if not p.exists():
        return None
    keys: set[str] = set()
    with p.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            name = row.get("company_name") or row.get("issuer_name") or row.get("entity_name")
            if name:
                keys.add(f"name:{str(name).strip().lower()}")
            cik = row.get("form_d_cik") or row.get("cik") or row.get("target_cik")
            if cik:
                keys.add(f"cik:{str(cik).lstrip('0')}")
    return keys


@dataclass(frozen=True)
class MatchedCohortOutcomes:
    """Compute outcome rates on treated and matched-control cohorts.

    Event sets are optional because real FPDS/PATLINK control joins are not
    always materialized. Missing sets produce `available=False` rows instead
    of silently reporting zero.
    """

    federal_contract_keys: set[str] | None = None
    patent_keys: set[str] | None = None
    ma_event_keys: set[str] | None = None

    def compute(self, pairs: pd.DataFrame) -> pd.DataFrame:
        if pairs.empty:
            return _outcome_frame([])
        rows: list[dict[str, Any]] = []
        rows.extend(
            self._metric(
                pairs,
                metric="federal_contract_presence",
                keys=self.federal_contract_keys,
            )
        )
        rows.extend(self._metric(pairs, metric="patent_presence", keys=self.patent_keys))
        rows.extend(self._metric(pairs, metric="ma_exit_rate", keys=self.ma_event_keys))
        return _outcome_frame(rows)

    def _metric(
        self,
        pairs: pd.DataFrame,
        *,
        metric: str,
        keys: set[str] | None,
    ) -> list[dict[str, Any]]:
        treated = pairs.drop_duplicates("treated_company_key")
        controls = pairs.drop_duplicates("control_form_d_cik")
        return [
            self._row(
                cohort="agency_sbir",
                metric=metric,
                candidate_keys=_treated_keys(treated),
                keys=keys,
            ),
            self._row(
                cohort="form_d_control",
                metric=metric,
                candidate_keys=_control_keys(controls),
                keys=keys,
            ),
        ]

    def _row(
        self,
        *,
        cohort: str,
        metric: str,
        candidate_keys: dict[str, set[str]],
        keys: set[str] | None,
    ) -> dict[str, Any]:
        denominator = len(candidate_keys)
        if keys is None:
            return {
                "cohort": cohort,
                "metric": metric,
                "numerator": 0,
                "denominator": denominator,
                "rate": float("nan"),
                "ci_low": float("nan"),
                "ci_high": float("nan"),
                "available": False,
            }
        numerator = sum(1 for key_set in candidate_keys.values() if key_set & keys)
        wi = wilson_interval(numerator, denominator)
        return {
            "cohort": cohort,
            "metric": metric,
            "numerator": wi["numerator"],
            "denominator": wi["denominator"],
            "rate": wi["rate"],
            "ci_low": wi["ci_low"],
            "ci_high": wi["ci_high"],
            "available": True,
        }


def _treated_keys(rows: pd.DataFrame) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for _, row in rows.iterrows():
        key = str(row.get("treated_company_key") or "")
        keys = {f"name:{str(row.get('treated_company_name')).strip().lower()}"}
        cik = row.get("treated_form_d_cik")
        if cik:
            keys.add(f"cik:{str(cik).lstrip('0')}")
        out[key] = keys
    return out


def _control_keys(rows: pd.DataFrame) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for _, row in rows.iterrows():
        key = str(row.get("control_form_d_cik") or row.get("control_issuer_key") or "")
        keys = {f"name:{str(row.get('control_issuer_name')).strip().lower()}"}
        cik = row.get("control_form_d_cik")
        if cik:
            keys.add(f"cik:{str(cik).lstrip('0')}")
        out[key] = keys
    return out


def _outcome_frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    return pd.DataFrame(
        rows,
        columns=[
            "cohort",
            "metric",
            "numerator",
            "denominator",
            "rate",
            "ci_low",
            "ci_high",
            "available",
        ],
    )
