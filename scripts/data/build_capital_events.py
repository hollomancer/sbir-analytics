#!/usr/bin/env python3
"""Build the capital-event timeline parquet artifacts.

Reads per-source data files in $SBIR_DATA_DIR, projects each into the
common CapitalEvent schema, concatenates, sorts, writes:
  - capital_events.parquet          (long-format)
  - capital_events_per_firm.parquet (wide-format summary)
  - capital_events_sample.jsonl     (first 100 events for inspection)

Usage:
    python scripts/data/build_capital_events.py
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from capital_events._common import data_path  # noqa: E402
from capital_events.schema import EVENT_TABLE_COLUMNS  # noqa: E402
from capital_events.sources.form_d import build_form_d_events  # noqa: E402
from capital_events.sources.ma_events import build_ma_events  # noqa: E402
from capital_events.sources.patents import build_patent_events  # noqa: E402
from capital_events.sources.sbir_awards import build_sbir_award_events  # noqa: E402
from capital_events.sources.ucc import build_ucc_events  # noqa: E402
from capital_events.sources.usaspending import build_usaspending_events  # noqa: E402
from capital_events.summarize import summarize_per_firm  # noqa: E402


def _read_cohort(path: Path) -> list[dict]:
    cohort: list[dict] = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if line:
                cohort.append(json.loads(line))
    return cohort


def _to_dataframe(events: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(events, columns=list(EVENT_TABLE_COLUMNS))
    return df.sort_values(
        ["company_name", "event_date", "event_type"], kind="stable"
    ).reset_index(drop=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cohort", type=Path,
                        default=data_path("form_d_high_conf_cohort.jsonl"))
    parser.add_argument("--sbir-awards", type=Path,
                        default=data_path("raw/sbir/award_data.csv"))
    parser.add_argument("--form-d", type=Path,
                        default=data_path("form_d_details.jsonl"))
    parser.add_argument("--ma-events", type=Path,
                        default=data_path("enriched_sbir_ma_events.jsonl"))
    parser.add_argument("--usaspending", type=Path,
                        default=data_path("processed/sbir_phase3/usaspending_phase3_contracts.jsonl"))
    parser.add_argument("--patents-dir", type=Path,
                        default=data_path("transformed/uspto"))
    parser.add_argument("--ucc-matches", type=Path,
                        default=data_path("ucc1_pilot_matches.jsonl"))
    parser.add_argument("--out-events", type=Path,
                        default=data_path("capital_events.parquet"))
    parser.add_argument("--out-summary", type=Path,
                        default=data_path("capital_events_per_firm.parquet"))
    parser.add_argument("--out-sample", type=Path,
                        default=data_path("capital_events_sample.jsonl"))
    args = parser.parse_args()

    if not args.cohort.exists():
        print(f"ERROR: cohort file not found: {args.cohort}", file=sys.stderr)
        return 1

    cohort = _read_cohort(args.cohort)
    print(f"Loaded cohort: {len(cohort)} firms", file=sys.stderr)

    counts: Counter = Counter()
    all_events: list[dict] = []

    for source_name, builder, source_path in [
        ("sbir_award", build_sbir_award_events, args.sbir_awards),
        ("form_d_filing", build_form_d_events, args.form_d),
        ("ma_event", build_ma_events, args.ma_events),
        ("usaspending_contract", build_usaspending_events, args.usaspending),
        ("patent_grant", build_patent_events, args.patents_dir),
        ("ucc_filing", build_ucc_events, args.ucc_matches),
    ]:
        before = len(all_events)
        try:
            for evt in builder(cohort, source_path):
                all_events.append(evt)
            counts[source_name] = len(all_events) - before
            print(f"  {source_name}: {counts[source_name]} events", file=sys.stderr)
        except FileNotFoundError as e:
            print(f"  {source_name}: SKIPPED ({e})", file=sys.stderr)
        except Exception as e:
            print(f"  {source_name}: ERROR ({type(e).__name__}: {e})", file=sys.stderr)

    events_df = _to_dataframe(all_events)
    print(f"Total events: {len(events_df)}", file=sys.stderr)

    args.out_events.parent.mkdir(parents=True, exist_ok=True)
    events_df.to_parquet(args.out_events, index=False)

    summary_df = summarize_per_firm(events_df, cohort)
    summary_df.to_parquet(args.out_summary, index=False)

    with args.out_sample.open("w") as f:
        for row in events_df.head(100).to_dict("records"):
            f.write(json.dumps(row, default=str) + "\n")

    print(f"Wrote {args.out_events}", file=sys.stderr)
    print(f"Wrote {args.out_summary}", file=sys.stderr)
    print(f"Wrote {args.out_sample} (head 100)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
