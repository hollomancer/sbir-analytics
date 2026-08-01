#!/usr/bin/env python3
"""Generate the initial DoD SBIR concentration analysis and classifier review set."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from sbir_etl.reporting.dod_supply_chain_analysis import (
    build_classifier_validation_sample,
    build_initial_analysis_markdown,
    read_json,
    split_classifier_validation_sample,
    write_initial_analysis,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    baseline = Path("data/processed/dod_supply_chain_baseline")
    parser.add_argument(
        "--facts", type=Path, default=baseline / "dod_supply_chain_award_facts.parquet"
    )
    parser.add_argument(
        "--metrics", type=Path, default=baseline / "dod_supply_chain_cet_metrics.parquet"
    )
    parser.add_argument(
        "--run-metadata", type=Path, default=baseline / "dod_supply_chain_run_metadata.json"
    )
    parser.add_argument(
        "--awards", type=Path, default=Path("data/processed/enriched_sbir_awards.parquet")
    )
    parser.add_argument(
        "--classifications",
        type=Path,
        default=Path("data/processed/cet_award_classifications.parquet"),
    )
    parser.add_argument(
        "--classifier-manifest",
        type=Path,
        default=Path("data/processed/cet_award_classifications.manifest.json"),
    )
    parser.add_argument(
        "--report", type=Path, default=Path("docs/research/dod_supply_chain_initial_analysis.md")
    )
    parser.add_argument(
        "--validation-sample",
        type=Path,
        default=Path("data/reference/cet_classifier_validation_sample_2026q3.csv"),
    )
    parser.add_argument(
        "--validation-key",
        type=Path,
        default=Path("data/reference/cet_classifier_validation_key_2026q3.csv"),
    )
    parser.add_argument("--classified-per-cet", type=int, default=6)
    parser.add_argument("--unclassified-count", type=int, default=100)
    parser.add_argument("--seed", type=int, default=20260723)
    return parser


def main() -> int:
    args = _parser().parse_args()
    facts = pd.read_parquet(args.facts)
    metrics = pd.read_parquet(args.metrics)
    awards = pd.read_parquet(args.awards)
    classifications = pd.read_parquet(args.classifications)
    run_metadata = read_json(args.run_metadata)
    classifier_manifest = read_json(args.classifier_manifest)

    report = build_initial_analysis_markdown(facts, metrics, run_metadata, classifier_manifest)
    validation = build_classifier_validation_sample(
        awards,
        classifications,
        classified_per_cet=args.classified_per_cet,
        unclassified_count=args.unclassified_count,
        seed=args.seed,
    )
    blinded_sample, validation_key = split_classifier_validation_sample(validation)
    write_initial_analysis(
        report,
        blinded_sample,
        validation_key,
        report_path=args.report,
        validation_path=args.validation_sample,
        validation_key_path=args.validation_key,
    )
    print(f"Wrote analysis: {args.report}")
    print(
        f"Wrote {len(validation):,} validation records "
        f"({(validation['classifier_decision'] == 'classified').sum():,} classified, "
        f"{(validation['classifier_decision'] == 'unclassified').sum():,} unclassified): "
        f"{args.validation_sample}; key: {args.validation_key}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
