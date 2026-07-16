#!/usr/bin/env python3
"""Download and normalize public SAM.gov opportunities for the monthly report."""

import argparse
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pandas as pd

from sbir_etl.extractors.sam_gov_opportunities import SamGovOpportunitiesExtractor


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", type=date.fromisoformat, default=datetime.now(UTC).date())
    parser.add_argument("--lookback-days", type=int, default=365)
    parser.add_argument("--output", type=Path, default=Path("data/raw/sam_gov_opportunities/opportunities.parquet"))
    parser.add_argument("--raw-output", type=Path, default=Path("data/raw/sam_gov_opportunities/raw.ndjson"))
    parser.add_argument("--page-size", type=int, default=1000)
    parser.add_argument("--max-pages", type=int, default=100)
    parser.add_argument("--without-descriptions", action="store_true")
    args = parser.parse_args()

    posted_from = args.as_of - timedelta(days=args.lookback_days)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.raw_output.parent.mkdir(parents=True, exist_ok=True)
    raw_rows: list[dict] = []
    normalized = []
    with SamGovOpportunitiesExtractor(page_size=args.page_size, max_pages=args.max_pages) as extractor:
        for raw in extractor.iter_raw_records(posted_from=posted_from, posted_to=args.as_of):
            raw_rows.append(raw)
            normalized.append(
                extractor.normalize_record(raw, fetch_description=not args.without_descriptions)
            )
    pd.DataFrame([row.model_dump(mode="json") for row in normalized]).to_parquet(
        args.output, index=False
    )
    with args.raw_output.open("w", encoding="utf-8") as handle:
        for row in raw_rows:
            handle.write(json.dumps(row, default=str) + "\n")
    print(f"Wrote {len(normalized)} opportunities to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
