#!/usr/bin/env python3
"""Generate monthly procurement-center packets from normalized public data."""

import argparse
import os
from pathlib import Path

import pandas as pd

from sbir_etl.reporting.procurement_transition import MonthlyReportBuilder, build_award_cohorts
from sbir_etl.reporting.procurement_transition.ai import build_public_evidence_summarizer


def _read(path: Path | None) -> pd.DataFrame:
    if path is None or not path.exists():
        return pd.DataFrame()
    return pd.read_parquet(path) if path.suffix == ".parquet" else pd.read_csv(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--month", required=True, help="Calendar month in YYYY-MM format")
    parser.add_argument("--awards", type=Path, required=True, help="Current SBIR.gov CSV/parquet")
    parser.add_argument("--previous-awards", type=Path)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--opportunities", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=Path("reports/procurement_transition"))
    parser.add_argument("--ai", action="store_true", help="Add cited summaries from supplied public evidence")
    args = parser.parse_args()

    cohorts = build_award_cohorts(
        _read(args.awards), _read(args.previous_awards), report_month=args.month
    )
    api_key = os.getenv("OPENAI_API_KEY", "")
    summarizer = build_public_evidence_summarizer(api_key) if args.ai and api_key else None
    output = MonthlyReportBuilder(
        report_month=args.month, output_root=args.output_root, summarizer=summarizer
    ).write(
        award_cohorts=cohorts,
        candidates=_read(args.candidates),
        opportunities=_read(args.opportunities),
        source_manifest={
            "awards": str(args.awards),
            "previous_awards": str(args.previous_awards) if args.previous_awards else None,
            "candidates": str(args.candidates),
            "opportunities": str(args.opportunities),
        },
    )
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
