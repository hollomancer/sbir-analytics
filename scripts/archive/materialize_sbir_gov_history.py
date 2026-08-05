#!/usr/bin/env python3
"""Materialize the deterministic full-history SBIR.gov parquet used by Phase II."""

from __future__ import annotations

import argparse
from pathlib import Path

from sbir_analytics.assets.phase_transition.sbir_gov_source import (
    SBIR_GOV_SOURCE_URL,
    materialize_sbir_gov_history,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        required=True,
        help="Local SBIR.gov award_data.csv snapshot.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/processed/phase_iii_census_sbir_awards.parquet"),
        help=("Output parquet (default: data/processed/phase_iii_census_sbir_awards.parquet)."),
    )
    parser.add_argument(
        "--source-url",
        default=SBIR_GOV_SOURCE_URL,
        help="Canonical source URL recorded in provenance.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    manifest = materialize_sbir_gov_history(
        args.input,
        args.output,
        source_url=args.source_url,
    )
    grain = manifest["source_grain"]
    print(f"Wrote {manifest['output']['path']}")
    print(f"Rows retained: {grain['retained_rows']}")
    print(f"Exact duplicate rows collapsed: {grain['exact_duplicate_rows_collapsed']}")
    print(f"Generated canonical IDs: {grain['generated_id_rows']}")
    print(f"SHA-256: {manifest['output']['sha256']}")


if __name__ == "__main__":
    main()
