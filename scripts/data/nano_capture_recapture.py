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

A second, SEPARATE analysis (run_dark_population_analysis) repeats this exercise
within the 1,019-firm dark population (FIRM_ACTIVITY_ABSENT + ENTITY_RESOLUTION_
FAILURE) using the WS5/WS6 "life evidence" channels: patent, trademark, alias,
subaward. This is NOT comparable to the cohort-wide numbers from main() above
and must not be merged with them — the dark population is, by construction, already negative
on every cohort-wide channel (fpds/formd/strong/ma), so within-population capture
counts measure something narrower: given a firm shows none of the primary
transition signals, how disjoint are the SECONDARY "is it alive" signals from
each other? Sector-registry evidence (WS5c) is excluded from this second pass
because it was only searched for 206 of the 1,019 firms (HHS-funded slice) —
including it would confound "no evidence" with "never searched."

Path convention (same as nano_form_d_temporal.py / nano_ws1):
  --area <id>   → data/reports/<id>/capture_recapture[_darkfirms].csv
  (no flag)     → data/nano_capture_recapture[_darkfirms].csv  (legacy PR #428)

Outputs:
  stdout summary + capture_recapture.csv (per-firm channel matrix, cohort-wide)
  + capture_recapture_darkfirms.csv (dark-population pass)

Usage:
  python scripts/data/nano_capture_recapture.py [--area AREA] [--legacy]
"""

import argparse
import csv
import sys
from collections import Counter
from itertools import combinations
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

sys.path.insert(0, str(REPO))
from sbir_etl.utils.transition_report_paths import (  # noqa: E402
    ReportPaths,
    add_area_args,
    resolve_area_paths,
)

CHANNELS = ("fpds", "formd", "strong", "ma", "patent")


def main(paths: ReportPaths) -> int:
    inputs = {
        "kw": paths.artifact("cohort_keyword"),
        "fd": paths.artifact("form_d_post_phase2"),
        "ws1": paths.artifact("ws1_contract_evidence"),
        "ws2": paths.artifact("ws2_contract_evidence"),
        "cpc": paths.artifact("cohort_cpc"),
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

    out_csv = paths.artifact("capture_recapture")
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


DARK_CHANNELS = ("patent", "trademark", "alias", "subaward")


def run_dark_population_analysis(paths: ReportPaths) -> int:
    """Second, separate capture-recapture pass within the dark-firm population.

    See module docstring for why this is not comparable to run_cohort_analysis().
    """
    liveness_csv = paths.artifact("dark_firm_liveness")
    tm_csv = paths.artifact("dark_firm_trademarks")
    alias_csv = paths.artifact("alias_expanded_evidence")
    sub_csv = paths.artifact("ws5a_subawards")
    for p in (liveness_csv, tm_csv, alias_csv, sub_csv):
        if not p.exists():
            print(f"SKIP dark-population pass: {p.name} not found", file=sys.stderr)
            return 1

    liv = list(csv.DictReader(open(liveness_csv, newline="", encoding="utf-8")))
    firms = {r["normalized_name"] for r in liv}
    detect: dict[str, set[str]] = {c: set() for c in DARK_CHANNELS}

    for r in liv:
        if r.get("match_confidence") == "high" and r.get("any_filed_post_award") == "True":
            detect["patent"].add(r["normalized_name"])
    for r in csv.DictReader(open(tm_csv, newline="", encoding="utf-8")):
        if r.get("tm_filed_post_award") == "True":
            detect["trademark"].add(r["normalized_name"])
    for r in csv.DictReader(open(alias_csv, newline="", encoding="utf-8")):
        if r.get("negative_under_own_name") == "True":
            detect["alias"].add(r["firm_normalized"])
    for r in csv.DictReader(open(sub_csv, newline="", encoding="utf-8")):
        if r.get("subaward_tier") in ("strong", "moderate"):
            detect["subaward"].add(r["firm_normalized"])

    histories = {f: tuple(f in detect[c] for c in DARK_CHANNELS) for f in firms}
    n_firms = len(firms)
    observed = {f for f, h in histories.items() if any(h)}
    s_obs = len(observed)
    capture_counts = Counter(sum(h) for h in histories.values() if any(h))
    f1, f2 = capture_counts.get(1, 0), capture_counts.get(2, 0)
    chao = s_obs + (f1 * f1) / (2 * f2) if f2 else float("inf")

    out_csv = paths.artifact("capture_recapture_darkfirms")
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["firm_normalized", *DARK_CHANNELS, "n_channels"])
        for fm in sorted(firms):
            h = histories[fm]
            w.writerow([fm, *(int(x) for x in h), sum(h)])
    print(f"Written: {out_csv} ({n_firms:,} firms)")

    print()
    print("=" * 70)
    print("CAPTURE-RECAPTURE — WITHIN DARK-FIRM POPULATION (separate from cohort-wide)")
    print("=" * 70)
    print(f"Dark firms: {n_firms:,}   detected by ≥1 of {len(DARK_CHANNELS)} secondary channels: "
          f"{s_obs:,} ({100*s_obs/n_firms:.1f}%)")
    for c in DARK_CHANNELS:
        print(f"  {c:<10} {len(detect[c] & firms):>4}")
    print(f"Capture-count distribution: {dict(sorted(capture_counts.items()))}")
    if f2:
        print(f"\nChao lower bound: N ≥ {s_obs} + {f1}²/(2×{f2}) = {chao:.0f} "
              f"→ ≥ {100*chao/n_firms:.1f}% of dark firms")
    else:
        print("\nChao bound undefined (f2=0) — cannot estimate from doubletons alone.")

    print("\nPairwise overlaps (independence not assumed; informational only):")
    for a, b in combinations(DARK_CHANNELS, 2):
        na, nb = len(detect[a] & firms), len(detect[b] & firms)
        m = len(detect[a] & detect[b] & firms)
        note = ""
        if "alias" in (a, b) and {a, b} & {"patent", "trademark"}:
            note = "overlap ~0 BY CONSTRUCTION — alias recovery requires patent+trademark negativity"
        print(f"  {a}×{b:<10} {na:>4} {nb:>4}   overlap {m:>4}   {note}")
    return 0


if __name__ == "__main__":
    _parser = argparse.ArgumentParser(description=__doc__)
    add_area_args(_parser)
    _argv = sys.argv[1:]
    _args = _parser.parse_args(_argv)
    _paths = resolve_area_paths(_args, _argv)
    print(
        f"area={_paths.area_id}{', legacy' if _paths.legacy else ''}",
        file=sys.stderr,
    )
    rc1 = main(_paths)
    rc2 = run_dark_population_analysis(_paths)
    sys.exit(rc1 or rc2)
