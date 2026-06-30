#!/usr/bin/env python3
"""Enrich Phase III rows with FPDS competition fields and parent IDV."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

import httpx

BASE = "https://api.usaspending.gov/api/v2/awards/{aid}/"
HEADERS = {"User-Agent": "SBIR-Analytics/0.1.0"}
SOLE_SOURCE_PROC = "ONLY ONE SOURCE"


async def fetch_one(client, sem, row):
    aid = row.get("generated_internal_id") or row.get("Award ID")
    if not aid:
        row["_competition_status"] = "missing_aid"
        return row
    async with sem:
        for attempt in range(4):
            try:
                resp = await client.get(BASE.format(aid=aid), timeout=30)
                if resp.status_code == 200:
                    data = resp.json()
                    ltcd = data.get("latest_transaction_contract_data") or {}
                    extent = ltcd.get("extent_competed_description")
                    proc = ltcd.get("solicitation_procedures_description")
                    row["extent_competed"] = extent
                    row["solicitation_procedures"] = proc
                    row["other_than_full_and_open"] = ltcd.get(
                        "other_than_full_and_open_competition_description"
                    )
                    row["type_set_aside"] = ltcd.get("type_set_aside_description")
                    n_offers = ltcd.get("number_of_offers_received")
                    row["number_of_offers_received"] = (
                        int(n_offers) if n_offers not in (None, "") else None
                    )
                    parent = (
                        data.get("parent_award", {}).get("piid")
                        if isinstance(data.get("parent_award"), dict)
                        else None
                    )
                    row["parent_award_id_canonical"] = parent
                    row["is_638r_sole_source"] = proc == SOLE_SOURCE_PROC
                    row["_competition_status"] = "ok"
                    return row
                if resp.status_code == 404:
                    row["_competition_status"] = "404"
                    return row
                if resp.status_code in (429, 500, 502, 503, 504):
                    await asyncio.sleep(2**attempt)
                    continue
                resp.raise_for_status()
            except (httpx.TimeoutException, httpx.HTTPError) as e:
                if attempt == 3:
                    row["_competition_status"] = f"error: {type(e).__name__}"
                    return row
                await asyncio.sleep(2**attempt)
        row["_competition_status"] = "error: retries exhausted"
        return row


async def main_async(args):
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
        args.output.parent.mkdir(parents=True, exist_ok=True)
        done = ok = sole_source = 0
        with args.output.open("w") as fout:
            for coro in asyncio.as_completed(tasks):
                r = await coro
                fout.write(json.dumps(r) + "\n")
                done += 1
                if r.get("_competition_status") == "ok":
                    ok += 1
                if r.get("is_638r_sole_source"):
                    sole_source += 1
                if done % 100 == 0:
                    print(f"  {done:,}/{len(rows):,} ({ok} ok, {sole_source} §638(r))", flush=True)
    print(f"\n>> wrote {done:,} -> {args.output} ({ok} ok, {sole_source} §638(r))", flush=True)
    return 0


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", type=Path, default=Path("data/processed/sbir_phase3/phase3_universe_enriched.jsonl"))
    p.add_argument("--output", type=Path, default=Path("data/processed/sbir_phase3/phase3_universe_competition.jsonl"))
    p.add_argument("--concurrency", type=int, default=4)
    args = p.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(main())
