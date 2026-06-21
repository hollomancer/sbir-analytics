#!/usr/bin/env python3
"""FPDS substitution test — PR #342 deferred item #1.

Tests the "DoD commercializes via federal contracts rather than VC"
hypothesis from the bootstrap doc by pulling USAspending federal-contract
activity for the DoD high-tier Form D matched cohort and computing the
per-Branch follow-on-FPDS leverage ratio. Compares against the per-Branch
Form D leverage ratios from PR #342 / PR #343.

**Hypothesis under test:** If DoD firms commercialize via federal
contracts not VC, then low-Form-D branches (Navy, MDA) should have
substantially HIGHER follow-on-FPDS-per-SBIR-dollar than high-Form-D
branches (Air Force).

**Method:**

1. Identify cohort: DoD high-tier Form D matched firms (re-derived from
   ``form_d_details.jsonl`` + ``award_data.csv``, matching the
   methodology of the bootstrap and DoD-decomposition scripts).
2. For each firm, query the USAspending public API
   (``/api/v2/search/spending_by_award/``) for all federal contracts
   (PIID-type, award_type_codes A/B/C/D) with the firm name as
   ``recipient_search_text`` and the 2009-2024 year window.
3. Aggregate per-firm total federal-contract dollars. Cache results to
   a local JSONL (re-runs are fast).
4. Compute per-Branch follow-on-FPDS leverage:
   sum(firm federal-contract $) / DoD-Branch program SBIR $.
5. Compare directly against the per-Branch Form D leverage from PR #342.

**Substitution signal:** A branch where follow-on-FPDS leverage is
substantially HIGHER than Form D leverage (and where Form D is also
low) supports the substitution hypothesis.

**Caveats:**

- Recipient-name matching is fuzzy. False positives possible (similar
  company names) but for the substitution-signal magnitude question
  the noise is bounded.
- USAspending data quality degrades for pre-2015 contracts (less
  complete coverage). Branch-level ratios should be interpreted with
  this in mind.
- "Federal contract $" here INCLUDES SBIR contracts (which already
  appear in SBIR.gov data). The denominator is DoD-Branch program SBIR
  $, so the per-Branch ratio counts the firm's full federal-contract
  surface relative to their SBIR allocation. A more rigorous version
  would subtract SBIR contracts from the numerator — flagged as
  future work.

Inputs:
  data/form_d_details.jsonl              (Form D matches with tier)
  data/raw/sbir/award_data.csv           (SBIR.gov bulk awards)
  USAspending public API (no auth)

Outputs:
  data/processed/fpds_substitution/firm_contracts.jsonl  (cached per-firm USAspending pull)
  reports/ml/dod_fpds_substitution_test.json
  reports/ml/dod_fpds_substitution_test.md
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import httpx


YEAR_MIN = 2009
YEAR_MAX = 2024
DOD_AGENCY = "Department of Defense"

EXCLUDED_INDUSTRY_GROUPS = frozenset(
    {
        "Insurance",
        "Lodging and Conventions",
        "Other Travel",
        "Pooled Investment Fund",
        "Restaurants",
        "Retailing",
        "Tourism and Travel Services",
    }
)

USASPENDING_BASE = "https://api.usaspending.gov/api/v2"
SPENDING_BY_AWARD_ENDPOINT = f"{USASPENDING_BASE}/search/spending_by_award/"

# Federal contract type codes per USAspending API
CONTRACT_TYPE_CODES = ["A", "B", "C", "D"]


def _norm_name(s: str | None) -> str:
    return (s or "").strip().upper()


def _parse_amount(s: str | None) -> float | None:
    if s is None:
        return None
    cleaned = str(s).replace("$", "").replace(",", "").strip()
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def load_dod_cohort(
    form_d_path: Path, sbir_path: Path, year_min: int, year_max: int
) -> dict[str, dict[str, Any]]:
    """Build the DoD high-tier Form D matched cohort.

    Returns: {normalized_name: {sbir_dod_total, dominant_dod_branch, form_d_raised}}
    """
    # Per-firm SBIR DoD aggregates with dominant Branch
    sbir_by_firm: dict[str, dict[str, Any]] = {}
    with open(sbir_path) as f:
        for row in csv.DictReader(f):
            if (row.get("Agency") or "").strip() != DOD_AGENCY:
                continue
            try:
                year = int(row.get("Award Year") or 0)
            except ValueError:
                continue
            if year < year_min or year > year_max:
                continue
            amt = _parse_amount(row.get("Award Amount"))
            if amt is None or amt <= 0:
                continue
            name = _norm_name(row.get("Company"))
            if not name:
                continue
            branch = (row.get("Branch") or "Unknown").strip() or "Unknown"
            entry = sbir_by_firm.setdefault(
                name,
                {"sbir_dod_total": 0.0, "branches": defaultdict(float), "original_name": (row.get("Company") or "").strip()},
            )
            entry["sbir_dod_total"] += amt
            entry["branches"][branch] += amt

    for e in sbir_by_firm.values():
        if e["branches"]:
            e["dominant_dod_branch"] = max(e["branches"].items(), key=lambda kv: kv[1])[0]
        else:
            e["dominant_dod_branch"] = None
        e["branches"] = dict(e["branches"])

    # Form D high-tier matches with positive in-window raised
    fd_raised: dict[str, float] = {}
    with open(form_d_path) as f:
        for line in f:
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            name = _norm_name(r.get("company_name"))
            tier = (r.get("match_confidence") or {}).get("tier")
            if not name or tier != "high":
                continue
            raised = 0.0
            for off in r.get("offerings", []):
                ig = off.get("industry_group") or ""
                if ig in EXCLUDED_INDUSTRY_GROUPS:
                    continue
                fdate = off.get("filing_date") or ""
                fyear = int(fdate[:4]) if fdate[:4].isdigit() else None
                if fyear is None or fyear < year_min or fyear > year_max:
                    continue
                try:
                    raised += float(off.get("total_amount_sold") or 0)
                except (TypeError, ValueError):
                    continue
            if raised > 0:
                fd_raised[name] = raised

    # Inner join
    cohort = {}
    for name, fd in fd_raised.items():
        sbir = sbir_by_firm.get(name)
        if not sbir:
            continue
        cohort[name] = {
            "original_name": sbir["original_name"],
            "sbir_dod_total": sbir["sbir_dod_total"],
            "dominant_dod_branch": sbir["dominant_dod_branch"],
            "form_d_raised": fd,
        }
    return cohort


def query_usaspending_for_firm(
    client: httpx.Client,
    firm_name: str,
    year_min: int,
    year_max: int,
    sleep_between: float = 1.1,
) -> dict[str, Any]:
    """Query USAspending for one firm's federal-contract activity.

    Returns: {total_contract_usd, n_awards, sub_agencies (dict), error (None or str)}
    """
    payload = {
        "filters": {
            "recipient_search_text": [firm_name],
            "time_period": [{"start_date": f"{year_min}-01-01", "end_date": f"{year_max}-12-31"}],
            "award_type_codes": CONTRACT_TYPE_CODES,
        },
        "fields": [
            "Award ID",
            "Recipient Name",
            "Award Amount",
            "Awarding Sub Agency",
        ],
        "limit": 100,
        "page": 1,
    }

    total = 0.0
    n_awards = 0
    sub_agency_totals: dict[str, float] = defaultdict(float)

    page = 1
    while True:
        payload["page"] = page
        try:
            resp = client.post(SPENDING_BY_AWARD_ENDPOINT, json=payload, timeout=60.0)
        except httpx.HTTPError as e:
            return {"error": f"http error page {page}: {e}", "total_contract_usd": total, "n_awards": n_awards, "sub_agencies": dict(sub_agency_totals)}

        if resp.status_code != 200:
            return {"error": f"status {resp.status_code} page {page}", "total_contract_usd": total, "n_awards": n_awards, "sub_agencies": dict(sub_agency_totals)}
        body = resp.json()
        results = body.get("results", [])
        for r in results:
            amt = r.get("Award Amount") or 0
            try:
                amt = float(amt)
            except (TypeError, ValueError):
                continue
            # Only count exact-recipient-name matches to control false positives.
            # The recipient_search_text filter is fuzzy; we tighten here.
            recipient = (r.get("Recipient Name") or "").strip().upper()
            if recipient != firm_name.upper():
                continue
            total += amt
            n_awards += 1
            sub = r.get("Awarding Sub Agency") or "Unknown"
            sub_agency_totals[sub] += amt
        has_next = body.get("page_metadata", {}).get("hasNext", False)
        if not has_next:
            break
        page += 1
        time.sleep(sleep_between)

    time.sleep(sleep_between)
    return {
        "error": None,
        "total_contract_usd": total,
        "n_awards": n_awards,
        "sub_agencies": dict(sub_agency_totals),
        "n_pages_fetched": page,
    }


def fetch_firm_contracts(
    cohort: dict[str, dict[str, Any]],
    cache_path: Path,
    year_min: int,
    year_max: int,
    max_firms: int | None,
    sleep_between: float,
) -> dict[str, dict[str, Any]]:
    """Fetch USAspending contracts for each firm; cache to JSONL.

    If a firm is already in the cache, skip the API call. This makes
    reruns fast after a one-time pull.
    """
    cached: dict[str, dict[str, Any]] = {}
    if cache_path.exists():
        for line in open(cache_path):
            try:
                r = json.loads(line)
                cached[r["firm_name"]] = r
            except (json.JSONDecodeError, KeyError):
                continue
        print(f"  Cache hit: {len(cached):,} firms already pulled", file=sys.stderr)

    # Sort cohort by SBIR$ desc so larger firms are queried first
    cohort_items = sorted(cohort.items(), key=lambda kv: -kv[1]["sbir_dod_total"])
    if max_firms is not None:
        cohort_items = cohort_items[:max_firms]

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    new_pulls = 0
    errors = 0
    with httpx.Client() as client, open(cache_path, "a") as cache_f:
        for i, (name, entry) in enumerate(cohort_items):
            if name in cached:
                continue
            search_name = entry["original_name"] or name
            print(
                f"  [{i + 1}/{len(cohort_items)}] {search_name[:50]:<50} (SBIR ${entry['sbir_dod_total']/1e6:>6.2f}M, {entry['dominant_dod_branch'][:15]})",
                file=sys.stderr,
            )
            result = query_usaspending_for_firm(client, search_name, year_min, year_max, sleep_between)
            row = {"firm_name": name, "original_name": search_name, **result}
            cache_f.write(json.dumps(row) + "\n")
            cache_f.flush()
            cached[name] = row
            new_pulls += 1
            if result.get("error"):
                errors += 1
                print(f"    ERROR: {result['error']}", file=sys.stderr)

    print(f"  New pulls: {new_pulls:,} ({errors} errors)", file=sys.stderr)
    return {name: cached[name] for name, _ in cohort_items if name in cached}


def compute_per_branch_substitution(
    cohort: dict[str, dict[str, Any]],
    contracts: dict[str, dict[str, Any]],
    program_by_branch: dict[str, float],
    min_program_usd: float = 100e6,
) -> list[dict[str, Any]]:
    """Per-Branch follow-on-FPDS leverage + Form D leverage comparison."""
    by_branch: dict[str, dict[str, float]] = defaultdict(
        lambda: {"firms": 0, "fpds_total": 0.0, "form_d_total": 0.0, "sbir_total": 0.0}
    )
    for name, entry in cohort.items():
        branch = entry["dominant_dod_branch"]
        if branch is None:
            continue
        fpds = contracts.get(name, {}).get("total_contract_usd") or 0.0
        by_branch[branch]["firms"] += 1
        by_branch[branch]["fpds_total"] += fpds
        by_branch[branch]["form_d_total"] += entry["form_d_raised"]
        by_branch[branch]["sbir_total"] += entry["sbir_dod_total"]

    out = []
    for branch, program in sorted(program_by_branch.items(), key=lambda kv: -kv[1]):
        if program < min_program_usd:
            continue
        bstats = by_branch.get(branch)
        if not bstats:
            continue
        fpds_ratio = bstats["fpds_total"] / program if program > 0 else 0.0
        fd_ratio = bstats["form_d_total"] / program if program > 0 else 0.0
        substitution_signal = (fpds_ratio - fd_ratio) / fd_ratio if fd_ratio > 0 else None
        out.append(
            {
                "branch": branch,
                "program_usd": program,
                "n_matched_firms": bstats["firms"],
                "matched_sbir_total_usd": bstats["sbir_total"],
                "form_d_total_usd": bstats["form_d_total"],
                "fpds_total_usd": bstats["fpds_total"],
                "form_d_program_ratio": fd_ratio,
                "fpds_program_ratio": fpds_ratio,
                "substitution_signal_pct": substitution_signal,  # (FPDS/FD - 1) - higher = more substitution
            }
        )
    return out


def write_markdown(snapshot: dict[str, Any], path: Path) -> None:
    L = []
    L.append("# DoD FPDS substitution test — does federal-contract follow-on replace private capital?")
    L.append("")
    L.append(f"**Cohort:** {snapshot['cohort_size']} DoD high-tier Form D matched firms")
    L.append(f"**Firms queried:** {snapshot['firms_queried']}")
    L.append(f"**Year window:** {snapshot['year_min']}-{snapshot['year_max']}")
    L.append(f"**Source:** USAspending public API (no auth)")
    L.append("")

    L.append("## Per-Branch follow-on FPDS vs Form D leverage")
    L.append("")
    L.append("Both ratios use the Branch's DoD program SBIR $ as the denominator (consistent with PR #342 methodology). \"Substitution signal\" is (FPDS_ratio − FD_ratio) / FD_ratio — positive means FPDS dominates, negative means Form D dominates.")
    L.append("")
    L.append("| Branch | Program $B | Matched firms | Form D $B | FPDS $B | Form D ratio | FPDS ratio | Substitution signal |")
    L.append("|---|---|---|---|---|---|---|---|")
    for r in snapshot["per_branch"]:
        sig = r["substitution_signal_pct"]
        sig_str = f"{sig:+.0%}" if sig is not None else "—"
        L.append(
            f"| {r['branch']} | {r['program_usd']/1e9:.2f} | {r['n_matched_firms']:,} | "
            f"${r['form_d_total_usd']/1e9:.2f} | ${r['fpds_total_usd']/1e9:.2f} | "
            f"{r['form_d_program_ratio']:.3f}x | {r['fpds_program_ratio']:.3f}x | **{sig_str}** |"
        )
    L.append("")
    L.append("## Caveats")
    L.append("")
    L.append("- Recipient matching uses USAspending's `recipient_search_text` fuzzy search, tightened to exact uppercased recipient-name equality. False positives from name collisions remain possible but bounded.")
    L.append("- USAspending coverage degrades pre-2015. Pre-2015 firm-contract sums may be undercounted; the per-Branch signal should be interpreted with that in mind.")
    L.append("- The FPDS total here INCLUDES contracts that are themselves SBIR awards (which appear in both USAspending and SBIR.gov). A more rigorous version would subtract SBIR-tagged contracts from the FPDS numerator to isolate true non-SBIR follow-on activity.")
    L.append("- The cohort is HIGH-tier Form D matched firms only. Firms with no Form D match are not represented — so the comparison is *within the cohort that DID raise some private capital*, asking whether they ALSO have heavy federal-contract activity.")
    L.append("")

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        f.write("\n".join(L) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--form-d-path", type=Path, default=Path("data/form_d_details.jsonl"))
    parser.add_argument("--sbir-path", type=Path, default=Path("data/raw/sbir/award_data.csv"))
    parser.add_argument("--year-min", type=int, default=YEAR_MIN)
    parser.add_argument("--year-max", type=int, default=YEAR_MAX)
    parser.add_argument("--cache-path", type=Path, default=Path("data/processed/fpds_substitution/firm_contracts.jsonl"))
    parser.add_argument("--max-firms", type=int, default=None, help="Cap on firms queried (default: all in cohort)")
    parser.add_argument("--sleep-between", type=float, default=1.1, help="Seconds between API calls (1.1 = ~55 req/min, under USAspending's 60/min limit)")
    parser.add_argument("--output-json", type=Path, default=Path("reports/ml/dod_fpds_substitution_test.json"))
    parser.add_argument("--output-md", type=Path, default=Path("reports/ml/dod_fpds_substitution_test.md"))
    parser.add_argument("--skip-fetch", action="store_true", help="Use cache only; do not query API for new firms")
    args = parser.parse_args()

    for p in (args.form_d_path, args.sbir_path):
        if not p.exists():
            print(f"ERROR: {p} not found", file=sys.stderr)
            return 2

    print("Loading cohort...", file=sys.stderr)
    cohort = load_dod_cohort(args.form_d_path, args.sbir_path, args.year_min, args.year_max)
    print(f"  Cohort: {len(cohort):,} DoD high-tier Form D matched firms", file=sys.stderr)

    # Re-derive per-Branch program totals (matches the script-1 methodology)
    program_by_branch: dict[str, float] = defaultdict(float)
    with open(args.sbir_path) as f:
        for row in csv.DictReader(f):
            if (row.get("Agency") or "").strip() != DOD_AGENCY:
                continue
            try:
                year = int(row.get("Award Year") or 0)
            except ValueError:
                continue
            if year < args.year_min or year > args.year_max:
                continue
            amt = _parse_amount(row.get("Award Amount"))
            if amt is None or amt <= 0:
                continue
            branch = (row.get("Branch") or "Unknown").strip() or "Unknown"
            program_by_branch[branch] += amt
    program_by_branch = dict(program_by_branch)

    # Fetch (or use cache)
    if args.skip_fetch:
        print("Skip-fetch mode: using cache only", file=sys.stderr)
        contracts = {}
        if args.cache_path.exists():
            for line in open(args.cache_path):
                try:
                    r = json.loads(line)
                    contracts[r["firm_name"]] = r
                except (json.JSONDecodeError, KeyError):
                    continue
        print(f"  Cached firms: {len(contracts):,}", file=sys.stderr)
    else:
        print(f"Querying USAspending for {min(args.max_firms or len(cohort), len(cohort)):,} firms (~{args.sleep_between}s/req)...", file=sys.stderr)
        contracts = fetch_firm_contracts(
            cohort, args.cache_path, args.year_min, args.year_max, args.max_firms, args.sleep_between
        )

    print("\nComputing per-Branch substitution signal...", file=sys.stderr)
    per_branch = compute_per_branch_substitution(cohort, contracts, program_by_branch)

    snapshot = {
        "schema_version": "1",
        "form_d_path": str(args.form_d_path),
        "sbir_path": str(args.sbir_path),
        "year_min": args.year_min,
        "year_max": args.year_max,
        "cohort_size": len(cohort),
        "firms_queried": len(contracts),
        "per_branch": per_branch,
    }

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output_json, "w") as f:
        json.dump(snapshot, f, indent=2)
    write_markdown(snapshot, args.output_md)

    # Console summary
    print("\n=== Per-Branch Form D vs FPDS leverage ===", file=sys.stderr)
    print(f"{'Branch':<45} {'Firms':>6} {'FD ratio':>10} {'FPDS ratio':>12} {'Substitution':>15}", file=sys.stderr)
    for r in per_branch:
        sig = r["substitution_signal_pct"]
        sig_str = f"{sig:+.0%}" if sig is not None else "—"
        print(f"  {r['branch'][:43]:<43} {r['n_matched_firms']:>6,} {r['form_d_program_ratio']:>9.3f}x {r['fpds_program_ratio']:>11.3f}x {sig_str:>15}", file=sys.stderr)

    print(f"\nWrote {args.output_json} and {args.output_md}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
