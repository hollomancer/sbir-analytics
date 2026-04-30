#!/usr/bin/env python3
"""Analyze SBIR M&A exit events.

Reads sbir_ma_events.jsonl and produces exit rate analysis by agency,
year, and confidence tier.

Usage:
    python scripts/data/analyze_sbir_ma_exits.py
    python scripts/data/analyze_sbir_ma_exits.py data/sbir_ma_events.jsonl /tmp/sbir_awards_full.csv
"""

import csv
import json
import sys
from collections import Counter, defaultdict

import numpy as np


def load_events(path: str) -> list[dict]:
    events = []
    with open(path) as f:
        for line in f:
            events.append(json.loads(line))
    return events


def load_total_companies_by_agency(awards_csv: str) -> dict[str, int]:
    """Count unique SBIR companies per agency."""
    agency_cos: dict[str, set] = defaultdict(set)
    with open(awards_csv, encoding="utf-8", errors="replace") as f:
        for row in csv.DictReader(f):
            name = row.get("Company", "").strip()
            agency = row.get("Agency", "").strip()
            if name and agency:
                agency_cos[agency].add(name)
    return {a: len(cos) for a, cos in agency_cos.items()}


def main():
    events_path = sys.argv[1] if len(sys.argv) > 1 else "data/sbir_ma_events.jsonl"
    awards_path = sys.argv[2] if len(sys.argv) > 2 else "/tmp/sbir_awards_full.csv"

    events = load_events(events_path)
    total_by_agency = load_total_companies_by_agency(awards_path)

    all_cos: set[str] = set()
    with open(awards_path, encoding="utf-8", errors="replace") as f:
        for row in csv.DictReader(f):
            name = row.get("Company", "").strip()
            if name:
                all_cos.add(name)
    total_sbir = len(all_cos)

    print(f"Loaded {len(events):,} M&A events\n")

    # --- Tier distribution ---
    tiers = Counter(e["confidence"] for e in events)
    print("=== CONFIDENCE TIERS ===")
    for t in ["high", "medium", "low"]:
        print(f"  {t:>8s}: {tiers.get(t, 0):>5,}")

    # --- Overall exit rate ---
    print(f"\n=== EXIT RATE ===")
    print(f"  Total SBIR companies: {total_sbir:,}")
    print(f"  Companies with M&A event: {len(events):,}")
    print(f"  Overall exit rate: {len(events)/total_sbir*100:.1f}%")
    high_med = [e for e in events if e["confidence"] in ("high", "medium")]
    print(f"  Exit rate (H+M only): {len(high_med)/total_sbir*100:.1f}%")
    high_only = [e for e in events if e["confidence"] == "high"]
    print(f"  Exit rate (high only): {len(high_only)/total_sbir*100:.1f}%")

    # --- By agency ---
    print(f"\n=== EXIT RATE BY AGENCY ===")
    agency_events = defaultdict(lambda: {"high": 0, "medium": 0, "low": 0})
    for e in events:
        ctx = e.get("sbir_context")
        if ctx:
            agency_events[ctx["agency"]][e["confidence"]] += 1

    print(f"{'Agency':>45s} | {'H+M':>5s} | {'High':>5s} | {'Total cos':>9s} | {'Rate(H+M)':>9s} | {'Rate(Hi)':>8s}")
    print(f"{'-'*45}-+-{'-'*5}-+-{'-'*5}-+-{'-'*9}-+-{'-'*9}-+-{'-'*8}")
    for agency in sorted(total_by_agency, key=lambda a: -total_by_agency[a]):
        ae = agency_events[agency]
        hm = ae["high"] + ae["medium"]
        h = ae["high"]
        total = total_by_agency[agency]
        if total < 100:
            continue
        print(f"{agency:>45s} | {hm:>5,} | {h:>5,} | {total:>9,} | {hm/total*100:>7.1f}% | {h/total*100:>6.1f}%")

    # --- By year ---
    print(f"\n=== EXIT EVENTS BY YEAR (H+M) ===")
    year_counts = Counter()
    for e in events:
        if e["confidence"] not in ("high", "medium"):
            continue
        date = e.get("event_date", "")
        if len(date) >= 4:
            year_counts[date[:4]] += 1

    for y in sorted(year_counts):
        print(f"  {y}: {year_counts[y]:>5,}")

    # --- Top acquirers ---
    print(f"\n=== TOP ACQUIRERS (H+M, where identified) ===")
    acquirers = Counter()
    for e in events:
        if e["confidence"] not in ("high", "medium"):
            continue
        acq = e.get("acquirer")
        if acq:
            acquirers[acq] += 1

    for acq, ct in acquirers.most_common(20):
        print(f"  {acq:>45s}: {ct:>3,}")

    # --- Time from first SBIR to exit ---
    print(f"\n=== TIME FROM FIRST SBIR AWARD TO EXIT (H+M) ===")
    gaps = []
    for e in events:
        if e["confidence"] not in ("high", "medium"):
            continue
        ctx = e.get("sbir_context")
        date = e.get("event_date", "")
        if ctx and len(date) >= 4:
            try:
                exit_year = int(date[:4])
                gap = exit_year - ctx["first_award_year"]
                if gap >= 0:
                    gaps.append(gap)
            except ValueError:
                pass

    if gaps:
        arr = np.array(gaps)
        print(f"  N={len(arr):,}  P25={np.percentile(arr,25):.0f}yr  "
              f"P50={np.percentile(arr,50):.0f}yr  P75={np.percentile(arr,75):.0f}yr  "
              f"mean={arr.mean():.1f}yr")

    # --- Signal co-occurrence ---
    print(f"\n=== SIGNAL CO-OCCURRENCE ===")
    combos = Counter()
    for e in events:
        fired = sorted(k for k, v in e.get("signals", {}).items() if v)
        combos[" + ".join(fired)] += 1

    for combo, ct in combos.most_common(10):
        print(f"  {combo:>60s}: {ct:>5,}")


if __name__ == "__main__":
    main()
