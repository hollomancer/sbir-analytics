"""Transition evidence assets.

This module contains:
- transformed_transition_evidence: Extract structured evidence for transitions
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from .utils import (
    Output,
    _ensure_parent_dir,
    _env_bool,
    _env_float,
    _env_int,
    asset,
    now_utc_iso,
    write_json,
)


@asset(
    name="transformed_transition_evidence",
    group_name="transformation",
    compute_kind="pandas",
    description=(
        "Emit structured evidence for each transition candidate. "
        "Writes NDJSON under data/processed/transitions_evidence.ndjson."
    ),
)
def transformed_transition_evidence(
    context,
    transformed_transition_scores: pd.DataFrame,
    validated_contracts_sample: pd.DataFrame,
) -> Output[str]:
    out_path = Path("data/processed/transitions_evidence.ndjson")
    _ensure_parent_dir(out_path)

    # Build lookup of contracts for quick evidence reference
    contracts_by_id: dict[str, dict[str, Any]] = {}
    for _, c in validated_contracts_sample.iterrows():
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
        for _, row in transformed_transition_scores.iterrows():
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
                "total": int(len(transformed_transition_scores)),
                "distinct_awards": int(transformed_transition_scores["award_id"].nunique())
                if len(transformed_transition_scores)
                else 0,
                "distinct_contracts": int(transformed_transition_scores["contract_id"].nunique())
                if len(transformed_transition_scores)
                else 0,
                "by_method": transformed_transition_scores["method"]
                .value_counts(dropna=False)
                .to_dict()
                if len(transformed_transition_scores)
                else {},
                "score": {
                    "min": float(transformed_transition_scores["score"].min())
                    if len(transformed_transition_scores)
                    else None,
                    "max": float(transformed_transition_scores["score"].max())
                    if len(transformed_transition_scores)
                    else None,
                    "mean": float(transformed_transition_scores["score"].mean())
                    if len(transformed_transition_scores)
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
                summary["gates"]["validated_contracts_sample"] = {
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
                summary["gates"]["enriched_vendor_resolution"] = {
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
        int((transformed_transition_scores["score"] >= float(threshold)).sum())
        if len(transformed_transition_scores)
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


