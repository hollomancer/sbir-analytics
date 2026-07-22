#!/usr/bin/env python3
"""Build the DoD SBIR industrial-base concentration baseline."""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

import pandas as pd

from sbir_etl.reporting.dod_supply_chain_baseline import build_baseline, write_baseline_outputs


def _read_frame(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"required input does not exist: {path}")
    suffix = path.suffix.lower()
    if suffix in {".parquet", ".pq"}:
        return pd.read_parquet(path)
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix in {".json", ".jsonl", ".ndjson"}:
        try:
            return pd.read_json(path, orient="records")
        except ValueError:
            return pd.read_json(path, lines=True)
    raise ValueError(f"unsupported input format: {path}")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Measure observable concentration in the DoD SBIR/STTR awardee base. "
            "This is not a physical or sub-tier supply-chain map."
        )
    )
    parser.add_argument(
        "--awards",
        type=Path,
        default=Path("data/processed/enriched_sbir_awards.parquet"),
    )
    parser.add_argument(
        "--classifications",
        type=Path,
        default=Path("data/processed/cet_award_classifications.parquet"),
    )
    parser.add_argument(
        "--survival",
        type=Path,
        default=None,
        help="Optional phase_transition_survival artifact; omitted means not computed.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/processed/dod_supply_chain_baseline"),
    )
    parser.add_argument("--as-of", type=date.fromisoformat, default=date.today())
    parser.add_argument("--min-fiscal-year", type=int, default=2012)
    parser.add_argument("--min-cet-score", type=float, default=40.0)
    parser.add_argument("--window-years", type=int, default=5)
    return parser


def main() -> int:
    args = _parser().parse_args()
    awards = _read_frame(args.awards)
    classifications = _read_frame(args.classifications)
    survival = _read_frame(args.survival) if args.survival else None
    result = build_baseline(
        awards,
        classifications,
        survival=survival,
        as_of=args.as_of,
        min_fiscal_year=args.min_fiscal_year,
        min_cet_score=args.min_cet_score,
        window_years=args.window_years,
    )
    paths = write_baseline_outputs(result, args.output_dir)
    print(f"Wrote {len(result.award_facts):,} award facts and {len(result.cet_metrics):,} metrics")
    for label, path in sorted(paths.items()):
        print(f"{label}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
