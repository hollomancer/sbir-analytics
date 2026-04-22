#!/usr/bin/env python3
"""Fetch Form D XML details and compute confidence scores for SBIR matches.

Reads the bulk index output (data/form_d_index.jsonl), fetches
primary_doc.xml for each filing, parses structured data, and computes
confidence tiers using PI-to-related-person matching and other signals.

Usage:
    # Full fetch (all filings per company)
    python scripts/data/fetch_form_d_details.py

    # Latest filing only (faster)
    python scripts/data/fetch_form_d_details.py --latest-only

    # Resume from partial run
    python scripts/data/fetch_form_d_details.py --resume

    # Custom input/output
    python scripts/data/fetch_form_d_details.py \
        --input data/form_d_index.jsonl \
        --output data/form_d_details.jsonl
"""

import argparse
import asyncio
import csv
import json
import sys
import time
from datetime import date
from pathlib import Path

sys.stdout.reconfigure(line_buffering=True)
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rapidfuzz import fuzz

from sbir_etl.enrichers.sec_edgar.client import EdgarAPIClient
from sbir_etl.enrichers.sec_edgar.form_d_scoring import (
    compute_form_d_confidence,
    parse_form_d_xml,
)


def load_earliest_award_years(awards_csv: str) -> dict[str, int]:
    """Load the earliest SBIR award year per company."""
    years: dict[str, int] = {}
    with open(awards_csv, encoding="utf-8", errors="replace") as f:
        for row in csv.DictReader(f):
            name = row.get("Company", "").strip()
            year_str = row.get("Award Year", "").strip()
            if not name or not year_str:
                continue
            try:
                year = int(year_str)
            except ValueError:
                continue
            if name not in years or year < years[name]:
                years[name] = year
    return years


def load_checkpoint(path: Path) -> set[str]:
    """Load already-processed company names from output file."""
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
    parser = argparse.ArgumentParser(
        description="Fetch Form D XML details and compute confidence scores",
    )
    parser.add_argument(
        "--input", default="data/form_d_index.jsonl",
        help="Input JSONL from fetch_form_d_index.py",
    )
    parser.add_argument(
        "--output", default="data/form_d_details.jsonl",
        help="Output JSONL with XML details and confidence scores",
    )
    parser.add_argument("--awards", default="/tmp/sbir_awards_full.csv",
                        help="SBIR awards CSV (for earliest award year)")
    parser.add_argument("--latest-only", action="store_true",
                        help="Fetch only the latest Form D filing per company")
    parser.add_argument("--resume", action="store_true",
                        help="Resume from existing output")
    parser.add_argument("--concurrency", type=int, default=8,
                        help="Companies to process concurrently")
    parser.add_argument("--contact-email", default="conrad@hollomon.dev",
                        help="Email for SEC User-Agent")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not input_path.exists():
        print(f"Error: {input_path} not found. Run fetch_form_d_index.py first.")
        sys.exit(1)

    # Load input data
    print(f"Loading Form D index from {input_path}...")
    companies = []
    with open(input_path) as f:
        for line in f:
            companies.append(json.loads(line))
    print(f"  {len(companies):,} companies with Form D matches")

    # Load earliest award years
    print(f"Loading award years from {args.awards}...")
    award_years = load_earliest_award_years(args.awards)
    print(f"  {len(award_years):,} companies with award year data")

    # Load checkpoint
    done: set[str] = set()
    if args.resume:
        done = load_checkpoint(output_path)
        print(f"  Resuming: {len(done):,} already processed")

    remaining = [c for c in companies if c["company_name"] not in done]
    print(f"  {len(remaining):,} companies to process\n")

    # Initialize client
    config = {
        "efts_url": "https://efts.sec.gov/LATEST",
        "rate_limit_per_minute": 600,
        "timeout_seconds": 30,
        "contact_email": args.contact_email,
    }
    client = EdgarAPIClient(config=config)

    # Process
    semaphore = asyncio.Semaphore(args.concurrency)
    write_lock = asyncio.Lock()
    tiers = {"high": 0, "medium": 0, "low": 0}
    fetch_errors = 0
    processed = 0
    start_time = time.time()

    async def process_company(company: dict, out) -> None:
        nonlocal fetch_errors, processed

        async with semaphore:
            name = company["company_name"]
            pi_names = company.get("pi_names", [])
            sbir_state = company.get("state")
            earliest_year = award_years.get(name, 2000)

            filings = company.get("form_d_filings", [])
            if args.latest_only:
                filings = filings[-1:]  # sorted by date, last is latest

            # Fetch and parse XML for each filing
            offerings = []
            all_persons = []
            all_biz_states = set()
            all_dates = []
            year_of_inc = None
            best_name_score = 0.0

            for filing in filings:
                cik = filing["cik"]
                accession = filing["accession_number"]
                filing_date = filing["date_filed"]

                # Compute name score from filer name vs SBIR name
                score = fuzz.token_set_ratio(
                    name.upper(), filing["filer_name"].upper()
                ) / 100.0
                if score > best_name_score:
                    best_name_score = score

                xml_text = await client.fetch_form_d_xml(cik, accession)
                if xml_text is None:
                    async with write_lock:
                        fetch_errors += 1
                    continue

                try:
                    fd_date = date.fromisoformat(filing_date)
                except ValueError:
                    fd_date = date.today()
                parsed = parse_form_d_xml(
                    xml_text, accession_number=accession, filing_date=fd_date,
                )
                if parsed is None:
                    continue

                offerings.append(parsed)
                all_persons.extend(parsed.get("related_persons", []))
                if parsed.get("state"):
                    all_biz_states.add(parsed["state"])
                try:
                    all_dates.append(date.fromisoformat(filing_date))
                except ValueError:
                    pass
                if parsed.get("year_of_inc") is not None and year_of_inc is None:
                    year_of_inc = parsed["year_of_inc"]

            # Compute confidence
            if best_name_score < 0.85:
                best_name_score = 0.85  # minimum gate from index matching

            confidence = compute_form_d_confidence(
                name_score=best_name_score,
                pi_names=pi_names,
                related_persons=all_persons,
                sbir_state=sbir_state,
                biz_states=sorted(all_biz_states),
                earliest_sbir_award_year=earliest_year,
                form_d_dates=all_dates,
                year_of_inc=year_of_inc,
            )

            # Compute total raised across all offerings
            total_raised = sum(
                o.get("total_amount_sold") or 0 for o in offerings
            )

            rec = {
                "company_name": name,
                "form_d_cik": filings[0]["cik"] if filings else None,
                "offering_count": len(offerings),
                "total_raised": total_raised if total_raised > 0 else None,
                "match_confidence": confidence.model_dump(),
                "offerings": offerings,
            }

            async with write_lock:
                tiers[confidence.tier] += 1
                processed += 1
                out.write(json.dumps(rec, default=str) + "\n")
                out.flush()

    # Process in batches
    batch_size = 100
    with open(output_path, "a" if args.resume else "w") as out:
        for batch_start in range(0, len(remaining), batch_size):
            batch = remaining[batch_start:batch_start + batch_size]
            tasks = [process_company(c, out) for c in batch]
            await asyncio.gather(*tasks)

            elapsed = time.time() - start_time
            done_count = batch_start + len(batch)
            rate = done_count / elapsed if elapsed > 0 else 0
            eta = (len(remaining) - done_count) / rate / 60 if rate > 0 else 0
            print(
                f"  {processed:,}/{len(remaining):,} ({rate:.1f}/s, ETA {eta:.0f}min) "
                f"high={tiers['high']} med={tiers['medium']} low={tiers['low']} "
                f"xml_err={fetch_errors}"
            )

    await client.aclose()
    elapsed = time.time() - start_time

    # Summary
    total = sum(tiers.values())
    print(f"\n{'=' * 60}")
    print(f"FORM D XML PASS COMPLETE — {total:,} companies in {elapsed / 60:.1f} min")
    print(f"{'=' * 60}")
    print(f"High confidence:   {tiers['high']:,} ({tiers['high']/max(total,1)*100:.1f}%)")
    print(f"Medium confidence:  {tiers['medium']:,} ({tiers['medium']/max(total,1)*100:.1f}%)")
    print(f"Low confidence:     {tiers['low']:,} ({tiers['low']/max(total,1)*100:.1f}%)")
    print(f"XML fetch errors:   {fetch_errors:,}")
    print(f"Output:             {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
