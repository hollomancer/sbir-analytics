#!/usr/bin/env python3
"""Enrich the monthly SBIR outreach cohort with public USAspending history."""

import argparse
import json
from pathlib import Path

import pandas as pd

from sbir_etl.enrichers.company_enrichment import lookup_company_federal_awards
from sbir_etl.reporting.procurement_transition import build_award_cohorts


def _read(path: Path | None, *, required: bool = False) -> pd.DataFrame:
    """Load a tabular input; required inputs fail closed rather than yielding no rows."""

    if path is None or not path.exists():
        if required:
            raise FileNotFoundError(f"required input not found: {path}")
        return pd.DataFrame()
    return pd.read_parquet(path) if path.suffix == ".parquet" else pd.read_csv(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--month", required=True)
    parser.add_argument("--awards", type=Path, required=True)
    parser.add_argument("--previous-awards", type=Path)
    parser.add_argument(
        "--output", type=Path, default=Path("data/processed/procurement_award_cohort.parquet")
    )
    parser.add_argument("--max-companies", type=int, default=100)
    args = parser.parse_args()

    cohort = build_award_cohorts(
        _read(args.awards, required=True), _read(args.previous_awards), report_month=args.month
    )
    prioritized = cohort.assign(
        _phase_ii=cohort["phase"].fillna("").str.upper().str.contains("II").astype(int),
        _ending=(cohort["recent_recorded_end"] | cohort["approaching_recorded_end"]).astype(int),
    ).sort_values(["_ending", "_phase_ii", "newly_observed"], ascending=False)
    companies = prioritized[["company", "uei"]].drop_duplicates().head(args.max_companies)
    summaries = {}
    for _, row in companies.iterrows():
        company = str(row.get("company") or "").strip()
        if not company:
            continue
        summaries[company] = lookup_company_federal_awards(
            company, str(row.get("uei") or "").strip() or None
        )
    enriched_naics = {
        company: summary.naics_codes[0]
        for company, summary in summaries.items()
        if summary and summary.naics_codes
    }
    companies_by_row = cohort["company"].astype(str)
    # Vectorized map + combine_first: the enriched NAICS wins where we looked the
    # company up, the cohort's own code stays everywhere else.
    cohort["naics_code"] = companies_by_row.map(enriched_naics).combine_first(cohort["naics_code"])
    cohort["federal_award_count"] = (
        companies_by_row.map(
            {company: summary.total_awards for company, summary in summaries.items() if summary}
        )
        .fillna(0)
        .astype(int)
    )
    cohort["possible_followon_count"] = (
        companies_by_row.map(
            {
                company: summary.non_sbir_award_count
                for company, summary in summaries.items()
                if summary
            }
        )
        .fillna(0)
        .astype(int)
    )
    cohort["usaspending_enriched"] = companies_by_row.isin(
        {company for company, summary in summaries.items() if summary}
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    cohort.to_parquet(args.output, index=False)
    coverage = {
        "cohort_companies": int(cohort["company"].nunique()),
        "attempted_companies": len(companies),
        "matched_companies": sum(value is not None for value in summaries.values()),
        "max_companies": args.max_companies,
    }
    args.output.with_suffix(".coverage.json").write_text(json.dumps(coverage, indent=2))
    print(f"Wrote {len(cohort)} publicly enriched awards to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
