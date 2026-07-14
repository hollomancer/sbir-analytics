#!/usr/bin/env python3
"""
M&A signal extraction for nanotech SBIR cohort from existing EDGAR scan.

Uses sec_edgar_scan.jsonl (35k-firm complete scan) as the primary source,
filtered to M&A-specific mention types. Cross-references enriched_sbir_ma_events.jsonl
for confidence scoring where available.

The sec_edgar_scan.summary.json showing 0 results is from a separate, broken
recent scan (39s, 500 errors throughout). The sec_edgar_scan.jsonl data is
the usable record and has 99.9% coverage of the nanotech cohort.

Path convention (same as nano_form_d_temporal.py / nano_ws1):
  --area <id>   → data/reports/<id>/ma_signal.csv (+ analysis/ma_signal.png)
  (no flag)     → data/nano_ma_signal.csv  (legacy PR #428)

The keyword cohort, CSV output, and figure are area-scoped; the SEC EDGAR scan
and M&A enrichment JSONL inputs are shared global inputs under data/.

Outputs:
  ma_signal.csv            — per-award M&A signal (joins to keyword cohort)
  analysis/ma_signal.png   — breakdown by type and agency

Usage:
  python scripts/data/nano_ma_signal.py [--area AREA] [--legacy]
"""

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

REPO = Path(__file__).resolve().parents[2]
DATA = REPO / "data"

sys.path.insert(0, str(REPO))
from sbir_etl.utils.transition_report_paths import (  # noqa: E402
    add_area_args,
    resolve_area_paths,
)

# Mention types that indicate M&A activity for the target firm.
# Ordered roughly by specificity — ma_definitive is strongest.
MA_SIGNAL_TYPES = frozenset({
    "ma_definitive",    # definitive merger/acquisition agreement
    "ma_proxy",         # proxy statement related to M&A
    "acquisition",      # acquisition language in filing text
    "subsidiary",       # named as subsidiary of another entity
    "ownership_active", # active ownership/control change
})

# Types present in the scan that are NOT M&A evidence for the target firm
NOISE_TYPES = frozenset({
    "filing_mention",    # generic mention in another firm's filing
    "financial_mention", # financial relationship, not M&A
    "contract",          # government or commercial contract
    "competitor",        # named as competitor
    "investment",        # passive investment (not control change)
    "ownership_passive", # passive ownership, no control
    "disclosure",        # generic disclosure
})


def load_scan(path: Path) -> dict[str, dict]:
    """Load sec_edgar_scan.jsonl indexed by uppercase company name."""
    index: dict[str, dict] = {}
    if not path.exists():
        return index
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                name = rec.get("company_name", "").strip().upper()
                if name:
                    index[name] = rec
            except json.JSONDecodeError:
                pass
    return index


def load_enriched(path: Path) -> dict[str, dict]:
    """
    Load enriched_sbir_ma_events.jsonl indexed by uppercase company name.
    Keeps highest-signal-count record per firm.
    """
    index: dict[str, dict] = {}
    if not path.exists():
        return index
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                name = rec.get("company_name", "").strip().upper()
                if not name:
                    continue
                existing = index.get(name)
                if existing is None or rec.get("signal_count", 0) > existing.get("signal_count", 0):
                    index[name] = rec
            except json.JSONDecodeError:
                pass
    return index


def ma_signal_for_firm(name_upper: str, scan: dict, enriched: dict) -> dict:
    """
    Derive M&A signal for one firm from scan + enriched data.

    Returns a dict of signal fields to attach to each award row.
    """
    result = {
        "ma_in_scan": False,
        "ma_signal": False,
        "ma_types": "",
        "ma_mention_count": 0,
        "ma_filers": "",
        "ma_latest_date": "",
        "ma_confidence": "",
        "ma_acquirer": "",
        "ma_signal_count": 0,
    }

    scan_rec = scan.get(name_upper)
    enriched_rec = enriched.get(name_upper)

    if scan_rec:
        result["ma_in_scan"] = True
        all_types = set(scan_rec.get("mention_types") or [])
        ma_types = all_types & MA_SIGNAL_TYPES
        result["ma_types"] = "|".join(sorted(ma_types))
        result["ma_mention_count"] = scan_rec.get("mention_count", 0)
        result["ma_filers"] = "|".join((scan_rec.get("mention_filers") or [])[:5])
        result["ma_latest_date"] = scan_rec.get("latest_mention_date", "")
        if ma_types:
            result["ma_signal"] = True

    if enriched_rec:
        result["ma_confidence"] = enriched_rec.get("confidence", "")
        result["ma_acquirer"] = enriched_rec.get("acquirer", "") or ""
        result["ma_signal_count"] = enriched_rec.get("signal_count", 0)
        # If enriched record exists but scan didn't show M&A types, trust enriched
        # (enriched pipeline may have used doc-level text analysis scan missed)
        if enriched_rec.get("signal_count", 0) > 0 and not result["ma_signal"]:
            signals = enriched_rec.get("signals", {})
            if any([
                signals.get("efts_ma_definitive"),
                signals.get("efts_ma_proxy"),
                signals.get("form_d_business_combination"),
            ]):
                result["ma_signal"] = True
                if not result["ma_types"]:
                    result["ma_types"] = "enriched_pipeline"

    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    add_area_args(parser)
    args = parser.parse_args(argv)
    paths = resolve_area_paths(args, argv)

    cohort_csv = paths.artifact("cohort_keyword")
    scan_jsonl = DATA / "sec_edgar_scan.jsonl"
    enriched_jsonl = DATA / "enriched_sbir_ma_events.jsonl"

    # Missing scan/enriched files would yield empty indexes and a valid-looking
    # output CSV with zero signals — fail fast instead.
    required_inputs = {
        cohort_csv: f"run build_tech_area_cohort.py --area {paths.area_id} first",
        scan_jsonl: "SEC EDGAR scan output expected at this path",
        enriched_jsonl: "M&A enrichment output expected at this path",
    }
    for p, hint in required_inputs.items():
        if not p.exists():
            print(f"ERROR: {p} not found — {hint}", file=sys.stderr)
            return 1

    print("Loading nanotech keyword cohort...")
    with open(cohort_csv, newline="", encoding="utf-8") as f:
        awards = list(csv.DictReader(f))
    print(f"  {len(awards):,} Phase II awards, {len({r['company'].upper() for r in awards}):,} unique firms")

    print("Loading EDGAR full scan (sec_edgar_scan.jsonl)...")
    scan = load_scan(scan_jsonl)
    print(f"  {len(scan):,} firms in scan")

    print("Loading enriched M&A events...")
    enriched = load_enriched(enriched_jsonl)
    print(f"  {len(enriched):,} firms in enriched index")

    print("Building per-award M&A signals...")
    results = []
    for aw in awards:
        name_upper = aw.get("company", "").strip().upper()
        sig = ma_signal_for_firm(name_upper, scan, enriched)
        row = {**aw, **sig}
        results.append(row)

    # Write output
    out_csv = paths.artifact("ma_signal")
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(results[0].keys()))
        w.writeheader()
        w.writerows(results)
    print(f"  Written: {out_csv}")

    # --- Summary ---
    total = len(results)
    in_scan = sum(1 for r in results if r["ma_in_scan"])
    with_signal = sum(1 for r in results if r["ma_signal"])
    by_type: dict[str, int] = defaultdict(int)
    for r in results:
        for t in r["ma_types"].split("|"):
            if t:
                by_type[t] += 1
    by_conf: dict[str, int] = defaultdict(int)
    for r in results:
        if r["ma_signal"]:
            by_conf[r["ma_confidence"] or "unscored"] += 1

    print()
    print("=" * 60)
    print("M&A SIGNAL SUMMARY — NANOTECH KEYWORD COHORT")
    print("=" * 60)
    print(f"Awards in cohort:                {total:,}")
    print(f"Awards matched in EDGAR scan:    {in_scan:,} ({100*in_scan/total:.1f}%)")
    print(f"Awards with M&A signal:          {with_signal:,} ({100*with_signal/total:.1f}%)")
    print()
    print("Signal breakdown by mention type (awards, not unique firms):")
    for t, n in sorted(by_type.items(), key=lambda x: -x[1]):
        print(f"  {t:<30} {n:>5} ({100*n/total:.1f}%)")
    print()
    print("Signal breakdown by confidence tier:")
    for c, n in sorted(by_conf.items(), key=lambda x: -x[1]):
        print(f"  {c:<15} {n:>5} ({100*n/total:.1f}%)")
    print()

    # By agency
    ag_stats: dict[str, dict] = defaultdict(lambda: {"n": 0, "signal": 0})
    for r in results:
        ag = r.get("agency", "Unknown")
        ag_stats[ag]["n"] += 1
        if r["ma_signal"]:
            ag_stats[ag]["signal"] += 1

    print("M&A signal rate by agency:")
    for ag, s in sorted(ag_stats.items(), key=lambda x: -x[1]["n"]):
        if s["n"] >= 10:
            print(f"  {ag[:45]:<45} {s['signal']:>4}/{s['n']:>4} ({100*s['signal']/s['n']:.1f}%)")

    # --- Previous vs current comparison ---
    old_count = sum(1 for r in awards if r.get("sig_ma_detected") == "True")
    print()
    print("Comparison with previous M&A signal approach:")
    print(f"  Old (enriched_sbir_ma_events, all conf, exact name): {old_count:,} ({100*old_count/total:.1f}%)")
    print(f"  New (scan + enriched, M&A types only):               {with_signal:,} ({100*with_signal/total:.1f}%)")
    delta = old_count - with_signal
    print(f"  Reduction:                                            {delta:,} ({100*delta/total:.1f}% removed as noise)")

    # --- Figure ---
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))

    # Left: mention type breakdown
    ax = axes[0]
    plot_types = [(t, n) for t, n in sorted(by_type.items(), key=lambda x: -x[1]) if t != "enriched_pipeline"]
    if plot_types:
        labels, vals = zip(*plot_types)
        pcts = [100 * v / total for v in vals]
        bars = ax.barh(labels, pcts, color="#2196F3", alpha=0.85)
        ax.set_xlabel("% of nanotech Phase II cohort", fontsize=10)
        ax.set_title("M&A signal types\n(firms may have multiple)", fontsize=10)
        for bar, pct in zip(bars, pcts):
            ax.text(pct + 0.05, bar.get_y() + bar.get_height() / 2,
                    f"{pct:.1f}%", va="center", fontsize=8)

    # Right: by agency
    ax2 = axes[1]
    ag_labels, ag_rates, ag_ns = [], [], []
    for ag, s in sorted(ag_stats.items(), key=lambda x: -x[1]["signal"]):
        if s["n"] >= 20:
            short = ag.replace("Department of ", "Dept. ").replace("National ", "")[:28]
            ag_labels.append(f"{short} (n={s['n']})")
            ag_rates.append(100 * s["signal"] / s["n"])
            ag_ns.append(s["n"])
    if ag_labels:
        bars2 = ax2.barh(ag_labels, ag_rates, color="#FF9800", alpha=0.85)
        ax2.set_xlabel("% with M&A signal", fontsize=10)
        ax2.set_title("M&A signal rate by agency\n(scan + enriched, M&A types only)", fontsize=10)
        avg = 100 * with_signal / total
        ax2.axvline(avg, color="gray", linestyle="--", linewidth=1, label=f"Avg {avg:.1f}%")
        ax2.legend(fontsize=9)
        for bar, rate in zip(bars2, ag_rates):
            ax2.text(rate + 0.1, bar.get_y() + bar.get_height() / 2,
                     f"{rate:.1f}%", va="center", fontsize=8)

    fig.suptitle("Nanotech SBIR Phase II: M&A signal from EDGAR scan\n"
                 "(filtered to M&A mention types; noise types excluded)",
                 fontsize=11, fontweight="bold")
    fig.tight_layout()
    fig_path = paths.analysis_dir / ("nano_ma_signal.png" if paths.legacy else "ma_signal.png")
    fig.savefig(fig_path, dpi=150)
    plt.close(fig)
    print(f"\nFigure saved: {fig_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
