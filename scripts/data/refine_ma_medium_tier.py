#!/usr/bin/env python3
"""Refine medium-tier M&A events with directional text analysis.

Re-queries EFTS for medium-tier companies, fetches filing documents,
and applies directional regex to distinguish:
  - "acquired Company X" → confirmed target (keep medium)
  - "Company X acquired a license" → not an exit (demote to low)
  - "comparable to Company X" → not an exit (demote to low)

Usage:
    python scripts/data/refine_ma_medium_tier.py
    python scripts/data/refine_ma_medium_tier.py --resume
"""

import argparse
import asyncio
import json
import re
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(line_buffering=True)
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sbir_etl.enrichers.sec_edgar.client import EdgarAPIClient

# --- Directional regex patterns ---

# Company is the TARGET of acquisition (strong positive)
# Pattern: [acquirer] acquired/purchased/bought [company_name]
# We check for acquisition verbs BEFORE the company name in the window
_TARGET_BEFORE = re.compile(
    r"(?:acquir(?:ed|es|ing)|purchas(?:ed|es|ing)|bought|merged with|"
    r"acquisition of|business combination with|tender offer for|"
    r"completed (?:the |its )?(?:acquisition|purchase) of)\s+"
    r"(?:all of the (?:outstanding )?(?:shares|stock|equity|assets) of\s+)?",
    re.IGNORECASE,
)

# Company is the TARGET — pattern after company name
# Pattern: [company_name] was acquired/purchased/merged
_TARGET_AFTER = re.compile(
    r"\s+(?:was |were |has been |have been )?"
    r"(?:acquir(?:ed|es)|purchas(?:ed|es)|merged|bought|"
    r"became a (?:wholly[- ]owned )?subsidiary)",
    re.IGNORECASE,
)

# Company is NOT the target — it did the acquiring or licensing
# Pattern: [company_name] acquired a license / acquired rights / acquired assets
_NOT_TARGET = re.compile(
    r"\s+(?:acquir(?:ed|es|ing)|purchas(?:ed|es|ing)|obtain(?:ed|s|ing)|"
    r"licens(?:ed|es|ing)|enter(?:ed|s|ing) into)\s+"
    r"(?:a |an |the |certain |exclusive |non-exclusive )?"
    r"(?:licen[sc]e|rights?|assets?|technology|patent|option|agreement|contract)",
    re.IGNORECASE,
)

# Company appears in a comparison context
_COMPARATOR = re.compile(
    r"(?:comparable|similar to|peer|competitor|in comparison|"
    r"relative to|as compared|benchmarked against)",
    re.IGNORECASE,
)


def classify_direction(
    text: str,
    company_name: str,
    context_chars: int = 500,
) -> str:
    """Classify whether the company is the acquisition target.

    Returns:
        'target' — company is being acquired (keep medium)
        'not_target' — company is the acquirer/licensor (demote)
        'comparator' — company is a comparison (demote)
        'ambiguous' — can't determine direction (keep medium)
    """
    # Find company name in text
    pattern = re.compile(re.escape(company_name), re.IGNORECASE)
    match = pattern.search(text)
    if not match:
        # Try without common corporate suffixes
        clean = re.sub(
            r"\s*(?:Inc\.?|Corp\.?|LLC|L\.?L\.?C\.?|Ltd\.?|Co\.?|Company|"
            r"Corporation|Incorporated|Limited)\s*$",
            "", company_name, flags=re.IGNORECASE,
        ).strip()
        if len(clean) >= 5:
            match = re.search(re.escape(clean), text, re.IGNORECASE)
    if not match:
        return "ambiguous"

    # Extract windows before and after the match
    before_start = max(0, match.start() - context_chars)
    after_end = min(len(text), match.end() + context_chars)
    before_window = text[before_start:match.start()]
    after_window = text[match.end():after_end]

    # Check for comparator context (anywhere in window)
    full_window = text[before_start:after_end]
    if _COMPARATOR.search(full_window):
        return "comparator"

    # Check if company is NOT the target (it acquired/licensed something)
    if _NOT_TARGET.match(after_window):
        return "not_target"

    # Check if company IS the target
    # Look for acquisition verbs just before the company name
    if _TARGET_BEFORE.search(before_window[-200:]):
        return "target"

    # Look for passive construction after the company name
    if _TARGET_AFTER.match(after_window):
        return "target"

    return "ambiguous"


async def refine_events(
    events: list[dict],
    client: EdgarAPIClient,
    output_path: Path,
    resume_done: set[str],
    concurrency: int = 2,
) -> dict[str, int]:
    """Re-query EFTS and refine each medium-tier event."""
    semaphore = asyncio.Semaphore(concurrency)
    write_lock = asyncio.Lock()
    stats = {"target": 0, "not_target": 0, "comparator": 0, "ambiguous": 0, "no_filing": 0, "error": 0}
    processed = 0
    start_time = time.time()

    async def process_one(event: dict, out) -> None:
        nonlocal processed
        async with semaphore:
            name = event["company_name"]
            if name in resume_done:
                return

            # Query EFTS for filings mentioning this company
            try:
                mentions = await client.search_filing_mentions(
                    name,
                    forms="8-K,10-K,DEFM14A,PREM14A,SC TO-T,SC 14D9",
                    limit=10,
                )
            except Exception:
                mentions = []

            if not mentions:
                event["direction"] = "no_filing"
                async with write_lock:
                    stats["no_filing"] += 1
                    processed += 1
                    out.write(json.dumps(event, default=str) + "\n")
                    out.flush()
                return

            # Try to fetch and classify the first M&A-related filing
            best_direction = "ambiguous"
            for mention in mentions:
                doc_id = mention.get("doc_id", "")
                if not doc_id or ":" not in doc_id:
                    continue
                filer_cik = mention.get("filer_cik", "")
                if not filer_cik:
                    continue

                accession, filename = doc_id.split(":", 1)
                try:
                    text = await client.fetch_filing_document(
                        filer_cik, accession, filename
                    )
                except Exception:
                    text = None

                if not text:
                    continue

                direction = classify_direction(text, name)
                if direction == "target":
                    best_direction = "target"
                    break
                elif direction == "not_target":
                    best_direction = "not_target"
                    break
                elif direction == "comparator":
                    best_direction = "comparator"
                    break
                # If ambiguous, keep trying other filings

            event["direction"] = best_direction
            async with write_lock:
                stats[best_direction] += 1
                processed += 1
                out.write(json.dumps(event, default=str) + "\n")
                out.flush()

                if processed % 50 == 0:
                    elapsed = time.time() - start_time
                    rate = processed / elapsed if elapsed > 0 else 0
                    remaining = len(events) - processed - len(resume_done)
                    eta = remaining / rate / 60 if rate > 0 else 0
                    print(
                        f"  {processed:,}/{len(events):,} ({rate:.1f}/s, ETA {eta:.0f}min) "
                        f"target={stats['target']} not_target={stats['not_target']} "
                        f"comp={stats['comparator']} ambig={stats['ambiguous']} "
                        f"no_filing={stats['no_filing']}"
                    )

    batch_size = 50
    with open(output_path, "a" if resume_done else "w") as out:
        for batch_start in range(0, len(events), batch_size):
            batch = events[batch_start:batch_start + batch_size]
            tasks = [process_one(e, out) for e in batch]
            await asyncio.gather(*tasks)

    return stats


def load_checkpoint(path: Path) -> set[str]:
    done = set()
    if not path.exists():
        return done
    with open(path) as f:
        for line in f:
            try:
                r = json.loads(line)
                done.add(r["company_name"])
            except (json.JSONDecodeError, KeyError):
                continue
    return done


async def main():
    parser = argparse.ArgumentParser(description="Refine medium-tier M&A events")
    parser.add_argument("--input", default="data/sbir_ma_events.jsonl")
    parser.add_argument("--output", default="data/sbir_ma_medium_refined.jsonl")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--concurrency", type=int, default=2)
    parser.add_argument("--contact-email", default="conrad@hollomon.dev")
    args = parser.parse_args()

    # Load medium-tier events
    events = []
    with open(args.input) as f:
        for line in f:
            r = json.loads(line)
            if r["confidence"] == "medium":
                events.append(r)

    print(f"Medium-tier events to refine: {len(events):,}")

    output_path = Path(args.output)
    resume_done = set()
    if args.resume:
        resume_done = load_checkpoint(output_path)
        print(f"  Resuming: {len(resume_done):,} already processed")

    remaining = [e for e in events if e["company_name"] not in resume_done]
    print(f"  {len(remaining):,} to process\n")

    config = {
        "efts_url": "https://efts.sec.gov/LATEST",
        "rate_limit_per_minute": 120,
        "timeout_seconds": 30,
        "retry_attempts": 3,
        "retry_backoff_seconds": 10.0,
        "contact_email": args.contact_email,
    }
    client = EdgarAPIClient(config=config)

    stats = await refine_events(remaining, client, output_path, resume_done, args.concurrency)

    await client.aclose()

    total = sum(stats.values())
    print(f"\n{'='*60}")
    print(f"MEDIUM-TIER REFINEMENT COMPLETE — {total:,} events")
    print(f"{'='*60}")
    print(f"  Confirmed target:  {stats['target']:,}")
    print(f"  Not target:        {stats['not_target']:,}")
    print(f"  Comparator:        {stats['comparator']:,}")
    print(f"  Ambiguous:         {stats['ambiguous']:,}")
    print(f"  No filing found:   {stats['no_filing']:,}")
    print(f"  Output: {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
