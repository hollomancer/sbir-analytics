#!/usr/bin/env python3
"""
Time-to-first-commercialization-signal survival analysis (WS4 / T2).

Kaplan–Meier estimate of time from Phase II end to the first *dateable*
commercialization signal, treating awards without a signal as right-censored
at the data cutoff instead of counting them as failures. Dateable channels:

  - Form D: first post-Phase-II offering date (nano_form_d_post_phase2.csv)
  - WS1 strong contract evidence: first non-SBIR evidence date
    (nano_ws1_contract_evidence.csv, strong tier only)
  - B82 patents: firm's first nanotech filing, when it postdates the award's
    Phase II end (nano_cohort_cpc.csv; undercounts firms whose first filing
    predates the award but who kept filing)

FPDS-coded Phase III and M&A signals carry no reliable per-award dates and
are excluded — the curve therefore UNDERSTATES total observable signal and
should be read for its time profile, not its plateau height.

Path convention (same as nano_form_d_temporal.py / nano_ws1):
  --area <id>   → data/reports/<id>/analysis/time_to_signal_km.png
  (no flag)     → data/analysis/nano_time_to_signal_km.png  (legacy PR #428)

Outputs:
  analysis/time_to_signal_km.png
  stdout: S(t) at 2/3/5/7/10 years and matured-basis indeterminate shares

Usage:
  python scripts/data/nano_survival_analysis.py [--area AREA] [--legacy]
"""

import argparse
import csv
import sys
from datetime import date
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

REPO = Path(__file__).resolve().parents[2]
CUTOFF = date(2026, 7, 1)  # data currency of the underlying signal files

sys.path.insert(0, str(REPO))
from sbir_etl.utils.transition_report_paths import (  # noqa: E402
    add_area_args,
    resolve_area_paths,
)


def parse(s: str) -> date | None:
    try:
        return date.fromisoformat((s or "")[:10])
    except ValueError:
        return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    add_area_args(parser)
    args = parser.parse_args(argv)
    paths = resolve_area_paths(args, argv)

    fd_csv = paths.artifact("form_d_post_phase2")
    ws1_csv = paths.artifact("ws1_contract_evidence")
    cpc_csv = paths.artifact("cohort_cpc")
    for p, hint in {fd_csv: "run nano_form_d_temporal.py",
                    ws1_csv: "run nano_ws1_contract_evidence.py",
                    cpc_csv: "run build_nano_cohort.py"}.items():
        if not p.exists():
            print(f"ERROR: {p} not found — {hint}", file=sys.stderr)
            return 1

    csv.field_size_limit(sys.maxsize)
    rows = list(csv.DictReader(open(fd_csv, newline="", encoding="utf-8")))
    key = lambda r: (r["award_id"], r["company"], r["award_year"])

    ws1_first = {key(r): parse(r.get("first_evidence_date", ""))
                 for r in csv.DictReader(open(ws1_csv, newline="", encoding="utf-8"))
                 if r["evidence_tier"] == "strong"}
    cpc_first_filing = {}
    for r in csv.DictReader(open(cpc_csv, newline="", encoding="utf-8")):
        d = parse(r.get("cpc_first_b82_filing", ""))
        if d:
            k = r["company"].strip().upper()
            cpc_first_filing[k] = min(cpc_first_filing.get(k, d), d)

    durations: list[tuple[float, bool]] = []  # (years, event_observed)
    skipped = 0
    for r in rows:
        end = parse(r.get("phase_ii_end_date", ""))
        if end is None or end > CUTOFF:
            skipped += 1  # active awards cannot contribute observation time
            continue
        candidates = []
        if r.get("form_d_post_p2") == "True":
            d = parse(r.get("form_d_post_p2_first_date", ""))
            if d and d > end:
                candidates.append(d)
        d = ws1_first.get(key(r))
        if d and d > end:
            candidates.append(d)
        d = cpc_first_filing.get(r["company"].strip().upper())
        if d and d > end:
            candidates.append(d)
        if candidates:
            durations.append(((min(candidates) - end).days / 365.25, True))
        else:
            durations.append(((CUTOFF - end).days / 365.25, False))

    n = len(durations)
    events = sum(1 for _, e in durations if e)
    print(f"Awards observed: {n:,} (skipped {skipped} still-active); events: {events:,} ({100*events/n:.1f}%)")

    # Kaplan–Meier
    durations.sort()
    at_risk = n
    surv = 1.0
    km_t = [0.0]
    km_s = [1.0]
    i = 0
    while i < len(durations):
        t = durations[i][0]
        d = 0
        c = 0
        while i < len(durations) and durations[i][0] == t:
            if durations[i][1]:
                d += 1
            else:
                c += 1
            i += 1
        if d and at_risk:
            surv *= 1 - d / at_risk
            km_t.append(t)
            km_s.append(surv)
        at_risk -= d + c

    def s_at(years: float) -> float:
        s = 1.0
        for t, v in zip(km_t, km_s):
            if t <= years:
                s = v
            else:
                break
        return s

    print("\nCumulative signal incidence (1 - S(t)) among matured awards:")
    for y in (2, 3, 5, 7, 10):
        print(f"  by {y:>2} years: {100 * (1 - s_at(y)):.1f}%")
    event_times = sorted(t for t, e in durations if e)
    if event_times:
        med = event_times[len(event_times) // 2]
        within2 = sum(1 for t in event_times if t <= 2) / len(event_times)
        print(f"\nAmong awards that ever signal: median time-to-signal {med:.1f} yr; "
              f"{100*within2:.0f}% signal within 2 years")

    fig, ax = plt.subplots(figsize=(9, 5.5))
    ax.step(km_t, [100 * (1 - s) for s in km_s], where="post", color="#1565C0", linewidth=2)
    ax.set_xlabel("Years since Phase II end", fontsize=11)
    ax.set_ylabel("% of awards with ≥1 dateable commercialization signal", fontsize=11)
    ax.set_xlim(0, 20)
    ax.set_ylim(0, max(35.0, 100 * (1 - km_s[-1]) + 5))
    ax.grid(alpha=0.3)
    ax.set_title(
        "Nanotech SBIR Phase II: cumulative time-to-first-signal (Kaplan–Meier)\n"
        "Dateable channels only (Form D, contract-level recovery, post-award B82 filing); "
        "censored at 2026-07",
        fontsize=10,
    )
    out = paths.analysis_dir / (
        "nano_time_to_signal_km.png" if paths.legacy else "time_to_signal_km.png"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    print(f"\nFigure saved: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
