#!/usr/bin/env python3
"""Enrich Phase III universe rows with business-size categories.

The `spending_by_award` search endpoint does not populate the size fields
(`Contracting Officers Determination of Business Size`, `business_categories`)
— they're `null` in every row. The per-award detail endpoint
`/awards/{generated_internal_id}/` returns `business_categories` populated.

Reads `data/processed/sbir_phase3/phase3_universe.jsonl`, calls the
per-award detail endpoint for each row's `generated_internal_id`, and writes
an enriched JSONL with three new fields:

  - `business_categories`: list of all categories on the award (e.g.
    "Small Business", "Women Owned Small Business", "8(a)")
  - `is_small_business`: bool, True iff "Small Business" appears in categories
  - `_enrichment_status`: "ok" / "404" / "error"

Concurrency: bounded by httpx.Limits + asyncio.Semaphore. With concurrency=8
and 0.1s per-task base throttle, ~2,000 rows complete in ~5 min.

Usage:
    uv run python scripts/archive/data/enrich_phase3_business_size.py \
        --in data/processed/sbir_phase3/phase3_universe.jsonl \
        --out data/processed/sbir_phase3/phase3_universe_enriched.jsonl
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

import httpx

BASE = "https://api.usaspending.gov/api/v2/awards/{aid}/"
HEADERS = {"User-Agent": "SBIR-Analytics/0.1.0"}


async def fetch_one(
    client: httpx.AsyncClient, sem: asyncio.Semaphore, row: dict
) -> dict:
    """Look up business_categories for one Award ID; merge into the row."""
    aid = row.get("generated_internal_id") or row.get("Award ID")
    if not aid:
        row["_enrichment_status"] = "missing_aid"
        return row

    async with sem:
        for attempt in range(4):
            try:
                resp = await client.get(BASE.format(aid=aid), timeout=30)
                if resp.status_code == 200:
                    data = resp.json()
                    recip = data.get("recipient") or {}
                    cats = recip.get("business_categories") or []
                    if not cats:
                        cats = data.get("business_categories") or []
                    row["business_categories"] = list(cats)
                    row["is_small_business"] = "Small Business" in cats
                    row["_enrichment_status"] = "ok"
                    return row
                if resp.status_code == 404:
                    row["_enrichment_status"] = "404"
                    return row
                if resp.status_code in (429, 500, 502, 503, 504):
                    await asyncio.sleep(2**attempt)
                    continue
                resp.raise_for_status()
            except (httpx.TimeoutException, httpx.HTTPError) as e:
                if attempt == 3:
                    row["_enrichment_status"] = f"error: {type(e).__name__}"
                    return row
                await asyncio.sleep(2**attempt)
        row["_enrichment_status"] = "error: retries exhausted"
        return row


async def main_async(args) -> int:
    rows = []
    with args.input.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    print(f"Read {len(rows):,} rows from {args.input}", flush=True)

    sem = asyncio.Semaphore(args.concurrency)
    limits = httpx.Limits(max_connections=args.concurrency * 2)
    async with httpx.AsyncClient(headers=HEADERS, limits=limits) as client:
        tasks = [fetch_one(client, sem, r) for r in rows]
        # Process in chunks so we can emit progress
        out_path = args.output
        out_path.parent.mkdir(parents=True, exist_ok=True)
        done = 0
        ok = 0
        with out_path.open("w") as fout:
            for coro in asyncio.as_completed(tasks):
                r = await coro
                fout.write(json.dumps(r) + "\n")
                done += 1
                if r.get("_enrichment_status") == "ok":
                    ok += 1
                if done % 100 == 0:
                    print(f"  {done:,}/{len(rows):,} processed ({ok} ok)", flush=True)

    print(
        f"\n>> wrote {done:,} rows -> {out_path}  "
        f"({ok} enriched OK, {done - ok} non-ok)",
        flush=True,
    )
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument(
        "--input",
        type=Path,
        default=Path("data/processed/sbir_phase3/phase3_universe.jsonl"),
    )
    p.add_argument(
        "--output",
        type=Path,
        default=Path("data/processed/sbir_phase3/phase3_universe_enriched.jsonl"),
    )
    p.add_argument(
        "--concurrency",
        type=int,
        default=8,
        help="Max parallel API requests (default 8; USAspending tolerates this)",
    )
    args = p.parse_args()

    return asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(main())
