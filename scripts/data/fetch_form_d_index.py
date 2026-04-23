#!/usr/bin/env python3
"""Download SEC EDGAR Form D index and match against SBIR companies locally.

Replaces ~34K EFTS API queries with ~70 index file downloads + local
fuzzy matching. Produces a JSONL file mapping SBIR company names to
their Form D filing accession numbers and metadata.

Usage:
    # Full download and match
    python scripts/data/fetch_form_d_index.py \
        --awards /tmp/sbir_awards_full.csv \
        --output data/form_d_index.jsonl

    # Resume from partial download
    python scripts/data/fetch_form_d_index.py \
        --awards /tmp/sbir_awards_full.csv \
        --output data/form_d_index.jsonl --resume
"""

import argparse
import asyncio
import csv
import json
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

import httpx
from rapidfuzz import fuzz

sys.stdout.reconfigure(line_buffering=True)
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sbir_etl.utils.text_normalization import normalize_name

# Form D electronic filing started in earnest Q1 2009
START_YEAR = 2009
END_YEAR = 2026
INDEX_BASE = "https://www.sec.gov/Archives/edgar/full-index"
FORM_D_PATTERN = re.compile(r"^D(?:/A)?\s")


def load_sbir_companies(awards_csv: str) -> dict[str, dict]:
    """Load unique SBIR companies with normalized names for matching.

    Returns dict keyed by normalized name -> {raw_names, award_count, state, pi_names}.
    """
    from collections import Counter

    raw_counts: Counter[str] = Counter()
    company_state: dict[str, str] = {}
    company_pis: dict[str, set[str]] = defaultdict(set)

    # State name mapping (reuse from scan script)
    state_map = {
        "ALABAMA": "AL", "ALASKA": "AK", "ARIZONA": "AZ", "ARKANSAS": "AR",
        "CALIFORNIA": "CA", "COLORADO": "CO", "CONNECTICUT": "CT", "DELAWARE": "DE",
        "FLORIDA": "FL", "GEORGIA": "GA", "HAWAII": "HI", "IDAHO": "ID",
        "ILLINOIS": "IL", "INDIANA": "IN", "IOWA": "IA", "KANSAS": "KS",
        "KENTUCKY": "KY", "LOUISIANA": "LA", "MAINE": "ME", "MARYLAND": "MD",
        "MASSACHUSETTS": "MA", "MICHIGAN": "MI", "MINNESOTA": "MN",
        "MISSISSIPPI": "MS", "MISSOURI": "MO", "MONTANA": "MT", "NEBRASKA": "NE",
        "NEVADA": "NV", "NEW HAMPSHIRE": "NH", "NEW JERSEY": "NJ",
        "NEW MEXICO": "NM", "NEW YORK": "NY", "NORTH CAROLINA": "NC",
        "NORTH DAKOTA": "ND", "OHIO": "OH", "OKLAHOMA": "OK", "OREGON": "OR",
        "PENNSYLVANIA": "PA", "RHODE ISLAND": "RI", "SOUTH CAROLINA": "SC",
        "SOUTH DAKOTA": "SD", "TENNESSEE": "TN", "TEXAS": "TX", "UTAH": "UT",
        "VERMONT": "VT", "VIRGINIA": "VA", "WASHINGTON": "WA",
        "WEST VIRGINIA": "WV", "WISCONSIN": "WI", "WYOMING": "WY",
        "DISTRICT OF COLUMBIA": "DC", "PUERTO RICO": "PR",
    }

    with open(awards_csv, encoding="utf-8", errors="replace") as f:
        for row in csv.DictReader(f):
            name = row.get("Company", "").strip()
            if not name:
                continue
            raw_counts[name] += 1

            if name not in company_state:
                raw_state = (row.get("State") or "").strip().upper()
                code = state_map.get(raw_state, raw_state if len(raw_state) == 2 else "")
                if code:
                    company_state[name] = code

            pi = (row.get("PI Name") or "").strip()
            if pi:
                company_pis[name].add(pi)

    # Group by normalized name
    companies: dict[str, dict] = {}
    for raw_name, count in raw_counts.items():
        norm = normalize_name(raw_name, remove_suffixes=True)
        if norm not in companies:
            companies[norm] = {
                "raw_names": set(),
                "award_count": 0,
                "state": None,
                "pi_names": set(),
                "earliest_award_year": None,
            }
        companies[norm]["raw_names"].add(raw_name)
        companies[norm]["award_count"] += count
        if raw_name in company_state and not companies[norm]["state"]:
            companies[norm]["state"] = company_state[raw_name]
        companies[norm]["pi_names"].update(company_pis.get(raw_name, set()))

    return companies


def parse_index_line(line: str) -> dict | None:
    """Parse a fixed-width form.idx line into a dict.

    Format: 'FormType  CompanyName  CIK  DateFiled  Filename'
    Fields are separated by variable whitespace in fixed-width columns.
    """
    if not FORM_D_PATTERN.match(line):
        return None

    # Fixed-width parsing based on observed format:
    # Form type: cols 0-16, Company: cols 17-78, CIK: cols 79-90,
    # Date: cols 91-103, Filename: 104+
    # But widths vary, so we parse from the right (filename, date, cik are fixed-ish)
    parts = line.rstrip().split()
    if len(parts) < 5:
        return None

    # Filename is always last, date is second-to-last, CIK is third-to-last
    filename = parts[-1]
    date_filed = parts[-2]
    cik = parts[-3]

    # Form type is first token (D or D/A)
    form_type = parts[0]

    # Company name is everything between form type and CIK
    # Find where the CIK starts in the original line
    cik_pos = line.rfind(cik, 0, line.rfind(date_filed))
    if cik_pos < 0:
        return None
    company_name = line[len(form_type):cik_pos].strip()

    # Extract accession number from filename path
    # Format: edgar/data/CIK/ACCESSION.txt
    acc_match = re.search(r"edgar/data/\d+/(\S+)\.txt", filename)
    accession = acc_match.group(1) if acc_match else ""

    return {
        "form_type": form_type,
        "company_name": company_name,
        "cik": cik,
        "date_filed": date_filed,
        "accession_number": accession,
        "filename": filename,
    }


async def download_form_d_index(
    contact_email: str,
    *,
    concurrency: int = 4,
) -> list[dict]:
    """Download all Form D entries from EDGAR quarterly index files."""
    headers = {"User-Agent": f"SBIR-Analytics/0.1.0 ({contact_email})"}

    # Build list of quarters to fetch
    quarters = []
    for year in range(START_YEAR, END_YEAR + 1):
        for qtr in range(1, 5):
            quarters.append((year, qtr))

    all_entries: list[dict] = []
    semaphore = asyncio.Semaphore(concurrency)
    lock = asyncio.Lock()
    errors = 0

    async def fetch_quarter(client: httpx.AsyncClient, year: int, qtr: int) -> None:
        nonlocal errors
        url = f"{INDEX_BASE}/{year}/QTR{qtr}/form.idx"
        async with semaphore:
            try:
                resp = await client.get(url, headers=headers)
                if resp.status_code == 404:
                    return  # Future quarter, skip
                resp.raise_for_status()
                text = resp.text

                entries = []
                for line in text.splitlines():
                    parsed = parse_index_line(line)
                    if parsed:
                        entries.append(parsed)

                async with lock:
                    all_entries.extend(entries)

            except Exception as e:
                async with lock:
                    errors += 1
                    print(f"  Error fetching {year}/QTR{qtr}: {e}")

    print(f"Downloading Form D index ({len(quarters)} quarters)...")
    async with httpx.AsyncClient(timeout=60) as client:
        tasks = [fetch_quarter(client, y, q) for y, q in quarters]
        await asyncio.gather(*tasks)

    print(f"  Downloaded {len(all_entries):,} Form D entries ({errors} errors)")
    return all_entries


def match_form_d_to_sbir(
    form_d_entries: list[dict],
    sbir_companies: dict[str, dict],
    *,
    threshold: int = 85,
) -> dict[str, list[dict]]:
    """Match Form D filer names to SBIR companies using fuzzy matching.

    Returns dict keyed by normalized SBIR company name -> list of matching
    Form D entries.
    """
    # Build normalized index of Form D filer names
    # Group by normalized name for efficient matching
    fd_by_norm: dict[str, list[dict]] = defaultdict(list)
    for entry in form_d_entries:
        norm = normalize_name(entry["company_name"], remove_suffixes=True)
        fd_by_norm[norm].append(entry)

    matches: dict[str, list[dict]] = {}
    checked = 0

    # First pass: exact normalized name match (fast)
    for sbir_norm, sbir_data in sbir_companies.items():
        if sbir_norm in fd_by_norm:
            matches[sbir_norm] = fd_by_norm[sbir_norm]

    exact = len(matches)
    print(f"  Exact normalized matches: {exact:,}")

    # Second pass: fuzzy match for remaining companies
    # Only check SBIR companies that didn't get an exact match
    unmatched_sbir = {k: v for k, v in sbir_companies.items() if k not in matches}
    fd_norms = list(fd_by_norm.keys())

    # Build a simple blocking index by first 3 chars to avoid O(n*m) comparison
    fd_blocks: dict[str, list[str]] = defaultdict(list)
    for norm in fd_norms:
        if len(norm) >= 3:
            fd_blocks[norm[:3]].append(norm)

    for sbir_norm, sbir_data in unmatched_sbir.items():
        if len(sbir_norm) < 3:
            continue
        candidates = fd_blocks.get(sbir_norm[:3], [])
        for fd_norm in candidates:
            score = fuzz.token_set_ratio(sbir_norm, fd_norm)
            if score >= threshold:
                matches[sbir_norm] = fd_by_norm[fd_norm]
                break
        checked += 1
        if checked % 5000 == 0:
            print(f"  Fuzzy checked {checked:,}/{len(unmatched_sbir):,}...")

    fuzzy = len(matches) - exact
    print(f"  Fuzzy matches: {fuzzy:,}")
    print(f"  Total matched: {len(matches):,}")

    return matches


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download Form D index and match to SBIR companies"
    )
    parser.add_argument("--awards", required=True, help="Path to SBIR awards CSV")
    parser.add_argument(
        "--output", default="data/form_d_index.jsonl",
        help="Output JSONL file",
    )
    parser.add_argument("--resume", action="store_true", help="Skip already-matched companies")
    parser.add_argument(
        "--contact-email", default="conrad@hollomon.dev",
        help="Email for SEC User-Agent",
    )
    args = parser.parse_args()

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    start = time.time()

    # Step 1: Load SBIR companies
    print(f"Loading SBIR companies from {args.awards}...")
    sbir_companies = load_sbir_companies(args.awards)
    print(f"  {len(sbir_companies):,} unique normalized companies")

    # Step 2: Download Form D index
    form_d_entries = await download_form_d_index(args.contact_email)

    # Step 3: Match
    print("\nMatching Form D filers to SBIR companies...")
    matches = match_form_d_to_sbir(form_d_entries, sbir_companies)

    # Step 4: Load checkpoint if resuming
    done: set[str] = set()
    if args.resume and output_path.exists():
        with open(output_path) as f:
            for line in f:
                try:
                    rec = json.loads(line)
                    done.add(rec["company_name"])
                except (json.JSONDecodeError, KeyError):
                    continue
        print(f"\n  Resuming: {len(done):,} already written")

    # Step 5: Write results
    written = 0
    with open(output_path, "a" if args.resume else "w") as out:
        for sbir_norm, fd_entries in sorted(matches.items()):
            sbir_data = sbir_companies[sbir_norm]
            # Use the most common raw name
            raw_name = max(sbir_data["raw_names"], key=lambda n: 1)
            if raw_name in done:
                continue

            rec = {
                "company_name": raw_name,
                "company_names_all": sorted(sbir_data["raw_names"]),
                "award_count": sbir_data["award_count"],
                "state": sbir_data["state"],
                "pi_names": sorted(sbir_data["pi_names"]),
                "form_d_count": len(fd_entries),
                "form_d_filings": [
                    {
                        "filer_name": e["company_name"],
                        "cik": e["cik"],
                        "date_filed": e["date_filed"],
                        "accession_number": e["accession_number"],
                        "form_type": e["form_type"],
                    }
                    for e in sorted(fd_entries, key=lambda e: e["date_filed"])
                ],
            }
            out.write(json.dumps(rec) + "\n")
            written += 1

    elapsed = time.time() - start

    # Summary
    total_filings = sum(len(v) for v in matches.values())
    print(f"\n{'=' * 60}")
    print(f"FORM D INDEX MATCH COMPLETE — {elapsed:.1f}s")
    print(f"{'=' * 60}")
    print(f"Form D entries downloaded:  {len(form_d_entries):,}")
    print(f"SBIR companies matched:     {len(matches):,}")
    print(f"Total Form D filings:       {total_filings:,}")
    print(f"Records written:            {written:,}")
    print(f"Output:                     {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
