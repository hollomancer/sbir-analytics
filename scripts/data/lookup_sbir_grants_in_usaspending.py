#!/usr/bin/env python3
"""Batch-lookup SBIR.gov grant IDs in USAspending FABS.

Companion to `lookup_sbir_contracts_in_usaspending.py`. Where that one
joins SBIR.gov to FPDS contracts (NAICS + PSC), this one joins to FABS
assistance awards (grants and cooperative agreements). FABS records
expose CFDA Number but not NAICS — NAICS is procurement-only.

Per-agency ID normalization (USAspending FAIN conventions):
  - HHS/NIH: strip leading application-type digit and "-XX" support-year
             suffix. `1R43CA295178-01A1` → `R43CA295178`.
  - DoE:     strip dashes. `DE-SC0025753` → `DESC0025753`.
  - NSF, DoC: pass-through (alphanumeric already canonical).

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

# USAspending assistance award type codes: 02 block, 03 formula, 04 project,
# 05 coop agreement. SBIR is always 04 or 05. We include 02/03 for safety.
ASSISTANCE_TYPES = ["02", "03", "04", "05"]


def normalize(agency: str, raw: str) -> str:
    s = raw.strip().upper()
    if agency == "Department of Health and Human Services":
        s = re.sub(r"^\d", "", s)         # strip app type digit
        s = re.sub(r"-.*$", "", s)        # strip -XX support year and suffixes
    elif agency == "Department of Energy":
        s = s.replace("-", "")
    return s


def collect_grants(src: Path, award_year: int, agencies: list[str]) -> list[tuple[str, str]]:
    """Return (agency, normalized_id) for grant-funded SBIR.gov awards."""
    out: list[tuple[str, str]] = []
    with src.open(encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("Award Year", "").strip() != str(award_year):
                continue
            ag = (row.get("Agency") or "").strip()
            if ag not in agencies:
                continue
            raw = (row.get("Contract") or "").strip()
            if not raw:
                continue
            out.append((ag, normalize(ag, raw)))
    # Dedupe by normalized contract ID. Agency context is dropped here; only
    # the (ag, nid) pair is kept for the first occurrence of each nid, so
    # downstream consumers should not rely on agency attribution past this step.
    seen: set[str] = set()
    result: list[tuple[str, str]] = []
    for ag, nid in out:
        if nid in seen:
            continue
        seen.add(nid)
        result.append((ag, nid))
    return result


def lookup(piids: list[str], client: httpx.Client) -> list[dict]:
    body = {
        "filters": {
            "time_period": [{"start_date": "2023-10-01", "end_date": "2026-12-31"}],
            "award_type_codes": ASSISTANCE_TYPES,
            "award_ids": piids,
        },
        "fields": [
            "Award ID",
            "Recipient Name",
            "Recipient UEI",
            "Award Amount",
            "Description",
            "Start Date",
            "End Date",
            "Awarding Agency",
            "Awarding Sub Agency",
            "Funding Agency",
            "Funding Sub Agency",
            "CFDA Number",
            "recipient_id",
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
        help="SBIR.gov bulk CSV",
    )
    p.add_argument("--award-year", type=int, default=2025)
    p.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output JSONL (default: data/processed/sbir_phase3/fy<YY>_sbir_grant_lookups.jsonl)",
    )
    p.add_argument(
        "--agencies",
        nargs="*",
        default=[
            "National Science Foundation",
            "Department of Health and Human Services",
            "Department of Energy",
            "Department of Commerce",
        ],
        help="Agencies whose SBIR awards live in FABS (default: NSF, HHS, DoE, DoC)",
    )
    args = p.parse_args()

    out_path = args.out or Path(
        f"data/processed/sbir_phase3/fy{args.award_year % 100:02d}_sbir_grant_lookups.jsonl"
    )

    pairs = collect_grants(args.src, args.award_year, args.agencies)
    print(f"Award Year {args.award_year} SBIR.gov grant IDs to look up: {len(pairs):,} unique")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    matched = 0
    with httpx.Client(timeout=60, headers=HEADERS) as client, out_path.open("w") as fout:
        for i in range(0, len(pairs), BATCH):
            chunk = pairs[i : i + BATCH]
            ids = [nid for _, nid in chunk]
            results = lookup(ids, client)
            matched += len(results)
            for row in results:
                fout.write(json.dumps(row) + "\n")
            print(
                f"  batch {i // BATCH + 1}/{(len(pairs)+BATCH-1)//BATCH}: "
                f"requested={len(chunk)} matched={len(results)} (cum_matched={matched})",
                flush=True,
            )
            time.sleep(1.0)
    print(f"\nDone. {matched:,} of {len(pairs):,} found in USAspending FABS -> {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
