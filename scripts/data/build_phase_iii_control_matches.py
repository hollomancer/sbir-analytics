#!/usr/bin/env python3
"""Materialize pre-outcome Phase III control covariates, exact matches, and balance."""

import argparse
import hashlib
import json
import os
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from sbir_analytics.assets.phase_iii_census.assets import verify_frozen_spec
from sbir_analytics.assets.phase_iii_negative_controls import (
    CONTRACT_COLUMNS,
    build_balance_table,
    build_control_firm_frame,
    build_firm_covariates,
    build_treated_firm_frame,
    exact_match_controls,
    exclude_fpds_coded_awardees,
    exclude_phase_ii_awardees,
    require_covariate_balance,
    require_reliable_sam_eligibility,
    summarize_covariate_coverage,
    summarize_matching,
)


FEBRUARY_MIRROR_IDENTITY = {
    "archive_etag": '"69935c7e-2716dfff13"',
    "archive_total_bytes": 167_887_503_123,
    "canonical_table": "rpt.transaction_search",
    "column_count": 374,
    "member": "5924.dat.gz",
    "member_crc32": "2229c73c",
    "member_sha256": "619ef8f5ccd6e28f21deb49576fba0f4b0ce146a5b2e946e119006f3f892765b",
    "ordered_columns_sha256": "f3588a6dbce5b7633272969b95bd1fa717e899a5dd0333587e3711655de5ec6c",
    "physical_table": "rpt.transaction_search_fpds",
    "toc_sha256": "142c834a2fc98c9bb3b914e115eee8b3b37399f4e135acbf13fa71ee5abca54c",
}
FPDS_SBIR_STTR_CODES = ("SR1", "SR2", "SR3", "ST1", "ST2", "ST3")


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_parquet_atomic(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        frame.to_parquet(temporary, index=False)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _write_json_atomic(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump(payload, output, indent=2, sort_keys=True)
            output.write("\n")
        os.replace(temporary_name, path)
    finally:
        Path(temporary_name).unlink(missing_ok=True)


def _read_json_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is missing or unreadable at {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _verify_february_contracts(path: Path, vendor_filter_path: Path) -> dict[str, Any]:
    checks = _read_json_object(path.with_suffix(".checks.json"), label="contract provenance")
    source = checks.get("source_provenance")
    if checks.get("ok") is not True or not isinstance(source, Mapping):
        raise ValueError("contract provenance did not pass extraction checks")
    mismatches = {
        key: {"expected": expected, "observed": source.get(key)}
        for key, expected in FEBRUARY_MIRROR_IDENTITY.items()
        if source.get(key) != expected
    }
    if mismatches:
        raise ValueError(f"contract source is not the pinned February mirror: {mismatches}")
    output_sha256 = _file_sha256(path)
    if source.get("output_sha256") != output_sha256:
        raise ValueError("contract parquet SHA-256 differs from its extraction provenance")
    vendor_sha256 = _file_sha256(vendor_filter_path)
    if source.get("vendor_filter_sha256") != vendor_sha256:
        raise ValueError("contract extraction used a different vendor-filter frame")
    return {
        "path": str(path),
        "sha256": output_sha256,
        "rows": checks.get("total_rows"),
        "source_provenance": dict(source),
    }


def _verify_phase_ii(path: Path) -> dict[str, Any]:
    checks = _read_json_object(path.with_suffix(".checks.json"), label="Phase II provenance")
    output = checks.get("output")
    if (
        checks.get("ok") is not True
        or checks.get("schema_version") != "phase-ii-awards-v2"
        or not isinstance(output, Mapping)
    ):
        raise ValueError("Phase II provenance has an unsupported schema")
    digest = _file_sha256(path)
    if output.get("sha256") != digest:
        raise ValueError("Phase II parquet SHA-256 differs from its provenance")
    return {"path": str(path), "sha256": digest, "rows": output.get("rows")}


def _load_pre_outcome_contract_rows(path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Read only earliest-contract covariates and eligibility codes via DuckDB."""

    connection = duckdb.connect()
    try:
        columns = connection.execute("SELECT name FROM parquet_schema(?)", [str(path)]).df()["name"]
        required = set(CONTRACT_COLUMNS) | {"research"}
        if missing := sorted(required - set(columns)):
            raise ValueError(f"February contract parquet is missing required columns: {missing}")
        first_rows = connection.execute(
            """
            WITH source AS (
                SELECT
                    upper(trim(vendor_uei)) AS vendor_uei,
                    CAST(action_date AS DATE) AS action_date,
                    product_or_service_code,
                    metadata
                FROM read_parquet(?)
                WHERE vendor_uei IS NOT NULL AND action_date IS NOT NULL
            ),
            first_dates AS (
                SELECT vendor_uei, min(action_date) AS first_action_date
                FROM source
                GROUP BY vendor_uei
            )
            SELECT source.*
            FROM source
            INNER JOIN first_dates
                ON source.vendor_uei = first_dates.vendor_uei
                AND source.action_date = first_dates.first_action_date
            ORDER BY source.vendor_uei, source.product_or_service_code
            """,
            [str(path)],
        ).df()
        placeholders = ", ".join("?" for _ in FPDS_SBIR_STTR_CODES)
        coded = connection.execute(
            f"""
            SELECT DISTINCT upper(trim(vendor_uei)) AS vendor_uei, upper(trim(research)) AS research
            FROM read_parquet(?)
            WHERE upper(trim(research)) IN ({placeholders})
            ORDER BY vendor_uei, research
            """,
            [str(path), *FPDS_SBIR_STTR_CODES],
        ).df()
    finally:
        connection.close()
    return first_rows, coded


def run(
    sam_path: Path,
    eligibility_path: Path,
    phase_ii_path: Path,
    contracts_path: Path,
    vendor_filter_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Write all pre-outcome artifacts, then enforce the SMD stop gate."""

    freeze = verify_frozen_spec()
    contract_provenance = _verify_february_contracts(contracts_path, vendor_filter_path)
    phase_ii_provenance = _verify_phase_ii(phase_ii_path)
    sam = pd.read_parquet(
        sam_path, columns=["unique_entity_id", "primary_naics", "physical_address_state"]
    )
    initial_eligibility = pd.read_parquet(eligibility_path)
    require_reliable_sam_eligibility(initial_eligibility)
    phase_ii = pd.read_parquet(phase_ii_path, columns=["recipient_uei"])
    first_contract_rows, coded_awardees = _load_pre_outcome_contract_rows(contracts_path)

    eligibility = exclude_phase_ii_awardees(initial_eligibility, phase_ii)
    eligibility = exclude_fpds_coded_awardees(eligibility, coded_awardees)
    require_reliable_sam_eligibility(eligibility)
    treated_firms = build_treated_firm_frame(phase_ii)
    control_firms = build_control_firm_frame(eligibility)
    treated_covariates = build_firm_covariates(treated_firms, sam, first_contract_rows)
    control_covariates = build_firm_covariates(control_firms, sam, first_contract_rows)
    coverage = pd.concat(
        [
            summarize_covariate_coverage(treated_covariates, arm="sbir"),
            summarize_covariate_coverage(control_covariates, arm="control"),
        ],
        ignore_index=True,
    )
    matches = exact_match_controls(treated_covariates, control_covariates)
    matching_summary = summarize_matching(treated_covariates, matches)
    balance = build_balance_table(matches)

    artifacts = {
        "eligibility": output_dir / "phase_iii_control_eligibility.parquet",
        "treated_covariates": output_dir / "phase_iii_treated_covariates.parquet",
        "control_covariates": output_dir / "phase_iii_control_covariates.parquet",
        "coverage": output_dir / "phase_iii_covariate_coverage.parquet",
        "matches": output_dir / "phase_iii_control_matches.parquet",
        "matching_summary": output_dir / "phase_iii_matching_summary.parquet",
        "balance": output_dir / "phase_iii_balance.parquet",
    }
    frames = {
        "eligibility": eligibility,
        "treated_covariates": treated_covariates,
        "control_covariates": control_covariates,
        "coverage": coverage,
        "matches": matches,
        "matching_summary": matching_summary,
        "balance": balance,
    }
    for label, path in artifacts.items():
        _write_parquet_atomic(frames[label], path)

    summary = {
        "schema_version": "phase-iii-control-matching-v1",
        "pre_outcome_only": True,
        "census_filter_invoked": False,
        "contract_fields_read": {
            "eligibility_only": ["vendor_uei", "research"],
            "matching_covariates_only": [
                "vendor_uei",
                "action_date",
                "product_or_service_code",
                "metadata.business_categories",
            ],
        },
        "stochastic": False,
        "freeze": freeze,
        "inputs": {
            "sam": {"path": str(sam_path), "sha256": _file_sha256(sam_path), "rows": len(sam)},
            "initial_eligibility": {
                "path": str(eligibility_path),
                "sha256": _file_sha256(eligibility_path),
                "rows": len(initial_eligibility),
            },
            "phase_ii": phase_ii_provenance,
            "contracts": contract_provenance,
            "vendor_filter": {
                "path": str(vendor_filter_path),
                "sha256": _file_sha256(vendor_filter_path),
            },
        },
        "counts": {
            "fpds_coded_candidate_firms": int(
                eligibility["matched_fpds_sbir_sttr_ueis"].map(bool).sum()
            ),
            "phase_ii_intersecting_candidate_firms": int(
                eligibility["matched_phase_ii_ueis"].map(bool).sum()
            ),
            "treated_firms": len(treated_covariates),
            "match_eligible_treated_firms": int(treated_covariates["match_eligible"].sum()),
            "control_firms": len(control_covariates),
            "match_eligible_control_firms": int(control_covariates["match_eligible"].sum()),
            "matched_pairs": len(matches),
            "matched_treated_firms": int(matches["treated_firm_id"].nunique()),
        },
        "artifacts": {
            label: {"path": str(path), "sha256": _file_sha256(path), "rows": len(frames[label])}
            for label, path in artifacts.items()
        },
        "balance_flag": 0.1,
        "balance_passed": bool(not balance["flagged_above_0_1"].any())
        if not balance.empty
        else False,
        "requires_review_before_outcomes": True,
    }
    summary_path = output_dir / "phase_iii_control_matching.json"
    _write_json_atomic(summary, summary_path)
    require_covariate_balance(balance)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sam", type=Path, default=Path("data/raw/sam_gov/sam_entity_records.parquet")
    )
    parser.add_argument(
        "--eligibility",
        type=Path,
        default=Path(
            "data/processed/phase_iii_negative_controls/phase_iii_sam_eligibility.parquet"
        ),
    )
    parser.add_argument(
        "--phase-ii", type=Path, default=Path("data/processed/phase_ii_awards.parquet")
    )
    parser.add_argument(
        "--contracts",
        type=Path,
        default=Path(
            "data/processed/phase_iii_negative_controls/phase_iii_control_contracts.parquet"
        ),
    )
    parser.add_argument(
        "--vendor-filter",
        type=Path,
        default=Path(
            "data/processed/phase_iii_negative_controls/phase_iii_control_vendor_filters.json"
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/processed/phase_iii_negative_controls"),
    )
    args = parser.parse_args()
    print(
        json.dumps(
            run(
                args.sam,
                args.eligibility,
                args.phase_ii,
                args.contracts,
                args.vendor_filter,
                args.output_dir,
            ),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
