#!/usr/bin/env python3
"""View and export pipeline performance metrics.

Usage:
    python scripts/pipeline_metrics.py                        # Latest metrics summary
    python scripts/pipeline_metrics.py --group enrichment     # Filter by asset group
    python scripts/pipeline_metrics.py --export metrics.json  # Export to JSON
    python scripts/pipeline_metrics.py --export metrics.csv   # Export to CSV
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime

from sbir_etl.config.loader import get_config

from sbir_analytics.clients import MetricsCollector


def main() -> None:
    parser = argparse.ArgumentParser(description="View pipeline performance metrics")
    parser.add_argument("--group", help="Filter by asset group")
    parser.add_argument("--start", help="Start date (ISO format)")
    parser.add_argument("--end", help="End date (ISO format)")
    parser.add_argument("--export", help="Export to file (.json or .csv)")
    args = parser.parse_args()

    config = get_config()
    collector = MetricsCollector(config)

    start_date = datetime.fromisoformat(args.start) if args.start else None
    end_date = datetime.fromisoformat(args.end) if args.end else None

    if args.group:
        metrics = collector.get_metrics(
            start_date=start_date, end_date=end_date, asset_group=args.group
        )
    elif start_date or end_date:
        metrics = collector.get_metrics(start_date=start_date, end_date=end_date)
    else:
        # Show latest summary
        latest = collector.get_latest_metrics()
        if latest:
            print(f"Enrichment success rate: {latest.enrichment_success_rate:.1%}")
            print(f"Processing throughput:   {latest.processing_throughput:.1f} records/sec")
            print(f"Memory usage:            {latest.memory_usage_mb:.1f} MB")
            print(f"Error count:             {latest.error_count}")
            print(f"Last updated:            {latest.last_updated.isoformat()}")
        else:
            print("No metrics available in the last 24 hours.")
        return

    if not metrics:
        print("No metrics found for the given filters.")
        return

    if args.export:
        if args.export.endswith(".csv"):
            if metrics:
                with open(args.export, "w", newline="", encoding="utf-8") as f:
                    writer = csv.DictWriter(f, fieldnames=metrics[0].keys())
                    writer.writeheader()
                    writer.writerows(metrics)
                print(f"Exported {len(metrics)} records to {args.export}")
        else:
            with open(args.export, "w", encoding="utf-8") as f:
                json.dump(metrics, f, indent=2, default=str)
            print(f"Exported {len(metrics)} records to {args.export}")
    else:
        print(json.dumps(metrics, indent=2, default=str))


if __name__ == "__main__":
    main()
