#!/usr/bin/env python3
"""Build a fresh Phase III contract universe via multi-keyword USAspending refresh.

The existing `usaspending_phase3_contracts.jsonl` cache was built with a single
keyword (`description="SBIR Phase III"`), goes stale within weeks, and misses
contracts whose descriptions use variants. GAO-24-107036 documents ~30% DoD
historical Phase III undercount; description variants account for some of that.

This script pulls USAspending `spending_by_award` for several Phase-III keyword
variants across an FY range, unions and dedupes by Award ID, and writes a
provenance-tagged JSONL. Adds `Parent Award ID` to the fields list so downstream
contract-vehicle attribution (OASIS / Alliant / FEDSIM IDIQs) is one query away.

Throttle: 1s base sleep per page + per query; exponential backoff on 429/5xx.

Each output row carries:
  - `_keywords_matched`: list of keyword variants that returned this row
  - `_first_fy_seen`: earliest FY in the loop where it was returned

Usage:
    uv run python scripts/data/build_phase3_universe.py --start-fy 2014 --end-fy 2026
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

# Description variants. USAspending's `description` filter is a substring
# match, so we run each as a separate query to widen recall. Order is by
# expected recall, narrowest first.
PHASE3_KEYWORDS = [
    "SBIR Phase III",
    "SBIR Phase 3",
    "SBIR PH III",
    "Phase III SBIR",
    "SBIR follow-on",
    "Small Business Innovation Research Phase III",
]

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
    "Parent Award ID",
    "recipient_id",
    "generated_internal_id",
]


def fy_window(fy: int) -> dict:
    return {"start_date": f"{fy - 1}-10-01", "end_date": f"{fy}-09-30"}


def paginate(
    description: str, fy: int, client: httpx.Client, max_pages: int = 500
) -> list[dict]:
    """Cursor-paginate spending_by_award; return all rows for one (kw, fy) query."""
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
    rows: list[dict] = []
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
                print(f"    page {page}: {resp.status_code}, backoff {sleep}s", flush=True)
                time.sleep(sleep)
                continue
            resp.raise_for_status()
        else:
            raise RuntimeError(f"page {page}: gave up after retries")

        data = resp.json()
        results = data.get("results", [])
        rows.extend(results)
        meta = data.get("page_metadata", {})
        has_next = meta.get("hasNext", False)
        if not has_next or not results:
            break
        last_id = meta.get("last_record_unique_id")
        last_sort = meta.get("last_record_sort_value")
        time.sleep(1.0)

    return rows


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--start-fy", type=int, default=2014)
    p.add_argument("--end-fy", type=int, default=2026)
    p.add_argument(
        "--out",
        type=Path,
        default=Path("data/processed/sbir_phase3/phase3_universe.jsonl"),
    )
    p.add_argument(
        "--keywords",
        nargs="*",
        default=PHASE3_KEYWORDS,
        help="Keyword variants to query (defaults to the 6-variant canonical set).",
    )
    args = p.parse_args()

    # Indexed by Award ID; value tracks provenance + row content. Award IDs
    # are PIIDs which are unique per contract, so this is a safe dedup key.
    universe: dict[str, dict] = {}
    per_kw_counts: dict[str, int] = {kw: 0 for kw in args.keywords}

    with httpx.Client(timeout=60, headers=HEADERS) as client:
        for fy in range(args.start_fy, args.end_fy + 1):
            print(f"\n=== FY{fy} ===", flush=True)
            for kw in args.keywords:
                print(f"  keyword={kw!r}", flush=True)
                rows = paginate(kw, fy, client)
                per_kw_counts[kw] += len(rows)
                new_in_this_query = 0
                for row in rows:
                    aid = row.get("Award ID") or row.get("generated_internal_id")
                    if not aid:
                        continue
                    if aid in universe:
                        universe[aid]["_keywords_matched"].add(kw)
                    else:
                        row["_keywords_matched"] = {kw}
                        row["_first_fy_seen"] = fy
                        universe[aid] = row
                        new_in_this_query += 1
                print(
                    f"    -> {len(rows):,} rows ({new_in_this_query:,} new to universe)",
                    flush=True,
                )
                time.sleep(1.0)  # polite gap between keyword queries

    # Serialize: convert provenance set to sorted list for JSON.
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w") as f:
        for row in universe.values():
            row["_keywords_matched"] = sorted(row["_keywords_matched"])
            f.write(json.dumps(row) + "\n")

    print(f"\n>> wrote {len(universe):,} unique rows -> {args.out}")
    print("\nPer-keyword raw row counts (pre-dedup):")
    for kw, n in per_kw_counts.items():
        print(f"  {n:>6,}  {kw}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
