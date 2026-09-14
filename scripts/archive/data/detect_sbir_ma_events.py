#!/usr/bin/env python3
"""Detect M&A exit events for SBIR companies.

Extracts signals from Form D business combinations and EFTS mention
classifications, merges into a unified events dataset with confidence tiers.

Usage:
    python scripts/archive/data/detect_sbir_ma_events.py
    python scripts/archive/data/detect_sbir_ma_events.py --form-d data/form_d_details.jsonl
"""

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sbir_etl.enrichers.sec_edgar.form_d_scoring import (  # noqa: E402
    FORM_D_TIER_RULE_VERSION,
    require_form_d_tier_rule,
)

# Only high-tier identity matches enter the exit artifact. The scorer already
# graded these; carrying medium and low forward re-admits joins it rejected.
KEEP_MATCH_TIER = "high"

# EFTS mention types that are evidence the SBIR firm was the *target*.
# ma_proxy ("may be a comparable-table entry") and ownership_active (">5% stake
# with intent") are graded Low in the signal memo and are not target-side
# evidence, so they do not rescue an otherwise acquirer-side row.
TARGET_SIDE_EFTS_SIGNALS = (
    "efts_subsidiary",
    "efts_ma_definitive",
    "efts_acquisition_text",
)


def is_acquirer_side_only(signals: dict[str, bool]) -> bool:
    """True when the only evidence is a Form D business-combination flag.

    Form D Item 10 marks a Rule 145 transaction -- a deemed offer and sale of
    securities *by the issuer* -- so the filer is the acquirer. With no
    target-side EFTS mention alongside it, the row is evidence the SBIR firm
    *bought* something, which is the opposite of an exit.

    Demoting such rows to low is not enough. Several consumers treat row
    presence in the exit artifact as an exit and never read confidence, so a
    demoted row still counts. They are written to a sibling file instead, which
    keeps the evidence without letting an exit consumer mistake it.
    """
    if not signals.get("form_d_business_combination"):
        return False
    return not any(signals.get(key) for key in TARGET_SIDE_EFTS_SIGNALS)


def extract_form_d_signals(
    records: list[dict],
    *,
    expected_rule_version: str = FORM_D_TIER_RULE_VERSION,
) -> list[dict]:
    """Extract M&A events from Form D business combination flags.

    For each company with at least one is_business_combination offering,
    produces one event using the earliest combo filing date.

    Records whose identity match did not reach KEEP_MATCH_TIER are dropped. The
    scorer already rejected those joins; carrying them forward re-admits matches
    it graded away, and the count of drops is reported so the filter is visible.
    """
    events = []
    dropped_on_tier = 0
    for r in records:
        confidence = require_form_d_tier_rule(
            r.get("match_confidence"),
            expected_rule_version=expected_rule_version,
            context=f"Form D record {r.get('company_name') or '<unnamed>'!r}",
        )
        if confidence.get("tier") != KEEP_MATCH_TIER:
            dropped_on_tier += 1
            continue
        combos = [o for o in r.get("offerings", []) if o.get("is_business_combination")]
        if not combos:
            continue

        combos.sort(key=lambda o: str(o.get("filing_date", "")))
        earliest = combos[0]

        total_sold = sum(o.get("total_amount_sold") or 0 for o in combos)

        all_persons = []
        for o in combos:
            all_persons.extend(o.get("related_persons", []))

        events.append(
            {
                "company_name": r["company_name"],
                "event_date": str(earliest.get("filing_date", ""))[:10],
                "source": "form_d",
                "form_d_detail": {
                    "tier_rule_version": confidence["rule_version"],
                    "filing_date": str(earliest.get("filing_date", ""))[:10],
                    "total_amount_sold": total_sold if total_sold > 0 else None,
                    "combo_count": len(combos),
                    "related_persons": all_persons,
                },
            }
        )

    if dropped_on_tier:
        print(f"  dropped {dropped_on_tier} Form D records below match tier {KEEP_MATCH_TIER!r}")
    return events


def extract_efts_signals(records: list[dict]) -> list[dict]:
    """Extract M&A events from EFTS mention classifications.

    Maps mention types to confidence levels and extracts acquirer
    candidates from mention_filers.
    """
    MA_TYPES = {
        "subsidiary": "high",
        "acquisition": "medium",
        "ma_definitive": "low",
        "ma_proxy": "low",
        "ownership_active": "low",
    }

    events = []
    for r in records:
        types = r.get("mention_types", [])
        ma_hits = {t: MA_TYPES[t] for t in types if t in MA_TYPES}
        if not ma_hits:
            continue

        tier_order = {"high": 0, "medium": 1, "low": 2}
        best_tier = min(ma_hits.values(), key=lambda t: tier_order[t])

        events.append(
            {
                "company_name": r["company_name"],
                "event_date": r.get("latest_mention_date", ""),
                "source": "efts",
                "efts_detail": {
                    "mention_filers": r.get("mention_filers", []),
                    "mention_types": sorted(ma_hits.keys()),
                    "latest_mention_date": r.get("latest_mention_date", ""),
                    "efts_tier": best_tier,
                },
            }
        )

    return events


def merge_events(
    form_d_events: list[dict],
    efts_events: list[dict],
) -> list[dict]:
    """Merge Form D and EFTS events by company name.

    When both sources have an event for the same company, combine into
    one record (one event per company). Uses the earliest valid ISO date
    across sources; an empty/missing date is treated as unknown and a
    valid date always wins over an empty one.

    Note: merging is by exact company name only. The 12-month date-window
    same-event deduplication described in the design spec is not implemented
    here; in practice a single company rarely has events far enough apart to
    require it, and the one-event-per-company model matches the actual output.
    """
    merged: dict[str, dict] = {}

    for e in form_d_events:
        name = e["company_name"]
        merged[name] = {
            "company_name": name,
            "event_date": e["event_date"],
            "form_d_detail": e["form_d_detail"],
            "efts_detail": None,
        }

    for e in efts_events:
        name = e["company_name"]
        efts_date = e["event_date"]
        if name in merged:
            existing = merged[name]
            existing_date = existing["event_date"]
            # A valid date beats an empty one; when both valid, take the earlier.
            if efts_date and (not existing_date or efts_date < existing_date):
                existing["event_date"] = efts_date
            existing["efts_detail"] = e["efts_detail"]
        else:
            merged[name] = {
                "company_name": name,
                "event_date": efts_date,
                "form_d_detail": None,
                "efts_detail": e["efts_detail"],
            }

    return list(merged.values())


def assign_confidence(event: dict) -> str:
    """Grade how well the evidence supports the SBIR firm being *acquired*.

    A Form D business-combination flag does not contribute. Item 10 is filed by
    the acquirer, so on its own it is evidence in the wrong direction; grading
    it `high` inflated the exit population with rows that record purchases.
    Only target-side EFTS evidence earns a tier.
    """
    efts = event.get("efts_detail")
    has_efts_high = efts is not None and "subsidiary" in efts.get("mention_types", [])
    has_acq_text = efts is not None and ("acquisition" in efts.get("mention_types", []))

    if has_efts_high:
        return "high"
    elif has_acq_text:
        return "medium"
    else:
        return "low"


def build_signals_dict(event: dict) -> dict[str, bool]:
    """Build a flat dict of which signals fired."""
    efts_types = set()
    if event.get("efts_detail"):
        efts_types = set(event["efts_detail"].get("mention_types", []))

    return {
        "form_d_business_combination": event.get("form_d_detail") is not None,
        "efts_subsidiary": "subsidiary" in efts_types,
        "efts_ma_definitive": "ma_definitive" in efts_types,
        "efts_acquisition_text": "acquisition" in efts_types,
        "efts_ma_proxy": "ma_proxy" in efts_types,
        "efts_ownership_active": "ownership_active" in efts_types,
    }


def identify_acquirer(event: dict) -> str | None:
    """Best-effort acquirer identification from available signals."""
    efts = event.get("efts_detail")
    if efts and efts.get("mention_filers"):
        return efts["mention_filers"][0]
    return None


def load_sbir_context(awards_csv: str) -> dict[str, dict]:
    """Load SBIR award context per company.

    Keys the returned dict by normalised company name (upper-cased, stripped)
    so that SEC-derived event names (which are upper-cased) match correctly.
    """
    companies: dict[str, dict] = {}
    with open(awards_csv, encoding="utf-8", errors="replace") as f:
        for row in csv.DictReader(f):
            name = row.get("Company", "").strip()
            if not name:
                continue
            key = name.upper()
            agency = row.get("Agency", "").strip()
            year_str = row.get("Award Year", "").strip()
            amt_str = row.get("Award Amount", "").strip()
            if not year_str:
                continue
            try:
                year = int(year_str)
                amt_clean = amt_str.replace(",", "").replace("$", "")
                amt = float(amt_clean) if amt_clean else 0
            except ValueError:
                continue

            if key not in companies:
                companies[key] = {
                    "agency": agency,
                    "total_awards": 0,
                    "total_award_amount": 0,
                    "first_award_year": year,
                    "last_award_year": year,
                }
            c = companies[key]
            c["total_awards"] += 1
            c["total_award_amount"] += amt
            if year < c["first_award_year"]:
                c["first_award_year"] = year
            if year > c["last_award_year"]:
                c["last_award_year"] = year
            c["agency"] = agency

    return companies


def main():
    parser = argparse.ArgumentParser(description="Detect SBIR M&A exit events")
    parser.add_argument("--form-d", default="data/form_d_details.jsonl")
    parser.add_argument("--efts", default="data/sec_edgar_scan.jsonl")
    parser.add_argument("--awards", default="/tmp/sbir_awards_full.csv")
    parser.add_argument("--output", default="data/sbir_ma_events.jsonl")
    parser.add_argument(
        "--non-exit-output",
        default="data/sbir_ma_non_exit.jsonl",
        help=(
            "Rows whose only evidence is an acquirer-side Form D flag. Written "
            "here rather than to --output so an exit consumer cannot count them."
        ),
    )
    args = parser.parse_args()

    # Layer 1: Form D
    print("Loading Form D data...")
    form_d_records = []
    with open(args.form_d) as f:
        for line in f:
            form_d_records.append(json.loads(line))
    form_d_events = extract_form_d_signals(form_d_records)
    print(f"  Form D business combinations: {len(form_d_events)} companies")

    # Layer 2: EFTS
    print("Loading EFTS scan data...")
    efts_records = []
    with open(args.efts) as f:
        for line in f:
            efts_records.append(json.loads(line))
    efts_events = extract_efts_signals(efts_records)
    print(f"  EFTS M&A signals: {len(efts_events)} companies")

    # Merge
    merged = merge_events(form_d_events, efts_events)
    print(f"  Merged (deduplicated): {len(merged)} companies")

    # Load SBIR context
    print(f"Loading SBIR awards from {args.awards}...")
    sbir_context = load_sbir_context(args.awards)

    # Enrich and write
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    non_exit_path = Path(args.non_exit_output)
    non_exit_path.parent.mkdir(parents=True, exist_ok=True)

    tiers = {"high": 0, "medium": 0, "low": 0}
    non_exit_n = 0
    with open(output_path, "w") as out, open(non_exit_path, "w") as non_exit:
        for event in merged:
            signals = build_signals_dict(event)
            confidence = assign_confidence(event)
            acquirer = identify_acquirer(event)

            record = {
                "company_name": event["company_name"],
                "event_date": event["event_date"],
                "acquirer": acquirer,
                "confidence": confidence,
                "signals": signals,
                "signal_count": sum(signals.values()),
                "form_d_detail": event.get("form_d_detail"),
                "efts_detail": event.get("efts_detail"),
                "sbir_context": sbir_context.get(event["company_name"].strip().upper()),
            }
            if is_acquirer_side_only(signals):
                record["non_exit_reason"] = "acquirer_side"
                non_exit.write(json.dumps(record, default=str) + "\n")
                non_exit_n += 1
                continue
            out.write(json.dumps(record, default=str) + "\n")
            tiers[confidence] += 1

    total = sum(tiers.values())
    print(f"\n{'=' * 60}")
    print(f"M&A EXIT DETECTION COMPLETE — {total:,} events")
    print(f"{'=' * 60}")
    print(f"  High confidence:   {tiers['high']:,}")
    print(f"  Medium confidence: {tiers['medium']:,}")
    print(f"  Low confidence:    {tiers['low']:,}")
    print(f"  Output: {output_path}")
    print(f"  Acquirer-side (not exits): {non_exit_n:,} -> {non_exit_path}")


if __name__ == "__main__":
    main()
