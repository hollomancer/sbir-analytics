#!/usr/bin/env python3
"""Fetch SBIR contracts from USAspending with NAICS/PSC inline.

Uses `spending_by_award` with cursor pagination so we never hit the 10K
search-window cap. Polite throttling: 1s base sleep + exponential backoff
on 429/5xx.

Pulls two slices per fiscal year:
  - description="SBIR"            (broad; includes false positives like
                                    "SBIRS" satellite contracts — filter
                                    downstream by joining SBIR.gov PIIDs)
  - description="SBIR Phase III"  (Phase III floor count)

Writes one JSONL per query to `data/processed/sbir_phase3/`.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import httpx

API = "https://api.usaspending.gov/api/v2/search/spending_by_award/"
HEADERS = {"User-Agent": "SBIR-Analytics/0.1.0"}
CONTRACT_TYPES = ["A", "B", "C", "D"]

FIELDS = [
    "Award ID",
    "Recipient Name",
    "Recipient UEI",
    "Award Amount",
    "Total Outlays",
    "Description",
    "Contract Award Type",
    "Start Date",
    "End Date",
    "Awarding Agency",
    "Awarding Sub Agency",
    "Funding Agency",
    "Funding Sub Agency",
    "NAICS",
    "PSC",
    "recipient_id",
    "generated_internal_id",
]


def fy_window(fy: int) -> dict:
    return {"start_date": f"{fy - 1}-10-01", "end_date": f"{fy}-09-30"}


def paginate(description: str, fy: int, out_path: Path, max_pages: int = 500) -> int:
    """Cursor-paginate spending_by_award; write JSONL; return record count."""
    body = {
        "filters": {
            "time_period": [fy_window(fy)],
            "award_type_codes": CONTRACT_TYPES,
            "description": description,
        },
        "fields": FIELDS,
        "page": 1,
        "limit": 100,
        "sort": "Award Amount",
        "order": "desc",
        "subawards": False,
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    with httpx.Client(timeout=60, headers=HEADERS) as client, out_path.open("w") as f:
        last_id = None
        last_sort = None
        for page in range(1, max_pages + 1):
            if last_id is not None:
                body["last_record_unique_id"] = last_id
                body["last_record_sort_value"] = last_sort

            for attempt in range(5):
                resp = client.post(API, json=body)
                if resp.status_code == 200:
                    break
                if resp.status_code in (429, 500, 502, 503, 504):
                    sleep = 2 ** attempt
                    print(f"  page {page}: {resp.status_code}, backoff {sleep}s", flush=True)
                    time.sleep(sleep)
                    continue
                resp.raise_for_status()
            else:
                raise RuntimeError(f"page {page}: gave up after retries")

            data = resp.json()
            results = data.get("results", [])
            for row in results:
                f.write(json.dumps(row) + "\n")
            total += len(results)

            meta = data.get("page_metadata", {})
            has_next = meta.get("hasNext", False)
            print(
                f"  page {page}: +{len(results)} (total={total}) hasNext={has_next}",
                flush=True,
            )
            if not has_next or not results:
                break

            last_id = meta.get("last_record_unique_id")
            last_sort = meta.get("last_record_sort_value")
            time.sleep(1.0)

    return total


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--fy", type=int, default=2025, help="Federal fiscal year (default: 2025)")
    p.add_argument(
        "--out-dir",
        type=Path,
        default=Path("data/processed/sbir_phase3"),
        help="Output directory for JSONL files",
    )
    args = p.parse_args()

    queries = [
        ("SBIR", f"fy{args.fy % 100:02d}_all_sbir_contracts.jsonl"),
        ("SBIR Phase III", f"fy{args.fy % 100:02d}_sbir_phase3_contracts.jsonl"),
    ]
    for desc, fname in queries:
        print(f"\n>> fetching: fy={args.fy}, description={desc!r}")
        out = args.out_dir / fname
        n = paginate(desc, args.fy, out)
        print(f"   wrote {n:,} rows -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
