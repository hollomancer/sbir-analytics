#!/usr/bin/env python3
"""Build direct NSF SBIR/STTR awards, reconciliation, and awardee status products."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from sbir_etl.extractors.nsf_awards import (
    NSF_DIRECT_SCHEMA_VERSION,
    fetch_nsf_award_snapshots,
    load_nsf_awards,
    load_nsf_snapshot_index,
)
from sbir_etl.supply_chain.nsf_direct import (
    load_nsf_sbir_baseline,
    reconcile_nsf_sbir_awards,
    requested_nsf_award_ids,
)

DEFAULT_AWARDS = Path("data/raw/sbir/award_data.csv")
DEFAULT_OUTPUT_DIR = Path("data/processed/nsf_sbir_defense_lineage")
DEFAULT_SNAPSHOT_ROOT = Path("data/raw/nsf/award_api")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_parquet(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    frame.to_parquet(temporary, index=False)
    temporary.replace(path)


def _write_json(payload: object, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def build_release(
    *,
    awards_path: Path,
    output_dir: Path,
    analysis_date: date,
    direct_sources: list[Path] | None = None,
    snapshot_root: Path = DEFAULT_SNAPSHOT_ROOT,
    max_workers: int = 8,
    allow_partial: bool = False,
    limit: int | None = None,
) -> dict[str, Any]:
    """Materialize reproducible Phase 1 products and a release manifest."""

    baseline = load_nsf_sbir_baseline(awards_path)
    award_ids = requested_nsf_award_ids(baseline)
    if limit is not None:
        if limit < 1:
            raise ValueError("limit must be at least one")
        award_ids = award_ids[:limit]
        baseline = baseline.loc[baseline["sbir_gov_nsf_award_id"].isin(award_ids)].copy()
    if not award_ids:
        raise ValueError("SBIR.gov baseline produced no direct NSF IDs")

    sources = list(direct_sources or [])
    snapshot_summary: dict[str, Any] | None = None
    if not sources:
        id_hash = hashlib.sha256("\n".join(award_ids).encode()).hexdigest()[:12]
        snapshot = snapshot_root / f"{analysis_date.isoformat()}-{id_hash}"
        snapshot_manifest = fetch_nsf_award_snapshots(
            award_ids,
            snapshot,
            max_workers=max_workers,
            allow_partial=allow_partial,
        )
        sources = [snapshot]
        snapshot_summary = {
            "path": str(snapshot),
            "manifest_sha256": _sha256(snapshot / "manifest.json")
            if (snapshot / "manifest.json").is_file()
            else None,
            **{
                key: snapshot_manifest.get(key)
                for key in (
                    "requested_award_count",
                    "found_award_count",
                    "not_found_award_count",
                    "failed_award_count",
                    "retrieval_complete",
                    "schema_version",
                )
            },
        }
    direct = load_nsf_awards(sources)
    indexes = [
        load_nsf_snapshot_index(path)
        for path in sources
        if path.is_dir()
        and ((path / "manifest.json").is_file() or (path / "manifest.partial.json").is_file())
    ]
    lookup = pd.concat(indexes, ignore_index=True) if indexes else None
    result = reconcile_nsf_sbir_awards(
        baseline,
        direct,
        analysis_date=analysis_date,
        direct_lookup=lookup,
    )
    if not result.quality["quality_gates_passed"]:
        raise ValueError(f"direct NSF reconciliation quality gates failed: {result.quality}")

    products = {
        "direct_awards": output_dir / "nsf_sbir_awards_direct.parquet",
        "reconciliation": output_dir / "nsf_sbir_award_reconciliation.parquet",
        "awardees": output_dir / "nsf_sbir_awardee_status.parquet",
    }
    frames = {
        "direct_awards": result.direct_awards,
        "reconciliation": result.reconciliation,
        "awardees": result.awardees,
    }
    for name, path in products.items():
        _write_parquet(frames[name], path)

    quality = {
        **result.quality,
        "generated_at": datetime.now(UTC).isoformat(),
        "direct_schema_version": NSF_DIRECT_SCHEMA_VERSION,
        "sbir_gov_source_path": str(awards_path),
        "sbir_gov_source_sha256": _sha256(awards_path),
        "direct_source_paths": [str(path) for path in sources],
        "direct_snapshot": snapshot_summary,
        "limitations": [
            "current/former describes NSF award periods, not business operating status",
            "conflicting Contract and tracking identifiers remain explicit findings",
            "name-only organization identities remain review candidates",
            "firm co-occurrence does not link an NSF award to a DoD requirement",
        ],
    }
    quality_path = output_dir / "nsf_defense_lineage_quality.json"
    _write_json(quality, quality_path)
    product_metadata = {
        name: {"path": str(path), "sha256": _sha256(path), "row_count": len(frames[name])}
        for name, path in products.items()
    }
    release = {
        "release_schema_version": "NSF-DEFENSE-LINEAGE-2026Q3",
        "phase": "direct_nsf_ingestion_and_reconciliation",
        "analysis_date": analysis_date.isoformat(),
        "generated_at": datetime.now(UTC).isoformat(),
        "inputs": {
            "sbir_gov_awards": {"path": str(awards_path), "sha256": _sha256(awards_path)},
            "direct_nsf_sources": [str(path) for path in sources],
            "direct_nsf_snapshot": snapshot_summary,
        },
        "products": product_metadata,
        "quality_report": {
            "path": str(quality_path),
            "sha256": _sha256(quality_path),
            "quality_gates_passed": True,
        },
    }
    _write_json(release, output_dir / "nsf_defense_lineage_manifest.json")
    return release


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--awards", type=Path, default=DEFAULT_AWARDS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--analysis-date", type=date.fromisoformat, required=True)
    parser.add_argument("--direct-source", type=Path, action="append")
    parser.add_argument("--snapshot-root", type=Path, default=DEFAULT_SNAPSHOT_ROOT)
    parser.add_argument("--max-workers", type=int, default=8)
    parser.add_argument("--allow-partial", action="store_true")
    parser.add_argument("--limit", type=int)
    return parser


def main() -> int:
    args = _parser().parse_args()
    manifest = build_release(
        awards_path=args.awards,
        output_dir=args.output_dir,
        analysis_date=args.analysis_date,
        direct_sources=args.direct_source,
        snapshot_root=args.snapshot_root,
        max_workers=args.max_workers,
        allow_partial=args.allow_partial,
        limit=args.limit,
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
