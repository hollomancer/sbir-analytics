"""Validate a reproducible NSF-to-defense lineage research release."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pandas as pd

RELEASE_PRODUCT_SCHEMAS: dict[str, tuple[str, set[str]]] = {
    "direct_awards": (
        "nsf_sbir_awards_direct.parquet",
        {
            "nsf_award_id",
            "nsf_organization_id",
            "nsf_start_date",
            "nsf_end_date",
            "nsf_award_performance_status",
            "source_path",
            "source_record_sha256",
            "analysis_date",
        },
    ),
    "reconciliation": (
        "nsf_sbir_award_reconciliation.parquet",
        {
            "nsf_organization_id",
            "reconciliation_disposition",
            "match_method",
            "match_confidence",
            "analysis_date",
        },
    ),
    "awardees": (
        "nsf_sbir_awardee_status.parquet",
        {"nsf_organization_id", "nsf_awardee_status", "analysis_date"},
    ),
    "prime_transactions": (
        "nsf_awardee_dod_prime_transactions.parquet",
        {
            "prime_transaction_id",
            "nsf_organization_id",
            "dod_award_generated_id",
            "funding_mode",
            "instrument_group",
            "signed_obligation_amount",
            "action_date",
            "fiscal_year",
            "recipient_match_method",
            "recipient_match_confidence",
            "source_record_id",
            "analysis_date",
        },
    ),
    "subaward_transactions": (
        "nsf_awardee_dod_subaward_transactions.parquet",
        {
            "subaward_transaction_id",
            "nsf_organization_id",
            "dod_award_generated_id",
            "funding_mode",
            "instrument_group",
            "signed_obligation_amount",
            "action_date",
            "fiscal_year",
            "recipient_match_method",
            "recipient_match_confidence",
            "source_record_id",
            "analysis_date",
        },
    ),
    "funding_summary": (
        "nsf_awardee_defense_funding_summary.parquet",
        {
            "nsf_organization_id",
            "fiscal_year",
            "funding_mode",
            "instrument_group",
            "signed_obligation_total",
            "source_transaction_ids",
            "nsf_awardee_status",
            "organization_resolution_method",
            "organization_resolution_confidence",
            "specific_award_usage_status",
            "critical_supply_chain_status",
            "analysis_date",
        },
    ),
    "award_defense_evidence": (
        "nsf_award_defense_evidence.parquet",
        {
            "evidence_assertion_id",
            "nsf_award_id",
            "nsf_organization_id",
            "specific_award_usage_status",
            "critical_supply_chain_status",
            "source_transaction_ids",
            "evidence_method",
            "review_award_descriptions",
            "review_transaction_descriptions",
            "review_product_service_codes",
            "analysis_date",
        },
    ),
    "critical_supply_chain_screen": (
        "nsf_sbir_critical_supply_chain_screen.parquet",
        {
            "nsf_award_id",
            "cet_taxonomy_version",
            "cet_classifier_version",
            "critical_supply_chain_review_candidate",
            "critical_supply_chain_status",
            "specific_award_usage_status",
            "defense_policy_mapping_status",
            "analysis_date",
        },
    ),
}

_UNIQUE_IDS = {
    "direct_awards": "nsf_award_id",
    "prime_transactions": "prime_transaction_id",
    "subaward_transactions": "subaward_transaction_id",
    "award_defense_evidence": "evidence_assertion_id",
    "critical_supply_chain_screen": "nsf_award_id",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _as_date(value: object) -> date | None:
    timestamp = pd.to_datetime(str(value), errors="coerce", utc=True)
    return None if pd.isna(timestamp) else timestamp.date()


def validate_nsf_defense_lineage_release(
    lineage_dir: Path | str,
    *,
    expected_analysis_date: date | None = None,
    as_of: date | None = None,
    max_release_age_days: int = 45,
) -> dict[str, Any]:
    """Validate manifests, checksums, schemas, dates, and conclusion guardrails."""

    if max_release_age_days < 0:
        raise ValueError("max_release_age_days must not be negative")
    directory = Path(lineage_dir)
    manifest_path = directory / "nsf_defense_lineage_manifest.json"
    quality_path = directory / "nsf_defense_lineage_quality.json"
    manifest = (
        json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else {}
    )
    quality = json.loads(quality_path.read_text(encoding="utf-8")) if quality_path.is_file() else {}
    manifest_analysis_date = _as_date(manifest.get("analysis_date"))
    effective_as_of = as_of or datetime.now(UTC).date()
    release_age = (
        (effective_as_of - manifest_analysis_date).days if manifest_analysis_date else None
    )
    products: dict[str, dict[str, Any]] = {}
    all_schemas_valid = True
    all_analysis_dates_consistent = True
    all_unique_ids_valid = True
    all_manifest_checksums_valid = True
    all_manifest_row_counts_valid = True
    declared_products = manifest.get("products", {})

    for name, (file_name, required_columns) in RELEASE_PRODUCT_SCHEMAS.items():
        path = directory / file_name
        product: dict[str, Any] = {
            "path": str(path),
            "exists": path.is_file(),
            "required_columns": sorted(required_columns),
        }
        if not path.is_file():
            product.update(
                {
                    "row_count": None,
                    "schema_valid": False,
                    "missing_columns": sorted(required_columns),
                    "analysis_date_consistent": False,
                    "unique_id_valid": False if name in _UNIQUE_IDS else None,
                    "manifest_checksum_valid": False,
                    "manifest_row_count_valid": False,
                }
            )
            all_schemas_valid = False
            all_analysis_dates_consistent = False
            all_manifest_checksums_valid = False
            all_manifest_row_counts_valid = False
            if name in _UNIQUE_IDS:
                all_unique_ids_valid = False
            products[name] = product
            continue
        frame = pd.read_parquet(path)
        missing_columns = sorted(required_columns - set(frame.columns))
        schema_valid = not missing_columns
        analysis_dates = (
            pd.to_datetime(frame["analysis_date"], errors="coerce", utc=True).dt.date
            if "analysis_date" in frame.columns
            else pd.Series(dtype="object")
        )
        analysis_date_consistent = bool(
            "analysis_date" in frame.columns
            and manifest_analysis_date is not None
            and (
                frame.empty
                or (
                    analysis_dates.notna().all() and analysis_dates.eq(manifest_analysis_date).all()
                )
            )
        )
        unique_column = _UNIQUE_IDS.get(name)
        unique_id_valid = (
            bool(
                unique_column in frame.columns
                and frame[unique_column].notna().all()
                and ~frame[unique_column].duplicated().any()
            )
            if unique_column
            else None
        )
        declared = declared_products.get(name, {}) if isinstance(declared_products, dict) else {}
        checksum = _sha256(path)
        checksum_valid = bool(declared and checksum == declared.get("sha256"))
        row_count_valid = bool(declared and len(frame) == declared.get("row_count"))
        product.update(
            {
                "row_count": len(frame),
                "sha256": checksum,
                "schema_valid": schema_valid,
                "missing_columns": missing_columns,
                "analysis_date_consistent": analysis_date_consistent,
                "unique_id_valid": unique_id_valid,
                "manifest_checksum_valid": checksum_valid,
                "manifest_row_count_valid": row_count_valid,
            }
        )
        all_schemas_valid &= schema_valid
        all_analysis_dates_consistent &= analysis_date_consistent
        all_manifest_checksums_valid &= checksum_valid
        all_manifest_row_counts_valid &= row_count_valid
        if unique_column:
            all_unique_ids_valid &= bool(unique_id_valid)
        products[name] = product

    screen_path = directory / "nsf_sbir_critical_supply_chain_screen.parquet"
    evidence_path = directory / "nsf_award_defense_evidence.parquet"
    conclusions_gated = False
    policy_mapping_deferred = False
    if screen_path.is_file() and evidence_path.is_file():
        screen = pd.read_parquet(screen_path)
        evidence = pd.read_parquet(evidence_path)
        conclusions_gated = bool(
            screen["critical_supply_chain_status"].eq("not_assessed").all()
            and screen["specific_award_usage_status"].eq("not_established").all()
            and evidence["critical_supply_chain_status"].eq("not_assessed").all()
            and evidence["specific_award_usage_status"].eq("not_established").all()
        )
        policy_mapping_deferred = bool(
            screen["defense_policy_mapping_status"]
            .eq("deferred_no_authoritative_dod14_or_ndis8_mapping")
            .all()
        )

    gates = {
        "manifest_present": manifest_path.is_file(),
        "quality_report_present": quality_path.is_file(),
        "upstream_quality_gates_passed": quality.get("quality_gates_passed") is True,
        "expected_analysis_date_matches": (
            expected_analysis_date is None or manifest_analysis_date == expected_analysis_date
        ),
        "release_not_future_dated": release_age is not None and release_age >= 0,
        "release_is_fresh": release_age is not None and release_age <= max_release_age_days,
        "product_schemas_valid": all_schemas_valid,
        "product_analysis_dates_consistent": all_analysis_dates_consistent,
        "source_grain_ids_unique": all_unique_ids_valid,
        "manifest_product_checksums_valid": all_manifest_checksums_valid,
        "manifest_product_row_counts_valid": all_manifest_row_counts_valid,
        "conclusions_remain_evidence_gated": conclusions_gated,
        "dod14_ndis8_mapping_remains_deferred": policy_mapping_deferred,
        "foci_excluded": manifest.get("source_boundaries", {}).get("foci_in_scope") is False,
        "grants_gov_not_used_as_ledger": manifest.get("source_boundaries", {}).get(
            "grants_gov_usage"
        )
        == "optional_solicitation_context_only",
    }
    return {
        "validated_at": datetime.now(UTC).isoformat(),
        "analysis_date": manifest_analysis_date.isoformat() if manifest_analysis_date else None,
        "release_age_days": release_age,
        "max_release_age_days": max_release_age_days,
        "products": products,
        "quality_gates": gates,
        "quality_gates_passed": bool(all(gates.values())),
    }


__all__ = ["RELEASE_PRODUCT_SCHEMAS", "validate_nsf_defense_lineage_release"]
