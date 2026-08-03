#!/usr/bin/env python3
"""Materialize the pre-outcome unresolved-award quarantine-key audit."""

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path

import pandas as pd

from sbir_analytics.assets.phase_iii_negative_controls import (
    build_unresolved_quarantine_key_audit,
    quarantine_key_gate,
    require_complete_unresolved_quarantine_keys,
    summarize_quarantine_key_coverage,
)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def run(input_path: Path, recovery_path: Path, output_dir: Path) -> dict[str, object]:
    sbir_awards = pd.read_parquet(input_path)
    recovery_audit = pd.read_parquet(recovery_path)
    audit = build_unresolved_quarantine_key_audit(sbir_awards, recovery_audit)
    coverage = summarize_quarantine_key_coverage(audit)
    gate = quarantine_key_gate(audit)

    audit_path = output_dir / "phase_iii_identity_quarantine_key_audit.parquet"
    coverage_path = output_dir / "phase_iii_identity_quarantine_key_coverage.parquet"
    _write_parquet(audit, audit_path)
    _write_parquet(coverage, coverage_path)

    summary: dict[str, object] = {
        "input_path": str(input_path),
        "input_sha256": _file_sha256(input_path),
        "recovery_path": str(recovery_path),
        "recovery_sha256": _file_sha256(recovery_path),
        "audit_path": str(audit_path),
        "audit_sha256": _file_sha256(audit_path),
        "coverage_path": str(coverage_path),
        "coverage_sha256": _file_sha256(coverage_path),
        "coverage_category_counts": {
            str(row.coverage_category): int(row.source_rows)
            for row in coverage.itertuples(index=False)
        },
        "gate": gate,
        "pre_outcome_gate": True,
        "control_candidate_rows_read": 0,
    }
    summary_path = output_dir / "phase_iii_identity_quarantine_key_coverage.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    require_complete_unresolved_quarantine_keys(audit)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("data/processed/phase_iii_census_sbir_awards.parquet"),
    )
    parser.add_argument(
        "--recovery-audit",
        type=Path,
        default=Path("data/processed/phase_iii_identity/phase_iii_identity_recovery_audit.parquet"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/processed/phase_iii_identity"),
    )
    args = parser.parse_args()
    summary = run(args.input, args.recovery_audit, args.output_dir)
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
