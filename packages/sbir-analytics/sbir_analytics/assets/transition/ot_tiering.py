"""OT consortium verification-tiering assets.

Downstream of transition detection. Classifies OT-consortium-linked records into
honest verification tiers (T1 member-confirmed; T2/T3/T4 unverifiable) and emits
a magnitude report whose unverifiable share is reported as a first-class number.

Two modes, selected by configuration:
- baseline (default): classify the existing detected transitions.
- audit: when ``SBIR_ETL__OT_CONSORTIUM__CLAIMS_PATH`` points at a claims file,
  classify those firm-reported covered-sales claims instead.

NOTE: per project convention, Dagster asset modules must NOT use
``from __future__ import annotations`` — it breaks runtime context validation.
"""

import json
import os
from pathlib import Path

import pandas as pd

from sbir_etl.ot_consortium.aggregate import aggregate_assignment_frame
from sbir_etl.ot_consortium.claims_loader import load_claims
from sbir_etl.ot_consortium.registry import CMFRegistry
from sbir_etl.ot_consortium.runner import (
    assignments_to_records,
    classify_baseline,
    classify_claims,
)

from .utils import (
    MetadataValue,
    Output,
    VendorRecord,
    VendorResolver,
    asset,
    now_utc_iso,
    save_dataframe_parquet,
    write_json,
)

_CLAIMS_PATH_ENV = "SBIR_ETL__OT_CONSORTIUM__CLAIMS_PATH"
_REGISTRY_PATH_ENV = "SBIR_ETL__OT_CONSORTIUM__CMF_REGISTRY_PATH"


def _load_registry() -> CMFRegistry:
    path = os.getenv(_REGISTRY_PATH_ENV)
    return CMFRegistry.from_csv(path)


def _build_firm_resolver(awards: pd.DataFrame):
    """Build a VendorResolver over the SBIR firms so audit-mode claims that cite
    only a firm name can be resolved to a canonical UEI (flagged name-resolved)."""
    if awards is None or awards.empty:
        return None
    records = []
    for a in awards.to_dict("records"):
        name = a.get("Company") or a.get("company") or a.get("company_name")
        uei = a.get("UEI") or a.get("uei")
        if name:
            records.append(
                VendorRecord(uei=str(uei) if uei else None, cage=None, duns=None, name=str(name))
            )
    return VendorResolver(records) if records else None


@asset(
    name="ot_consortium_verification_tiers",
    group_name="transformation",
    compute_kind="pandas",
    description=(
        "Classify OT-consortium-linked awards into honest verification tiers "
        "(T1 member-confirmed; T2 rollup-only; T3 structurally invisible; T4 no federal record). "
        "Baseline mode runs over detected transitions; audit mode runs over a firm claims file."
    ),
)
def ot_consortium_verification_tiers(
    context,
    transformed_transition_detections: pd.DataFrame,
    validated_contracts_sample: pd.DataFrame,
    enriched_sbir_awards: pd.DataFrame,
) -> Output[pd.DataFrame]:
    registry = _load_registry()
    out_path = Path("data/processed/ot_consortium_tiers.parquet")

    claims_path = os.getenv(_CLAIMS_PATH_ENV)
    non_attributable_count = 0
    non_attributable_usd = 0.0

    if claims_path and Path(claims_path).exists():
        mode = "audit"
        claims = load_claims(claims_path)
        # Locate claimed awards against the federal OT records, and resolve
        # name-only firms against the SBIR firm master.
        assignments, non_attributable = classify_claims(
            claims,
            registry,
            federal_records=validated_contracts_sample,
            resolver=_build_firm_resolver(enriched_sbir_awards),
        )
        non_attributable_count = len(non_attributable)
        non_attributable_usd = float(sum(c.claimed_obligation_usd or 0.0 for c in non_attributable))
        context.log.info(
            "OT tiering audit mode: %d claims, %d non-attributable aggregates",
            len(claims),
            non_attributable_count,
        )
    else:
        mode = "baseline"
        assignments = classify_baseline(
            transformed_transition_detections,
            validated_contracts_sample,
            enriched_sbir_awards,
            registry,
        )
        context.log.info("OT tiering baseline mode: %d classified", len(assignments))

    records = assignments_to_records(assignments)
    df = pd.DataFrame(records)
    # Evidence is a list-of-dicts; serialize for a stable parquet schema.
    if not df.empty and "evidence" in df.columns:
        df["evidence"] = df["evidence"].apply(json.dumps)
    save_dataframe_parquet(df, out_path)

    by_tier = df["tier"].value_counts(dropna=False).to_dict() if not df.empty else {}
    unverifiable = (
        int(df[~df["is_verifiable"]].shape[0]) if not df.empty and "is_verifiable" in df else 0
    )
    meta = {
        "mode": mode,
        "rows": int(len(df)),
        "by_tier": MetadataValue.json(by_tier),
        "unverifiable_count": unverifiable,
        "non_attributable_count": non_attributable_count,
        "non_attributable_obligated_usd": non_attributable_usd,
        "output_path": str(out_path),
        "generated_at": now_utc_iso(),
        "cmf_registry_has_verified_ueis": registry.has_verified_ueis(),
    }
    context.log.info("Produced ot_consortium_verification_tiers", extra=meta)
    return Output(df, metadata=meta)  # type: ignore[arg-type]


@asset(
    name="ot_consortium_magnitude_report",
    group_name="transformation",
    compute_kind="duckdb",
    description=(
        "Magnitude report for OT consortium tiers: counts and obligated $ per tier, overall and "
        "by CMF, agency, and fiscal year. The unverifiable share (T2+T3+T4) is reported prominently "
        "and never folded into the verified (T1) total."
    ),
)
def ot_consortium_magnitude_report(
    context,
    ot_consortium_verification_tiers: pd.DataFrame,
) -> Output[dict]:
    df = ot_consortium_verification_tiers
    mode = "audit" if os.getenv(_CLAIMS_PATH_ENV) else "baseline"

    report = aggregate_assignment_frame(df, mode=mode)
    report_dict = report.model_dump(mode="json")

    out_path = Path("reports/ot_consortium_magnitude_report.json")
    write_json(out_path, report_dict)

    meta = {
        "mode": mode,
        "total_count": report.total_count,
        "total_obligated_usd": report.total_obligated_usd,
        "verified_count": report.verified_count,
        "unverifiable_count": report.unverifiable_count,
        "unverifiable_obligated_usd": report.unverifiable_obligated_usd,
        "unverifiable_share": round(report.unverifiable_share, 4),
        "report_path": str(out_path),
        "fpds_lag_note": report.fpds_lag_note,
    }
    context.log.info("Produced ot_consortium_magnitude_report", extra=meta)
    return Output(report_dict, metadata=meta)  # type: ignore[arg-type]
