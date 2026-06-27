"""Transition contracts assets.

This module contains:
- raw_contracts: Load federal contracts from parquet or DB dump
- validated_contracts_sample: Create a validated sample of contracts
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pandas as pd

from sbir_etl.exceptions import FileSystemError

from .utils import (
    ContractExtractor,
    MetadataValue,
    Output,
    _ensure_parent_dir,
    _env_bool,
    _env_int,
    asset,
    get_config,
    now_utc_iso,
    write_json,
)


@asset(
    name="raw_contracts",
    group_name="ingestion",
    compute_kind="python",
    description=(
        "Extract SBIR-relevant USAspending transactions from removable storage and persist "
        "them to Parquet for downstream transition detection."
    ),
)
def raw_contracts(context) -> Output[pd.DataFrame]:
    # Load configuration
    config = get_config()

    # Get paths from configuration (with environment variable override support)
    output_path = config.paths.resolve_path("transition_contracts_output")
    dump_dir = config.paths.resolve_path("transition_dump_dir")
    vendor_filter_path = config.paths.resolve_path("transition_vendor_filters")
    table_files_env = os.getenv("SBIR_ETL__TRANSITION__CONTRACTS__TABLE_FILES")
    table_files = (
        [item.strip() for item in table_files_env.split(",") if item.strip()]
        if table_files_env
        else None
    )
    batch_size = _env_int("SBIR_ETL__TRANSITION__CONTRACTS__BATCH_SIZE", 10000)
    force_refresh = _env_bool("SBIR_ETL__TRANSITION__CONTRACTS__FORCE_REFRESH", False)

    context.log.info(
        "Starting contracts_ingestion",
        extra={
            "output_path": str(output_path),
            "dump_dir": str(dump_dir),
            "vendor_filter_path": str(vendor_filter_path),
            "force_refresh": force_refresh,
            "table_files": table_files,
        },
    )

    stats_snapshot: dict[str, Any] | None = None

    if not dump_dir.exists():
        raise FileSystemError(
            f"USAspending dump directory not found: {dump_dir}",
            file_path=str(dump_dir),
            operation="contracts_sample",
            component="assets.transition",
        )
    if not vendor_filter_path.exists():
        raise FileSystemError(
            f"Vendor filter file not found: {vendor_filter_path}",
            file_path=str(vendor_filter_path),
            operation="contracts_sample",
            component="assets.transition",
        )

    needs_extract = force_refresh or not output_path.exists()
    if needs_extract:
        _ensure_parent_dir(output_path)
        extractor = ContractExtractor(
            vendor_filter_file=vendor_filter_path,
            batch_size=batch_size,
        )
        extracted_count = extractor.extract_from_dump(
            dump_dir=dump_dir,
            output_file=output_path,
            table_files=table_files,
        )
        context.log.info(
            "Contracts extraction complete",
            extra={"rows_written": extracted_count, "output_path": str(output_path)},
        )
        stats_snapshot = dict(extractor.stats)
    else:
        context.log.info(
            "Reusing existing contracts dataset", extra={"output_path": str(output_path)}
        )

    if not output_path.exists():
        raise FileSystemError(
            f"Expected contracts output at {output_path}",
            file_path=str(output_path),
            operation="contracts_sample",
            component="assets.transition",
        )

    df = pd.read_parquet(output_path)
    total_rows = len(df)

    def _coverage(column: str) -> float:
        if column not in df.columns or total_rows == 0:
            return 0.0
        return float(df[column].notna().mean())

    action_date_cov = _coverage("action_date")
    if action_date_cov == 0.0:
        action_date_cov = _coverage("start_date")

    coverage = {
        "action_date": round(action_date_cov, 4),
        "vendor_uei": round(_coverage("vendor_uei"), 4),
        "vendor_duns": round(_coverage("vendor_duns"), 4),
        "vendor_cage": round(_coverage("vendor_cage"), 4),
        "contract_id": round(_coverage("contract_id"), 4),
    }

    checks = {
        "ok": True,
        "generated_at": now_utc_iso(),
        "total_rows": total_rows,
        "coverage": coverage,
        "source": {
            "dump_dir": str(dump_dir),
            "vendor_filter_path": str(vendor_filter_path),
            "table_files": table_files,
        },
    }

    checks_path = output_path.with_suffix(".checks.json")
    write_json(checks_path, checks)

    metadata = {
        "rows": total_rows,
        "output_path": str(output_path),
        "checks_path": str(checks_path),
        "coverage": MetadataValue.json(coverage),
    }
    if stats_snapshot:
        metadata["extraction_stats"] = MetadataValue.json(stats_snapshot)

    context.log.info(
        "contracts_ingestion completed",
        extra={"rows": total_rows, "checks_path": str(checks_path)},
    )

    return Output(df, metadata=metadata)  # type: ignore[arg-type]


# -----------------------------
# 1) contracts_sample
# -----------------------------


# Maps the nested FederalContract.model_dump() schema (what raw_contracts writes to
# contracts_ingestion.parquet) onto the flat columns the transition sample expects.
# Each entry: flat_target -> (nested_column, key_inside_that_dict).
_CONTRACT_NESTED_FLATTEN = {
    "vendor_uei": ("vendor", "uei"),
    "vendor_duns": ("vendor", "duns_number"),
    "vendor_name": ("vendor", "name"),
    "vendor_cage": ("vendor", "cage_code"),
    "obligated_amount": ("value", "obligated_amount"),
    "action_date": ("period", "effective_date"),
}
# Flat renames where the extractor's column name differs from the expected one.
_CONTRACT_FLAT_RENAME = {
    "agency_code": "awarding_agency_code",
    "agency_name": "awarding_agency_name",
}


def flatten_contract_records(df: pd.DataFrame) -> pd.DataFrame:
    """Flatten a FederalContract-dump DataFrame to the flat transition-sample schema.

    ``raw_contracts`` writes ``FederalContract.model_dump()`` rows, where ``vendor`` /
    ``value`` / ``period`` are **nested dicts** — so the flat ``vendor_uei`` /
    ``obligated_amount`` / ``action_date`` columns the detection chain needs are
    absent. This lifts those nested values up to flat columns (and renames
    ``agency_code`` → ``awarding_agency_code``), letting ``validated_contracts_sample``
    consume the extractor output directly (e.g. via ``CONTRACTS_SAMPLE__PATH`` pointed
    at ``contracts_ingestion.parquet``).

    Only fills a flat target when it is **absent**, so an already-flat seeded sample
    passes through unchanged. No-op on an empty frame.
    """
    if df.empty:
        return df

    def _from_nested(col: str, key: str) -> pd.Series | None:
        if col not in df.columns:
            return None
        return df[col].apply(lambda v: v.get(key) if isinstance(v, dict) else None)

    # Record which flat targets were absent up front, so we never touch values that
    # a flat seed already provided (the "absent only" contract).
    action_date_derived = "action_date" not in df.columns

    for dst, (col, key) in _CONTRACT_NESTED_FLATTEN.items():
        if dst not in df.columns:
            values = _from_nested(col, key)
            if values is not None:
                df[dst] = values

    # signed_date fallback applies only to an action_date we just derived from the
    # nested period (effective_date) — never to a pre-existing flat action_date.
    if action_date_derived and "action_date" in df.columns:
        signed = _from_nested("period", "signed_date")
        if signed is not None:
            df["action_date"] = df["action_date"].where(df["action_date"].notna(), signed)

    for src_col, dst_col in _CONTRACT_FLAT_RENAME.items():
        if src_col in df.columns and dst_col not in df.columns:
            df[dst_col] = df[src_col]

    return df


@asset(
    name="validated_contracts_sample",
    group_name="validation",
    compute_kind="pandas",
    description=(
        "Load or create a sample of federal contracts for transition detection. "
        "Accepts either a flat seeded sample or the raw extractor output "
        "(contracts_ingestion.parquet, nested FederalContract schema) — the nested "
        "vendor/value/period columns are flattened to the expected flat schema. "
        "If no file is found, an empty dataframe with expected schema is produced. "
        "Writes checks JSON with coverage metrics."
    ),
)
def validated_contracts_sample(context) -> Output[pd.DataFrame]:
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

    # Flatten the extractor's nested vendor/value/period schema (no-op for flat seeds),
    # so contracts_ingestion.parquet can be used directly as the sample source.
    df = flatten_contract_records(df)

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
    date_series = pd.to_datetime(df.get("action_date", pd.Series(dtype=object)), errors="coerce")
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
                (df.get("vendor_uei", pd.Series(dtype=object)).notna())
                | (df.get("vendor_duns", pd.Series(dtype=object)).notna())
                | (df.get("piid", pd.Series(dtype=object)).notna())
                | (df.get("fain", pd.Series(dtype=object)).notna())
            ).mean()
        )
        if total > 0
        else 0.0
    )

    # Calculate parent-child relationship statistics
    parent_contract_col = df.get("parent_contract_id", pd.Series(dtype=object))
    contract_award_type_col = df.get("contract_award_type", pd.Series(dtype=object))
    child_rows = int(parent_contract_col.notna().sum()) if total > 0 else 0
    idv_parent_rows = 0
    if total > 0 and contract_award_type_col is not None:
        idv_parent_mask = contract_award_type_col.astype(str).str.upper().str.startswith("IDV")
        idv_parent_rows = int(idv_parent_mask.sum())
    child_ratio = child_rows / total if total > 0 else 0.0
    idv_parent_ratio = idv_parent_rows / total if total > 0 else 0.0
    parent_child_stats = {
        "child_rows": child_rows,
        "idv_parent_rows": idv_parent_rows,
        "child_ratio": round(child_ratio, 4),
        "idv_parent_ratio": round(idv_parent_ratio, 4),
    }

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
        "parent_child": parent_child_stats,
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
    checks["sample_size"] = {  # type: ignore[assignment]
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
        "coverage": MetadataValue.json(checks["coverage"]),  # type: ignore[arg-type]
    }
    context.log.info("Prepared contracts_sample", extra=meta)
    return Output(df, metadata=meta)  # type: ignore[arg-type]


# -----------------------------
# 2) vendor_resolution
# -----------------------------
