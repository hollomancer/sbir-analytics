#!/usr/bin/env python3
"""Refine direction-sensitive M&A events with filing-text analysis.

Re-queries EFTS for medium-tier acquisition-text events and low-tier
definitive-merger events, fetches filing documents,
and applies directional regex to distinguish:
  - "acquired Company X" → confirmed target (keep medium)
  - "Company X acquired a license" → not an exit (demote to low)
  - "comparable to Company X" → not an exit (demote to low)
  - failed or incomplete filing retrieval → context incomplete (quarantine)

Usage:
    python scripts/archive/data/refine_ma_medium_tier.py
    python scripts/archive/data/refine_ma_medium_tier.py --resume

    # After a complete fresh run, apply the verdicts fail-closed:
    python scripts/archive/data/apply_ma_direction_refinement.py \
        --events data/sbir_ma_events.jsonl \
        --refinements data/sbir_ma_medium_refined.jsonl \
        --output data/enriched_sbir_ma_events.jsonl
"""

import argparse
import asyncio
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path

sys.stdout.reconfigure(line_buffering=True)
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from sbir_etl.enrichers.sec_edgar.client import EdgarAPIClient

# --- Directional regex patterns ---

# Company is the TARGET of acquisition (strong positive)
# Pattern: [acquirer] acquired/purchased/bought [company_name]
# The verb phrase is anchored to the company mention. An acquisition elsewhere
# in the preceding window does not establish that this company was the target.
_TARGET_BEFORE = re.compile(
    r"(?:acquir(?:ed|es|ing)|purchas(?:ed|es|ing)|bought|merged with|"
    r"acquisition of|business combination with|tender offer for|"
    r"asset purchase agreement with|"
    r"completed (?:the |its )?(?:acquisition|purchase) of)\s+"
    r"(?:all of the (?:outstanding )?(?:shares|stock|equity|assets) of\s+)?$",
    re.IGNORECASE,
)

# Company is the TARGET — pattern after company name
# Pattern: [company_name] was acquired/purchased/merged
# Require passive voice: active "Company acquired Target" names the acquirer.
_TARGET_AFTER = re.compile(
    r"[,\s]+(?:a .{0,40} )?"
    r"(?:(?:was|were|has been|have been|is being|are being|will be)\s+"
    r"(?:acquired|purchased|merged|bought)"
    r"|became a (?:wholly[- ]owned )?subsidiary)",
    re.IGNORECASE,
)

# Company listed as operating entity / subsidiary in descriptions
# The ownership phrase must attach to the company name. Generic portfolio/list
# language is role-blind and cannot safely promote a low-confidence event.
_OPERATING_ENTITY = re.compile(
    r"^[,\s]+(?:is|was|became|remains)\s+(?:a|an)\s+"
    r"(?:direct |indirect |wholly[- ]owned |majority[- ]owned )*"
    r"subsidiar(?:y|ies)\s+of",
    re.IGNORECASE,
)

# Company is NOT the target — it did the acquiring or licensing
# Pattern: [company_name] acquired a license / acquired rights / acquired assets
_NOT_TARGET = re.compile(
    r"\s+(?:acquir(?:ed|es|ing)|purchas(?:ed|es|ing)|obtain(?:ed|s|ing)|"
    r"licens(?:ed|es|ing)|enter(?:ed|s|ing) into)\s+"
    r"(?:(?:a|an|the|certain)\s+)?"
    r"(?:(?:exclusive|non-exclusive|perpetual|worldwide|limited|irrevocable)\s+)?"
    r"(?:licen[sc]e|rights?|assets?|technology|patent|option|agreement|contract)",
    re.IGNORECASE,
)

# Company appears in a comparison context
_COMPARATOR = re.compile(
    r"(?:comparable|similar to|peer|competitor|in comparison|"
    r"relative to|as compared|benchmarked against)",
    re.IGNORECASE,
)

# Employment/consulting agreement — not an acquisition
_EMPLOYMENT = re.compile(
    r"(?:employment agreement|consulting agreement|executive employment|"
    r"offer letter|compensation arrangement)",
    re.IGNORECASE,
)

_REFINEMENT_DIRECTIONS = frozenset(
    {"target", "not_target", "comparator", "ambiguous", "no_filing", "context_incomplete"}
)


def needs_directional_refinement(event: dict) -> bool:
    """Return whether an event's confidence depends on target direction."""
    signals = event.get("signals") or {}
    strong_signal = bool(
        signals.get("form_d_business_combination") or signals.get("efts_subsidiary")
    )
    return not strong_signal and bool(
        signals.get("efts_acquisition_text") or signals.get("efts_ma_definitive")
    )


def confidence_after_directional_refinement(
    event: dict,
    *,
    direction: str,
    context_complete: bool,
) -> str:
    """Apply the existing direction-aware confidence rules to one event."""
    if direction not in _REFINEMENT_DIRECTIONS:
        raise ValueError(f"unsupported refinement direction: {direction!r}")
    signals = event.get("signals") or {}
    if signals.get("form_d_business_combination") or signals.get("efts_subsidiary"):
        return "high"
    if not context_complete:
        return "low"
    if signals.get("efts_acquisition_text"):
        return "medium" if direction in {"target", "ambiguous"} else "low"
    if signals.get("efts_ma_definitive"):
        return "medium" if direction == "target" else "low"
    return "low"


def _is_valid_refinement_record(record: object) -> bool:
    """Return whether *record* satisfies the typed refinement output contract."""
    if not isinstance(record, dict):
        return False
    company_name = record.get("company_name")
    direction = record.get("direction")
    context_complete = record.get("context_classification_complete")
    raw_reasons = record.get("context_incomplete_reasons")
    reasons = [] if raw_reasons is None else raw_reasons
    if not isinstance(company_name, str) or not company_name.strip():
        return False
    if not isinstance(direction, str) or direction.strip() not in _REFINEMENT_DIRECTIONS:
        return False
    if not isinstance(context_complete, bool):
        return False
    if not isinstance(reasons, list) or any(
        not isinstance(reason, str) or not reason.strip() for reason in reasons
    ):
        return False
    if context_complete:
        return direction.strip() != "context_incomplete" and not reasons
    return direction.strip() == "context_incomplete" and bool(reasons)


def _read_checkpoint_records(path: Path) -> list[dict]:
    """Read parseable object records, ignoring an interrupted JSONL tail."""
    records: list[dict] = []
    if not path.exists():
        return records
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(record, dict):
                records.append(record)
    return records


def _write_checkpoint_atomically(path: Path, records: list[dict]) -> None:
    """Replace a refinement checkpoint through a same-directory temporary file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            for record in records:
                handle.write(json.dumps(record, default=str) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _prepare_refinement_checkpoint(
    path: Path,
    *,
    requested_names: set[str],
    resume: bool,
) -> set[str]:
    """Atomically initialize or heal a typed refinement checkpoint."""
    retained_by_name: dict[str, dict] = {}
    if resume:
        for record in _read_checkpoint_records(path):
            if not _is_valid_refinement_record(record):
                continue
            company_name = str(record["company_name"]).strip()
            if company_name in requested_names:
                # A later valid row supersedes an earlier valid attempt.
                retained_by_name[company_name] = record
    retained = list(retained_by_name.values())
    _write_checkpoint_atomically(path, retained)
    return set(retained_by_name)


def _mark_context_incomplete(client: EdgarAPIClient) -> None:
    callback = getattr(client, "context_incomplete_callback", None)
    if callable(callback):
        callback()


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
            "",
            company_name,
            flags=re.IGNORECASE,
        ).strip()
        if len(clean) >= 5:
            match = re.search(re.escape(clean), text, re.IGNORECASE)
    if not match:
        return "ambiguous"

    # Extract windows before and after the match
    before_start = max(0, match.start() - context_chars)
    after_end = min(len(text), match.end() + context_chars)
    before_window = text[before_start : match.start()]
    after_window = text[match.end() : after_end]
    full_window = text[before_start:after_end]

    # Check for employment/consulting agreement — not an acquisition
    if _EMPLOYMENT.search(full_window):
        return "not_target"

    # Check for comparator context (anywhere in window)
    if _COMPARATOR.search(full_window):
        return "comparator"

    # Check if company is NOT the target (it acquired/licensed something)
    if _NOT_TARGET.match(after_window):
        return "not_target"

    # Check if company IS the target
    # 1. Acquisition verbs just before the company name
    if _TARGET_BEFORE.search(before_window[-300:]):
        return "target"

    # 2. Passive construction after the company name
    if _TARGET_AFTER.match(after_window):
        return "target"

    # 3. Listed as an owned subsidiary immediately after the company name.
    # Merger-agreement boilerplate is deliberately not a direction signal: it
    # names both sides and cannot distinguish target from acquirer.
    if _OPERATING_ENTITY.match(after_window):
        return "target"

    return "ambiguous"


async def refine_events(
    events: list[dict],
    client: EdgarAPIClient,
    output_path: Path,
    resume_done: set[str],
    concurrency: int = 2,
) -> dict[str, int]:
    """Re-query EFTS and refine each direction-sensitive event."""
    semaphore = asyncio.Semaphore(concurrency)
    write_lock = asyncio.Lock()
    stats = {
        "target": 0,
        "not_target": 0,
        "comparator": 0,
        "ambiguous": 0,
        "no_filing": 0,
        "context_incomplete": 0,
        "error": 0,
    }
    processed = 0
    start_time = time.time()

    async def process_one(event: dict, out) -> None:
        nonlocal processed
        async with semaphore:
            name = event["company_name"]
            if str(name).strip() in resume_done:
                return

            incomplete_reasons: set[str] = set()

            def mark_context_incomplete(reason: str) -> None:
                if not incomplete_reasons:
                    _mark_context_incomplete(client)
                incomplete_reasons.add(reason)

            async def write_result(direction: str) -> None:
                nonlocal processed
                event["direction"] = direction
                event["context_classification_complete"] = not incomplete_reasons
                if incomplete_reasons:
                    event["context_incomplete_reasons"] = sorted(incomplete_reasons)
                else:
                    event.pop("context_incomplete_reasons", None)
                async with write_lock:
                    stats[direction] += 1
                    processed += 1
                    out.write(json.dumps(event, default=str) + "\n")
                    out.flush()

                    if processed % 50 == 0:
                        elapsed = time.time() - start_time
                        rate = processed / elapsed if elapsed > 0 else 0
                        remaining = max(len(events) - processed, 0)
                        eta = remaining / rate / 60 if rate > 0 else 0
                        print(
                            f"  {processed:,}/{len(events):,} ({rate:.1f}/s, ETA {eta:.0f}min) "
                            f"target={stats['target']} not_target={stats['not_target']} "
                            f"comp={stats['comparator']} ambig={stats['ambiguous']} "
                            f"no_filing={stats['no_filing']} "
                            f"incomplete={stats['context_incomplete']}"
                        )

            # Query EFTS for filings mentioning this company
            try:
                mentions = await client.search_filing_mentions(
                    name,
                    forms="8-K,10-K,DEFM14A,PREM14A,SC TO-T,SC 14D9",
                    limit=10,
                    raise_on_error=True,
                )
            except Exception:
                mark_context_incomplete("mention_search_failed")
                mentions = []

            if not mentions:
                direction = "context_incomplete" if incomplete_reasons else "no_filing"
                await write_result(direction)
                return

            # Try to fetch and classify the first M&A-related filing
            best_direction = "ambiguous"
            for mention in mentions:
                doc_id = mention.get("doc_id")
                if not isinstance(doc_id, str) or ":" not in doc_id:
                    mark_context_incomplete("malformed_document_reference")
                    continue
                accession, filename = doc_id.split(":", 1)
                filer_cik = str(mention.get("filer_cik") or "").strip()
                if not accession.strip() or not filename.strip() or not filer_cik:
                    mark_context_incomplete("incomplete_document_reference")
                    continue

                try:
                    text = await client.fetch_filing_document(
                        filer_cik,
                        accession,
                        filename,
                        raise_on_error=True,
                    )
                except Exception:
                    mark_context_incomplete("document_fetch_failed")
                    continue

                if not text:
                    mark_context_incomplete("empty_document")
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

            if incomplete_reasons:
                best_direction = "context_incomplete"
            await write_result(best_direction)

    batch_size = 50
    with open(output_path, "a" if resume_done else "w") as out:
        for batch_start in range(0, len(events), batch_size):
            batch = events[batch_start : batch_start + batch_size]
            tasks = [process_one(e, out) for e in batch]
            await asyncio.gather(*tasks)

    return stats


async def main():
    parser = argparse.ArgumentParser(description="Refine direction-sensitive M&A events")
    parser.add_argument("--input", default="data/sbir_ma_events.jsonl")
    parser.add_argument("--output", default="data/sbir_ma_medium_refined.jsonl")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--concurrency", type=int, default=2)
    parser.add_argument("--contact-email", default="conrad@hollomon.dev")
    args = parser.parse_args()

    # Load every event whose tier depends on acquisition direction. Selection
    # follows source signals, not a mutable confidence value, so a rerun also
    # covers previously demoted acquisition hits and low definitive-merger hits.
    events = []
    with open(args.input) as f:
        for line in f:
            r = json.loads(line)
            if needs_directional_refinement(r):
                events.append(r)

    print(f"Direction-sensitive events to refine: {len(events):,}")

    output_path = Path(args.output)
    resume_done = _prepare_refinement_checkpoint(
        output_path,
        requested_names={str(event["company_name"]).strip() for event in events},
        resume=args.resume,
    )
    if args.resume:
        print(f"  Resuming: {len(resume_done):,} already processed")

    remaining = [event for event in events if str(event["company_name"]).strip() not in resume_done]
    print(f"  {len(remaining):,} to process\n")

    config = {
        "base_url": "https://efts.sec.gov/LATEST",
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
    print(f"\n{'=' * 60}")
    print(f"MEDIUM-TIER REFINEMENT COMPLETE — {total:,} events")
    print(f"{'=' * 60}")
    print(f"  Confirmed target:  {stats['target']:,}")
    print(f"  Not target:        {stats['not_target']:,}")
    print(f"  Comparator:        {stats['comparator']:,}")
    print(f"  Ambiguous:         {stats['ambiguous']:,}")
    print(f"  No filing found:   {stats['no_filing']:,}")
    print(f"  Context incomplete:{stats['context_incomplete']:,}")
    print(f"  Output: {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
