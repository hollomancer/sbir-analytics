#!/usr/bin/env python3
"""Batch-lookup SBIR.gov contract IDs in USAspending.

For each contract PIID found in SBIR.gov's bulk CSV at a given Award Year,
POST to `spending_by_award` with `award_ids=[batch]` to retrieve NAICS,
PSC, structured agency, and amounts. Pure-numeric IDs are skipped — those
are NSF/HHS grant numbers in FABS, not FPDS.

This is the throttle-friendly authoritative join: ~100 batched POSTs at
1s spacing instead of the description-keyword approach, which silently
misses ~70% of DoD SBIR contracts whose descriptions don't include the
literal token "SBIR".

Throttle: 1s between batches; exponential backoff on 429/5xx.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from pathlib import Path

import httpx

API = "https://api.usaspending.gov/api/v2/search/spending_by_award/"
HEADERS = {"User-Agent": "SBIR-Analytics/0.1.0"}
BATCH = 50
NUMERIC_ID = re.compile(r"^[0-9]+$")


def normalize(piid: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", piid.upper().strip())


def collect_piids(src: Path, award_year: int) -> list[str]:
    piids: list[str] = []
    with src.open(encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("Award Year", "").strip() != str(award_year):
                continue
            raw = (row.get("Contract") or "").strip()
            if not raw:
                continue
            norm = normalize(raw)
            if NUMERIC_ID.match(norm):
                continue
            piids.append(norm)
    return sorted(set(piids))


def lookup(piids: list[str], client: httpx.Client) -> list[dict]:
    body = {
        "filters": {
            "time_period": [{"start_date": "2020-10-01", "end_date": "2026-12-31"}],
            "award_type_codes": ["A", "B", "C", "D"],
            "award_ids": piids,
        },
        "fields": [
            "Award ID",
            "Recipient Name",
            "Recipient UEI",
            "Award Amount",
            "Description",
            "Start Date",
            "Awarding Agency",
            "Awarding Sub Agency",
            "Funding Agency",
            "Funding Sub Agency",
            "NAICS",
            "PSC",
            "generated_internal_id",
        ],
        "page": 1,
        "limit": 100,
        "sort": "Award Amount",
        "order": "desc",
        "subawards": False,
    }
    for attempt in range(5):
        resp = client.post(API, json=body)
        if resp.status_code == 200:
            return resp.json().get("results", [])
        if resp.status_code in (429, 500, 502, 503, 504):
            sleep = 2 ** attempt
            print(f"  {resp.status_code}, backoff {sleep}s", flush=True)
            time.sleep(sleep)
            continue
        resp.raise_for_status()
    raise RuntimeError("gave up after retries")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument(
        "--src",
        type=Path,
        default=Path("data/raw/sbir/award_data.csv"),
        help="SBIR.gov bulk CSV (default: data/raw/sbir/award_data.csv)",
    )
    p.add_argument("--award-year", type=int, default=2025, help="SBIR.gov Award Year")
    p.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output JSONL (default: data/processed/sbir_phase3/fy<YY>_sbir_contract_lookups.jsonl)",
    )
    args = p.parse_args()

    out_path = args.out or Path(
        f"data/processed/sbir_phase3/fy{args.award_year % 100:02d}_sbir_contract_lookups.jsonl"
    )

    piids = collect_piids(args.src, args.award_year)
    print(f"Award Year {args.award_year} SBIR.gov PIIDs to look up: {len(piids):,} unique")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    matched = 0
    with httpx.Client(timeout=60, headers=HEADERS) as client, out_path.open("w") as fout:
        for i in range(0, len(piids), BATCH):
            chunk = piids[i : i + BATCH]
            results = lookup(chunk, client)
            matched += len(results)
            for row in results:
                fout.write(json.dumps(row) + "\n")
            print(
                f"  batch {i // BATCH + 1}/{(len(piids)+BATCH-1)//BATCH}: "
                f"requested={len(chunk)} matched={len(results)} (cum_matched={matched})",
                flush=True,
            )
            time.sleep(1.0)
    print(f"\nDone. {matched:,} of {len(piids):,} found in USAspending FPDS -> {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
