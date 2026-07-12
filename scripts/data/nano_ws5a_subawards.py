#!/usr/bin/env python3
"""
WS5a / T13 — subaward (FSRS) evidence for the dark firms.

Every contract check so far queried *prime* awards. But a canonical SBIR
transition is delivering technology *through* a prime — the firm becomes a
subcontractor to Lockheed or Raytheon, which is invisible in prime-award data
and looks exactly like disappearance. This queries USAspending subawards by
sub-awardee name for the dark-bucket firms.

Evidence tier (per firm, post-Phase-II subawards only):
  strong    ≥1 subaward to a defense/pharma-scale prime, or total ≥ $100K
  moderate  ≥1 post-Phase-II subaward below that
  none      no post-Phase-II subaward

Known limits (stated in outputs): FSRS reporting threshold (~$30K) and
documented under-reporting; subaward coverage begins ~FY2011; sub-awardee names
are prime-entered and dirtier than recipient names, so exact-normalized matching
is conservative (precision over recall).

Inputs:
  data/nano_dark_firm_liveness.csv        — dark firms + first award year
  data/nano_form_d_post_phase2.csv         — phase_ii_end_date anchors (per award→firm)
  USAspending subaward API (cached: data/api_cache/usaspending_ws5a/)

Outputs:
  data/nano_ws5a_subawards.csv             — per-firm subaward evidence

Usage:
  python scripts/data/nano_ws5a_subawards.py [--refresh]
"""

import argparse
import csv
import json
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import requests

REPO = Path(__file__).resolve().parents[2]
DATA = REPO / "data"
CACHE = DATA / "api_cache/usaspending_ws5a"

sys.path.insert(0, str(REPO))
from sbir_etl.utils.text_normalization import normalize_name  # noqa: E402

API = "https://api.usaspending.gov/api/v2/search/spending_by_award/"
HEADERS = {"User-Agent": "SBIR-Analytics/0.1.0"}
FIELDS = ["Sub-Awardee Name", "Sub-Award Amount", "Sub-Award Date",
          "Prime Recipient Name", "Prime Award ID", "Sub-Award Description", "Awarding Agency"]
STRONG_USD = 100_000
MAX_PAGES = 5


def _norm(s: str) -> str:
    return normalize_name(s, remove_suffixes=True)


def fetch_subawards(name: str, refresh: bool) -> list[dict]:
    slug = re.sub(r"[^A-Z0-9]+", "_", name.upper())[:80]
    cache_file = CACHE / f"{slug}.json"
    if cache_file.exists() and not refresh:
        return json.loads(cache_file.read_text())

    results: list[dict] = []
    page = 1
    while page <= MAX_PAGES:
        body = {
            "filters": {
                "time_period": [{"start_date": "2010-10-01", "end_date": "2026-12-31"}],
                "award_type_codes": ["A", "B", "C", "D"],
                "recipient_search_text": [name[:100]],
            },
            "fields": FIELDS,
            "subawards": True,
            "page": page,
            "limit": 100,
            "sort": "Sub-Award Amount",
            "order": "desc",
        }
        resp = None
        for attempt in range(4):
            try:
                r = requests.post(API, json=body, headers=HEADERS, timeout=60)
                if r.status_code in (429, 500, 502, 503, 504):
                    time.sleep(2 ** (attempt + 1))
                    continue
                r.raise_for_status()
                resp = r
                break
            except requests.RequestException:
                if attempt == 3:
                    raise
                time.sleep(2 ** (attempt + 1))
        if resp is None:
            raise RuntimeError(f"USAspending subaward errors for '{name}' page {page}")
        batch = resp.json().get("results", [])
        results.extend(batch)
        if len(batch) < 100:
            break
        page += 1

    CACHE.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(results))
    time.sleep(1.0)
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()

    liveness_csv = DATA / "nano_dark_firm_liveness.csv"
    anchors_csv = DATA / "nano_form_d_post_phase2.csv"
    for p, hint in {liveness_csv: "run nano_dark_firm_liveness.py first",
                    anchors_csv: "run nano_form_d_temporal.py first"}.items():
        if not p.exists():
            print(f"ERROR: {p} not found — {hint}", file=sys.stderr)
            return 1

    csv.field_size_limit(sys.maxsize)
    # Per-firm Phase II end anchor: earliest end date across the firm's awards.
    firm_end: dict[str, str] = {}
    for r in csv.DictReader(open(anchors_csv, newline="", encoding="utf-8")):
        f = _norm(r["company"])
        end = r.get("phase_ii_end_date", "")
        if f and end and (f not in firm_end or end < firm_end[f]):
            firm_end[f] = end

    firms = {r["normalized_name"]: r for r in csv.DictReader(open(liveness_csv, newline="", encoding="utf-8"))}
    print(f"Dark firms: {len(firms):,}")

    out_rows = []
    for i, (norm, rec) in enumerate(sorted(firms.items()), 1):
        end_date = firm_end.get(norm, "")
        subs = fetch_subawards(rec["company"], args.refresh)
        # Exact normalized match + post-Phase-II temporal filter.
        matched = []
        for s in subs:
            if _norm(s.get("Sub-Awardee Name") or "") != norm:
                continue
            d = s.get("Sub-Award Date") or ""
            if end_date and d and d > end_date:
                matched.append(s)
        total = sum(float(s.get("Sub-Award Amount") or 0) for s in matched)
        primes = {(s.get("Prime Recipient Name") or "") for s in matched}
        if not matched:
            tier = "none"
        elif total >= STRONG_USD:
            tier = "strong"
        else:
            tier = "moderate"
        top = sorted(matched, key=lambda s: -float(s.get("Sub-Award Amount") or 0))[:3]
        out_rows.append({
            "firm_normalized": norm,
            "company": rec["company"],
            "bucket": rec["bucket"],
            "phase_ii_end": end_date,
            "subaward_tier": tier,
            "n_post_subawards": len(matched),
            "total_sub_usd": round(total, 2),
            "n_primes": len(primes),
            "top_primes": " | ".join(sorted(p for p in primes if p)[:3]),
            "top_subawards": " || ".join(
                f"{s.get('Sub-Award Date') or ''} {(s.get('Prime Recipient Name') or '')[:30]} "
                f"${float(s.get('Sub-Award Amount') or 0):,.0f}" for s in top),
        })
        if i % 100 == 0:
            print(f"  {i}/{len(firms)}")

    out_csv = DATA / "nano_ws5a_subawards.csv"
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(out_rows[0].keys()))
        w.writeheader()
        w.writerows(out_rows)
    print(f"  Written: {out_csv} ({len(out_rows)} firms)")

    print()
    print("=" * 70)
    print("WS5a SUBAWARD SUMMARY (FSRS; ~FY2011+, ~$30K threshold)")
    print("=" * 70)
    for bucket in ("FIRM_ACTIVITY_ABSENT", "ENTITY_RESOLUTION_FAILURE"):
        sub = [r for r in out_rows if r["bucket"] == bucket]
        n = len(sub)
        t = Counter(r["subaward_tier"] for r in sub)
        recov = sum(1 for r in sub if r["subaward_tier"] in ("strong", "moderate"))
        print(f"{bucket}: {n} firms — strong={t['strong']} moderate={t['moderate']} "
              f"({100*recov/n:.0f}% show a post-award subaward)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
