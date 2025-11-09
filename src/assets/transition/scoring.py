"""Transition scoring assets.

This module contains:
- transformed_transition_scores: Score transition candidates
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from .utils import (
    MetadataValue,
    Output,
    _env_float,
    _env_int,
    _norm_name,
    asset,
    now_utc_iso,
    save_dataframe_parquet,
    write_json,
)


@asset(
    name="transformed_transition_scores",
    group_name="transformation",
    compute_kind="pandas",
    description=(
        "Compute initial award↔contract transition candidates with a simple rule-based score. "
        "Combines vendor_resolution with award lookups; caps candidates per award."
    ),
)
def transformed_transition_scores(
    context,
    enriched_vendor_resolution: pd.DataFrame,
    validated_contracts_sample: pd.DataFrame,
    enriched_sbir_awards: pd.DataFrame,
) -> Output[pd.DataFrame]:
    limit_per_award = _env_int("SBIR_ETL__TRANSITION__LIMIT_PER_AWARD", 50)
    out_path = Path("data/processed/transitions.parquet")
    checks_path = out_path.with_suffix(".checks.json")

    # Build award lookup by vendor_id (same logic as vendor_resolution)
    def _award_vendor_id(row: pd.Series) -> str:
        if pd.notna(row.get("UEI")) and str(row["UEI"]).strip():
            return f"uei:{str(row['UEI']).strip()}"
        if pd.notna(row.get("Duns")) and str(row["Duns"]).strip():
            return f"duns:{str(row['Duns']).strip()}"
        return f"name:{_norm_name(str(row.get('Company', '')))}"

    awards = enriched_sbir_awards.copy()
    if "award_id" not in awards.columns:
        awards = awards.reset_index().rename(columns={"index": "award_id"})
        awards["award_id"] = awards["award_id"].apply(lambda x: f"award_{x}")
    awards["_vendor_id"] = awards.apply(_award_vendor_id, axis=1)

    # Prepare mapping vendor_id -> award_ids
    vendor_to_awards: dict[str, list[str]] = {}
    for vid, grp in awards.groupby("_vendor_id"):
        vendor_to_awards[vid] = list(grp["award_id"].astype(str).dropna().unique())

    # Lightweight score by method + small boosts from temporal and agency alignment
    METHOD_WEIGHTS = {"uei": 0.9, "duns": 0.8, "name_exact": 0.85, "name_fuzzy": 0.7}
    score_cap = 1.0

    # Env-tunable boost parameters
    date_window_years = _env_int("SBIR_ETL__TRANSITION__DATE_WINDOW_YEARS", 5)
    date_boost_max = _env_float("SBIR_ETL__TRANSITION__DATE_BOOST_MAX", 0.1)
    agency_boost_val = _env_float("SBIR_ETL__TRANSITION__AGENCY_BOOST", 0.05)
    amount_boost_val = _env_float("SBIR_ETL__TRANSITION__AMOUNT_BOOST", 0.03)
    id_link_boost_val = _env_float("SBIR_ETL__TRANSITION__ID_LINK_BOOST", 0.10)

    # Helpers (local to keep module import-safe)
    def _parse_date_any(v: Any):
        try:
            dt = pd.to_datetime(v, errors="coerce", utc=False)
            # to_datetime may return NaT
            return None if pd.isna(dt) else dt.to_pydatetime()
        except Exception:
            return None

    def _award_date_from_row(r: pd.Series | None):
        if r is None:
            return None
        for key in [
            "award_date",
            "Award Date",
            "start_date",
            "Start Date",
            "StartDate",
            "project_start_date",
            "award_start_date",
        ]:
            if key in r and pd.notna(r.get(key)):
                d = _parse_date_any(r.get(key))
                if d:
                    return d
        return None

    def _agency_from_award_row(r: pd.Series | None) -> tuple[str | None, str | None]:
        if r is None:
            return None, None
        code = None
        for key in ["awarding_agency_code", "Agency Code", "agency_code"]:
            val = str(r.get(key) or "").strip()
            if val:
                code = val.upper()
                break
        name = None
        for key in ["Agency", "agency", "awarding_agency_name"]:
            val = str(r.get(key) or "").strip()
            if val:
                name = _norm_name(val)
                break
        return code, name

    results: list[dict[str, Any]] = []
    # Build quick lookup for contracts by contract_id
    contracts_by_id = {
        str(c.get("contract_id") or c.get("piid") or ""): c
        for _, c in validated_contracts_sample.iterrows()
    }

    for _, row in enriched_vendor_resolution.iterrows():
        method = str(row.get("match_method") or "unresolved")
        if method == "unresolved":
            continue
        vid = str(row.get("matched_vendor_id") or "")
        contract_id = str(row.get("contract_id") or "")
        base = METHOD_WEIGHTS.get(method, 0.0)

        # Award candidates
        award_ids = vendor_to_awards.get(vid, [])[:limit_per_award]
        for aid in award_ids:
            # Base score
            score = base

            # Temporal and agency alignment boosts (best-effort; optional fields)
            contract_row: Any = contracts_by_id.get(contract_id, {})
            c_date = _parse_date_any(contract_row.get("action_date"))
            a_row: pd.Series | None = None
            try:
                # Filter once; safe even when no rows match
                matches = awards.loc[awards["award_id"] == aid]
                if len(matches) > 0:
                    a_row = matches.iloc[0]
            except Exception:
                a_row = None

            a_date = _award_date_from_row(a_row)
            a_code, a_name = _agency_from_award_row(a_row)
            c_code = str(contract_row.get("awarding_agency_code") or "").strip().upper()
            c_name = _norm_name(str(contract_row.get("awarding_agency_name") or ""))

            # Date boost: award date must be on/before contract date and within window
            date_boost = 0.0
            if a_date and c_date and c_date >= a_date:
                delta_years = (c_date - a_date).days / 365.25
                if 0.0 <= delta_years <= 2.0:
                    date_boost = min(date_boost_max, 0.08)
                elif 0.0 < delta_years <= float(date_window_years):
                    date_boost = min(date_boost_max, 0.04)

            # Agency boost: code or normalized name match
            agency_boost = 0.0
            codes_match = bool(c_code and a_code and c_code == a_code)
            names_match = bool(a_name and c_name and a_name == c_name)
            if codes_match or names_match:
                agency_boost = agency_boost_val

            # Identifier link boosts (PIID/FAIN)
            def _norm(s):
                return str(s or "").strip().upper()

            c_piid = _norm(contract_row.get("piid"))
            c_fain = _norm(contract_row.get("fain"))
            a_piid = _norm(a_row.get("piid") if a_row is not None else None)
            a_piid2 = _norm(a_row.get("PIID") if a_row is not None else None)
            a_fain = _norm(a_row.get("fain") if a_row is not None else None)
            a_fain2 = _norm(a_row.get("FAIN") if a_row is not None else None)
            a_contract = _norm(a_row.get("contract") if a_row is not None else None)
            piid_match = bool(
                c_piid and (c_piid == a_piid or c_piid == a_piid2 or c_piid == a_contract)
            )
            fain_match = bool(c_fain and (c_fain == a_fain or c_fain == a_fain2))
            id_boost = id_link_boost_val if (piid_match or fain_match) else 0.0

            # Amount sanity boost (contract vs award amount roughly similar)
            def _to_float(x):
                try:
                    return float(str(x).replace(",", ""))
                except Exception:
                    return None

            c_amt = _to_float(contract_row.get("obligated_amount"))
            a_amt = _to_float(
                a_row.get("Award Amount") if a_row is not None else None
            ) or _to_float(a_row.get("award_amount") if a_row is not None else None)
            amount_boost = 0.0
            if c_amt and a_amt and c_amt > 0 and a_amt > 0:
                ratio = min(c_amt, a_amt) / max(c_amt, a_amt)
                if 0.5 <= ratio <= 2.0:
                    amount_boost = amount_boost_val

            # Final score and signals list
            score = min(score_cap, score + date_boost + agency_boost + id_boost + amount_boost)
            signals = [method]
            if date_boost > 0:
                signals.append("date_overlap")
            if agency_boost > 0:
                signals.append("agency_align")
            if id_boost > 0:
                if piid_match:
                    signals.append("piid_link")
                if fain_match:
                    signals.append("fain_link")
            if amount_boost > 0:
                signals.append("amount_sanity")

            results.append(
                {
                    "award_id": aid,
                    "contract_id": contract_id,
                    "score": round(float(score), 4),
                    "method": method,
                    "signals": signals,
                    "computed_at": now_utc_iso(),
                }
            )

    df_out = pd.DataFrame(results)
    # Sort for deterministic ordering: by award_id, then score (desc), then contract_id
    # This ensures stable ordering when scores are tied
    if len(df_out) > 0:
        df_out = df_out.sort_values(
            by=["award_id", "score", "contract_id"], ascending=[True, False, True]
        ).reset_index(drop=True)
    save_dataframe_parquet(df_out, out_path)

    checks = {
        "ok": True,
        "generated_at": now_utc_iso(),
        "total_candidates": len(df_out),
        "distinct_awards": int(df_out["award_id"].nunique()) if len(df_out) else 0,
        "distinct_contracts": int(df_out["contract_id"].nunique()) if len(df_out) else 0,
        "by_method": df_out["method"].value_counts(dropna=False).to_dict() if len(df_out) else {},
        "limit_per_award": limit_per_award,
    }
    write_json(checks_path, checks)

    meta = {
        "rows": len(df_out),
        "checks_path": str(checks_path),
        "output_path": str(out_path),
        "by_method": MetadataValue.json(checks["by_method"]),
    }
    context.log.info("Computed transition_scores_v1", extra=meta)
    return Output(df_out, metadata=meta)


# -----------------------------
# 4) transition_evidence_v1
# -----------------------------
