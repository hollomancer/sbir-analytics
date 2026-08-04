#!/usr/bin/env python3
"""Build direct NSF SBIR/STTR awards, reconciliation, and awardee status products."""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from sbir_etl.supply_chain.nsf_release import (
    DEFAULT_AWARDS,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_SNAPSHOT_ROOT,
    build_release,
)


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


__all__ = ["build_release", "main"]
