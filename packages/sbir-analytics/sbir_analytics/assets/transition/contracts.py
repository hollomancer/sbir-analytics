"""Transition contracts assets.

This module contains:
- raw_contracts: Load federal contracts from parquet or DB dump
- validated_contracts_sample: Create a validated sample of contracts
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

import pandas as pd

from sbir_etl.exceptions import FileSystemError
from sbir_etl.utils.cloud_storage import (
    resolve_data_path,
    sync_s3_prefix_to_dir,
    upload_file_to_s3,
)

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


# These are source-provenance fields, not optional conveniences.  A cached parquet
# created by the former positional extractor cannot support the label-free census
# unless all required fields are present as top-level columns. Null values are valid source
# values; column absence is what invalidates the cache.
RAW_CONTRACT_PROVENANCE_COLUMNS = frozenset(
    {
        "piid",
        "transaction_unique_id",
        "generated_unique_award_id",
        "research",
        "naics_code",
        "product_or_service_code",
    }
)
SOURCE_PROVENANCE_VERSION = 1
SOURCE_PROVENANCE_KEYS = frozenset(
    {
        "canonical_table",
        "physical_table",
        "member",
        "ordered_columns_sha256",
        "column_count",
        "toc_sha256",
        "vendor_filter_sha256",
        "output_sha256",
        "provenance_version",
    }
)


def contract_provenance_status(columns: Iterable[str]) -> dict[str, object]:
    """Describe whether a contract schema preserves the required raw source fields."""

    available = set(columns)
    present = sorted(RAW_CONTRACT_PROVENANCE_COLUMNS.intersection(available))
    missing = sorted(RAW_CONTRACT_PROVENANCE_COLUMNS - available)
    return {
        "required_columns": sorted(RAW_CONTRACT_PROVENANCE_COLUMNS),
        "present_columns": present,
        "missing_columns": missing,
        "complete": not missing,
        "authoritative_research_column": "research",
        "supplemental_sbir_phase_present": "sbir_phase" in available,
    }


def _parquet_columns(path: Path) -> list[str]:
    """Read only parquet schema metadata so stale caches can be rejected cheaply."""

    import pyarrow.parquet as pq

    return list(pq.read_schema(path).names)


def _file_sha256(path: Path) -> str | None:
    """Hash one local input without loading it into memory; missing files stay explicit."""

    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_cached_source_provenance(checks_path: Path) -> dict[str, object]:
    if not checks_path.is_file():
        return {}
    try:
        payload = json.loads(checks_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    provenance = payload.get("source_provenance")
    return dict(provenance) if isinstance(provenance, Mapping) else {}


def source_provenance_status(
    provenance: Mapping[str, object],
    *,
    toc_sha256: str | None,
    vendor_filter_sha256: str | None,
    output_sha256: str | None,
    table_files: list[str] | None,
) -> dict[str, object]:
    """Validate cache provenance against the currently configured source inputs."""

    missing = sorted(SOURCE_PROVENANCE_KEYS - set(provenance))
    mismatches: list[str] = []
    expected = {
        "toc_sha256": toc_sha256,
        "vendor_filter_sha256": vendor_filter_sha256,
        "output_sha256": output_sha256,
        "provenance_version": SOURCE_PROVENANCE_VERSION,
    }
    for key, value in expected.items():
        if value is None or provenance.get(key) != value:
            mismatches.append(key)

    if provenance.get("canonical_table") != "rpt.transaction_search":
        mismatches.append("canonical_table")
    if provenance.get("physical_table") not in {
        "rpt.transaction_search",
        "rpt.transaction_search_fpds",
    }:
        mismatches.append("physical_table")

    member = provenance.get("member")
    if not isinstance(member, str) or not member.endswith(".dat.gz"):
        mismatches.append("member")
    if table_files is not None and isinstance(member, str):
        configured = [Path(value).name for value in table_files]
        if configured != [Path(member).name]:
            mismatches.append("table_files")

    fingerprint = provenance.get("ordered_columns_sha256")
    if not isinstance(fingerprint, str) or len(fingerprint) != 64:
        mismatches.append("ordered_columns_sha256")
    column_count = provenance.get("column_count")
    if not isinstance(column_count, int) or isinstance(column_count, bool) or column_count <= 0:
        mismatches.append("column_count")

    return {
        "required_keys": sorted(SOURCE_PROVENANCE_KEYS),
        "missing_keys": missing,
        "mismatches": sorted(set(mismatches)),
        "complete": not missing and not mismatches,
    }


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

    # Optionally sync the dump from an S3 prefix into the local dump_dir. Selective:
    # when table_files is set we pull only those + toc.dat (avoids fetching the full
    # ~17GB dump); otherwise the whole prefix. Lets the asset run in a fresh/ephemeral
    # env (e.g. AWS Batch). Empty config = local only (unchanged behavior).
    dump_s3_prefix = config.paths.transition_dump_s3_prefix
    if dump_s3_prefix:
        include = ["toc.dat", *table_files] if table_files else None
        if include is None:
            context.log.warning(
                "transition_dump_s3_prefix is set without TABLE_FILES; syncing the "
                "entire dump prefix (potentially very large). Set "
                "SBIR_ETL__TRANSITION__CONTRACTS__TABLE_FILES to sync selectively."
            )
        try:
            sync_s3_prefix_to_dir(dump_s3_prefix, dump_dir, include=include)
            context.log.info(f"Synced dump from {dump_s3_prefix} -> {dump_dir} (include={include})")
        except Exception as e:
            context.log.warning(f"S3 dump sync failed ({e}); using local {dump_dir}")

    # Optionally source the vendor-filter JSON from S3 (S3-first, local fallback).
    vendor_filters_s3 = config.paths.transition_vendor_filters_s3_path
    if vendor_filters_s3:
        try:
            vendor_filter_path = resolve_data_path(
                vendor_filters_s3, local_fallback=vendor_filter_path
            )
            context.log.info(
                f"Resolved vendor filters: {vendor_filters_s3} -> {vendor_filter_path}"
            )
        except Exception as e:
            context.log.warning(
                f"S3 vendor-filter resolution failed ({e}); using local {vendor_filter_path}"
            )

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
    source_provenance: dict[str, object] = {}

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

    checks_path = output_path.with_suffix(".checks.json")
    toc_sha256 = _file_sha256(dump_dir / "toc.dat")
    vendor_filter_sha256 = _file_sha256(vendor_filter_path)
    cached_provenance: dict[str, object] | None = None
    cached_source_status: dict[str, object] | None = None
    cache_schema_error: str | None = None
    if output_path.exists() and not force_refresh:
        try:
            cached_provenance = contract_provenance_status(_parquet_columns(output_path))
            source_provenance = _read_cached_source_provenance(checks_path)
            cached_source_status = source_provenance_status(
                source_provenance,
                toc_sha256=toc_sha256,
                vendor_filter_sha256=vendor_filter_sha256,
                output_sha256=_file_sha256(output_path),
                table_files=table_files,
            )
        except Exception as exc:
            # An unreadable schema is not a reusable cache. The extraction below will
            # either replace it or fail explicitly against the configured dump.
            cache_schema_error = str(exc)
            context.log.warning(
                "Could not validate cached contracts provenance; forcing re-extraction",
                extra={"output_path": str(output_path), "error": cache_schema_error},
            )

    cache_is_complete = bool(
        cached_provenance
        and cached_provenance["complete"]
        and cached_source_status
        and cached_source_status["complete"]
    )
    needs_extract = force_refresh or not output_path.exists() or not cache_is_complete
    if output_path.exists() and not force_refresh and cached_provenance and not cache_is_complete:
        context.log.warning(
            "Cached contracts dataset does not match the verified source provenance; "
            "forcing re-extraction",
            extra={
                "output_path": str(output_path),
                "missing_columns": cached_provenance["missing_columns"],
                "source_status": cached_source_status,
            },
        )
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
        source_provenance = dict(extractor.source_provenance)
        source_provenance.update(
            {
                "toc_sha256": toc_sha256,
                "vendor_filter_sha256": vendor_filter_sha256,
                "provenance_version": SOURCE_PROVENANCE_VERSION,
            }
        )
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
    output_sha256 = _file_sha256(output_path)
    if needs_extract:
        source_provenance["output_sha256"] = output_sha256
    provenance = contract_provenance_status(df.columns)
    if not provenance["complete"]:
        raise FileSystemError(
            "Contracts output is missing required raw USAspending provenance columns: "
            f"{provenance['missing_columns']}",
            file_path=str(output_path),
            operation="contracts_ingestion",
            component="assets.transition",
            details={"provenance": provenance, "cache_schema_error": cache_schema_error},
        )
    current_source_status = source_provenance_status(
        source_provenance,
        toc_sha256=toc_sha256,
        vendor_filter_sha256=vendor_filter_sha256,
        output_sha256=output_sha256,
        table_files=table_files,
    )
    if not current_source_status["complete"]:
        raise FileSystemError(
            "Contracts output is not bound to the configured USAspending dump and "
            f"vendor frame: {current_source_status}",
            file_path=str(output_path),
            operation="contracts_ingestion",
            component="assets.transition",
            details={"source_provenance": source_provenance},
        )

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
        "transaction_unique_id": round(_coverage("transaction_unique_id"), 4),
        "generated_unique_award_id": round(_coverage("generated_unique_award_id"), 4),
        "research": round(_coverage("research"), 4),
        "naics_code": round(_coverage("naics_code"), 4),
        "product_or_service_code": round(_coverage("product_or_service_code"), 4),
    }

    checks = {
        "ok": True,
        "generated_at": now_utc_iso(),
        "total_rows": total_rows,
        "coverage": coverage,
        "provenance": provenance,
        "source_provenance": source_provenance,
        "source": {
            "dump_dir": str(dump_dir),
            "vendor_filter_path": str(vendor_filter_path),
            "table_files": table_files,
        },
    }

    write_json(checks_path, checks)

    # Optionally persist the extracted parquet back to S3 for cross-run reuse
    # (e.g. so a later/remote run can read it without re-extracting from the dump).
    # Empty config = local only (unchanged behavior).
    output_s3 = config.paths.transition_contracts_output_s3_path
    if output_s3:
        try:
            upload_file_to_s3(output_path, output_s3)
            context.log.info(f"Uploaded contracts output -> {output_s3}")
        except Exception as e:
            context.log.warning(
                f"S3 output upload failed ({e}); output remains local at {output_path}"
            )

    metadata = {
        "rows": total_rows,
        "output_path": str(output_path),
        "checks_path": str(checks_path),
        "coverage": MetadataValue.json(coverage),
        "provenance": MetadataValue.json(provenance),
        "source_provenance": MetadataValue.json(source_provenance),
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


# Rename map: source column (as produced by the extractor or a raw seed) -> the flat
# canonical column the transition sample expects. ``raw_contracts`` writes the FLAT
# ``transition_models.FederalContract`` schema, where vendor_uei / vendor_duns /
# vendor_name already match the canonical names — only amount/date/agency differ — so
# the bridge is a set of flat renames, not a nested flatten.
_CONTRACT_COLUMN_ALIASES = {
    # Defensive: raw USAspending-style column names, if a seed uses them.
    "uei": "vendor_uei",
    "duns": "vendor_duns",
    "recipient_name": "vendor_name",
    "federal_action_obligation": "obligated_amount",
    "awarding_agency": "awarding_agency_name",
    # Extractor output (transition_models.FederalContract) -> canonical sample schema.
    # action_date is now a real top-level field (the true USAspending transaction
    # action_date, column 2), so it maps through directly and needs no alias.
    "obligation_amount": "obligated_amount",
    "agency": "awarding_agency_name",
}


def normalize_contract_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Rename extractor/raw contract columns to the flat transition-sample schema.

    The extractor output is already flat — ``vendor_uei`` / ``vendor_duns`` /
    ``vendor_name`` / ``action_date`` match the canonical schema directly. This fills
    the remaining canonical columns (``obligated_amount`` / ``awarding_agency_name``)
    from their differently-named sources. Only fills a target column when it is
    **absent**, so an already-canonical seeded sample passes through unchanged. No-op
    on empty.
    """
    if df.empty:
        return df
    for src_col, dst_col in _CONTRACT_COLUMN_ALIASES.items():
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
        "(contracts_ingestion.parquet) — extractor/raw column names are normalized to "
        "the canonical flat schema (e.g. obligation_amount -> obligated_amount, "
        "agency -> awarding_agency_name; action_date maps through directly). If no file "
        "is found, an empty dataframe with the expected schema is produced. Writes "
        "checks JSON with coverage metrics."
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

    # Normalize extractor/raw column names to the flat canonical sample schema, so
    # contracts_ingestion.parquet can be used directly as the sample source.
    df = normalize_contract_columns(df)

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
