#!/usr/bin/env python3
"""
T10 — bound the true commercialization rate via multi-list capture-recapture.

Population: the 1,339 keyword-cohort firms (firm grain — several channels are
firm-level, so award-grain capture-recapture would smear). Detection lists:

  L1 fpds     firm has an FPDS-coded Phase III award
  L2 formd    firm has a post-Phase-II Form D offering (temporally filtered)
  L3 strong   firm has strong contract-level evidence (WS1 or WS2 recovery)
  L4 ma       firm has a high-confidence M&A signal
  L5 patent   firm first filed a B82 patent application after its first award

ASSUMPTIONS — read before citing any number:
- Lincoln–Petersen (LP) pairwise estimates assume list independence. Finding 1
  argues the procurement and private-capital pathways are *structurally*
  disjoint (negative dependence), which inflates LP — so the FPDS×FormD LP
  estimate is reported as a LOOSE UPPER BOUND, not an estimate.
- L1×L3 overlap is zero BY CONSTRUCTION (WS1 targeted the complement of FPDS
  coding); that pair is excluded from estimation entirely.
- The Chao (1987) lower bound N ≥ S_obs + f1²/(2·f2) is robust to capture
  heterogeneity and requires no independence; it bounds the number of firms
  detectable by channels *of the kinds deployed*, not all commercialized firms.
- No channel provides negative evidence (proof of no commercialization), so no
  data-driven upper bound tighter than LP exists yet — that is what state
  registries / the survey (T7/T11) would add.

Outputs:
  stdout summary + data/nano_capture_recapture.csv (per-firm channel matrix)

Usage:
  python scripts/data/nano_capture_recapture.py
"""

import csv
import sys
from collections import Counter
from itertools import combinations
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DATA = REPO / "data"

CHANNELS = ("fpds", "formd", "strong", "ma", "patent")


def main() -> int:
    inputs = {
        "kw": DATA / "nano_cohort_keyword.csv",
        "fd": DATA / "nano_form_d_post_phase2.csv",
        "ws1": DATA / "nano_ws1_contract_evidence.csv",
        "ws2": DATA / "nano_ws2_contract_evidence.csv",
        "cpc": DATA / "nano_cohort_cpc.csv",
    }
    for p in inputs.values():
        if not p.exists():
            print(f"ERROR: {p} not found", file=sys.stderr)
            return 1

    csv.field_size_limit(sys.maxsize)
    load = lambda k: list(csv.DictReader(open(inputs[k], newline="", encoding="utf-8")))
    kw, fd, ws1, ws2, cpc = (load(k) for k in ("kw", "fd", "ws1", "ws2", "cpc"))
    firm = lambda r: r["company"].strip().upper()

    firms = {firm(r) for r in kw}
    detect: dict[str, set[str]] = {c: set() for c in CHANNELS}

    for r in kw:
        if r.get("sig_fpds_phase3_coded") == "True":
            detect["fpds"].add(firm(r))
        if r.get("sig_ma_high_conf") == "True":
            detect["ma"].add(firm(r))
    for r in fd:
        if r.get("form_d_post_p2") == "True":
            detect["formd"].add(firm(r))
    for r in ws1 + ws2:
        if r.get("evidence_tier") == "strong":
            detect["strong"].add(firm(r))

    # Patent channel: keyword-cohort firm whose first B82 filing postdates its
    # first Phase II award year (same rule as §5E).
    first_award: dict[str, int] = {}
    for r in kw:
        yr = int(float(r.get("award_year") or 0))
        if yr:
            first_award[firm(r)] = min(first_award.get(firm(r), 9999), yr)
    for r in cpc:
        f = firm(r)
        if f in firms and r.get("cpc_first_b82_filing"):
            if int(r["cpc_first_b82_filing"][:4]) > first_award.get(f, 9999):
                detect["patent"].add(f)

    # Per-firm capture histories
    histories: dict[str, tuple[bool, ...]] = {
        f: tuple(f in detect[c] for c in CHANNELS) for f in firms
    }
    n_firms = len(firms)
    observed = {f for f, h in histories.items() if any(h)}
    s_obs = len(observed)
    capture_counts = Counter(sum(h) for h in histories.values() if any(h))
    f1, f2 = capture_counts.get(1, 0), capture_counts.get(2, 0)

    out_csv = DATA / "nano_capture_recapture.csv"
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["company", *CHANNELS, "n_channels"])
        for fm in sorted(firms):
            h = histories[fm]
            w.writerow([fm, *(int(x) for x in h), sum(h)])
    print(f"Written: {out_csv} ({n_firms:,} firms)")

    print()
    print("=" * 70)
    print("CAPTURE-RECAPTURE BOUND — FIRM GRAIN")
    print("=" * 70)
    print(f"Cohort firms: {n_firms:,}   observed by ≥1 channel: {s_obs:,} ({100*s_obs/n_firms:.1f}%)")
    for c in CHANNELS:
        print(f"  {c:<7} {len(detect[c] & firms):>4}")
    print(f"Capture-count distribution (observed firms): {dict(sorted(capture_counts.items()))}")

    chao = s_obs + (f1 * f1) / (2 * f2) if f2 else float("inf")
    print(f"\nChao lower bound on ever-detectable commercialized firms:")
    print(f"  N ≥ {s_obs} + {f1}²/(2×{f2}) = {chao:.0f}  → ≥ {100*chao/n_firms:.1f}% of cohort firms")

    print("\nPairwise overlaps and LP estimates (independence NOT credible — see docstring):")
    print(f"  {'pair':<16} {'n1':>4} {'n2':>4} {'m':>4}   LP N̂    note")
    for a, b in combinations(CHANNELS, 2):
        n1, n2 = len(detect[a] & firms), len(detect[b] & firms)
        m = len(detect[a] & detect[b] & firms)
        note = ""
        if {a, b} == {"fpds", "strong"}:
            note = "overlap structurally 0 — excluded"
        elif {a, b} == {"fpds", "formd"}:
            note = "neg. dependence → loose UPPER bound"
        elif "patent" in (a, b):
            note = "pos. dependence → underestimates"
        lp = f"{n1*n2/m:7.0f}" if m else "    n/a"
        print(f"  {a}×{b:<10} {n1:>4} {n2:>4} {m:>4}  {lp}   {note}")

    fpds, formd = detect["fpds"] & firms, detect["formd"] & firms
    m = len(fpds & formd)
    if m:
        lp = len(fpds) * len(formd) / m
        print(f"\nDefensible interval for truly-commercialized firms:")
        print(f"  lower: {100*s_obs/n_firms:.1f}% (direct observation) — "
              f"{100*chao/n_firms:.1f}% (Chao, heterogeneity-robust)")
        print(f"  upper: ~{100*min(lp, n_firms)/n_firms:.0f}% (LP on FPDS×FormD; loose — "
              f"structural disjointness inflates it)")
        print("  Tightening the upper bound requires negative-evidence instruments")
        print("  (state registries, survey) — more positive channels cannot do it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
