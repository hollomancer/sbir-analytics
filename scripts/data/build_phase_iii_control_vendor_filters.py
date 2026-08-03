#!/usr/bin/env python3
"""Build the exact-UEI February contract-extraction frame for both study arms."""

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

import pandas as pd

from sbir_analytics.assets.phase_iii_negative_controls import (
    EligibilityStatus,
    require_reliable_sam_eligibility,
)
from sbir_etl.utils.identifiers import normalize_uei


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _values(value: Any) -> tuple[Any, ...]:
    if isinstance(value, tuple | list | set):
        return tuple(value)
    tolist = getattr(value, "tolist", None)
    converted = tolist() if callable(tolist) else None
    return tuple(converted) if isinstance(converted, list) else ()


def _phase_two(value: Any) -> bool:
    if value is None or value is pd.NA:
        return False
    return str(value).strip().upper() in {"II", "PHASE II"}


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
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


def run(eligibility_path: Path, sbir_path: Path, output_path: Path) -> dict[str, Any]:
    """Write an exact-UEI-only vendor filter and a provenance sidecar."""

    eligibility = pd.read_parquet(eligibility_path)
    require_reliable_sam_eligibility(eligibility)
    required_eligibility = {"eligibility_status", "candidate_ueis"}
    if missing := sorted(required_eligibility - set(eligibility.columns)):
        raise ValueError(f"eligibility table is missing required columns: {missing}")
    sbir = pd.read_parquet(sbir_path, columns=["phase", "company_uei"])

    eligible = eligibility.loc[
        eligibility["eligibility_status"].eq(EligibilityStatus.ELIGIBLE_SCREENED_NEGATIVE.value)
    ]
    control_ueis = {
        uei
        for values in eligible["candidate_ueis"]
        for value in _values(values)
        if (uei := normalize_uei(value))
    }
    treated_ueis = {
        uei
        for row in sbir.itertuples(index=False)
        if _phase_two(row.phase) and (uei := normalize_uei(row.company_uei))
    }
    all_ueis = sorted(control_ueis | treated_ueis)
    if not control_ueis or not treated_ueis:
        raise ValueError(
            "both the screened-control and Phase II treated UEI frames must be nonempty"
        )

    # The extractor accepts DUNS and name filters for other workflows. They are
    # deliberately empty here: this study's inherited pair boundary is exact UEI.
    _write_json_atomic(
        output_path,
        {"company_names": [], "duns": [], "uei": all_ueis},
    )
    checks = {
        "schema_version": "phase-iii-control-vendor-filter-v1",
        "ok": True,
        "inputs": {
            "eligibility_path": str(eligibility_path),
            "eligibility_sha256": _file_sha256(eligibility_path),
            "sbir_path": str(sbir_path),
            "sbir_sha256": _file_sha256(sbir_path),
        },
        "counts": {
            "eligible_control_envelopes": int(len(eligible)),
            "eligible_control_ueis": len(control_ueis),
            "phase_ii_treated_ueis": len(treated_ueis),
            "combined_unique_ueis": len(all_ueis),
        },
        "output": {
            "path": str(output_path),
            "sha256": _file_sha256(output_path),
            "identifier_methods": ["uei_exact"],
            "duns_filters": 0,
            "company_name_filters": 0,
        },
    }
    _write_json_atomic(output_path.with_suffix(".checks.json"), checks)
    return checks


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--eligibility",
        type=Path,
        default=Path(
            "data/processed/phase_iii_negative_controls/phase_iii_sam_eligibility.parquet"
        ),
    )
    parser.add_argument(
        "--sbir",
        type=Path,
        default=Path("data/processed/phase_iii_census_sbir_awards.parquet"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "data/processed/phase_iii_negative_controls/phase_iii_control_vendor_filters.json"
        ),
    )
    args = parser.parse_args()
    print(json.dumps(run(args.eligibility, args.sbir, args.output), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
