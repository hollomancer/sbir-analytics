#!/usr/bin/env python3
"""
WS2 — retroactive identity resolution for no-UEI dark-majority awards.

The ENTITY_RESOLUTION_FAILURE bucket (SBIR.gov record carries no UEI) cannot be
joined to federal systems by identifier — but USAspending's award search accepts
recipient *names*. For each no-UEI firm:

  1. Search USAspending prime awards by firm name (contracts + assistance).
  2. Keep candidate recipients whose normalized name exactly equals the firm's
     normalized name; collect their UEIs.
  3. Confidence: high = exactly one candidate UEI; medium = 2-3 UEIs (name
     variants / registration churn are common); low = >3 UEIs (ambiguous).
  4. For resolved firms, classify post-award evidence per award with the WS1
     tier logic (temporal filter on Phase II end, later-SBIR exclusion by ID
     join, Phase I/II text precedence, $25K same-agency floor).

Inputs:
  data/nano_cohort_keyword.csv          — ENTITY_RESOLUTION_FAILURE awards
  data/nano_form_d_post_phase2.csv      — phase_ii_end_date anchors
  data/raw/sbir/award_data.csv          — later-SBIR ID exclusion
  USAspending API (cached: data/api_cache/usaspending_ws2/)

Outputs:
  data/nano_no_uei_resolution.csv       — per-firm candidate UEIs + confidence
  data/nano_ws2_contract_evidence.csv   — per-award evidence tiers (resolved firms)

Usage:
  python scripts/data/nano_ws2_resolve_no_uei.py [--refresh]
"""

import argparse
import csv
import importlib.util
import json
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import requests

REPO = Path(__file__).resolve().parents[2]
DATA = REPO / "data"
CACHE = DATA / "api_cache/usaspending_ws2"

sys.path.insert(0, str(REPO))
from sbir_etl.utils.text_normalization import normalize_name  # noqa: E402

_ws1_spec = importlib.util.spec_from_file_location(
    "nano_ws1", Path(__file__).parent / "nano_ws1_contract_evidence.py"
)
ws1 = importlib.util.module_from_spec(_ws1_spec)
_ws1_spec.loader.exec_module(ws1)

API = "https://api.usaspending.gov/api/v2/search/spending_by_award/"
HEADERS = {"User-Agent": "SBIR-Analytics/0.1.0"}
FIELDS = ["Award ID", "Recipient Name", "Recipient UEI", "Award Amount", "Description",
          "Start Date", "Awarding Agency", "Funding Agency", "generated_internal_id"]
MAX_PAGES = 6


def fetch_by_name(name: str, type_codes: list[str], label: str, refresh: bool) -> list[dict]:
    """Search prime awards by recipient name text, cached on normalized name."""
    slug = re.sub(r"[^A-Z0-9]+", "_", name.upper())[:80]
    cache_file = CACHE / f"{slug}_{label}.json"
    if cache_file.exists() and not refresh:
        return json.loads(cache_file.read_text())

    results: list[dict] = []
    page = 1
    while page <= MAX_PAGES:
        body = {
            "filters": {
                "time_period": [{"start_date": "2007-10-01", "end_date": "2026-12-31"}],
                "award_type_codes": type_codes,
                "recipient_search_text": [name[:100]],
            },
            "fields": FIELDS,
            "page": page,
            "limit": 100,
            "sort": "Start Date",
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
            raise RuntimeError(f"USAspending persistent errors for '{name}' {label} page {page}")
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

    cohort_csv = DATA / "nano_cohort_keyword.csv"
    anchors_csv = DATA / "nano_form_d_post_phase2.csv"
    sbir_csv = DATA / "raw/sbir/award_data.csv"
    for p, hint in {cohort_csv: "run build_nano_cohort.py first",
                    anchors_csv: "run nano_form_d_temporal.py first",
                    sbir_csv: "SBIR.gov bulk CSV expected"}.items():
        if not p.exists():
            print(f"ERROR: {p} not found — {hint}", file=sys.stderr)
            return 1

    csv.field_size_limit(sys.maxsize)
    anchors = {r["award_id"]: r.get("phase_ii_end_date", "")
               for r in csv.DictReader(open(anchors_csv, newline="", encoding="utf-8"))}
    awards = [r for r in csv.DictReader(open(cohort_csv, newline="", encoding="utf-8"))
              if r.get("deficiency_class") == "ENTITY_RESOLUTION_FAILURE"]
    firms: dict[str, dict] = {}
    for r in awards:
        norm = normalize_name(r["company"], remove_suffixes=True)
        firms.setdefault(norm, {"company": r["company"], "awards": []})["awards"].append(r)
    print(f"WS2 population: {len(awards)} awards, {len(firms)} unique no-UEI firms")

    print("Loading SBIR.gov award IDs for later-SBIR exclusion...")
    sbir_piids = ws1.load_sbir_piids(sbir_csv)
    print(f"  {len(sbir_piids):,} normalized SBIR award IDs")

    print("Searching USAspending by firm name (cached)...")
    resolution_rows: list[dict] = []
    firm_activity: dict[str, list[tuple[bool, dict]]] = {}
    for i, (norm, rec) in enumerate(sorted(firms.items()), 1):
        contracts = fetch_by_name(rec["company"], ["A", "B", "C", "D"], "contracts", args.refresh)
        grants = fetch_by_name(rec["company"], ["02", "03", "04", "05"], "assistance", args.refresh)

        # Candidates: exact normalized-name equality with the SBIR firm
        cand_ueis: Counter = Counter()
        cand_names: set[str] = set()
        matched_actions: list[tuple[bool, dict]] = []
        for is_contract, batch in ((True, contracts), (False, grants)):
            for a in batch:
                rname = a.get("Recipient Name") or ""
                if normalize_name(rname, remove_suffixes=True) != norm:
                    continue
                uei = (a.get("Recipient UEI") or "").strip()
                if uei:
                    cand_ueis[uei] += 1
                cand_names.add(rname)
                matched_actions.append((is_contract, a))

        n_ueis = len(cand_ueis)
        if n_ueis == 1:
            confidence = "high"
        elif 2 <= n_ueis <= 3:
            confidence = "medium"
        elif n_ueis > 3:
            confidence = "low"
        else:
            confidence = "unresolved"
        if confidence in ("high", "medium"):
            firm_activity[norm] = matched_actions

        resolution_rows.append({
            "company": rec["company"],
            "normalized_name": norm,
            "awards_n": len(rec["awards"]),
            "candidate_ueis": "|".join(u for u, _ in cand_ueis.most_common()),
            "candidate_uei_count": n_ueis,
            "matched_recipient_names": "|".join(sorted(cand_names)[:3]),
            "matched_actions_n": len(matched_actions),
            "resolution_confidence": confidence,
        })
        if i % 50 == 0:
            print(f"  {i}/{len(firms)} firms searched")

    res_csv = DATA / "nano_no_uei_resolution.csv"
    with open(res_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(resolution_rows[0].keys()))
        w.writeheader()
        w.writerows(resolution_rows)
    print(f"  Written: {res_csv} ({len(resolution_rows)} firms)")

    print("Classifying per-award evidence for resolved firms...")
    out_rows: list[dict] = []
    for norm, rec in sorted(firms.items()):
        actions = firm_activity.get(norm)
        for aw in rec["awards"]:
            end_date = anchors.get(aw["award_id"], "")
            if actions is None:
                tier, counts, evidence = "unresolved", Counter(), []
            else:
                counts = Counter()
                evidence = []
                for is_contract, a in actions:
                    start = a.get("Start Date") or ""
                    if not (start and end_date and start > end_date):
                        continue
                    kind = ws1.classify_action(a, aw["agency"], is_contract, sbir_piids)
                    counts[kind] += 1
                    evidence.append((kind, start, a.get("Award ID", ""),
                                     (a.get("Funding Agency") or a.get("Awarding Agency") or "")[:40],
                                     float(a.get("Award Amount") or 0),
                                     (a.get("Description") or "")[:100]))
                if counts["phase3"] or counts["same_agency"]:
                    tier = "strong"
                elif (counts["other_agency"] or counts["same_agency_small"]
                      or counts["same_agency_grant"] or counts["other_agency_grant"]):
                    tier = "moderate"
                elif counts["sbir_p12"]:
                    tier = "weak"
                else:
                    tier = "none"
            order = {"phase3": 0, "same_agency": 1, "other_agency": 2, "same_agency_small": 3,
                     "same_agency_grant": 4, "other_agency_grant": 5, "sbir_p12": 6}
            evidence.sort(key=lambda e: (order[e[0]], e[1]))
            out_rows.append({
                "award_id": aw["award_id"],
                "company": aw["company"],
                "agency": aw["agency"],
                "award_year": aw["award_year"],
                "phase_ii_end_date": end_date,
                "resolution_confidence": next(
                    r["resolution_confidence"] for r in resolution_rows
                    if r["normalized_name"] == norm),
                "evidence_tier": tier,
                "n_phase3_marker": counts["phase3"],
                "n_same_agency_contracts": counts["same_agency"],
                "top_evidence": " || ".join(
                    f"[{k}] {d} {aid} {ag} ${amt:,.0f} :: {desc}"
                    for k, d, aid, ag, amt, desc in evidence[:3]),
            })

    out_csv = DATA / "nano_ws2_contract_evidence.csv"
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(out_rows[0].keys()))
        w.writeheader()
        w.writerows(out_rows)
    print(f"  Written: {out_csv} ({len(out_rows)} rows)")

    print()
    print("=" * 70)
    print("WS2 IDENTITY RESOLUTION SUMMARY")
    print("=" * 70)
    conf = Counter(r["resolution_confidence"] for r in resolution_rows)
    n = len(resolution_rows)
    print("Firm resolution: " + "  ".join(
        f"{c}={conf.get(c, 0)} ({100*conf.get(c, 0)/n:.0f}%)"
        for c in ("high", "medium", "low", "unresolved")))
    resolved_awards = [r for r in out_rows if r["resolution_confidence"] in ("high", "medium")]
    tiers = Counter(r["evidence_tier"] for r in resolved_awards)
    m = len(resolved_awards)
    if m:
        print(f"Evidence for {m} awards of resolved firms: " + "  ".join(
            f"{t}={tiers.get(t, 0)} ({100*tiers.get(t, 0)/m:.0f}%)"
            for t in ("strong", "moderate", "weak", "none")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
