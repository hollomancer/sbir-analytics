#!/usr/bin/env python3
"""Scan SBIR awardees for SEC EDGAR filing mentions and Form D filings.

Writes results to a JSONL checkpoint file as it runs, so progress is
never lost.  Can resume from a partial run.

Usage:
    # Full scan (writes to data/sec_edgar_scan.jsonl)
    python scripts/data/scan_sbir_edgar.py --awards /tmp/sbir_awards_full.csv

    # Resume from checkpoint
    python scripts/data/scan_sbir_edgar.py --awards /tmp/sbir_awards_full.csv --resume

    # Skip document fetches (faster, counts only)
    python scripts/data/scan_sbir_edgar.py --awards /tmp/sbir_awards_full.csv --no-doc-fetch

    # Scan first N companies only
    python scripts/data/scan_sbir_edgar.py --awards /tmp/sbir_awards_full.csv --limit 1000
"""

import argparse
import asyncio
import csv
import json
import sys
import time
from collections import Counter
from pathlib import Path

# Force unbuffered stdout
sys.stdout.reconfigure(line_buffering=True)

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from loguru import logger

from sbir_etl.enrichers.sec_edgar.client import EdgarAPIClient
from sbir_etl.enrichers.sec_edgar.enricher import enrich_company


class _ServerErrorTracker:
    """Loguru sink that detects HTTP 5xx warnings during a company's enrichment."""

    def __init__(self):
        self.saw_server_error = False

    def write(self, message):
        if "HTTP 5" in message:
            self.saw_server_error = True

    def reset(self):
        self.saw_server_error = False


def load_companies(awards_csv: str) -> list[tuple[str, int]]:
    """Load unique companies sorted by award count (descending)."""
    counts: Counter[str] = Counter()
    with open(awards_csv, encoding="utf-8", errors="replace") as f:
        for row in csv.DictReader(f):
            name = row.get("Company", "").strip()
            if name:
                counts[name] += 1
    return counts.most_common()


def load_company_cities(awards_csv: str) -> dict[str, str]:
    """Load the first city seen for each company."""
    cities: dict[str, str] = {}
    with open(awards_csv, encoding="utf-8", errors="replace") as f:
        for row in csv.DictReader(f):
            name = row.get("Company", "").strip()
            city = (row.get("City") or "").strip()
            if name and city and name not in cities:
                cities[name] = city
    return cities


def load_checkpoint(path: Path, *, rescan_errors: bool = False) -> set[str]:
    """Load already-scanned company names from checkpoint file.

    When *rescan_errors* is True, companies whose records have
    ``had_server_errors`` or ``error`` are excluded from the done set
    so they get re-scanned.
    """
    done: set[str] = set()
    if not path.exists():
        return done
    with open(path) as f:
        for line in f:
            try:
                rec = json.loads(line)
                if rescan_errors and (
                    rec.get("had_server_errors") or rec.get("error")
                ):
                    continue
                done.add(rec["company_name"])
            except (json.JSONDecodeError, KeyError):
                continue
    return done


async def run_city_pass(args) -> None:
    """Second pass: qualify mentions with city co-occurrence."""
    import httpx

    scan_path = Path(args.output)
    if not scan_path.exists():
        print(f"Error: scan file {scan_path} not found. Run the main scan first.")
        sys.exit(1)

    # Load company cities
    print(f"Loading cities from {args.awards}...")
    cities = load_company_cities(args.awards)

    # Load scan results, filter to companies with mentions
    with_mentions = []
    with open(scan_path) as f:
        for line in f:
            rec = json.loads(line)
            if rec.get("mention_count", 0) > 0 and "error" not in rec:
                with_mentions.append(rec)

    print(f"  {len(with_mentions):,} companies with mentions to qualify")

    output_path = scan_path.with_suffix(".city_qualified.jsonl")
    already_done = set()
    if args.resume and output_path.exists():
        with open(output_path) as f:
            for line in f:
                already_done.add(json.loads(line).get("company_name"))
        print(f"  Resuming: {len(already_done):,} already qualified")

    remaining = [r for r in with_mentions if r["company_name"] not in already_done]
    print(f"  {len(remaining):,} to process\n")

    headers = {"User-Agent": f"SBIR-Analytics/0.1.0 ({args.contact_email})"}
    confirmed = 0
    unconfirmed = 0
    no_city = 0
    start_time = time.time()

    async with httpx.AsyncClient(timeout=30) as client:
        with open(output_path, "a") as out:
            for i, rec in enumerate(remaining):
                name = rec["company_name"]
                city = cities.get(name, "")

                if not city or len(city) < 3:
                    # No city data — can't qualify
                    rec["city_qualified"] = None
                    rec["city_hits"] = None
                    no_city += 1
                else:
                    # Search EFTS for company + city
                    resp = await client.get(
                        "https://efts.sec.gov/LATEST/search-index",
                        params={
                            "q": f'"{name}" AND "{city}"',
                            "dateRange": "custom",
                            "startdt": "2000-01-01",
                            "enddt": "2026-12-31",
                        },
                        headers=headers,
                    )
                    if resp.status_code == 200:
                        hits = resp.json().get("hits", {}).get("total", {}).get("value", 0)
                        rec["city_qualified"] = hits > 0
                        rec["city_hits"] = hits
                        rec["city"] = city
                        if hits > 0:
                            confirmed += 1
                        else:
                            unconfirmed += 1
                    else:
                        rec["city_qualified"] = None
                        rec["city_hits"] = None

                out.write(json.dumps(rec) + "\n")
                out.flush()

                if (i + 1) % 100 == 0:
                    elapsed = time.time() - start_time
                    rate = (i + 1) / elapsed
                    eta = (len(remaining) - i - 1) / rate / 60
                    print(
                        f"  {i+1:,}/{len(remaining):,} ({rate:.1f}/s, ETA {eta:.0f}min) "
                        f"confirmed={confirmed} unconfirmed={unconfirmed} no_city={no_city}"
                    )

    elapsed = time.time() - start_time
    print(f"\n{'='*60}")
    print(f"CITY QUALIFICATION COMPLETE — {len(remaining):,} companies in {elapsed/60:.1f} min")
    print(f"{'='*60}")
    print(f"Confirmed (name+city match):   {confirmed} ({confirmed/max(1,confirmed+unconfirmed)*100:.0f}%)")
    print(f"Unconfirmed (name only):       {unconfirmed} ({unconfirmed/max(1,confirmed+unconfirmed)*100:.0f}%)")
    print(f"No city data:                  {no_city}")
    print(f"Output: {output_path}")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Scan SBIR awardees against SEC EDGAR")
    parser.add_argument("--awards", required=True, help="Path to SBIR awards CSV")
    parser.add_argument("--output", default="data/sec_edgar_scan.jsonl",
                        help="Output JSONL checkpoint file")
    parser.add_argument("--resume", action="store_true",
                        help="Resume from existing checkpoint")
    parser.add_argument("--city-pass", action="store_true",
                        help="Run city qualification pass on existing scan results")
    parser.add_argument("--no-doc-fetch", action="store_true",
                        help="Skip document fetches for context classification")
    parser.add_argument("--limit", type=int, default=0,
                        help="Scan only first N companies (0=all)")
    parser.add_argument("--rescan-errors", action="store_true",
                        help="Re-scan companies that had server errors in previous run")
    parser.add_argument("--contact-email", default="conrad@hollomon.dev",
                        help="Email for SEC User-Agent")
    args = parser.parse_args()

    # Dispatch city qualification pass
    if args.city_pass:
        await run_city_pass(args)
        return

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Load companies
    print(f"Loading companies from {args.awards}...")
    companies = load_companies(args.awards)
    total_awards = sum(c for _, c in companies)
    print(f"  {len(companies):,} unique companies, {total_awards:,} awards")

    if args.limit:
        companies = companies[:args.limit]
        print(f"  Limited to first {args.limit:,}")

    # Load checkpoint
    done: set[str] = set()
    if args.resume or args.rescan_errors:
        done = load_checkpoint(output_path, rescan_errors=args.rescan_errors)
        print(f"  Resuming: {len(done):,} already scanned")
        if args.rescan_errors:
            print("  (re-scanning companies with server errors)")

    remaining = [(name, count) for name, count in companies if name not in done]
    print(f"  {len(remaining):,} companies to scan\n")

    # Initialize client
    config = {
        "efts_url": "https://efts.sec.gov/LATEST",
        "companyfacts_url": "https://data.sec.gov/api/xbrl/companyfacts",
        "submissions_url": "https://data.sec.gov/submissions",
        "rate_limit_per_minute": 600,
        "timeout_seconds": 30,
        "contact_email": args.contact_email,
    }
    client = EdgarAPIClient(config=config)

    # Monkey-patch out document fetches if requested
    if args.no_doc_fetch:
        async def _no_fetch(*a, **kw):
            return None
        client.fetch_filing_document = _no_fetch
        print("  Document fetches DISABLED (counts only)\n")

    # Scan — track server errors per company via loguru sink
    error_tracker = _ServerErrorTracker()
    tracker_id = logger.add(error_tracker, level="WARNING", format="{message}")

    with_mentions = 0
    with_form_d = 0
    with_both = 0
    server_errors = 0
    errors = 0
    start_time = time.time()
    processed = len(done)

    with open(output_path, "a") as out:
        for i, (name, award_count) in enumerate(remaining):
            error_tracker.reset()
            try:
                p = await enrich_company(client, name)

                has_mention = p.mention_count > 0
                has_form_d = p.form_d_count > 0

                if has_mention:
                    with_mentions += 1
                if has_form_d:
                    with_form_d += 1
                if has_mention and has_form_d:
                    with_both += 1

                had_errors = error_tracker.saw_server_error
                if had_errors:
                    server_errors += 1

                # Write checkpoint record
                rec = {
                    "company_name": name,
                    "award_count": award_count,
                    "mention_count": p.mention_count,
                    "mention_filers": p.mention_filers[:5],
                    "mention_types": p.mention_types,
                    "latest_mention_date": str(p.latest_mention_date) if p.latest_mention_date else None,
                    "form_d_count": p.form_d_count,
                    "has_form_d": p.has_form_d,
                    "form_d_cik": p.form_d_cik,
                    "latest_form_d_date": str(p.latest_form_d_date) if p.latest_form_d_date else None,
                }
                if had_errors:
                    rec["had_server_errors"] = True
                out.write(json.dumps(rec) + "\n")
                out.flush()  # Flush after every record

            except Exception as e:
                errors += 1
                # Still checkpoint the error so we don't re-scan
                rec = {"company_name": name, "award_count": award_count, "error": str(e)[:200]}
                out.write(json.dumps(rec) + "\n")
                out.flush()

            processed += 1
            if (i + 1) % 100 == 0:
                elapsed = time.time() - start_time
                rate = (i + 1) / elapsed if elapsed > 0 else 0
                eta_min = (len(remaining) - i - 1) / rate / 60 if rate > 0 else 0
                print(
                    f"  {processed:,}/{len(companies):,} "
                    f"({rate:.1f}/s, ETA {eta_min:.0f}min) "
                    f"mentions={with_mentions} formD={with_form_d} "
                    f"both={with_both} err={errors} 5xx={server_errors}"
                )

    elapsed = time.time() - start_time
    logger.remove(tracker_id)
    await client.aclose()

    # Summary
    print(f"\n{'='*60}")
    print(f"SCAN COMPLETE — {processed:,} companies in {elapsed/60:.1f} min")
    print(f"{'='*60}")
    print(f"SEC filing mentions:  {with_mentions:,} ({with_mentions/len(remaining)*100:.1f}%)")
    print(f"Form D (investment):  {with_form_d:,} ({with_form_d/len(remaining)*100:.1f}%)")
    print(f"Both signals:         {with_both:,} ({with_both/len(remaining)*100:.1f}%)")
    print(f"Errors:               {errors:,}")
    print(f"Server errors (5xx):  {server_errors:,} (rescan with --rescan-errors)")
    print(f"Output:               {output_path}")

    # Also write summary
    summary_path = output_path.with_suffix(".summary.json")
    summary = {
        "total_companies": len(companies),
        "scanned": processed,
        "with_mentions": with_mentions,
        "with_form_d": with_form_d,
        "with_both": with_both,
        "errors": errors,
        "server_errors": server_errors,
        "elapsed_seconds": elapsed,
        "doc_fetch_enabled": not args.no_doc_fetch,
    }
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"Summary:              {summary_path}")


if __name__ == "__main__":
    asyncio.run(main())
