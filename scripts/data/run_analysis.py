#!/usr/bin/env python3
"""Run a registered analysis profile.

Epistemic tier: exploratory at the composition boundary. Injects the existing
census and cohort engines into the pipelines-tier runner.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from sbir_etl.analysis.contracts import (  # noqa: E402
    AnalysisKind,
    AnalysisSpec,
    AwardCorpus,
    ReportingWindow,
)
from sbir_etl.analysis.registry import load_registry  # noqa: E402
from sbir_etl.analysis.runner import materialize_analysis  # noqa: E402


EPISTEMIC_TIER = "exploratory"
DEFAULT_AWARDS = REPO / "data" / "raw" / "sbir" / "award_data.csv"
SNAPSHOT_ROOT = REPO / "data" / "reports" / "analysis_snapshots"


def _census_strategy(spec: AnalysisSpec) -> dict:
    from sbir_etl.utils.tech_census import (
        CompiledCensus,
        load_award_data_csv,
        load_census_config,
        run_census,
        write_census_artifacts,
    )

    cfg = load_census_config(spec.profile_id)
    compiled = CompiledCensus(cfg)
    awards = load_award_data_csv(spec.corpus.source_path)
    result = run_census(awards, compiled)
    out_dir = REPO / "data" / "tech_census" / spec.profile_id
    # This CLI path does not apply FY/state filters the way build_tech_census.py
    # can, so source and reporting row counts are the same corpus length here.
    write_census_artifacts(
        result,
        out_dir,
        awards_csv=spec.corpus.source_path,
        source_row_count=len(awards),
        reporting_row_count=len(awards),
    )
    grand = result["grand_total"]
    return {
        "output_dir": str(out_dir),
        "grand_total_n": grand["n"],
        "grand_total_usd": grand["usd"],
    }


def _cohort_strategy(spec: AnalysisSpec) -> dict:
    from sbir_etl.reporting.tech_area_cohort import materialize_tech_area_cohort

    report_dir = materialize_tech_area_cohort(
        spec.profile_id,
        awards_csv=spec.corpus.source_path,
    )
    summary_path = report_dir / "overlap_summary.json"
    composition_path = report_dir / "composition.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else {}
    composition = (
        json.loads(composition_path.read_text(encoding="utf-8"))
        if composition_path.exists()
        else {}
    )
    overlap = summary.get("overlap") or {}
    totals = composition.get("totals") or {}
    return {
        "output_dir": str(report_dir),
        "method_a_awards": composition.get("n_unique_awards"),
        "method_b_awards": overlap.get("method_b_n"),
        "intersection": overlap.get("intersection_n"),
        "jaccard": overlap.get("jaccard"),
        "phase2_dollars_m": totals.get("phase2_dollars_m"),
        "unique_firms": totals.get("unique_firms"),
    }


def strategy_for(kind: AnalysisKind):
    if kind is AnalysisKind.TECH_CENSUS:
        return _census_strategy
    if kind is AnalysisKind.TRANSITION_COHORT:
        return _cohort_strategy
    raise ValueError(f"unsupported analysis kind: {kind}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True, help="profile_id from the analysis registry")
    parser.add_argument("--awards", default=str(DEFAULT_AWARDS), help="SBIR award_data.csv")
    parser.add_argument(
        "--allow-methodology-change",
        action="store_true",
        help="Permit a run when methodology_version differs from a frozen snapshot",
    )
    parser.add_argument("--period", default="latest", help="Snapshot period label")
    parser.add_argument(
        "--frozen-snapshot",
        default=None,
        help=(
            "Baseline snapshot to gate this run against; pass 'previous' to use the "
            "existing snapshot for this profile and period. Without it there is no "
            "baseline and no drift check."
        ),
    )
    return parser


def _frozen_snapshot(args: argparse.Namespace, profile_id: str) -> Path | None:
    """Resolve the drift baseline.

    Opt-in rather than always-on: ``compare_snapshots`` also gates on
    ``source_sha256``, so an implicit baseline would refuse every ordinary run
    against refreshed award data, not just a methodology change. When the
    operator does ask for a baseline, missing files fail fast rather than
    silently disabling the gate.
    """

    if not args.frozen_snapshot:
        return None
    if args.frozen_snapshot == "previous":
        path = SNAPSHOT_ROOT / profile_id / f"{args.period}.json"
    else:
        path = Path(args.frozen_snapshot)
    if not path.is_file():
        raise SystemExit(f"frozen snapshot not found: {path}")
    return path


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    entry = load_registry().get(args.profile)
    spec = AnalysisSpec(
        profile_id=entry.profile_id,
        analysis_kind=entry.analysis_kind,
        config_path=entry.config_path,
        taxonomy_version=entry.taxonomy_version,
        methodology_version=entry.methodology_version,
        corpus=AwardCorpus.from_sbir_csv(Path(args.awards)),
        window=ReportingWindow(),
        allow_methodology_change=args.allow_methodology_change,
    )
    run = materialize_analysis(
        spec,
        strategy=strategy_for(entry.analysis_kind),
        snapshot_root=SNAPSHOT_ROOT,
        period=args.period,
        frozen_snapshot=_frozen_snapshot(args, entry.profile_id),
    )
    print(json.dumps(run.to_snapshot_dict(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
