#!/usr/bin/env python3
"""Recover identifier-poor SBIR rows from the pinned February mirror."""

import argparse
import json
import os
import tempfile
from pathlib import Path

import pandas as pd

from sbir_analytics.assets.phase_iii_negative_controls import (
    FebruaryAwardSearchExtractor,
    build_usaspending_official_keys,
    build_usaspending_sbir_attempts,
    reconcile_award_identity_attempts,
    resolve_award_identities,
)
from sbir_etl.utils.identifiers import normalize_duns, normalize_uei


def _write_parquet(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        temporary_path = Path(handle.name)
    try:
        frame.to_parquet(temporary_path, index=False)
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _identifier_poor_rows(sbir_awards: pd.DataFrame) -> pd.DataFrame:
    required = {
        "source_row_sha256",
        "agency",
        "contract",
        "agency_tracking_number",
        "Award Year",
        "uei",
        "duns",
    }
    if missing := sorted(required - set(sbir_awards.columns)):
        raise ValueError(f"SBIR award artifact is missing columns: {missing}")
    usable_uei = sbir_awards["uei"].map(normalize_uei).notna()
    usable_duns = sbir_awards["duns"].map(normalize_duns).notna()
    result = sbir_awards.loc[~usable_uei & ~usable_duns].copy()
    if result["source_row_sha256"].duplicated().any():
        raise ValueError("Identifier-poor SBIR source-row fingerprints are not unique")
    return result.rename(columns={"Award Year": "award_year"})


def run(input_path: Path, output_dir: Path) -> dict[str, object]:
    sbir_awards = pd.read_parquet(input_path)
    identifier_poor = _identifier_poor_rows(sbir_awards)
    attempts = build_usaspending_sbir_attempts(identifier_poor)

    official_path = output_dir / "phase_iii_identity_usaspending_awards.parquet"
    extractor = FebruaryAwardSearchExtractor(attempts)
    official_count = extractor.extract_to_parquet(official_path)
    official_awards = pd.read_parquet(official_path)
    official_keys = build_usaspending_official_keys(
        official_awards,
        source_digest=str(extractor.provenance["member_sha256"]),
        snapshot_date=str(extractor.provenance["snapshot_date"]),
    )
    attempt_audit = resolve_award_identities(attempts, official_keys)
    recovery_audit = reconcile_award_identity_attempts(attempt_audit)
    source_context = identifier_poor[
        ["source_row_sha256", "agency", "award_year"]
    ].copy()
    recovery_audit = recovery_audit.merge(
        source_context,
        on="source_row_sha256",
        how="left",
        validate="one_to_one",
    )

    _write_parquet(
        attempts,
        output_dir / "phase_iii_identity_usaspending_attempts.parquet",
    )
    _write_parquet(
        attempt_audit,
        output_dir / "phase_iii_identity_usaspending_attempt_audit.parquet",
    )
    _write_parquet(
        recovery_audit,
        output_dir / "phase_iii_identity_usaspending_recovery_audit.parquet",
    )
    coverage = (
        recovery_audit.groupby(["recovery_status", "agency", "award_year"], dropna=False)
        .size()
        .rename("source_rows")
        .reset_index()
    )
    _write_parquet(
        coverage,
        output_dir / "phase_iii_identity_usaspending_coverage.parquet",
    )

    summary: dict[str, object] = {
        "input_path": str(input_path),
        "input_rows": len(sbir_awards),
        "identifier_poor_source_rows": len(identifier_poor),
        "recovery_attempts": len(attempts),
        "official_exact_match_rows": official_count,
        "recovery_status_counts": {
            str(key): int(value)
            for key, value in recovery_audit["recovery_status"].value_counts().items()
        },
        "source_scope": "February 2026 USAspending award_search only; NIH not yet applied",
        "pre_outcome_gate": True,
        "mirror_provenance": extractor.provenance,
    }
    summary_path = output_dir / "phase_iii_identity_usaspending_coverage.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("data/processed/phase_iii_census_sbir_awards.parquet"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/processed/phase_iii_identity"),
    )
    args = parser.parse_args()
    summary = run(args.input, args.output_dir)
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
