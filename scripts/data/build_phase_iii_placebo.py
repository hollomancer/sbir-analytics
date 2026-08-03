#!/usr/bin/env python3
"""Materialize frozen Phase III actual/placebo audit tables after owner approval.

R15 permits implementation and fixture tests only. The first production invocation of
this script remains process-gated on a separate repository-owner approval; this script
must not be treated as that approval.
"""

import argparse
import hashlib
import json
import os
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pandas as pd

from sbir_analytics.assets.phase_iii_candidates.pairing import build_uei_pairs
from sbir_analytics.assets.phase_iii_census.assets import (
    CENSUS_CONTRACT_COLUMNS,
    CENSUS_PAIR_COLUMNS,
    DROP_OFF_OUTPUT_PATH,
    PHASE_II_AWARDS_PATH,
    PHASE_II_OUTPUT_ENV,
    SENSITIVITY_OUTPUT_PATH,
    _load_contracts,
    _verify_phase_ii_provenance,
    parse_census_data_cut_date,
    verify_frozen_spec,
)
from sbir_analytics.assets.phase_iii_census.criteria import (
    CensusInputError,
    build_census_tables,
    validate_source_columns,
)
from sbir_analytics.assets.phase_iii_negative_controls.placebo import (
    PLACEBO_SEED,
    build_placebo_study_tables,
)


OUTPUT_NAMES = {
    "assignment_audit": "phase_iii_placebo_assignment.parquet",
    "actual_dropoff": "phase_iii_placebo_actual_dropoff.parquet",
    "placebo_dropoff": "phase_iii_placebo_dropoff.parquet",
    "dropoff_comparison": "phase_iii_placebo_dropoff_comparison.parquet",
    "actual_sensitivity": "phase_iii_placebo_actual_sensitivity.parquet",
    "placebo_sensitivity": "phase_iii_placebo_sensitivity.parquet",
    "sensitivity_comparison": "phase_iii_placebo_sensitivity_comparison.parquet",
}
METRIC_COLUMNS = (
    "surviving_pairs",
    "distinct_firms",
    "distinct_contracts",
    "total_obligated_dollars",
)


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


def _require_columns(frame: pd.DataFrame, required: Sequence[str], *, label: str) -> None:
    missing = sorted(set(required) - set(frame.columns))
    if missing:
        raise CensusInputError(f"{label} is missing required columns: {missing}")


def _compare_tables(
    actual: pd.DataFrame,
    placebo: pd.DataFrame,
    *,
    keys: Sequence[str],
    labels: Sequence[str],
) -> pd.DataFrame:
    """Join like-for-like rows and emit every frozen actual/placebo comparison."""

    required = [*keys, *labels, *METRIC_COLUMNS]
    _require_columns(actual, required, label="actual census table")
    _require_columns(placebo, required, label="placebo census table")
    if actual.duplicated(list(keys)).any() or placebo.duplicated(list(keys)).any():
        raise CensusInputError("actual/placebo comparison keys must be unique")

    merged = actual.merge(
        placebo,
        on=list(keys),
        how="outer",
        suffixes=("_actual", "_placebo"),
        validate="one_to_one",
        indicator=True,
        sort=False,
    )
    if not merged["_merge"].eq("both").all():
        raise CensusInputError("actual and placebo tables do not contain the same stages or cells")
    merged = merged.drop(columns="_merge")
    for label in labels:
        actual_label = f"{label}_actual"
        placebo_label = f"{label}_placebo"
        if not merged[actual_label].equals(merged[placebo_label]):
            raise CensusInputError(f"actual/placebo comparison disagrees on {label}")
        merged[label] = merged.pop(actual_label)
        merged = merged.drop(columns=placebo_label)

    for metric in METRIC_COLUMNS:
        actual_column = f"{metric}_actual"
        placebo_column = f"{metric}_placebo"
        delta_column = f"{metric}_actual_minus_placebo"
        ratio_column = f"{metric}_actual_to_placebo_ratio"
        status_column = f"{ratio_column}_status"
        merged[delta_column] = merged[actual_column] - merged[placebo_column]
        zero_denominator = merged[placebo_column].eq(0)
        ratio = merged[actual_column].astype(float).div(merged[placebo_column].astype(float))
        merged[ratio_column] = ratio.mask(zero_denominator, pd.NA).astype("Float64")
        merged[status_column] = zero_denominator.map(
            {True: "undefined_zero_placebo_denominator", False: "defined"}
        )

    ordered = [*keys, *labels]
    for metric in METRIC_COLUMNS:
        ordered.extend(
            [
                f"{metric}_actual",
                f"{metric}_placebo",
                f"{metric}_actual_minus_placebo",
                f"{metric}_actual_to_placebo_ratio",
                f"{metric}_actual_to_placebo_ratio_status",
            ]
        )
    return merged[ordered]


def _verify_phase_i_tables(
    actual_dropoff: pd.DataFrame,
    actual_sensitivity: pd.DataFrame,
) -> dict[str, dict[str, Any]]:
    """Require recomputation to equal the already-persisted complete Phase I tables."""

    records: dict[str, dict[str, Any]] = {}
    for label, path, recomputed in (
        ("dropoff", DROP_OFF_OUTPUT_PATH, actual_dropoff),
        ("sensitivity", SENSITIVITY_OUTPUT_PATH, actual_sensitivity),
    ):
        try:
            persisted = pd.read_parquet(path)
            pd.testing.assert_frame_equal(
                persisted.reset_index(drop=True),
                recomputed.reset_index(drop=True),
                check_dtype=False,
                check_exact=True,
            )
        except (OSError, AssertionError) as exc:
            raise CensusInputError(
                f"recomputed actual {label} does not equal the persisted Phase I artifact"
            ) from exc
        records[label] = {
            "path": str(path),
            "sha256": _file_sha256(path),
            "rows": len(persisted),
        }
    return records


def _build_output_frames(
    pairs: pd.DataFrame,
    data_cut_date,
) -> tuple[dict[str, pd.DataFrame], str]:
    """Run exactly one shared census pass for the actual and placebo pair frames."""

    actual_dropoff, actual_sensitivity = build_census_tables(pairs, data_cut_date)
    placebo = build_placebo_study_tables(pairs, data_cut_date)
    frames = {
        "assignment_audit": placebo.assignment.audit,
        "actual_dropoff": actual_dropoff,
        "placebo_dropoff": placebo.dropoff,
        "dropoff_comparison": _compare_tables(
            actual_dropoff,
            placebo.dropoff,
            keys=("step_order", "clause_id"),
            labels=("clause",),
        ),
        "actual_sensitivity": actual_sensitivity,
        "placebo_sensitivity": placebo.sensitivity,
        "sensitivity_comparison": _compare_tables(
            actual_sensitivity,
            placebo.sensitivity,
            keys=("cell_id",),
            labels=("time_window", "agency_match"),
        ),
    }
    return frames, placebo.assignment.mapping_sha256


def run(output_dir: Path, *, owner_approved: bool = False) -> dict[str, Any]:
    """Build the R15 artifacts from the exact verified Phase I source universe.

    Calling this function for production is the first placebo run and requires the
    separate repository-owner approval recorded by the R15 process gate.
    """

    if not owner_approved:
        raise CensusInputError(
            "Phase 3 production materialization remains blocked: pass owner_approved=True "
            "only after the repository owner separately approves the first placebo run"
        )

    freeze = verify_frozen_spec()
    phase_ii_path = Path(os.getenv(PHASE_II_OUTPUT_ENV) or PHASE_II_AWARDS_PATH)
    try:
        priors = pd.read_parquet(phase_ii_path)
    except OSError as exc:
        raise CensusInputError(f"Phase II prior frame is unreadable at {phase_ii_path}") from exc
    contracts, contracts_path = _load_contracts()
    sbir_awards_path, verified_phase_ii_path = _verify_phase_ii_provenance(priors, contracts_path)
    if verified_phase_ii_path.resolve() != phase_ii_path.resolve():
        raise CensusInputError("loaded Phase II path differs from verified Phase I provenance")

    data_cut = parse_census_data_cut_date()
    validate_source_columns(priors, contracts)
    pairs = build_uei_pairs(priors, contracts, columns=CENSUS_PAIR_COLUMNS)
    output_frames, mapping_sha256 = _build_output_frames(pairs, data_cut)
    phase_i_artifacts = _verify_phase_i_tables(
        output_frames["actual_dropoff"], output_frames["actual_sensitivity"]
    )

    artifact_paths = {label: output_dir / filename for label, filename in OUTPUT_NAMES.items()}
    for label, path in artifact_paths.items():
        _write_parquet_atomic(output_frames[label], path)

    manifest = {
        "schema_version": "phase-iii-full-census-placebo-v1",
        "data_cut_date": data_cut.isoformat(),
        "stochastic": True,
        "seed": PLACEBO_SEED,
        "assignment_method": "randomized_cyclic_group_derangement_not_uniform",
        "assignment_mapping_sha256": mapping_sha256,
        "scoring_invoked": False,
        "headline_cell_selected": False,
        "similarity_threshold_applied": False,
        "first_production_run_requires_separate_owner_approval": True,
        "owner_approval_asserted_at_invocation": True,
        "shared_pair_builder": "phase_iii_candidates.pairing.build_uei_pairs",
        "shared_table_builder": "phase_iii_census.criteria.build_census_tables",
        "freeze": freeze,
        "inputs": {
            "sbir_awards": {
                "path": str(sbir_awards_path),
                "sha256": _file_sha256(sbir_awards_path),
            },
            "phase_ii": {
                "path": str(phase_ii_path),
                "sha256": _file_sha256(phase_ii_path),
                "rows": len(priors),
            },
            "contracts": {
                "path": str(contracts_path),
                "sha256": _file_sha256(contracts_path),
                "rows": len(contracts),
                "projected_columns": list(CENSUS_CONTRACT_COLUMNS),
            },
            "persisted_phase_i_tables": phase_i_artifacts,
        },
        "artifacts": {
            label: {
                "path": str(path),
                "sha256": _file_sha256(path),
                "rows": len(output_frames[label]),
            }
            for label, path in artifact_paths.items()
        },
        "comparison_contract": {
            "difference": "actual_minus_placebo",
            "ratio": "actual_to_placebo_ratio",
            "zero_placebo_denominator": "undefined",
            "signed_dollar_ratios": "descriptive_only",
            "pass_fail_rule": None,
        },
    }
    manifest_path = output_dir / "phase_iii_placebo_manifest.json"
    _write_json_atomic(manifest, manifest_path)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog="Do not invoke for production until the repository owner approves the first run.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/processed/phase_iii_placebo"),
    )
    parser.add_argument(
        "--owner-approved",
        action="store_true",
        help="Assert that the repository owner separately approved the first production run.",
    )
    args = parser.parse_args()
    print(
        json.dumps(
            run(args.output_dir, owner_approved=args.owner_approved),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
