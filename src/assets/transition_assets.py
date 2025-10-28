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
        with ndjson_path.open("w", encoding="utf-8") as fh:
            for _, row in df.iterrows():
                fh.write(
                    json.dumps({k: (v if pd.notna(v) else None) for k, v in row.items()}) + "\n"
                )
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

    # Ensure required columns exist (fill missing)
    for c in expected_cols:
        if c not in df.columns:
            df[c] = pd.Series(dtype="object")

    total = len(df)
    date_cov = float(df["action_date"].notna().mean()) if total > 0 else 0.0
    ident_cov = (
        float(
            (
                (df["vendor_uei"].notna())
                | (df["vendor_duns"].notna())
                | (df["piid"].notna())
                | (df["fain"].notna())
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
        },
        "generated_at": now_utc_iso(),
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

            score = min(score_cap, score + date_boost + agency_boost)

            results.append(
                {
                    "award_id": aid,
                    "contract_id": contract_id,
                    "score": round(float(score), 4),
                    "method": method,
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

    count = 0
    with out_path.open("w", encoding="utf-8") as fh:
        for _, row in transition_scores_v1.iterrows():
            cid = str(row.get("contract_id") or "")
            evidence = {
                "award_id": row.get("award_id"),
                "contract_id": cid,
                "score": row.get("score"),
                "method": row.get("method"),
                "matched_keys": [row.get("method")],
                "contract_snapshot": contracts_by_id.get(cid, {}),
                "notes": None,
                "generated_at": now_utc_iso(),
            }
            fh.write(json.dumps(evidence) + "\n")
            count += 1

    # Emit a lightweight validation summary for the MVP
    try:
        summary = {
            "generated_at": now_utc_iso(),
            "artifacts": {
                "transitions": "data/processed/transitions.parquet",
                "evidence": str(out_path),
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
                summary["gates"]["contracts_sample"] = {
                    "passed": (date_cov >= date_min) and (any_id_cov >= id_min),
                    "action_date_coverage": date_cov,
                    "any_identifier_coverage": any_id_cov,
                    "thresholds": {"action_date": date_min, "any_identifier": id_min},
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

    meta = {
        "rows": count,
        "path": str(out_path),
        "validation_summary_path": "reports/validation/transition_mvp.json",
    }
    context.log.info("Wrote transition_evidence_v1", extra=meta)
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
    description="Contracts sample coverage thresholds: action_date ≥ 0.90, any identifier ≥ 0.60",
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
    passed = (date_cov >= min_date_cov) and (ident_cov >= min_ident_cov)
    return AssetCheckResult(
        passed=passed,
        severity=AssetCheckSeverity.ERROR if not passed else AssetCheckSeverity.WARN,
        description=(
            f"{'✓' if passed else '✗'} contracts_sample coverage: "
            f"action_date={date_cov:.2%} (min {min_date_cov:.2%}), "
            f"any_identifier={ident_cov:.2%} (min {min_ident_cov:.2%})"
        ),
        metadata={
            "total_rows": total,
            "action_date_coverage": f"{date_cov:.2%}",
            "any_identifier_coverage": f"{ident_cov:.2%}",
            "thresholds": {
                "action_date_min": f"{min_date_cov:.2%}",
                "any_identifier_min": f"{min_ident_cov:.2%}",
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
