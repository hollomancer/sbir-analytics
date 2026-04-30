# SBIR M&A Exit Detection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Detect which SBIR companies were acquired, measure exit rates by agency/year, and produce a curated M&A events dataset + analysis report.

**Architecture:** Two-layer signal extraction — Form D business combinations (Layer 1, high confidence) then EFTS mention classification (Layer 2, variable confidence) — merged into a unified events dataset with confidence tiers. Two scripts: detection then analysis.

**Tech Stack:** Python 3.11, json, csv, pytest. No new dependencies.

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `scripts/data/detect_sbir_ma_events.py` | Create | Extract M&A signals from Form D + EFTS, merge, deduplicate, output events JSONL |
| `scripts/data/analyze_sbir_ma_exits.py` | Create | Read events JSONL, compute exit rates, produce analysis report |
| `tests/unit/scripts/test_detect_ma_events.py` | Create | Unit tests for signal extraction, tier assignment, deduplication |
| `data/sbir_ma_events.jsonl` | Output | M&A events dataset |
| `docs/research/sbir-ma-exit-analysis.md` | Output | Analysis report |

---

### Task 1: Form D business combination extraction

**Files:**
- Create: `tests/unit/scripts/test_detect_ma_events.py`
- Create: `scripts/data/detect_sbir_ma_events.py`

- [ ] **Step 1: Write failing test for Form D signal extraction**

```python
"""Tests for M&A event detection."""

import pytest

from detect_sbir_ma_events import extract_form_d_signals


def test_extract_form_d_signals_finds_business_combination():
    records = [
        {
            "company_name": "ACME INC",
            "match_confidence": {"tier": "high"},
            "offerings": [
                {
                    "filing_date": "2019-03-15",
                    "is_business_combination": True,
                    "total_amount_sold": 25_000_000,
                    "related_persons": [
                        {"name": "Jane Doe", "title": "Executive Officer"}
                    ],
                },
                {
                    "filing_date": "2020-01-01",
                    "is_business_combination": False,
                    "total_amount_sold": 5_000_000,
                    "related_persons": [],
                },
            ],
        }
    ]
    events = extract_form_d_signals(records)
    assert len(events) == 1
    e = events[0]
    assert e["company_name"] == "ACME INC"
    assert e["event_date"] == "2019-03-15"
    assert e["form_d_detail"]["total_amount_sold"] == 25_000_000
    assert e["form_d_detail"]["related_persons"][0]["name"] == "Jane Doe"


def test_extract_form_d_signals_skips_non_combo():
    records = [
        {
            "company_name": "BORING INC",
            "match_confidence": {"tier": "medium"},
            "offerings": [
                {
                    "filing_date": "2020-06-01",
                    "is_business_combination": False,
                    "total_amount_sold": 1_000_000,
                    "related_persons": [],
                }
            ],
        }
    ]
    events = extract_form_d_signals(records)
    assert len(events) == 0


def test_extract_form_d_signals_uses_earliest_combo_date():
    records = [
        {
            "company_name": "MULTI INC",
            "match_confidence": {"tier": "high"},
            "offerings": [
                {
                    "filing_date": "2021-06-01",
                    "is_business_combination": True,
                    "total_amount_sold": 10_000_000,
                    "related_persons": [{"name": "A", "title": "Director"}],
                },
                {
                    "filing_date": "2020-01-15",
                    "is_business_combination": True,
                    "total_amount_sold": 5_000_000,
                    "related_persons": [{"name": "B", "title": "Director"}],
                },
            ],
        }
    ]
    events = extract_form_d_signals(records)
    assert len(events) == 1
    assert events[0]["event_date"] == "2020-01-15"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/hollomancer/projects/sbir-analytics && .venv/bin/python3 -m pytest tests/unit/scripts/test_detect_ma_events.py -v`
Expected: FAIL — `ModuleNotFoundError` or `ImportError`

- [ ] **Step 3: Implement Form D signal extraction**

Create `scripts/data/detect_sbir_ma_events.py`:

```python
#!/usr/bin/env python3
"""Detect M&A exit events for SBIR companies.

Extracts signals from Form D business combinations and EFTS mention
classifications, merges into a unified events dataset with confidence tiers.

Usage:
    python scripts/data/detect_sbir_ma_events.py
    python scripts/data/detect_sbir_ma_events.py --form-d data/form_d_details.jsonl
"""

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def extract_form_d_signals(records: list[dict]) -> list[dict]:
    """Extract M&A events from Form D business combination flags.

    For each company with at least one is_business_combination offering,
    produces one event using the earliest combo filing date.
    """
    events = []
    for r in records:
        combos = [
            o for o in r.get("offerings", [])
            if o.get("is_business_combination")
        ]
        if not combos:
            continue

        combos.sort(key=lambda o: str(o.get("filing_date", "")))
        earliest = combos[0]

        # Aggregate deal size across all combo offerings
        total_sold = sum(o.get("total_amount_sold") or 0 for o in combos)

        # Collect all related persons from combo offerings
        all_persons = []
        for o in combos:
            all_persons.extend(o.get("related_persons", []))

        events.append({
            "company_name": r["company_name"],
            "event_date": str(earliest.get("filing_date", ""))[:10],
            "source": "form_d",
            "form_d_detail": {
                "filing_date": str(earliest.get("filing_date", ""))[:10],
                "total_amount_sold": total_sold if total_sold > 0 else None,
                "combo_count": len(combos),
                "related_persons": all_persons,
            },
        })

    return events


def extract_efts_signals(records: list[dict]) -> list[dict]:
    """Extract M&A events from EFTS mention classifications.

    Maps mention types to confidence levels and extracts acquirer
    candidates from mention_filers.
    """
    MA_TYPES = {
        "subsidiary": "high",
        "acquisition": "medium",
        "ma_definitive": "medium",
        "ma_proxy": "low",
        "ownership_active": "low",
    }

    events = []
    for r in records:
        types = r.get("mention_types", [])
        ma_hits = {t: MA_TYPES[t] for t in types if t in MA_TYPES}
        if not ma_hits:
            continue

        # Best confidence from any signal
        tier_order = {"high": 0, "medium": 1, "low": 2}
        best_tier = min(ma_hits.values(), key=lambda t: tier_order[t])

        events.append({
            "company_name": r["company_name"],
            "event_date": r.get("latest_mention_date", ""),
            "source": "efts",
            "efts_detail": {
                "mention_filers": r.get("mention_filers", []),
                "mention_types": sorted(ma_hits.keys()),
                "latest_mention_date": r.get("latest_mention_date", ""),
                "efts_tier": best_tier,
            },
        })

    return events


def merge_events(
    form_d_events: list[dict],
    efts_events: list[dict],
) -> list[dict]:
    """Merge Form D and EFTS events by company name.

    When both sources have an event for the same company, combine into
    one record. Uses earliest date across sources.
    """
    # Index by company name
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
        if name in merged:
            # Both signals — keep earliest date
            existing = merged[name]
            if e["event_date"] and e["event_date"] < existing["event_date"]:
                existing["event_date"] = e["event_date"]
            existing["efts_detail"] = e["efts_detail"]
        else:
            merged[name] = {
                "company_name": name,
                "event_date": e["event_date"],
                "form_d_detail": None,
                "efts_detail": e["efts_detail"],
            }

    return list(merged.values())


def assign_confidence(event: dict) -> str:
    """Assign confidence tier based on which signals fired."""
    has_form_d = event.get("form_d_detail") is not None
    efts = event.get("efts_detail")
    has_efts_high = (
        efts is not None and "subsidiary" in efts.get("mention_types", [])
    )
    has_efts_medium = efts is not None and (
        "ma_definitive" in efts.get("mention_types", [])
        or "acquisition" in efts.get("mention_types", [])
    )

    if has_form_d or has_efts_high:
        return "high"
    elif has_efts_medium:
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
    # EFTS mention_filers is the best source — the filer is the acquirer
    efts = event.get("efts_detail")
    if efts and efts.get("mention_filers"):
        return efts["mention_filers"][0]
    return None


def load_sbir_context(awards_csv: str) -> dict[str, dict]:
    """Load SBIR award context per company."""
    companies: dict[str, dict] = {}
    with open(awards_csv, encoding="utf-8", errors="replace") as f:
        for row in csv.DictReader(f):
            name = row.get("Company", "").strip()
            agency = row.get("Agency", "").strip()
            year_str = row.get("Award Year", "").strip()
            amt_str = row.get("Award Amount", "").strip()
            if not name or not year_str:
                continue
            try:
                year = int(year_str)
                amt = float(amt_str) if amt_str else 0
            except ValueError:
                continue

            if name not in companies:
                companies[name] = {
                    "agency": agency,
                    "total_awards": 0,
                    "total_award_amount": 0,
                    "first_award_year": year,
                    "last_award_year": year,
                }
            c = companies[name]
            c["total_awards"] += 1
            c["total_award_amount"] += amt
            if year < c["first_award_year"]:
                c["first_award_year"] = year
            if year > c["last_award_year"]:
                c["last_award_year"] = year
            # Use most common agency (approximation: last seen)
            c["agency"] = agency

    return companies


def main():
    parser = argparse.ArgumentParser(description="Detect SBIR M&A exit events")
    parser.add_argument("--form-d", default="data/form_d_details.jsonl")
    parser.add_argument("--efts", default="data/sec_edgar_scan.jsonl")
    parser.add_argument("--awards", default="/tmp/sbir_awards_full.csv")
    parser.add_argument("--output", default="data/sbir_ma_events.jsonl")
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

    tiers = {"high": 0, "medium": 0, "low": 0}
    with open(output_path, "w") as out:
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
                "sbir_context": sbir_context.get(event["company_name"]),
            }
            out.write(json.dumps(record, default=str) + "\n")
            tiers[confidence] += 1

    total = sum(tiers.values())
    print(f"\n{'='*60}")
    print(f"M&A EXIT DETECTION COMPLETE — {total:,} events")
    print(f"{'='*60}")
    print(f"  High confidence:   {tiers['high']:,}")
    print(f"  Medium confidence: {tiers['medium']:,}")
    print(f"  Low confidence:    {tiers['low']:,}")
    print(f"  Output: {output_path}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Fix test imports and run tests**

The test needs `sys.path` to import from `scripts/data/`. Update the test file header:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts" / "data"))
```

Run: `.venv/bin/python3 -m pytest tests/unit/scripts/test_detect_ma_events.py -v`
Expected: 3 PASSED

- [ ] **Step 5: Commit**

```bash
git add scripts/data/detect_sbir_ma_events.py tests/unit/scripts/test_detect_ma_events.py
git commit -m "feat(ma): add M&A event detection from Form D + EFTS signals"
```

---

### Task 2: EFTS signal extraction and merge tests

**Files:**
- Modify: `tests/unit/scripts/test_detect_ma_events.py`

- [ ] **Step 1: Write failing tests for EFTS extraction and merge**

Add to `test_detect_ma_events.py`:

```python
from detect_sbir_ma_events import (
    extract_efts_signals,
    merge_events,
    assign_confidence,
    build_signals_dict,
)


def test_extract_efts_signals_subsidiary():
    records = [
        {
            "company_name": "TARGET INC",
            "mention_types": ["subsidiary", "filing_mention"],
            "mention_filers": ["BIG CORP"],
            "latest_mention_date": "2020-06-15",
        }
    ]
    events = extract_efts_signals(records)
    assert len(events) == 1
    assert events[0]["efts_detail"]["efts_tier"] == "high"
    assert events[0]["efts_detail"]["mention_filers"] == ["BIG CORP"]


def test_extract_efts_signals_skips_passive():
    records = [
        {
            "company_name": "PASSIVE INC",
            "mention_types": ["ownership_passive"],
            "mention_filers": ["FUND LP"],
            "latest_mention_date": "2021-01-01",
        }
    ]
    events = extract_efts_signals(records)
    assert len(events) == 0


def test_extract_efts_signals_no_ma_types():
    records = [
        {
            "company_name": "BORING INC",
            "mention_types": ["filing_mention", "disclosure"],
            "mention_filers": ["SOMEONE"],
            "latest_mention_date": "2020-01-01",
        }
    ]
    events = extract_efts_signals(records)
    assert len(events) == 0


def test_merge_events_both_sources():
    fd = [{"company_name": "ACME", "event_date": "2020-03-01", "source": "form_d",
           "form_d_detail": {"filing_date": "2020-03-01", "total_amount_sold": 1e6,
                             "combo_count": 1, "related_persons": []}}]
    efts = [{"company_name": "ACME", "event_date": "2020-01-15", "source": "efts",
             "efts_detail": {"mention_filers": ["BIG CO"], "mention_types": ["ma_definitive"],
                             "latest_mention_date": "2020-01-15", "efts_tier": "medium"}}]
    merged = merge_events(fd, efts)
    assert len(merged) == 1
    assert merged[0]["form_d_detail"] is not None
    assert merged[0]["efts_detail"] is not None
    # Should use earliest date
    assert merged[0]["event_date"] == "2020-01-15"


def test_merge_events_separate_companies():
    fd = [{"company_name": "A", "event_date": "2020-01-01", "source": "form_d",
           "form_d_detail": {"filing_date": "2020-01-01", "total_amount_sold": None,
                             "combo_count": 1, "related_persons": []}}]
    efts = [{"company_name": "B", "event_date": "2021-06-01", "source": "efts",
             "efts_detail": {"mention_filers": ["X"], "mention_types": ["subsidiary"],
                             "latest_mention_date": "2021-06-01", "efts_tier": "high"}}]
    merged = merge_events(fd, efts)
    assert len(merged) == 2


def test_assign_confidence_form_d_is_high():
    event = {"form_d_detail": {"filing_date": "2020-01-01"}, "efts_detail": None}
    assert assign_confidence(event) == "high"


def test_assign_confidence_subsidiary_is_high():
    event = {"form_d_detail": None,
             "efts_detail": {"mention_types": ["subsidiary", "ma_definitive"]}}
    assert assign_confidence(event) == "high"


def test_assign_confidence_ma_definitive_only_is_medium():
    event = {"form_d_detail": None,
             "efts_detail": {"mention_types": ["ma_definitive"]}}
    assert assign_confidence(event) == "medium"


def test_assign_confidence_ownership_only_is_low():
    event = {"form_d_detail": None,
             "efts_detail": {"mention_types": ["ownership_active"]}}
    assert assign_confidence(event) == "low"


def test_build_signals_dict():
    event = {
        "form_d_detail": {"filing_date": "2020-01-01"},
        "efts_detail": {"mention_types": ["subsidiary", "ma_definitive"]},
    }
    signals = build_signals_dict(event)
    assert signals["form_d_business_combination"] is True
    assert signals["efts_subsidiary"] is True
    assert signals["efts_ma_definitive"] is True
    assert signals["efts_acquisition_text"] is False
```

- [ ] **Step 2: Run all tests**

Run: `.venv/bin/python3 -m pytest tests/unit/scripts/test_detect_ma_events.py -v`
Expected: All PASSED (3 from Task 1 + 10 new = 13 total)

- [ ] **Step 3: Commit**

```bash
git add tests/unit/scripts/test_detect_ma_events.py
git commit -m "test(ma): add EFTS extraction, merge, and confidence tests"
```

---

### Task 3: Run detection on real data

**Files:**
- Run: `scripts/data/detect_sbir_ma_events.py`
- Output: `data/sbir_ma_events.jsonl`

- [ ] **Step 1: Run detection script**

```bash
.venv/bin/python3 scripts/data/detect_sbir_ma_events.py \
    --form-d data/form_d_details.jsonl \
    --efts data/sec_edgar_scan.jsonl \
    --awards /tmp/sbir_awards_full.csv
```

Expected output: event counts by tier, output file path.

- [ ] **Step 2: Validate output**

```bash
wc -l data/sbir_ma_events.jsonl
head -1 data/sbir_ma_events.jsonl | python3 -m json.tool
```

Verify: record count matches stdout summary, schema matches spec.

- [ ] **Step 3: Commit**

```bash
git add scripts/data/detect_sbir_ma_events.py
git commit -m "feat(ma): run M&A detection on full dataset"
```

---

### Task 4: Analysis script and report

**Files:**
- Create: `scripts/data/analyze_sbir_ma_exits.py`
- Output: `docs/research/sbir-ma-exit-analysis.md`

- [ ] **Step 1: Create analysis script**

```python
#!/usr/bin/env python3
"""Analyze SBIR M&A exit events.

Reads sbir_ma_events.jsonl and produces exit rate analysis by agency,
year, confidence tier, and funding amount.

Usage:
    python scripts/data/analyze_sbir_ma_exits.py
"""

import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

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
    total_sbir = sum(total_by_agency.values())

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
```

- [ ] **Step 2: Run analysis**

```bash
.venv/bin/python3 scripts/data/analyze_sbir_ma_exits.py
```

- [ ] **Step 3: Write findings to analysis report**

Create `docs/research/sbir-ma-exit-analysis.md` from the script output. Include methodology, tables, and caveats.

- [ ] **Step 4: Commit**

```bash
git add scripts/data/analyze_sbir_ma_exits.py docs/research/sbir-ma-exit-analysis.md
git commit -m "feat(ma): add exit analysis script and report"
```

---

### Task 5: Update old spec and final cleanup

**Files:**
- Modify: `specs/merger_acquisition_detection/requirements.md`
- Modify: `specs/merger_acquisition_detection/design.md`
- Modify: `specs/merger_acquisition_detection/tasks.md`

- [ ] **Step 1: Replace old spec files**

`requirements.md`:
```markdown
# Requirements

Replaced by design spec at
`docs/superpowers/specs/2026-04-23-sbir-ma-exit-detection-design.md`.

See also: research question A4 in `docs/research-questions.md`.
```

`design.md`:
```markdown
# Design

Replaced by design spec at
`docs/superpowers/specs/2026-04-23-sbir-ma-exit-detection-design.md`.
```

`tasks.md`:
```markdown
# Implementation

Replaced by implementation plan at
`docs/superpowers/plans/2026-04-23-sbir-ma-exit-detection.md`.
```

- [ ] **Step 2: Run all tests**

```bash
.venv/bin/python3 -m pytest tests/unit/scripts/test_detect_ma_events.py tests/unit/enrichers/test_form_d_scoring.py -v
```

Expected: All pass.

- [ ] **Step 3: Commit and push**

```bash
git add specs/merger_acquisition_detection/
git commit -m "docs(ma): replace old spec skeleton with new design + plan pointers"
git push origin claude/sbir-ma-exit-analysis
```
