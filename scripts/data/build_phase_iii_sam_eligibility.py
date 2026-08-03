#!/usr/bin/env python3
"""Materialize exact SAM identity envelopes and three-way SBIR eligibility."""

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path

import pandas as pd

from sbir_analytics.assets.phase_iii_negative_controls import (
    build_sam_eligibility_table,
    require_reliable_sam_eligibility,
    sam_eligibility_gate,
    summarize_sam_eligibility,
    summarize_sam_exclusion_reasons,
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


def run(
    sam_path: Path,
    sbir_path: Path,
    recovery_path: Path,
    quarantine_path: Path,
    output_dir: Path,
    *,
    identity_links_path: Path | None = None,
) -> dict[str, object]:
    """Build artifacts before enforcing the pre-matching reliability gate."""

    input_paths = {
        "sam_entities": sam_path,
        "sbir_awards": sbir_path,
        "recovery_audit": recovery_path,
        "quarantine_audit": quarantine_path,
    }
    if identity_links_path is not None:
        input_paths["identity_links"] = identity_links_path
    inputs = {label: pd.read_parquet(path) for label, path in input_paths.items()}

    eligibility = build_sam_eligibility_table(
        inputs["sam_entities"],
        inputs["sbir_awards"],
        inputs["recovery_audit"],
        inputs["quarantine_audit"],
        identity_links=inputs.get("identity_links"),
    )
    statuses = summarize_sam_eligibility(eligibility)
    reasons = summarize_sam_exclusion_reasons(eligibility)
    gate = sam_eligibility_gate(eligibility)

    artifact_paths = {
        "eligibility": output_dir / "phase_iii_sam_eligibility.parquet",
        "statuses": output_dir / "phase_iii_sam_eligibility_statuses.parquet",
        "exclusion_reasons": output_dir / "phase_iii_sam_exclusion_reasons.parquet",
    }
    _write_parquet(eligibility, artifact_paths["eligibility"])
    _write_parquet(statuses, artifact_paths["statuses"])
    _write_parquet(reasons, artifact_paths["exclusion_reasons"])

    summary: dict[str, object] = {
        "inputs": {
            label: {
                "path": str(path),
                "sha256": _file_sha256(path),
                "rows": len(inputs[label]),
            }
            for label, path in input_paths.items()
        },
        "artifacts": {
            label: {
                "path": str(path),
                "sha256": _file_sha256(path),
            }
            for label, path in artifact_paths.items()
        },
        "eligibility_status_counts": {
            str(row.eligibility_status): int(row.candidate_firms)
            for row in statuses.itertuples(index=False)
        },
        "exclusion_reason_counts": {
            str(row.exclusion_reason): int(row.candidate_firms)
            for row in reasons.itertuples(index=False)
        },
        "gate": gate,
        "pre_matching_gate": True,
    }
    summary_path = output_dir / "phase_iii_sam_eligibility.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    require_reliable_sam_eligibility(eligibility)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sam",
        type=Path,
        default=Path("data/raw/sam_gov/sam_entity_records.parquet"),
    )
    parser.add_argument(
        "--sbir",
        type=Path,
        default=Path("data/processed/phase_iii_census_sbir_awards.parquet"),
    )
    parser.add_argument(
        "--recovery-audit",
        type=Path,
        default=Path("data/processed/phase_iii_identity/phase_iii_identity_recovery_audit.parquet"),
    )
    parser.add_argument(
        "--quarantine-audit",
        type=Path,
        default=Path(
            "data/processed/phase_iii_identity/phase_iii_identity_quarantine_key_audit.parquet"
        ),
    )
    parser.add_argument("--identity-links", type=Path)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/processed/phase_iii_negative_controls"),
    )
    args = parser.parse_args()
    summary = run(
        args.sam,
        args.sbir,
        args.recovery_audit,
        args.quarantine_audit,
        args.output_dir,
        identity_links_path=args.identity_links,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
