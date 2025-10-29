"""
Dagster assets for Transition Detection MVP:
- contracts_sample: Load or create a sample of federal contracts
- vendor_resolution: Resolve contract vendor → SBIR recipient using UEI/DUNS/fuzzy name
- transition_scores_v1: Produce initial award↔contract transition candidates with simple scoring
- transition_evidence_v1: Emit structured evidence for each transition candidate

Design goals:
- Import-safe: gracefully operates when Dagster is not available (e.g., unit tests)
- File outputs: parquet artifacts under data/processed/, companion checks JSON for gating
- Config via env vars (lightweight): thresholds, caps, and paths
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd
from loguru import logger

# Import-safe shims for Dagster
try:
    from dagster import AssetExecutionContext, MetadataValue, Output, asset
except Exception:  # pragma: no cover
    # Minimal shims so this module can be imported without Dagster installed
    def asset(*args, **kwargs):  # type: ignore
        def _wrap(fn):
            return fn

        return _wrap

    class Output:  # type: ignore
        def __init__(self, value, metadata=None):
            self.value = value
            self.metadata = metadata or {}

    class MetadataValue:  # type: ignore
        @staticmethod
        def json(v: Any) -> Any:
            return v

    class AssetExecutionContext:  # type: ignore
        def __init__(self) -> None:
            self.log = logger


# Optional fuzzy matching (RapidFuzz); fallback to trivial similarity if unavailable
try:
    from rapidfuzz import fuzz
except Exception:  # pragma: no cover

    class _Fuzz:  # type: ignore
        @staticmethod
        def partial_ratio(a: str, b: str) -> float:
            return 100.0 if a.strip().lower() == b.strip().lower() else 0.0

    fuzz = _Fuzz()  # type: ignore


# -----------------------------
# Utilities
# -----------------------------


def _ensure_parent_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def save_dataframe_parquet(df: pd.DataFrame, path: Path) -> None:
    """Persist a DataFrame to parquet, falling back to NDJSON if pyarrow not present."""
    _ensure_parent_dir(path)
    try:
        df.to_parquet(path, index=False)
    except Exception:
        # Fallback to NDJSON in the same directory with .ndjson suffix
        ndjson_path = path.with_suffix(".ndjson")

        # Convert values to JSON-serializable, handling NaN/NaT/NumPy scalars and nested containers
        def _to_jsonable(x):
            try:
                if pd.isna(x):
                    return None
            except Exception:
                pass
            # pandas Timestamps
            if hasattr(x, "isoformat"):
                try:
                    return x.isoformat()
                except Exception:
                    pass
            # NumPy scalars
            try:
                import numpy as _np  # type: ignore

                if isinstance(x, _np.generic):
                    try:
                        return x.item()
                    except Exception:
                        pass
            except Exception:
                pass
            # Containers
            if isinstance(x, dict):
                return {str(k): _to_jsonable(v) for k, v in x.items()}
            if isinstance(x, (list, tuple, set)):
                return [_to_jsonable(v) for v in list(x)]
            return x

        with ndjson_path.open("w", encoding="utf-8") as fh:
            for _, row in df.iterrows():
                record = {k: _to_jsonable(v) for k, v in row.items()}
                fh.write(json.dumps(record) + "\n")
        logger.warning("Parquet save failed; wrote NDJSON fallback", path=str(ndjson_path))


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    _ensure_parent_dir(path)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)


def now_utc_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def _norm_name(s: Optional[str]) -> str:
    return (s or "").strip().lower()


def _env_float(key: str, default: float) -> float:
    try:
        return float(os.getenv(key, str(default)))
    except Exception:
        return default


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, str(default)))
    except Exception:
        return default


def _env_bool(key: str, default: bool) -> bool:
    v = os.getenv(key)
    if v is None:
        return default
    return v.strip().lower() in {"1", "true", "yes", "on"}


# -----------------------------
# 1) contracts_sample
# -----------------------------


@asset(
    name="contracts_sample",
    group_name="transition",
    compute_kind="pandas",
    description=(
        "Load or create a sample of federal contracts for transition detection. "
        "If no file is found, an empty dataframe with expected schema is produced. "
        "Writes checks JSON with coverage metrics."
    ),
)
def contracts_sample(context: AssetExecutionContext) -> Output[pd.DataFrame]:
    contracts_parquet = Path(
        os.getenv(
            "SBIR_ETL__TRANSITION__CONTRACTS_SAMPLE__PATH",
            "data/processed/contracts_sample.parquet",
        )
    )
    contracts_csv = contracts_parquet.with_suffix(".csv")

    # Expected schema (minimal, extend as needed)
    expected_cols = [
        "contract_id",  # canonical id (PIID preferred)
        "piid",
        "fain",
        "vendor_uei",
        "vendor_duns",
        "vendor_name",
        "action_date",
        "obligated_amount",
        "awarding_agency_code",
    ]
    df: pd.DataFrame
    src = None
    if contracts_parquet.exists():
        df = pd.read_parquet(contracts_parquet)
        src = str(contracts_parquet)
    elif contracts_csv.exists():
        df = pd.read_csv(contracts_csv)
        src = str(contracts_csv)
    else:
        df = pd.DataFrame({c: pd.Series(dtype="object") for c in expected_cols})
        src = "generated_empty"

    # Column aliases -> canonical names (best-effort)
    alias_map = {
        "uei": "vendor_uei",
        "duns": "vendor_duns",
        "recipient_name": "vendor_name",
        "federal_action_obligation": "obligated_amount",
        "awarding_agency": "awarding_agency_name",
    }
    for src_col, dst_col in alias_map.items():
        if src_col in df.columns and dst_col not in df.columns:
            df[dst_col] = df[src_col]
    # Ensure required columns exist (fill missing)
    for c in expected_cols:
        if c not in df.columns:
            df[c] = pd.Series(dtype="object")

    total = len(df)
    date_series = pd.to_datetime(df.get("action_date"), errors="coerce")
    date_cov = float(date_series.notna().mean()) if total > 0 else 0.0
    uei_cov = (
        float(df.get("vendor_uei", pd.Series(dtype=object)).notna().mean()) if total > 0 else 0.0
    )
    duns_cov = (
        float(df.get("vendor_duns", pd.Series(dtype=object)).notna().mean()) if total > 0 else 0.0
    )
    piid_cov = float(df.get("piid", pd.Series(dtype=object)).notna().mean()) if total > 0 else 0.0
    fain_cov = float(df.get("fain", pd.Series(dtype=object)).notna().mean()) if total > 0 else 0.0
    ident_cov = (
        float(
            (
                df.get("vendor_uei", pd.Series(dtype=object)).notna()
                | df.get("vendor_duns", pd.Series(dtype=object)).notna()
                | df.get("piid", pd.Series(dtype=object)).notna()
                | df.get("fain", pd.Series(dtype=object)).notna()
            ).mean()
        )
        if total > 0
        else 0.0
    )

    checks = {
        "ok": True,
        "reason": None,
        "source": src,
        "total_rows": total,
        "coverage": {
            "action_date": round(date_cov, 4),
            "any_identifier": round(ident_cov, 4),
            "vendor_uei": round(uei_cov, 4),
            "vendor_duns": round(duns_cov, 4),
            "piid": round(piid_cov, 4),
            "fain": round(fain_cov, 4),
        },
        "date_range": {
            "min": date_series.min().isoformat()
            if total > 0 and pd.notna(date_series.min())
            else None,
            "max": date_series.max().isoformat()
            if total > 0 and pd.notna(date_series.max())
            else None,
        },
        "generated_at": now_utc_iso(),
    }
    # Sample size thresholds (exposed via env)
    min_size = _env_int("SBIR_ETL__TRANSITION__CONTRACTS__SAMPLE_SIZE_MIN", 1000)
    max_size = _env_int("SBIR_ETL__TRANSITION__CONTRACTS__SAMPLE_SIZE_MAX", 10000)
    checks["sample_size"] = {
        "value": int(total),
        "min": int(min_size),
        "max": int(max_size),
        "in_range": bool(total >= int(min_size) and total <= int(max_size)) if total > 0 else False,
    }
    checks_path = contracts_parquet.with_suffix(".checks.json")
    write_json(checks_path, checks)

    meta = {
        "rows": total,
        "source": src,
        "checks_path": str(checks_path),
        "coverage": MetadataValue.json(checks["coverage"]),
    }
    context.log.info("Prepared contracts_sample", extra=meta)
    return Output(df, metadata=meta)


# -----------------------------
# 2) vendor_resolution
# -----------------------------


@asset(
    name="vendor_resolution",
    group_name="transition",
    compute_kind="pandas",
    description=(
        "Resolve contract vendors to SBIR recipients using UEI/DUNS exact matching and fuzzy name fallback. "
        "Outputs a mapping table and a checks JSON."
    ),
)
def vendor_resolution(
    context: AssetExecutionContext,
    contracts_sample: pd.DataFrame,
    enriched_sbir_awards: pd.DataFrame,
) -> Output[pd.DataFrame]:
    # Config
    fuzzy_threshold = _env_float("SBIR_ETL__TRANSITION__FUZZY__THRESHOLD", 0.85)
    out_path = Path("data/processed/vendor_resolution.parquet")
    checks_path = out_path.with_suffix(".checks.json")

    # Build a simple vendor index from SBIR awards
    # We will form a canonical vendor_id as UEI (preferred), else DUNS, else normalized name
    def _award_vendor_id(row: pd.Series) -> str:
        if pd.notna(row.get("UEI")) and str(row["UEI"]).strip():
            return f"uei:{str(row['UEI']).strip()}"
        if pd.notna(row.get("Duns")) and str(row["Duns"]).strip():
            return f"duns:{str(row['Duns']).strip()}"
        return f"name:{_norm_name(str(row.get('Company', '')))}"

    awards_min = enriched_sbir_awards.copy()
    if "award_id" not in awards_min.columns:
        # create a synthetic award_id if not present
        awards_min = awards_min.reset_index().rename(columns={"index": "award_id"})
        awards_min["award_id"] = awards_min["award_id"].apply(lambda x: f"award_{x}")

    awards_min["_vendor_id"] = awards_min.apply(_award_vendor_id, axis=1)

    # Prepare mapping of vendor_id -> award_ids
    vendor_to_awards: Dict[str, List[str]] = {}
    for vid, grp in awards_min.groupby("_vendor_id"):
        vendor_to_awards[vid] = list(grp["award_id"].astype(str).dropna().unique())

    # Resolve each contract vendor to a vendor_id
    rows: List[Dict[str, Any]] = []
    total_contracts = len(contracts_sample)
    resolved = 0

    for _, c in contracts_sample.iterrows():
        v_uei = str(c.get("vendor_uei") or "").strip()
        v_duns = str(c.get("vendor_duns") or "").strip()
        v_name_raw = str(c.get("vendor_name") or "")
        v_name = _norm_name(v_name_raw)

        # Try UEI
        if v_uei:
            vid = f"uei:{v_uei}"
            if vid in vendor_to_awards:
                rows.append(
                    {
                        "contract_id": c.get("contract_id") or c.get("piid") or "",
                        "matched_vendor_id": vid,
                        "match_method": "uei",
                        "confidence": 1.0,
                    }
                )
                resolved += 1
                continue

        # Try DUNS
        if v_duns:
            vid = f"duns:{v_duns}"
            if vid in vendor_to_awards:
                rows.append(
                    {
                        "contract_id": c.get("contract_id") or c.get("piid") or "",
                        "matched_vendor_id": vid,
                        "match_method": "duns",
                        "confidence": 1.0,
                    }
                )
                resolved += 1
                continue

        # Fuzzy name match (only if we have a name)
        if v_name:
            # simple nearest neighbor: compute best score over known name-based vendor ids
            best_vid = None
            best_score = -1.0
            for vid in vendor_to_awards.keys():
                if not vid.startswith("name:"):
                    continue
                candidate = vid.split("name:", 1)[1]
                score = float(fuzz.partial_ratio(v_name, candidate)) / 100.0
                if score > best_score:
                    best_score = score
                    best_vid = vid
            if best_vid and best_score >= fuzzy_threshold:
                rows.append(
                    {
                        "contract_id": c.get("contract_id") or c.get("piid") or "",
                        "matched_vendor_id": best_vid,
                        "match_method": "name_fuzzy",
                        "confidence": round(best_score, 4),
                    }
                )
                resolved += 1
                continue

        # No resolution
        rows.append(
            {
                "contract_id": c.get("contract_id") or c.get("piid") or "",
                "matched_vendor_id": None,
                "match_method": "unresolved",
                "confidence": 0.0,
            }
        )

    df_out = pd.DataFrame(rows)
    save_dataframe_parquet(df_out, out_path)

    # Checks
    coverage = float((df_out["match_method"] != "unresolved").mean()) if len(df_out) else 0.0
    checks = {
        "ok": True,
        "generated_at": now_utc_iso(),
        "stats": {
            "total_contracts": total_contracts,
            "resolved": resolved,
            "resolution_rate": round(coverage, 4),
            "by_method": df_out["match_method"].value_counts(dropna=False).to_dict(),
        },
    }
    write_json(checks_path, checks)

    meta = {
        "rows": len(df_out),
        "resolution_rate": coverage,
        "checks_path": str(checks_path),
        "output_path": str(out_path),
    }
    context.log.info("Produced vendor_resolution", extra=meta)
    return Output(df_out, metadata=meta)


# -----------------------------
# 3) transition_scores_v1
# -----------------------------


@asset(
    name="transition_scores_v1",
    group_name="transition",
    compute_kind="pandas",
    description=(
        "Compute initial award↔contract transition candidates with a simple rule-based score. "
        "Combines vendor_resolution with award lookups; caps candidates per award."
    ),
)
def transition_scores_v1(
    context: AssetExecutionContext,
    vendor_resolution: pd.DataFrame,
    contracts_sample: pd.DataFrame,
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
    vendor_to_awards: Dict[str, List[str]] = {}
    for vid, grp in awards.groupby("_vendor_id"):
        vendor_to_awards[vid] = list(grp["award_id"].astype(str).dropna().unique())

    # Lightweight score by method + small boosts from temporal and agency alignment
    METHOD_WEIGHTS = {"uei": 0.9, "duns": 0.8, "name_fuzzy": 0.7}
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

    def _award_date_from_row(r: Optional[pd.Series]):
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

    def _agency_from_award_row(r: Optional[pd.Series]) -> Tuple[Optional[str], Optional[str]]:
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

    results: List[Dict[str, Any]] = []
    # Build quick lookup for contracts by contract_id
    contracts_by_id = {
        str(c.get("contract_id") or c.get("piid") or ""): c for _, c in contracts_sample.iterrows()
    }

    for _, row in vendor_resolution.iterrows():
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
            contract_row = contracts_by_id.get(contract_id, {})
            c_date = _parse_date_any(contract_row.get("action_date"))
            a_row: Optional[pd.Series] = None
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


@asset(
    name="transition_evidence_v1",
    group_name="transition",
    compute_kind="pandas",
    description=(
        "Emit structured evidence for each transition candidate. "
        "Writes NDJSON under data/processed/transitions_evidence.ndjson."
    ),
)
def transition_evidence_v1(
    context: AssetExecutionContext,
    transition_scores_v1: pd.DataFrame,
    contracts_sample: pd.DataFrame,
) -> Output[str]:
    out_path = Path("data/processed/transitions_evidence.ndjson")
    _ensure_parent_dir(out_path)

    # Build lookup of contracts for quick evidence reference
    contracts_by_id: Dict[str, Dict[str, Any]] = {}
    for _, c in contracts_sample.iterrows():
        cid = str(c.get("contract_id") or c.get("piid") or "")
        contracts_by_id[cid] = {
            "piid": c.get("piid"),
            "fain": c.get("fain"),
            "vendor_uei": c.get("vendor_uei"),
            "vendor_duns": c.get("vendor_duns"),
            "vendor_name": c.get("vendor_name"),
            "action_date": c.get("action_date"),
            "awarding_agency_code": c.get("awarding_agency_code"),
        }

    threshold = _env_float("SBIR_ETL__TRANSITION__EVIDENCE_SCORE_MIN", 0.60)
    count = 0
    count_above = 0
    with out_path.open("w", encoding="utf-8") as fh:
        for _, row in transition_scores_v1.iterrows():
            cid = str(row.get("contract_id") or "")
            cs = contracts_by_id.get(cid, {})
            evidence = {
                "award_id": row.get("award_id"),
                "contract_id": cid,
                "score": row.get("score"),
                "method": row.get("method"),
                "matched_keys": row.get("signals") or [row.get("method")],
                "resolver_path": row.get("method"),
                "dates": {
                    "contract_action_date": cs.get("action_date"),
                },
                "amounts": {
                    "contract_obligated_amount": cs.get("obligated_amount"),
                },
                "agencies": {
                    "awarding_agency_code": cs.get("awarding_agency_code"),
                    "awarding_agency_name": cs.get("awarding_agency_name"),
                },
                "contract_snapshot": cs,
                "notes": None,
                "generated_at": now_utc_iso(),
            }
            fh.write(json.dumps(evidence) + "\n")
            count += 1
            if float(row.get("score") or 0.0) >= float(threshold):
                count_above += 1

    # Emit a lightweight validation summary for the MVP
    try:
        summary = {
            "generated_at": now_utc_iso(),
            "artifacts": {
                "transitions": "data/processed/transitions.parquet",
                "evidence": str(out_path),
                "evidence_checks": str(out_path.with_suffix(".checks.json")),
                "vendor_resolution_checks": "data/processed/vendor_resolution.checks.json",
                "contracts_sample_checks": "data/processed/contracts_sample.checks.json",
            },
            "candidates": {
                "total": int(len(transition_scores_v1)),
                "distinct_awards": int(transition_scores_v1["award_id"].nunique())
                if len(transition_scores_v1)
                else 0,
                "distinct_contracts": int(transition_scores_v1["contract_id"].nunique())
                if len(transition_scores_v1)
                else 0,
                "by_method": transition_scores_v1["method"].value_counts(dropna=False).to_dict()
                if len(transition_scores_v1)
                else {},
                "score": {
                    "min": float(transition_scores_v1["score"].min())
                    if len(transition_scores_v1)
                    else None,
                    "max": float(transition_scores_v1["score"].max())
                    if len(transition_scores_v1)
                    else None,
                    "mean": float(transition_scores_v1["score"].mean())
                    if len(transition_scores_v1)
                    else None,
                },
            },
            "gates": {},
        }

        # Best-effort: read checks and evaluate gates
        try:
            cs_checks_path = Path("data/processed/contracts_sample.checks.json")
            if cs_checks_path.exists():
                with cs_checks_path.open("r", encoding="utf-8") as fh:
                    cs = json.load(fh)
                date_cov = float(cs.get("coverage", {}).get("action_date", 0.0))
                any_id_cov = float(cs.get("coverage", {}).get("any_identifier", 0.0))
                date_min = _env_float("SBIR_ETL__TRANSITION__CONTRACTS__DATE_COVERAGE_MIN", 0.90)
                id_min = _env_float("SBIR_ETL__TRANSITION__CONTRACTS__IDENT_COVERAGE_MIN", 0.60)
                total_rows = int(cs.get("total_rows", 0))
                min_size = _env_int("SBIR_ETL__TRANSITION__CONTRACTS__SAMPLE_SIZE_MIN", 1000)
                max_size = _env_int("SBIR_ETL__TRANSITION__CONTRACTS__SAMPLE_SIZE_MAX", 10000)
                size_ok = (
                    (total_rows >= min_size) and (total_rows <= max_size)
                    if total_rows > 0
                    else False
                )
                enforce_size = _env_bool(
                    "SBIR_ETL__TRANSITION__CONTRACTS__ENFORCE_SAMPLE_SIZE", False
                )
                passed = (
                    (date_cov >= date_min)
                    and (any_id_cov >= id_min)
                    and (size_ok if enforce_size else True)
                )
                summary["gates"]["contracts_sample"] = {
                    "passed": passed,
                    "action_date_coverage": date_cov,
                    "any_identifier_coverage": any_id_cov,
                    "sample_size": {
                        "value": total_rows,
                        "min": min_size,
                        "max": max_size,
                        "in_range": size_ok,
                    },
                    "enforce_sample_size": enforce_size,
                    "thresholds": {
                        "action_date": date_min,
                        "any_identifier": id_min,
                        "sample_size": {"min": min_size, "max": max_size},
                    },
                }
        except Exception:
            pass

        try:
            vr_checks_path = Path("data/processed/vendor_resolution.checks.json")
            if vr_checks_path.exists():
                with vr_checks_path.open("r", encoding="utf-8") as fh:
                    vr = json.load(fh)
                res_rate = float(vr.get("stats", {}).get("resolution_rate", 0.0))
                min_rate = _env_float("SBIR_ETL__TRANSITION__VENDOR_RESOLUTION__MIN_RATE", 0.60)
                summary["gates"]["vendor_resolution"] = {
                    "passed": res_rate >= min_rate,
                    "resolution_rate": res_rate,
                    "threshold": min_rate,
                }
        except Exception:
            pass

        validation_path = Path("reports/validation/transition_mvp.json")
        _ensure_parent_dir(validation_path)
        write_json(validation_path, summary)
    except Exception:
        # Non-fatal; evidence should still be returned
        context.log.exception("Failed to write validation summary")

    # Checks JSON for evidence
    checks_path = out_path.with_suffix(".checks.json")
    num_above = (
        int((transition_scores_v1["score"] >= float(threshold)).sum())
        if len(transition_scores_v1)
        else 0
    )
    checks = {
        "ok": bool(count_above == num_above),
        "generated_at": now_utc_iso(),
        "rows": count,
        "source": str(out_path),
        "completeness": {
            "threshold": float(threshold),
            "candidates_above_threshold": int(num_above),
            "evidence_rows_for_above_threshold": int(count_above),
            "complete": bool(count_above == num_above),
        },
    }
    write_json(checks_path, checks)

    meta = {
        "rows": count,
        "path": str(out_path),
        "checks_path": str(checks_path),
        "validation_summary_path": "reports/validation/transition_mvp.json",
    }
    context.log.info("Wrote transition_evidence_v1", extra=meta)
    return Output(str(out_path), metadata=meta)


# -----------------------------
# 5) transition_analytics
# -----------------------------


@asset(
    name="transition_analytics",
    group_name="transition",
    compute_kind="pandas",
    description=(
        "Compute dual-perspective transition analytics (award/company rates, phase, agency) "
        "and emit a checks JSON for gating."
    ),
)
@asset(
    name="transition_detections",
    group_name="transition",
    compute_kind="pandas",
    description=(
        "Consolidated transition detections derived from transition_scores_v1. "
        "Writes parquet and logs basic metrics."
    ),
)
def transition_detections(
    context: AssetExecutionContext,
    transition_scores_v1: pd.DataFrame,
) -> Output[pd.DataFrame]:
    out_path = Path("data/processed/transition_detections.parquet")

    # Start from the scored candidates; ensure core columns exist
    df = transition_scores_v1.copy()
    required_cols = ["award_id", "contract_id", "score", "method", "computed_at"]
    for c in required_cols:
        if c not in df.columns:
            df[c] = None

    # Metrics
    threshold = _env_float("SBIR_ETL__TRANSITION__ANALYTICS__SCORE_THRESHOLD", 0.60)
    scores = (
        pd.to_numeric(df["score"], errors="coerce").fillna(0.0)
        if "score" in df.columns
        else pd.Series([], dtype=float)  # type: ignore
    )
    total = int(len(df))
    high_conf = int((scores >= threshold).sum()) if total > 0 else 0
    avg_score = float(scores.mean()) if total > 0 else 0.0
    by_method = (
        df["method"].value_counts(dropna=False).to_dict()
        if "method" in df.columns and total > 0
        else {}
    )

    # Persist detections table
    save_dataframe_parquet(df, out_path)

    # Log and return with metadata
    metrics = {
        "generated_at": now_utc_iso(),
        "total_candidates": total,
        "high_confidence_candidates": high_conf,
        "avg_score": round(avg_score, 6),
        "threshold": float(threshold),
        "by_method": by_method,
    }
    context.log.info("Produced transition_detections", extra=metrics)

    meta = {
        "output_path": str(out_path),
        "rows": total,
        "high_confidence_candidates": high_conf,
        "avg_score": avg_score,
        "threshold": float(threshold),
        "by_method": by_method,
    }
    return Output(df, metadata=meta)


def transition_analytics(
    context: AssetExecutionContext,
    enriched_sbir_awards: pd.DataFrame,
    transition_scores_v1: pd.DataFrame,
    contracts_sample: Optional[pd.DataFrame] = None,
) -> Output[str]:
    """
    Analyze transition candidates and awards to produce summary KPIs:
    - Award-level transition rate
    - Company-level transition rate
    - Phase effectiveness (I vs II)
    - By-agency transition rates
    - Optional: avg time-to-transition by agency (when dates are available)

    Writes:
      - data/processed/transition_analytics.json (summary)
      - data/processed/transition_analytics.checks.json (checks)
    """
    # Lazy import to keep module import-safe
    from src.transition.analysis.analytics import TransitionAnalytics  # noqa: WPS433

    score_threshold = _env_float("SBIR_ETL__TRANSITION__ANALYTICS__SCORE_THRESHOLD", 0.60)
    analytics = TransitionAnalytics(score_threshold=score_threshold)

    # Compute summary (contracts optional for time-to-transition metrics)
    summary = analytics.summarize(
        awards_df=enriched_sbir_awards,
        transitions_df=transition_scores_v1,
        contracts_df=contracts_sample,
    )

    # Persist summary JSON
    out_path = Path("data/processed/transition_analytics.json")
    _ensure_parent_dir(out_path)
    write_json(out_path, summary)

    # Build and write checks JSON
    award_rate = summary.get("award_transition_rate") or {}  # {"numerator","denominator","rate"}
    company_rate = summary.get("company_transition_rate") or {}
    checks = {
        "ok": True,
        "generated_at": now_utc_iso(),
        "score_threshold": float(score_threshold),
        "award_transition_rate": award_rate,
        "company_transition_rate": company_rate,
        "counts": {
            "total_awards": int(award_rate.get("denominator") or 0),
            "transitioned_awards": int(award_rate.get("numerator") or 0),
            "total_companies": int(company_rate.get("denominator") or 0),
            "companies_transitioned": int(company_rate.get("numerator") or 0),
        },
    }
    checks_path = out_path.with_suffix(".checks.json")
    write_json(checks_path, checks)

    meta = {
        "summary_path": str(out_path),
        "checks_path": str(checks_path),
        "award_transition_rate": MetadataValue.json(award_rate),
        "company_transition_rate": MetadataValue.json(company_rate),
    }
    context.log.info("Computed transition_analytics", extra=meta)
    return Output(str(out_path), metadata=meta)


# -----------------------------
# Asset checks (import-safe shims)
# -----------------------------
try:
    from dagster import asset_check, AssetCheckResult, AssetCheckSeverity
except Exception:  # pragma: no cover

    def asset_check(*args, **kwargs):  # type: ignore
        def _wrap(fn):
            return fn

        return _wrap

    @dataclass
    class AssetCheckResult:  # type: ignore
        passed: bool
        severity: str = "WARN"
        description: Optional[str] = None
        metadata: Optional[Dict[str, Any]] = None

    class AssetCheckSeverity:  # type: ignore
        ERROR = "ERROR"
        WARN = "WARN"


@asset_check(
    asset="contracts_sample",
    description="Contracts sample thresholds: action_date ≥ 0.90, any identifier ≥ 0.60, sample size within configured range",
)
def contracts_sample_quality_check(contracts_sample: pd.DataFrame) -> AssetCheckResult:
    total = len(contracts_sample)
    date_cov = float(contracts_sample["action_date"].notna().mean()) if total > 0 else 0.0
    ident_cov = (
        float(
            (
                (contracts_sample.get("vendor_uei", pd.Series(dtype=object)).notna())
                | (contracts_sample.get("vendor_duns", pd.Series(dtype=object)).notna())
                | (contracts_sample.get("piid", pd.Series(dtype=object)).notna())
                | (contracts_sample.get("fain", pd.Series(dtype=object)).notna())
            ).mean()
        )
        if total > 0
        else 0.0
    )
    min_date_cov = _env_float("SBIR_ETL__TRANSITION__CONTRACTS__DATE_COVERAGE_MIN", 0.90)
    min_ident_cov = _env_float("SBIR_ETL__TRANSITION__CONTRACTS__IDENT_COVERAGE_MIN", 0.60)
    min_size = _env_int("SBIR_ETL__TRANSITION__CONTRACTS__SAMPLE_SIZE_MIN", 1000)
    max_size = _env_int("SBIR_ETL__TRANSITION__CONTRACTS__SAMPLE_SIZE_MAX", 10000)
    size_ok = (total >= min_size) and (total <= max_size)
    enforce_size = _env_bool("SBIR_ETL__TRANSITION__CONTRACTS__ENFORCE_SAMPLE_SIZE", False)
    passed = (
        (date_cov >= min_date_cov)
        and (ident_cov >= min_ident_cov)
        and (size_ok if enforce_size else True)
    )
    return AssetCheckResult(
        passed=passed,
        severity=AssetCheckSeverity.ERROR if not passed else AssetCheckSeverity.WARN,
        description=(
            f"{'✓' if passed else '✗'} contracts_sample quality: "
            f"action_date={date_cov:.2%} (min {min_date_cov:.2%}), "
            f"any_identifier={ident_cov:.2%} (min {min_ident_cov:.2%}), "
            f"sample_size={total} (min {min_size}, max {max_size})"
        ),
        metadata={
            "total_rows": total,
            "action_date_coverage": f"{date_cov:.2%}",
            "any_identifier_coverage": f"{ident_cov:.2%}",
            "sample_size": {
                "value": total,
                "min": min_size,
                "max": max_size,
                "in_range": size_ok,
            },
            "thresholds": {
                "action_date_min": f"{min_date_cov:.2%}",
                "any_identifier_min": f"{min_ident_cov:.2%}",
                "sample_size_min": int(min_size),
                "sample_size_max": int(max_size),
            },
        },
    )


@asset_check(
    asset="vendor_resolution",
    description="Vendor resolution rate meets minimum threshold (default 60%)",
)
def vendor_resolution_quality_check(vendor_resolution: pd.DataFrame) -> AssetCheckResult:
    total = len(vendor_resolution)
    res_rate = (
        float((vendor_resolution["match_method"] != "unresolved").mean()) if total > 0 else 0.0
    )
    min_rate = _env_float("SBIR_ETL__TRANSITION__VENDOR_RESOLUTION__MIN_RATE", 0.60)
    passed = res_rate >= min_rate
    return AssetCheckResult(
        passed=passed,
        severity=AssetCheckSeverity.ERROR if not passed else AssetCheckSeverity.WARN,
        description=(
            f"{'✓' if passed else '✗'} vendor_resolution: "
            f"resolution_rate={res_rate:.2%} (min {min_rate:.2%})"
        ),
        metadata={
            "total_contracts": total,
            "resolution_rate": f"{res_rate:.2%}",
            "threshold": f"{min_rate:.2%}",
            "by_method": vendor_resolution["match_method"].value_counts(dropna=False).to_dict()
            if total > 0
            else {},
        },
    )


@asset_check(
    asset="transition_scores_v1",
    description="Transition scores quality: schema fields, score bounds [0,1], and non-empty signals",
)
def transition_scores_quality_check(transition_scores_v1: pd.DataFrame) -> AssetCheckResult:
    required_cols = ["award_id", "contract_id", "score", "method", "signals", "computed_at"]
    missing = [c for c in required_cols if c not in transition_scores_v1.columns]
    total = len(transition_scores_v1)

    # Validate score bounds and signals presence
    invalid_scores = 0
    empty_signals = 0
    if total > 0 and "score" in transition_scores_v1.columns:
        s = pd.to_numeric(transition_scores_v1["score"], errors="coerce")
        invalid_scores = int(((s < 0) | (s > 1) | (s.isna())).sum())

    if total > 0 and "signals" in transition_scores_v1.columns:

        def _is_empty_signals(v):
            if v is None:
                return True
            if isinstance(v, (list, tuple, set)):
                return len(v) == 0
            # Strings or other scalars: consider empty only if len == 0
            try:
                return len(v) == 0
            except Exception:
                return False

        empty_signals = int(transition_scores_v1["signals"].apply(_is_empty_signals).sum())
    else:
        # If signals column is absent, treat as fully empty
        empty_signals = total

    passed = (len(missing) == 0) and (invalid_scores == 0) and (empty_signals == 0)

    return AssetCheckResult(
        passed=passed,
        severity=AssetCheckSeverity.ERROR if not passed else AssetCheckSeverity.WARN,
        description=(
            f"{'✓' if passed else '✗'} transition_scores_v1 quality: "
            f"missing={len(missing)}, invalid_scores={invalid_scores}, empty_signals={empty_signals}"
        ),
        metadata={
            "total_rows": total,
            "missing_columns": missing,
            "invalid_score_count": invalid_scores,
            "empty_signals_count": empty_signals,
            "columns_present": list(transition_scores_v1.columns),
        },
    )


@asset_check(
    asset="transition_analytics",
    description="Sanity checks for transition analytics: positive denominators and 0≤rates≤1 (optional min-rate thresholds via env).",
)
def transition_analytics_quality_check(context: AssetExecutionContext) -> AssetCheckResult:
    """
    Validate transition_analytics KPIs using the emitted checks JSON.

    Gates:
      - award/company denominators > 0
      - 0 <= award/company rates <= 1
      - optional minimum thresholds via:
          SBIR_ETL__TRANSITION__ANALYTICS__MIN_AWARD_RATE (default 0.0)
          SBIR_ETL__TRANSITION__ANALYTICS__MIN_COMPANY_RATE (default 0.0)
    """
    from pathlib import Path as _Path
    import json as _json

    checks_path = _Path("data/processed/transition_analytics.checks.json")
    if not checks_path.exists():
        desc = "Missing transition_analytics.checks.json; analytics asset may not have run."
        context.log.error(desc)
        return AssetCheckResult(
            passed=False,
            severity=AssetCheckSeverity.ERROR,
            description=desc,
            metadata={"checks_path": str(checks_path), "reason": "missing_checks"},
        )

    try:
        payload = _json.loads(checks_path.read_text(encoding="utf-8"))
    except Exception as exc:
        desc = f"Failed to read analytics checks JSON: {exc}"
        context.log.error(desc)
        return AssetCheckResult(
            passed=False,
            severity=AssetCheckSeverity.ERROR,
            description=desc,
            metadata={"checks_path": str(checks_path), "reason": "read_error"},
        )

    award = payload.get("award_transition_rate") or {}
    company = payload.get("company_transition_rate") or {}

    def _safe_int(v, default=0):
        try:
            return int(v)
        except Exception:
            return default

    def _safe_float(v, default=0.0):
        try:
            return float(v)
        except Exception:
            return default

    a_num = _safe_int(award.get("numerator"))
    a_den = _safe_int(award.get("denominator"))
    a_rate = _safe_float(award.get("rate"))
    c_num = _safe_int(company.get("numerator"))
    c_den = _safe_int(company.get("denominator"))
    c_rate = _safe_float(company.get("rate"))

    # Basic sanity
    denom_ok = (a_den > 0) and (c_den > 0)
    rate_bounds_ok = (0.0 <= a_rate <= 1.0) and (0.0 <= c_rate <= 1.0)

    # Optional minimum thresholds
    min_award_rate = _env_float("SBIR_ETL__TRANSITION__ANALYTICS__MIN_AWARD_RATE", 0.0)
    min_company_rate = _env_float("SBIR_ETL__TRANSITION__ANALYTICS__MIN_COMPANY_RATE", 0.0)
    min_ok = (a_rate >= min_award_rate) and (c_rate >= min_company_rate)

    passed = denom_ok and rate_bounds_ok and min_ok

    return AssetCheckResult(
        passed=passed,
        severity=AssetCheckSeverity.ERROR if not passed else AssetCheckSeverity.WARN,
        description=(
            f"{'✓' if passed else '✗'} transition_analytics: "
            f"award_rate={a_rate:.2%} (den={a_den}, min {min_award_rate:.2%}), "
            f"company_rate={c_rate:.2%} (den={c_den}, min {min_company_rate:.2%})"
        ),
        metadata={
            "checks_path": str(checks_path),
            "award": {"num": a_num, "den": a_den, "rate": a_rate},
            "company": {"num": c_num, "den": c_den, "rate": c_rate},
            "thresholds": {
                "min_award_rate": min_award_rate,
                "min_company_rate": min_company_rate,
            },
            "sanity": {
                "denominators_positive": denom_ok,
                "rates_within_0_1": rate_bounds_ok,
            },
        },
    )


@asset_check(
    asset="transition_evidence_v1",
    description="Evidence completeness for candidates with score ≥ configured threshold",
)
def transition_evidence_quality_check(context: AssetExecutionContext) -> AssetCheckResult:
    """
    Check evidence completeness by consuming the checks JSON emitted by transition_evidence_v1.

    Passes when all candidates with score >= threshold have an evidence row.
    """
    from pathlib import Path as _Path
    import json as _json

    checks_path = _Path("data/processed/transitions_evidence.checks.json")
    if not checks_path.exists():
        desc = "Missing transitions_evidence.checks.json; evidence asset may not have run."
        context.log.error(desc)
        return AssetCheckResult(
            passed=False,
            severity=AssetCheckSeverity.ERROR,
            description=desc,
            metadata={"checks_path": str(checks_path), "reason": "missing_checks"},
        )

    try:
        payload = _json.loads(checks_path.read_text(encoding="utf-8"))
    except Exception as exc:
        desc = f"Failed to read evidence checks JSON: {exc}"
        context.log.error(desc)
        return AssetCheckResult(
            passed=False,
            severity=AssetCheckSeverity.ERROR,
            description=desc,
            metadata={"checks_path": str(checks_path), "reason": "read_error"},
        )

    comp = payload.get("completeness", {}) or {}
    complete = bool(comp.get("complete", False))
    threshold = comp.get("threshold")
    num_above = comp.get("candidates_above_threshold")
    ev_rows = comp.get("evidence_rows_for_above_threshold")

    return AssetCheckResult(
        passed=complete,
        severity=AssetCheckSeverity.ERROR if not complete else AssetCheckSeverity.WARN,
        description=(
            f"{'✓' if complete else '✗'} evidence completeness: "
            f"{ev_rows}/{num_above} candidates at≥{threshold}"
        ),
        metadata={
            "checks_path": str(checks_path),
            "threshold": threshold,
            "candidates_above_threshold": num_above,
            "evidence_rows_for_above_threshold": ev_rows,
            "complete": complete,
        },
    )
