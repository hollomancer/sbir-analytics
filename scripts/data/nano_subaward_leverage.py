#!/usr/bin/env python3
"""
Subaward leverage: post-award subcontract dollar volume against cumulative
SBIR investment, for the WS5a strong-tier firms.

Not the same economic concept as Finding 2's acquisition leverage (a one-time
exit price against cumulative investment). A subaward stream is recurring
supply-chain revenue, not a sale — this measures whether a small upfront SBIR
R&D bet turned into a materially larger ongoing commercial relationship, not
an exit multiple. Reported as leverage anyway, for direct comparability with
Finding 2's framing, but the distinction is stated wherever the number is used.

Cumulative SBIR investment matches Finding 2's methodology: total Award Amount
across ALL of a firm's SBIR.gov records (all phases, all years, not limited to
the nanotech cohort awards).

Firms already named in Finding 2 (confirmed EDGAR-detected acquisitions) are
flagged and excluded from "newly discovered" framing — their subaward evidence
enriches an already-known story rather than illuminating a new one.

Inputs:
  data/nano_ws5a_subawards.csv    — strong-tier firms + post-award subaward totals
  data/raw/sbir/award_data.csv    — full per-firm SBIR award history

Outputs:
  data/nano_subaward_leverage.csv

Usage:
  python scripts/data/nano_subaward_leverage.py
"""

import csv
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DATA = REPO / "data"

sys.path.insert(0, str(REPO))
from sbir_etl.utils.text_normalization import normalize_name  # noqa: E402

# Firms confirmed acquired in Finding 2 (docs/nanotech_sbir_transition_findings.md).
# Subaward evidence for these enriches an already-known outcome, not a new one.
FINDING2_KNOWN_ACQUISITIONS = {
    normalize_name(n, remove_suffixes=True)
    for n in [
        "Physical Optics Corporation", "Intellisense Systems Inc", "Nomadics, Inc.",
        "SY Technology, Inc.", "GATR Technologies", "KAI, LLC",
        "Anasys Instruments Corp", "EKOS Corporation", "EraGen Biosciences",
        "Senior Scientific", "Visen Medical, Inc.",
    ]
}


def _safe_float(v: str) -> float:
    try:
        return float((v or "0").replace("$", "").replace(",", "")) if v else 0.0
    except ValueError:
        return 0.0


def main() -> int:
    sub_csv = DATA / "nano_ws5a_subawards.csv"
    awards_csv = DATA / "raw/sbir/award_data.csv"
    for p in (sub_csv, awards_csv):
        if not p.exists():
            print(f"ERROR: {p} not found", file=sys.stderr)
            return 1

    csv.field_size_limit(sys.maxsize)
    strong = [r for r in csv.DictReader(open(sub_csv, newline="", encoding="utf-8"))
              if r["subaward_tier"] == "strong"]
    strong_norms = {r["firm_normalized"] for r in strong}
    print(f"Strong-tier subaward firms: {len(strong)}")

    print("Summing cumulative SBIR investment per firm (all phases, all years)...")
    cumulative: dict[str, float] = {}
    with open(awards_csv, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            norm = normalize_name(row.get("Company", ""), remove_suffixes=True)
            if norm in strong_norms:
                cumulative[norm] = cumulative.get(norm, 0.0) + _safe_float(row.get("Award Amount", ""))

    out_rows = []
    for r in strong:
        norm = r["firm_normalized"]
        sub_total = float(r["total_sub_usd"])
        sbir_total = cumulative.get(norm, 0.0)
        leverage = sub_total / sbir_total if sbir_total > 0 else None
        out_rows.append({
            "company": r["company"],
            "known_finding2_acquisition": norm in FINDING2_KNOWN_ACQUISITIONS,
            "post_award_subaward_usd": round(sub_total, 2),
            "cumulative_sbir_usd": round(sbir_total, 2),
            "leverage": round(leverage, 2) if leverage is not None else "",
            "n_post_subawards": r["n_post_subawards"],
            "top_primes": r["top_primes"],
        })

    out_csv = DATA / "nano_subaward_leverage.csv"
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(out_rows[0].keys()))
        w.writeheader()
        w.writerows(sorted(out_rows, key=lambda x: -x["post_award_subaward_usd"]))
    print(f"  Written: {out_csv} ({len(out_rows)} firms)")

    known = [r for r in out_rows if r["known_finding2_acquisition"]]
    new = [r for r in out_rows if not r["known_finding2_acquisition"]]
    print()
    print("=" * 70)
    print("SUBAWARD LEVERAGE SUMMARY")
    print("=" * 70)
    print(f"Total: {len(out_rows)} firms  ({len(known)} already known from Finding 2, "
          f"{len(new)} newly characterized by this analysis)")

    for label, subset in (("ALL 103", out_rows), ("NEWLY CHARACTERIZED (excl. Finding 2 acquisitions)", new)):
        vals = sorted(r["post_award_subaward_usd"] for r in subset)
        lev = sorted(r["leverage"] for r in subset if r["leverage"] != "")
        n = len(vals)
        print(f"\n{label} (n={n}):")
        print(f"  post-award subaward $: median ${vals[n//2]:,.0f}  "
              f"90th pct ${vals[int(n*0.9)]:,.0f}  total ${sum(vals):,.0f}")
        if lev:
            m = len(lev)
            print(f"  leverage (subaward $ / cumulative SBIR $): median {lev[m//2]:.2f}x  "
                  f"90th pct {lev[int(m*0.9)]:.2f}x")
            over1x = sum(1 for x in lev if x >= 1.0)
            print(f"  firms with subaward $ >= cumulative SBIR $ (leverage >= 1x): {over1x}/{m} ({100*over1x/m:.0f}%)")

    print("\nTop 5 by post-award subaward $ (dominate the raw sum; large going concerns, not typical):")
    for r in sorted(out_rows, key=lambda x: -x["post_award_subaward_usd"])[:5]:
        flag = " [KNOWN Finding 2 acquisition]" if r["known_finding2_acquisition"] else ""
        print(f"  {r['company'][:34]:<34} ${r['post_award_subaward_usd']:>14,.0f}  "
              f"leverage={r['leverage']}x{flag}")

    print("\nTop 5 newly-characterized firms by leverage multiple (excl. Finding 2 acquisitions):")
    lev_sorted = sorted([r for r in new if r["leverage"] != ""], key=lambda x: -x["leverage"])
    for r in lev_sorted[:5]:
        print(f"  {r['company'][:34]:<34} leverage={r['leverage']:>7}x  "
              f"sub=${r['post_award_subaward_usd']:,.0f}  sbir=${r['cumulative_sbir_usd']:,.0f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
