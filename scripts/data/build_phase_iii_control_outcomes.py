#!/usr/bin/env python3
"""Materialize the frozen matched Phase III negative-control outcome tables."""

import argparse
import hashlib
import json
import os
import tempfile
from collections.abc import Mapping
from datetime import date
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from sbir_analytics.assets.phase_iii_candidates.pairing import build_uei_pairs
from sbir_analytics.assets.phase_iii_census.assets import (
    CENSUS_CONTRACT_COLUMNS,
    CENSUS_PAIR_COLUMNS,
    verify_frozen_spec,
)
from sbir_analytics.assets.phase_iii_census.criteria import (
    CensusInputError,
    validate_source_columns,
)
from sbir_analytics.assets.phase_iii_negative_controls import (
    build_control_pseudo_priors,
    build_uei_firm_mapping,
    compare_firm_outcomes,
    evaluate_firm_outcomes,
    require_covariate_balance,
)
from sbir_etl.utils.identifiers import normalize_uei


DATA_CUT_DATE = date(2026, 2, 6)
MATCHING_ARTIFACTS = {
    "treated_covariates": "phase_iii_treated_covariates.parquet",
    "control_covariates": "phase_iii_control_covariates.parquet",
    "coverage": "phase_iii_covariate_coverage.parquet",
    "matches": "phase_iii_control_matches.parquet",
    "matching_summary": "phase_iii_matching_summary.parquet",
    "balance": "phase_iii_balance.parquet",
}
MATCHING_REQUIRED_COLUMNS = {
    "treated_covariates": {"firm_id", "firm_ueis"},
    "control_covariates": {"firm_id", "firm_ueis"},
    "coverage": {
        "arm",
        "covariate",
        "observed_firms",
        "missing_firms",
        "conflict_firms",
        "total_firms",
    },
    "matches": {"treated_firm_id", "control_firm_id", "control_slot"},
    "matching_summary": {"matched_control_count", "treated_firms"},
    "balance": {
        "covariate",
        "level",
        "treated_value",
        "control_value",
        "standardized_mean_difference",
        "absolute_smd",
        "flagged_above_0_1",
    },
}
OUTPUT_NAMES = {
    "firm_counts": "phase_iii_negative_control_firm_counts.parquet",
    "distributions": "phase_iii_negative_control_distributions.parquet",
    "audit_totals": "phase_iii_negative_control_audit_totals.parquet",
    "comparison": "phase_iii_negative_control_comparison.parquet",
}


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path, *, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CensusInputError(f"{label} is missing or unreadable at {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise CensusInputError(f"{label} must be a JSON object")
    return payload


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


def _verified_artifact(path: Path, record: Any, *, label: str) -> dict[str, Any]:
    if not isinstance(record, Mapping):
        raise CensusInputError(f"matching manifest has no {label} artifact record")
    rows = record.get("rows")
    if not isinstance(rows, int) or isinstance(rows, bool) or rows < 0:
        raise CensusInputError(f"matching manifest has an invalid {label} row count")
    try:
        digest = _file_sha256(path)
    except OSError as exc:
        raise CensusInputError(f"matching artifact {label} is unreadable at {path}: {exc}") from exc
    if record.get("sha256") != digest:
        raise CensusInputError(f"{label} SHA-256 differs from the matching manifest")
    return {"path": str(path), "sha256": digest, "rows": rows}


def _parquet_columns(path: Path) -> set[str]:
    connection = duckdb.connect()
    try:
        schema = connection.execute("SELECT name FROM parquet_schema(?)", [str(path)]).df()
    finally:
        connection.close()
    return set(schema["name"])


def _load_matching_inputs(
    matching_dir: Path, matching_manifest_path: Path
) -> tuple[dict[str, pd.DataFrame], dict[str, Any], dict[str, dict[str, Any]]]:
    manifest = _read_json(matching_manifest_path, label="control-matching manifest")
    if (
        manifest.get("schema_version") != "phase-iii-control-matching-v1"
        or manifest.get("balance_passed") is not True
        or manifest.get("pre_outcome_only") is not True
        or manifest.get("census_filter_invoked") is not False
        or manifest.get("stochastic") is not False
    ):
        raise CensusInputError("control-matching manifest does not authorize outcome inputs")
    artifact_records = manifest.get("artifacts")
    if not isinstance(artifact_records, Mapping):
        raise CensusInputError("control-matching manifest has no artifact records")

    provenance: dict[str, dict[str, Any]] = {}
    frames: dict[str, pd.DataFrame] = {}
    for label, filename in MATCHING_ARTIFACTS.items():
        path = matching_dir / filename
        provenance[label] = _verified_artifact(path, artifact_records.get(label), label=label)
        if missing := sorted(MATCHING_REQUIRED_COLUMNS[label] - _parquet_columns(path)):
            raise CensusInputError(f"{label} artifact is missing required columns: {missing}")
        columns = (
            ["firm_id", "firm_ueis"]
            if label in {"treated_covariates", "control_covariates"}
            else None
        )
        frame = pd.read_parquet(path, columns=columns)
        if len(frame) != provenance[label]["rows"]:
            raise CensusInputError(f"{label} row count differs from the matching manifest")
        frames[label] = frame
    require_covariate_balance(frames["balance"])
    return frames, manifest, provenance


def _verify_phase_ii(path: Path, matching_manifest: Mapping[str, Any]) -> dict[str, Any]:
    checks = _read_json(path.with_suffix(".checks.json"), label="Phase II provenance")
    output = checks.get("output")
    if (
        checks.get("ok") is not True
        or checks.get("schema_version") != "phase-ii-awards-v2"
        or not isinstance(output, Mapping)
    ):
        raise CensusInputError("Phase II provenance has an unsupported schema")
    digest = _file_sha256(path)
    matching_phase_ii = matching_manifest.get("inputs", {}).get("phase_ii", {})
    if output.get("sha256") != digest or matching_phase_ii.get("sha256") != digest:
        raise CensusInputError("Phase II parquet differs from frozen matching provenance")
    return {"path": str(path), "sha256": digest, "rows": output.get("rows")}


def _verify_contracts(path: Path, matching_manifest: Mapping[str, Any]) -> dict[str, Any]:
    checks = _read_json(path.with_suffix(".checks.json"), label="contract provenance")
    source = checks.get("source_provenance")
    matching_contracts = matching_manifest.get("inputs", {}).get("contracts", {})
    if checks.get("ok") is not True or not isinstance(source, Mapping):
        raise CensusInputError("contract extraction provenance did not pass")
    digest = _file_sha256(path)
    if source.get("output_sha256") != digest or matching_contracts.get("sha256") != digest:
        raise CensusInputError("contract parquet differs from frozen matching provenance")
    return {
        "path": str(path),
        "sha256": digest,
        "rows": checks.get("total_rows"),
        "source_provenance": dict(source),
    }


def _load_contract_rows(path: Path, exact_ueis: set[str]) -> pd.DataFrame:
    if not exact_ueis:
        raise CensusInputError("matched exact-UEI risk set is empty")
    connection = duckdb.connect()
    try:
        schema = connection.execute("SELECT name FROM parquet_schema(?)", [str(path)]).df()
        if missing := sorted(set(CENSUS_CONTRACT_COLUMNS) - set(schema["name"])):
            raise CensusInputError(f"contract parquet is missing frozen fields: {missing}")
        matched_ueis = pd.DataFrame({"exact_uei": pd.Series(sorted(exact_ueis), dtype="object")})
        connection.register("matched_ueis", matched_ueis)
        projection = ", ".join(f'source."{column}"' for column in CENSUS_CONTRACT_COLUMNS)
        return connection.execute(
            f"""
            SELECT {projection}
            FROM read_parquet(?) AS source
            INNER JOIN matched_ueis
                ON upper(trim(CAST(source.vendor_uei AS VARCHAR))) = matched_ueis.exact_uei
            """,
            [str(path)],
        ).df()
    finally:
        connection.close()


def _mapping_sets(mapping: pd.DataFrame) -> tuple[list[str], set[str]]:
    firms = list(dict.fromkeys(mapping["firm_id"].astype(str)))
    return firms, set(mapping["exact_uei"].astype(str))


def _audit_totals(firm_counts: pd.DataFrame) -> pd.DataFrame:
    return (
        firm_counts.groupby(["arm", "step_order", "clause_id", "clause"], as_index=False)
        .agg(
            surviving_pairs=("surviving_pairs", "sum"),
            distinct_transactions=("distinct_transactions", "sum"),
            firm_contract_instances=("distinct_contracts", "sum"),
            firms=("firm_id", "nunique"),
        )
        .sort_values(["arm", "step_order"], kind="stable")
        .reset_index(drop=True)
    )


def run(
    phase_ii_path: Path,
    contracts_path: Path,
    matching_dir: Path,
    matching_manifest_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Build both arms with one pair boundary and one pure outcome evaluator."""

    freeze = verify_frozen_spec()
    frames, matching_manifest, matching_provenance = _load_matching_inputs(
        matching_dir, matching_manifest_path
    )
    phase_ii_provenance = _verify_phase_ii(phase_ii_path, matching_manifest)
    contract_provenance = _verify_contracts(contracts_path, matching_manifest)

    matches = frames["matches"]
    if matches.empty or not matches["control_firm_id"].is_unique:
        raise CensusInputError("matched frame must contain unique, without-replacement controls")
    treated_ids = list(dict.fromkeys(matches["treated_firm_id"].astype(str)))
    control_ids = list(dict.fromkeys(matches["control_firm_id"].astype(str)))
    treated_mapping = build_uei_firm_mapping(frames["treated_covariates"], treated_ids)
    control_mapping = build_uei_firm_mapping(frames["control_covariates"], control_ids)
    treated_firms, treated_ueis = _mapping_sets(treated_mapping)
    control_firms, control_ueis = _mapping_sets(control_mapping)
    if treated_ueis & control_ueis:
        raise CensusInputError("treated and control exact-UEI risk sets must be disjoint")

    phase_ii = pd.read_parquet(phase_ii_path)
    phase_ii_ueis = phase_ii["recipient_uei"].map(normalize_uei)
    treated_priors = phase_ii.loc[phase_ii_ueis.isin(treated_ueis)].copy()
    missing_treated = sorted(treated_ueis - set(phase_ii_ueis.dropna()))
    if missing_treated:
        raise CensusInputError(f"matched treated firms have no Phase II rows: {missing_treated}")
    control_priors = build_control_pseudo_priors(
        treated_priors, matches, frames["control_covariates"]
    )

    contracts = _load_contract_rows(contracts_path, treated_ueis | control_ueis)
    contract_ueis = contracts["vendor_uei"].map(normalize_uei)
    treated_contracts = contracts.loc[contract_ueis.isin(treated_ueis)].copy()
    control_contracts = contracts.loc[contract_ueis.isin(control_ueis)].copy()
    validate_source_columns(treated_priors, treated_contracts)
    validate_source_columns(control_priors, control_contracts)
    treated_pairs = build_uei_pairs(treated_priors, treated_contracts, columns=CENSUS_PAIR_COLUMNS)
    control_pairs = build_uei_pairs(control_priors, control_contracts, columns=CENSUS_PAIR_COLUMNS)

    treated_outcomes = evaluate_firm_outcomes(
        treated_pairs, treated_mapping, treated_firms, DATA_CUT_DATE
    )
    control_outcomes = evaluate_firm_outcomes(
        control_pairs, control_mapping, control_firms, DATA_CUT_DATE
    )
    comparison = compare_firm_outcomes(treated_outcomes, control_outcomes)
    output_frames = {
        "firm_counts": comparison.firm_counts,
        "distributions": comparison.frequency_distribution,
        "audit_totals": _audit_totals(comparison.firm_counts),
        "comparison": comparison.final_comparison,
    }
    artifacts = {label: output_dir / filename for label, filename in OUTPUT_NAMES.items()}
    for label, path in artifacts.items():
        _write_parquet_atomic(output_frames[label], path)

    manifest = {
        "schema_version": "phase-iii-negative-control-outcomes-v1",
        "data_cut_date": DATA_CUT_DATE.isoformat(),
        "stochastic": False,
        "placebo_invoked": False,
        "scoring_invoked": False,
        "shared_pair_builder": "phase_iii_candidates.pairing.build_uei_pairs",
        "shared_outcome_evaluator": "phase_iii_negative_controls.evaluate_firm_outcomes",
        "firm_outcome": "distinct target_contract_key values with at least one surviving pair",
        "freeze": freeze,
        "inputs": {
            "phase_ii": phase_ii_provenance,
            "contracts": contract_provenance,
            "matching_manifest": {
                "path": str(matching_manifest_path),
                "sha256": _file_sha256(matching_manifest_path),
                "freeze": matching_manifest.get("freeze"),
            },
            "matching_artifacts": matching_provenance,
        },
        "artifacts": {
            label: {
                "path": str(path),
                "sha256": _file_sha256(path),
                "rows": len(output_frames[label]),
            }
            for label, path in artifacts.items()
        },
        "interpretation": (
            "Unweighted empirical comparison of retained SBIR firms and retained matched "
            "control firms; not a matched-set causal estimate and not generalizable to "
            "unmatched Phase II firms."
        ),
    }
    manifest_path = output_dir / "phase_iii_negative_control_outcomes.json"
    _write_json_atomic(manifest, manifest_path)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
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
        "--matching-dir",
        type=Path,
        default=Path("data/processed/phase_iii_negative_controls"),
    )
    parser.add_argument(
        "--matching-manifest",
        type=Path,
        default=Path("data/processed/phase_iii_negative_controls/phase_iii_control_matching.json"),
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
                args.phase_ii,
                args.contracts,
                args.matching_dir,
                args.matching_manifest,
                args.output_dir,
            ),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
