#!/usr/bin/env python3
"""
WS1 — contract-level reclassification of the "mislabeled" dark-majority awards.

For the NO_FPDS_CODING and DATA_GAP_FPDS_NONDOD deficiency buckets (firm is in
federal data; only the FPDS Phase III flag is missing — GAO-24-106398), pull each
firm's post-award federal activity from USAspending by recipient UEI and classify
follow-on evidence per award:

  strong    ≥1 post-Phase-II *contract* whose description carries an explicit
            Phase III marker, OR a non-SBIR contract from the same funding agency
            as the Phase II (continued-customer evidence)
  moderate  post-Phase-II non-SBIR contract from a different agency, or a
            non-SBIR assistance award (grants can never exceed moderate: FABS
            descriptions cannot reliably distinguish SBIR grants)
  weak      only SBIR/STTR Phase I/II activity after the award (continued program
            participation, not transition)
  none      no post-Phase-II federal actions returned

Temporal filter: action Start Date > the award's phase_ii_end_date
(anchors from form_d_post_phase2.csv).

Path convention (same as nano_form_d_temporal.py):
  --area <id>   → data/reports/<id>/ws1_contract_evidence.csv
  (no flag)     → data/nano_ws1_contract_evidence.csv  (legacy PR #428)

Inputs:
  cohort_keyword.csv / nano_cohort_keyword.csv
  form_d_post_phase2.csv / nano_form_d_post_phase2.csv
  USAspending API (cached: data/api_cache/usaspending_ws1/)

Outputs:
  ws1_contract_evidence.csv — per-award tier + provenance

Usage:
  python scripts/data/nano_ws1_contract_evidence.py [--area AREA] [--legacy] [--refresh]
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
sys.path.insert(0, str(REPO))
from sbir_etl.utils.transition_report_paths import (  # noqa: E402
    add_area_args,
    resolve_area_paths,
)

DATA = REPO / "data"
CACHE = DATA / "api_cache/usaspending_ws1"

WS1_OUT_FIELDS = [
    "award_id",
    "company",
    "uei",
    "agency",
    "award_year",
    "phase_ii_end_date",
    "deficiency_class",
    "evidence_tier",
    "n_phase3_marker",
    "n_same_agency_contracts",
    "n_same_agency_small",
    "n_other_agency_contracts",
    "n_post_grants",
    "n_sbir_p12",
    "total_post_award_usd",
    "first_evidence_date",
    "top_evidence",
]

API = "https://api.usaspending.gov/api/v2/search/spending_by_award/"
HEADERS = {"User-Agent": "SBIR-Analytics/0.1.0"}
WS1_BUCKETS = ("NO_FPDS_CODING", "DATA_GAP_FPDS_NONDOD")
CONTRACT_CODES = ["A", "B", "C", "D"]
ASSISTANCE_CODES = ["02", "03", "04", "05"]
FIELDS = ["Award ID", "Recipient Name", "Award Amount", "Description", "Start Date",
          "Awarding Agency", "Awarding Sub Agency", "Funding Agency", "generated_internal_id"]
MAX_PAGES = 10

PHASE3_MARKER = re.compile(r"PHASE\s*(?:III|3)\b", re.IGNORECASE)
# Phase I / Phase II (but not Phase III), or explicit SBIR/STTR program language
SBIR_P12_MARKER = re.compile(
    r"\bSBIR\b|\bSTTR\b|SMALL BUSINESS (?:INNOVATION|TECHNOLOGY)|PHASE\s*II(?!I)|PHASE\s*I\b(?!I)|PHASE\s*[12]\b",
    re.IGNORECASE,
)


def fetch_awards(uei: str, type_codes: list[str], label: str, refresh: bool) -> list[dict]:
    """Fetch all prime awards for a recipient UEI, with on-disk caching."""
    cache_file = CACHE / f"{uei}_{label}.json"
    if cache_file.exists() and not refresh:
        return json.loads(cache_file.read_text())

    results: list[dict] = []
    page = 1
    while page <= MAX_PAGES:
        body = {
            "filters": {
                # USAspending award search floor is FY2008; earlier start dates 500.
                # Consequence: follow-on activity before 2008 is invisible (noted in outputs).
                "time_period": [{"start_date": "2007-10-01", "end_date": "2026-12-31"}],
                "award_type_codes": type_codes,
                "recipient_search_text": [uei],
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
            raise RuntimeError(f"USAspending returned persistent errors for {uei} {label} page {page}")
        payload = resp.json()
        batch = payload.get("results", [])
        results.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    if page > MAX_PAGES:
        print(f"  WARNING: {uei} {label} hit {MAX_PAGES}-page cap; evidence may be truncated",
              file=sys.stderr)

    CACHE.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(results))
    time.sleep(1.0)  # throttle courtesy (matches repo convention)
    return results


P12_PHASE_TEXT = re.compile(r"PHASE\s*II(?!I)|PHASE\s*I\b(?!I)|PHASE\s*[12]\b", re.IGNORECASE)
SAME_AGENCY_MIN_USD = 25_000  # de-minimis floor: $500 IDV minimum-guarantees are not evidence


def _norm_piid(piid: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (piid or "").upper())


def load_sbir_piids(awards_csv: Path) -> set[str]:
    """All SBIR.gov contract/grant numbers (normalized) — any phase, all years.

    A post-award action whose ID appears here is a *later SBIR award*, not
    Phase III evidence, even when its description omits the SBIR token
    (~70% of DoD SBIR contract descriptions do).
    """
    piids: set[str] = set()
    with open(awards_csv, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            p = _norm_piid(row.get("Contract", ""))
            if p:
                piids.add(p)
    return piids


def classify_action(action: dict, award_agency: str, is_contract: bool,
                    sbir_piids: set[str]) -> str:
    """Classify one post-Phase-II action.

    Returns: sbir_p12 | phase3 | same_agency | same_agency_small |
             other_agency | same_agency_grant | other_agency_grant
    """
    # A later SBIR/STTR award (matched by ID against SBIR.gov) is continued
    # program participation regardless of what its description says.
    if _norm_piid(action.get("Award ID", "")) in sbir_piids:
        return "sbir_p12"
    desc = action.get("Description") or ""
    # Phase I/II language wins over a Phase III *mention* (P1 abstracts often
    # describe Phase III plans); an explicit Phase III contract has no P1/P2 text.
    if P12_PHASE_TEXT.search(desc) or (SBIR_P12_MARKER.search(desc) and not PHASE3_MARKER.search(desc)):
        return "sbir_p12"
    if is_contract and PHASE3_MARKER.search(desc):
        return "phase3"
    agency = action.get("Funding Agency") or action.get("Awarding Agency") or ""
    amount = float(action.get("Award Amount") or 0)
    if agency.strip().lower() == award_agency.strip().lower():
        if not is_contract:
            return "same_agency_grant"
        return "same_agency" if amount >= SAME_AGENCY_MIN_USD else "same_agency_small"
    return "other_agency" if is_contract else "other_agency_grant"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    add_area_args(parser)
    parser.add_argument("--refresh", action="store_true", help="Ignore cached API responses")
    args = parser.parse_args(argv)
    paths = resolve_area_paths(args, argv)

    cohort_csv = paths.artifact("cohort_keyword")
    anchors_csv = paths.artifact("form_d_post_phase2")
    out_csv = paths.artifact("ws1_contract_evidence")
    for p, hint in {
        cohort_csv: f"run build_tech_area_cohort.py --area {paths.area_id} first",
        anchors_csv: "run nano_form_d_temporal.py first",
    }.items():
        if not p.exists():
            print(f"ERROR: {p} not found — {hint}", file=sys.stderr)
            return 1

    print(
        f"area={paths.area_id}{', legacy' if paths.legacy else ''}  out={out_csv}",
        file=sys.stderr,
    )

    csv.field_size_limit(sys.maxsize)
    anchors = {
        r["award_id"]: r.get("phase_ii_end_date", "")
        for r in csv.DictReader(open(anchors_csv, newline="", encoding="utf-8"))
    }

    sbir_csv = DATA / "raw/sbir/award_data.csv"
    if not sbir_csv.exists():
        print(f"ERROR: {sbir_csv} not found — needed to exclude later SBIR awards", file=sys.stderr)
        return 1
    print("Loading SBIR.gov award IDs for later-SBIR exclusion...")
    sbir_piids = load_sbir_piids(sbir_csv)
    print(f"  {len(sbir_piids):,} normalized SBIR award IDs")

    awards = [
        r
        for r in csv.DictReader(open(cohort_csv, newline="", encoding="utf-8"))
        if r.get("deficiency_class") in WS1_BUCKETS
    ]
    ueis = sorted({r["uei"] for r in awards if r.get("uei")})
    print(f"WS1 population: {len(awards)} awards, {len(ueis)} unique UEIs")

    print("Fetching USAspending activity per UEI (cached)...")
    activity: dict[str, dict[str, list[dict]]] = {}
    for i, uei in enumerate(ueis, 1):
        activity[uei] = {
            "contracts": fetch_awards(uei, CONTRACT_CODES, "contracts", args.refresh),
            "assistance": fetch_awards(uei, ASSISTANCE_CODES, "assistance", args.refresh),
        }
        if i % 25 == 0:
            print(f"  {i}/{len(ueis)} UEIs fetched")

    print("Classifying per-award evidence...")
    out_rows: list[dict] = []
    for aw in awards:
        uei = aw["uei"]
        end_date = anchors.get(aw["award_id"], "")
        acts = activity.get(uei, {"contracts": [], "assistance": []})

        counts: Counter = Counter()
        evidence: list[tuple] = []
        total_post_usd = 0.0
        for is_contract, key in ((True, "contracts"), (False, "assistance")):
            for a in acts[key]:
                start = a.get("Start Date") or ""
                if not (start and end_date and start > end_date):
                    continue
                kind = classify_action(a, aw["agency"], is_contract, sbir_piids)
                counts[kind] += 1
                total_post_usd += float(a.get("Award Amount") or 0)
                evidence.append(
                    (
                        kind,
                        start,
                        a.get("Award ID", ""),
                        (a.get("Funding Agency") or a.get("Awarding Agency") or "")[:40],
                        float(a.get("Award Amount") or 0),
                        (a.get("Description") or "")[:100],
                    )
                )

        if counts["phase3"] or counts["same_agency"]:
            tier = "strong"
        elif (
            counts["other_agency"]
            or counts["same_agency_small"]
            or counts["same_agency_grant"]
            or counts["other_agency_grant"]
        ):
            tier = "moderate"
        elif counts["sbir_p12"]:
            tier = "weak"
        else:
            tier = "none"

        strength_order = {
            "phase3": 0,
            "same_agency": 1,
            "other_agency": 2,
            "same_agency_small": 3,
            "same_agency_grant": 4,
            "other_agency_grant": 5,
            "sbir_p12": 6,
        }
        evidence.sort(key=lambda e: (strength_order[e[0]], e[1]))
        top = " || ".join(
            f"[{k}] {d} {aid} {ag} ${amt:,.0f} :: {desc}"
            for k, d, aid, ag, amt, desc in evidence[:3]
        )
        # Earliest non-SBIR evidence date (for time-to-signal survival analysis)
        non_sbir_dates = [e[1] for e in evidence if e[0] != "sbir_p12"]
        first_evidence_date = min(non_sbir_dates) if non_sbir_dates else ""

        out_rows.append(
            {
                "award_id": aw["award_id"],
                "company": aw["company"],
                "uei": uei,
                "agency": aw["agency"],
                "award_year": aw["award_year"],
                "phase_ii_end_date": end_date,
                "deficiency_class": aw["deficiency_class"],
                "evidence_tier": tier,
                "n_phase3_marker": counts["phase3"],
                "n_same_agency_contracts": counts["same_agency"],
                "n_same_agency_small": counts["same_agency_small"],
                "n_other_agency_contracts": counts["other_agency"],
                "n_post_grants": counts["same_agency_grant"] + counts["other_agency_grant"],
                "n_sbir_p12": counts["sbir_p12"],
                "total_post_award_usd": round(total_post_usd, 2),
                "first_evidence_date": first_evidence_date,
                "top_evidence": top,
            }
        )

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=WS1_OUT_FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(out_rows)
    print(f"  Written: {out_csv} ({len(out_rows)} rows)")

    print()
    print("=" * 70)
    print("WS1 CONTRACT-LEVEL EVIDENCE SUMMARY")
    print("=" * 70)
    for bucket in WS1_BUCKETS:
        sub = [r for r in out_rows if r["deficiency_class"] == bucket]
        tiers = Counter(r["evidence_tier"] for r in sub)
        print(
            f"{bucket} ({len(sub)} awards): "
            + "  ".join(f"{t}={tiers.get(t, 0)}" for t in ("strong", "moderate", "weak", "none"))
        )
    tiers_all = Counter(r["evidence_tier"] for r in out_rows)
    n = len(out_rows)
    if n:
        print(
            f"TOTAL ({n}): "
            + "  ".join(
                f"{t}={tiers_all.get(t, 0)} ({100 * tiers_all.get(t, 0) / n:.0f}%)"
                for t in ("strong", "moderate", "weak", "none")
            )
        )
    else:
        print("TOTAL (0): no WS1-bucket awards in cohort")
    return 0


if __name__ == "__main__":
    sys.exit(main())
