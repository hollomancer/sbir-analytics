#!/usr/bin/env python3
"""Score directed and competitive opportunity candidates for all SBIR phases."""

import argparse
import json
from pathlib import Path

import pandas as pd

from sbir_analytics.assets.phase_iii_candidates.assets import (
    HIGH_THRESHOLD_DIRECTED,
    HIGH_THRESHOLD_FOLLOWON,
    WEIGHTS_DIRECTED,
    WEIGHTS_FOLLOWON,
    score_candidate_pairs,
)
from sbir_analytics.assets.phase_iii_candidates.pairing import pair_filter_s2, pair_filter_s3
from sbir_etl.models.phase_iii_candidate import SignalClass
from sbir_etl.reporting.procurement_transition import build_award_cohorts, normalize_awards


def _read(path: Path) -> pd.DataFrame:
    return pd.read_parquet(path) if path.suffix == ".parquet" else pd.read_csv(path)


def _priors(raw: pd.DataFrame) -> pd.DataFrame:
    awards = normalize_awards(raw)
    return awards.rename(
        columns={
            "uei": "recipient_uei",
            "branch": "sub_agency",
            "recorded_end_date": "period_of_performance_end",
        }
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--awards", type=Path, required=True)
    parser.add_argument("--previous-awards", type=Path)
    parser.add_argument("--month", required=True)
    parser.add_argument("--opportunities", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("data/processed/phase_iii_candidates.parquet"))
    parser.add_argument("--evidence", type=Path, default=Path("data/processed/phase_iii_evidence.ndjson"))
    args = parser.parse_args()

    current = _read(args.awards)
    previous = _read(args.previous_awards) if args.previous_awards else pd.DataFrame()
    priors = _priors(build_award_cohorts(current, previous, report_month=args.month))
    opportunities = _read(args.opportunities)
    directed, directed_evidence = score_candidate_pairs(
        pair_filter_s2(priors, opportunities),
        signal_class=SignalClass.DIRECTED,
        weights=WEIGHTS_DIRECTED,
        high_threshold=HIGH_THRESHOLD_DIRECTED,
    )
    followon, followon_evidence = score_candidate_pairs(
        pair_filter_s3(priors, opportunities),
        signal_class=SignalClass.FOLLOWON,
        weights=WEIGHTS_FOLLOWON,
        high_threshold=HIGH_THRESHOLD_FOLLOWON,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.evidence.parent.mkdir(parents=True, exist_ok=True)
    pd.concat([directed, followon], ignore_index=True).to_parquet(args.output, index=False)
    with args.evidence.open("w", encoding="utf-8") as handle:
        for row in [*directed_evidence, *followon_evidence]:
            handle.write(json.dumps(row, default=str) + "\n")
    print(f"Wrote {len(directed)} directed and {len(followon)} follow-on candidates")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
