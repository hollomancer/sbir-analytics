#!/usr/bin/env python3
"""Build signed DoD prime/subaward funding products for direct NSF awardees."""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from sbir_etl.supply_chain.defense_release import (
    DEFAULT_ARCHIVE_EXTRACT_DIR,
    DEFAULT_LINEAGE_DIR,
    DEFAULT_PRIME_SNAPSHOT_ROOT,
    build_release,
    prepare_defense_funding,
)
from sbir_etl.supply_chain.nsf_screen import screen_direct_nsf_awards


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lineage-dir", type=Path, default=DEFAULT_LINEAGE_DIR)
    parser.add_argument("--analysis-date", type=date.fromisoformat, required=True)
    parser.add_argument("--prime-snapshot", type=Path, action="append")
    parser.add_argument("--prime-api-parquet", type=Path, action="append")
    parser.add_argument("--fetch-prime-api", action="store_true")
    parser.add_argument("--prime-snapshot-root", type=Path, default=DEFAULT_PRIME_SNAPSHOT_ROOT)
    parser.add_argument("--prime-contract-archive", type=Path, action="append")
    parser.add_argument("--prime-archive-parquet", type=Path, action="append")
    parser.add_argument("--archive-extract-dir", type=Path, default=DEFAULT_ARCHIVE_EXTRACT_DIR)
    parser.add_argument("--subaward", type=Path, action="append")
    parser.add_argument("--allow-missing-prime", action="store_true")
    parser.add_argument("--allow-missing-subawards", action="store_true")
    return parser


def main() -> int:
    args = _parser().parse_args()
    workset = prepare_defense_funding(
        lineage_dir=args.lineage_dir,
        analysis_date=args.analysis_date,
        prime_snapshots=args.prime_snapshot,
        prime_api_parquets=args.prime_api_parquet,
        fetch_prime_api=args.fetch_prime_api,
        prime_snapshot_root=args.prime_snapshot_root,
        prime_contract_archives=args.prime_contract_archive,
        prime_archive_parquets=args.prime_archive_parquet,
        archive_extract_dir=args.archive_extract_dir,
        subaward_sources=args.subaward,
        allow_missing_prime=args.allow_missing_prime,
        allow_missing_subawards=args.allow_missing_subawards,
    )
    # Exploratory CLI: run the contestable CET screen, then hand the frame to the
    # pipelines release builder (spec epistemic-tier-enforcement R3).
    award_screen = screen_direct_nsf_awards(
        workset.direct,
        funded_organization_ids=set(workset.funded_organization_ids),
    )
    manifest = build_release(workset, award_screen=award_screen)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["build_release", "main", "prepare_defense_funding"]
