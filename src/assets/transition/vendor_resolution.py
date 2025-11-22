"""Transition vendor resolution assets.

This module contains:
- enriched_vendor_resolution: Resolve contract vendors to SBIR recipients
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from .utils import (
    Output,
    VendorRecord,
    VendorResolver,
    _env_float,
    _norm_name,
    asset,
    now_utc_iso,
    save_dataframe_parquet,
    write_json,
)


@asset(
    name="enriched_vendor_resolution",
    group_name="enrichment",
    compute_kind="pandas",
    description=(
        "Resolve contract vendors to SBIR recipients using UEI/DUNS exact matching and fuzzy name fallback. "
        "Outputs a mapping table and a checks JSON."
    ),
)
def enriched_vendor_resolution(
    context,
    validated_contracts_sample: pd.DataFrame,
    enriched_sbir_awards: pd.DataFrame,
) -> Output[pd.DataFrame]:
    # Config
    fuzzy_threshold = _env_float("SBIR_ETL__TRANSITION__FUZZY__THRESHOLD", 0.85)
    out_path = Path("data/processed/vendor_resolution.parquet")
    checks_path = out_path.with_suffix(".checks.json")

    # Build resolver from SBIR awards
    award_vendors = []
    for _, award in enriched_sbir_awards.iterrows():
        # Create a unique, stable vendor_id for each award recipient
        vendor_id = None
        if pd.notna(award.get("UEI")) and str(award["UEI"]).strip():
            vendor_id = f"uei:{str(award['UEI']).strip()}"
        elif pd.notna(award.get("Duns")) and str(award["Duns"]).strip():
            vendor_id = f"duns:{str(award['Duns']).strip()}"
        else:
            vendor_id = f"name:{_norm_name(str(award.get('Company', '')))}"

        award_vendors.append(
            VendorRecord(
                uei=str(award["UEI"]) if pd.notna(award.get("UEI")) else None,
                duns=str(award["Duns"]) if pd.notna(award.get("Duns")) else None,
                cage=None,  # No CAGE code in SBIR awards data
                name=str(award["Company"]),
                metadata={"vendor_id": vendor_id},
            )
        )
    resolver = VendorResolver.from_records(award_vendors, fuzzy_threshold=fuzzy_threshold)
    context.log.info("Built VendorResolver", extra=resolver.stats())

    # Resolve each contract vendor
    rows: list[dict[str, Any]] = []
    for _, contract in validated_contracts_sample.iterrows():
        match = resolver.resolve(
            uei=str(contract.get("vendor_uei") or "").strip(),
            duns=str(contract.get("vendor_duns") or "").strip(),
            name=str(contract.get("vendor_name") or "").strip(),
        )
        if match.record:
            rows.append(
                {
                    "contract_id": contract.get("contract_id") or contract.get("piid") or "",
                    "matched_vendor_id": match.record.metadata.get("vendor_id"),
                    "match_method": match.method,
                    "confidence": match.score,
                }
            )
        else:
            rows.append(
                {
                    "contract_id": contract.get("contract_id") or contract.get("piid") or "",
                    "matched_vendor_id": None,
                    "match_method": "unresolved",
                    "confidence": 0.0,
                }
            )

    df_out = pd.DataFrame(rows)
    save_dataframe_parquet(df_out, out_path)

    # Checks
    total_contracts = len(df_out)
    resolved = int((df_out["match_method"] != "unresolved").sum())
    coverage = float(resolved / total_contracts) if total_contracts > 0 else 0.0
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
    return Output(df_out, metadata=meta)  # type: ignore[arg-type]


# -----------------------------
# 3) transition_scores_v1
# -----------------------------
