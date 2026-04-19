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

from sbir_etl.enrichers.sec_edgar.client import EdgarAPIClient
from sbir_etl.enrichers.sec_edgar.enricher import enrich_company


def load_companies(awards_csv: str) -> list[tuple[str, int]]:
    """Load unique companies sorted by award count (descending)."""
    counts: Counter[str] = Counter()
    with open(awards_csv, encoding="utf-8", errors="replace") as f:
        for row in csv.DictReader(f):
            name = row.get("Company", "").strip()
            if name:
                counts[name] += 1
    return counts.most_common()


def load_checkpoint(path: Path) -> set[str]:
    """Load already-scanned company names from checkpoint file."""
    done: set[str] = set()
    if not path.exists():
        return done
    with open(path) as f:
        for line in f:
            try:
                rec = json.loads(line)
                done.add(rec["company_name"])
            except (json.JSONDecodeError, KeyError):
                continue
    return done


async def main() -> None:
    parser = argparse.ArgumentParser(description="Scan SBIR awardees against SEC EDGAR")
    parser.add_argument("--awards", required=True, help="Path to SBIR awards CSV")
    parser.add_argument("--output", default="data/sec_edgar_scan.jsonl",
                        help="Output JSONL checkpoint file")
    parser.add_argument("--resume", action="store_true",
                        help="Resume from existing checkpoint")
    parser.add_argument("--no-doc-fetch", action="store_true",
                        help="Skip document fetches for context classification")
    parser.add_argument("--limit", type=int, default=0,
                        help="Scan only first N companies (0=all)")
    parser.add_argument("--contact-email", default="conrad@hollomon.dev",
                        help="Email for SEC User-Agent")
    args = parser.parse_args()

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
    if args.resume:
        done = load_checkpoint(output_path)
        print(f"  Resuming: {len(done):,} already scanned")

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

    # Scan
    with_mentions = 0
    with_form_d = 0
    with_both = 0
    errors = 0
    start_time = time.time()
    processed = len(done)

    with open(output_path, "a") as out:
        for i, (name, award_count) in enumerate(remaining):
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
                    f"both={with_both} err={errors}"
                )

    elapsed = time.time() - start_time
    await client.aclose()

    # Summary
    print(f"\n{'='*60}")
    print(f"SCAN COMPLETE — {processed:,} companies in {elapsed/60:.1f} min")
    print(f"{'='*60}")
    print(f"SEC filing mentions:  {with_mentions:,} ({with_mentions/len(remaining)*100:.1f}%)")
    print(f"Form D (investment):  {with_form_d:,} ({with_form_d/len(remaining)*100:.1f}%)")
    print(f"Both signals:         {with_both:,} ({with_both/len(remaining)*100:.1f}%)")
    print(f"Errors:               {errors:,}")
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
        "elapsed_seconds": elapsed,
        "doc_fetch_enabled": not args.no_doc_fetch,
    }
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"Summary:              {summary_path}")


if __name__ == "__main__":
    asyncio.run(main())
