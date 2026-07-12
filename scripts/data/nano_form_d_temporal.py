#!/usr/bin/env python3
"""
Temporal Form D analysis for nanotech SBIR Phase II cohort.

For each high-confidence Form D match in the keyword cohort, filter to offerings
where filing_date > phase_ii_end_date. This establishes temporal ordering — a
necessary (not sufficient) condition for treating private investment as evidence
of post-Phase-II commercialization.

Inputs:
  data/nano_cohort_keyword.csv          — built by build_nano_cohort.py
  data/form_d_details.jsonl             — full Form D records with per-offering dates

Outputs:
  data/nano_form_d_post_phase2.csv      — one row per award with post-Phase II Form D signal
  data/analysis/nano_form_d_temporal.png

Path convention:
  --area <id>   → data/reports/<id>/form_d_post_phase2.csv
  (no flag)     → data/nano_form_d_post_phase2.csv  (legacy PR #428)

Usage:
  python scripts/data/nano_form_d_temporal.py [--area AREA] [--legacy]
"""

import csv
import json
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

REPO = Path(__file__).resolve().parents[2]
DATA = REPO / "data"
ANALYSIS_DIR = DATA / "analysis"
ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)

PHASE_II_TYPICAL_DURATION_YEARS = 2  # fallback when contract_end_date absent


def parse_date(s: str) -> date | None:
    if not s or not s.strip():
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y/%m/%d"):
        try:
            from datetime import datetime
            return datetime.strptime(s.strip(), fmt).date()
        except ValueError:
            continue
    return None


def phase_ii_end(row: dict) -> tuple[date | None, str]:
    """
    Return (end_date, source) for a Phase II award row.
    source is 'contract_end_date' or 'award_year_plus_2_fallback'.
    """
    d = parse_date(row.get("contract_end_date", ""))
    if d:
        return d, "contract_end_date"
    yr = int(float(row.get("award_year", 0) or 0))
    if yr >= 1980:
        return date(yr + PHASE_II_TYPICAL_DURATION_YEARS, 9, 30), "award_year_plus_2_fallback"
    return None, "unknown"


def load_form_d_high_conf(jsonl_path: Path) -> dict[str, dict]:
    """
    Load high-confidence Form D records keyed by uppercase company name.
    Retains full offering list with filing_date for temporal filtering.
    """
    by_name: dict[str, dict] = {}
    if not jsonl_path.exists():
        print(f"  WARNING: {jsonl_path} not found", file=sys.stderr)
        return by_name
    with open(jsonl_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("match_confidence", {}).get("tier") != "high":
                continue
            name = rec.get("company_name", "").strip().upper()
            if not name:
                continue
            offerings = [
                o for o in rec.get("offerings", [])
                if o.get("filing_date")
            ]
            by_name[name] = {
                "cik": rec.get("form_d_cik", ""),
                "match_score": rec.get("match_confidence", {}).get("score", 0.0),
                "offerings": offerings,
            }
    return by_name


def temporal_join(award: dict, form_d: dict) -> dict | None:
    """
    Find Form D offerings that post-date the Phase II end date.
    Returns enriched dict if any exist, else None.
    """
    end_date, end_source = phase_ii_end(award)
    if end_date is None:
        return None

    post_offerings = [
        o for o in form_d["offerings"]
        if parse_date(o.get("filing_date", "")) and parse_date(o["filing_date"]) > end_date
    ]
    if not post_offerings:
        return None

    post_offerings_sorted = sorted(post_offerings, key=lambda o: o["filing_date"])
    first = post_offerings_sorted[0]
    first_date = parse_date(first["filing_date"])
    lag_days = (first_date - end_date).days

    total_raised = sum(
        float(o.get("total_amount_sold") or 0) for o in post_offerings
    )
    sec_types = sorted(set(
        t for o in post_offerings for t in o.get("securities_types", [])
    ))

    return {
        "form_d_cik": form_d["cik"],
        "form_d_match_score": form_d["match_score"],
        "phase_ii_end_date": end_date.isoformat(),
        "phase_ii_end_source": end_source,
        "form_d_post_p2_offerings_n": len(post_offerings),
        "form_d_post_p2_first_date": first["filing_date"],
        "form_d_post_p2_lag_days": lag_days,
        "form_d_post_p2_total_raised": total_raised,
        "form_d_post_p2_securities_types": "|".join(sec_types),
    }


def main() -> int:
    import argparse

    try:
        from sbir_etl.utils.transition_report_paths import add_area_args, resolve_area_paths
    except ImportError:
        sys.path.insert(0, str(REPO))
        from sbir_etl.utils.transition_report_paths import add_area_args, resolve_area_paths

    parser = argparse.ArgumentParser(description=__doc__)
    add_area_args(parser)
    args = parser.parse_args()
    # Unflagged keeps PR #428 data/nano_* paths; --area X → data/reports/X/.
    paths = resolve_area_paths(args)
    legacy = paths.legacy

    cohort_csv = paths.artifact("cohort_keyword")
    form_d_jsonl = DATA / "form_d_details.jsonl"
    out_csv = paths.artifact("form_d_post_phase2")
    fig_name = "nano_form_d_temporal.png" if legacy else "form_d_temporal.png"

    if not cohort_csv.exists():
        print(
            f"ERROR: {cohort_csv} not found — run "
            f"build_tech_area_cohort.py --area {paths.area_id} first "
            f"(or build_nano_cohort.py for --legacy)",
            file=sys.stderr,
        )
        return 1

    print(f"Loading keyword cohort ({paths.area_id}{', legacy' if legacy else ''})...")
    with open(cohort_csv, newline="", encoding="utf-8") as f:
        awards = list(csv.DictReader(f))
    print(f"  {len(awards):,} Phase II awards")

    print("Loading Form D details (high-confidence only)...")
    form_d_by_name = load_form_d_high_conf(form_d_jsonl)
    print(f"  {len(form_d_by_name):,} high-confidence firms")

    print("Running temporal join...")
    results = []
    stats = defaultdict(int)

    for aw in awards:
        company_upper = aw.get("company", "").strip().upper()
        fd = form_d_by_name.get(company_upper)

        end_date, end_source = phase_ii_end(aw)

        row = dict(aw)
        row["phase_ii_end_date"] = end_date.isoformat() if end_date else ""
        row["phase_ii_end_source"] = end_source

        if fd is None:
            stats["no_form_d_match"] += 1
            row["form_d_match"] = False
            row["form_d_post_p2"] = False
        elif end_date is None:
            stats["form_d_match_no_anchor"] += 1
            row["form_d_match"] = True
            row["form_d_post_p2"] = False
            row["form_d_post_p2_note"] = "CANNOT_DETERMINE_ANCHOR"
        else:
            temporal = temporal_join(aw, fd)
            if temporal:
                stats["form_d_post_p2"] += 1
                row["form_d_match"] = True
                row["form_d_post_p2"] = True
                row.update(temporal)
                # Also flag if Phase II is still active (end_date in future)
                if end_date > date.today():
                    stats["form_d_post_p2_active_award"] += 1
                    row["form_d_post_p2_note"] = "AWARD_STILL_ACTIVE"
                else:
                    stats["form_d_post_p2_mature"] += 1
                    row["form_d_post_p2_note"] = ""
            else:
                stats["form_d_match_predates_p2"] += 1
                row["form_d_match"] = True
                row["form_d_post_p2"] = False
                row["form_d_post_p2_note"] = "ALL_OFFERINGS_PREDATE_PHASE_II_END"

        results.append(row)

    # Write output CSV. Build the header from the union of keys across all rows,
    # not just results[0]: the Form D detail columns are attached only to matched
    # rows, so keying off the first (usually unmatched) row would silently drop
    # them via extrasaction="ignore".
    fieldnames = list(dict.fromkeys(key for row in results for key in row))
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        w.writerows(results)
    print(f"  Written: {out_csv} ({len(results):,} rows)")

    # Summary stats
    total = len(awards)
    n_match = stats["form_d_post_p2"]
    n_mature = stats["form_d_post_p2_mature"]
    n_active = stats["form_d_post_p2_active_award"]
    n_predate = stats["form_d_match_predates_p2"]

    post_p2 = [r for r in results if r.get("form_d_post_p2") == True]

    print()
    print("=" * 60)
    print("FORM D TEMPORAL ANALYSIS — KEYWORD COHORT")
    print("=" * 60)
    print(f"Total nanotech Phase II awards:     {total:,}")
    print(f"Awards with high-conf Form D match: {total - stats['no_form_d_match']:,} ({100*(total-stats['no_form_d_match'])/total:.1f}%)")
    print()
    print("Of matched awards:")
    print(f"  Post-Phase II Form D (any):       {n_match:,} ({100*n_match/total:.1f}% of cohort)")
    print(f"    of which, award now mature:     {n_mature:,}")
    print(f"    of which, award still active:   {n_active:,}  ← temporal filter is weaker here")
    print(f"  All offerings predate Phase II:   {n_predate:,}  ← would inflate unadjusted count")
    print(f"  No date anchor available:         {stats['form_d_match_no_anchor']:,}")
    print()
    # Unadjusted rate comes from the cohort CSV's own sig_form_d_detected column
    # (written by build_nano_cohort.py) so it tracks upstream changes.
    if awards and "sig_form_d_detected" in awards[0]:
        unadj_n = sum(1 for r in awards if r.get("sig_form_d_detected") == "True")
        print(f"Unadjusted Form D rate (build_nano_cohort):  {100*unadj_n/total:.1f}% ({unadj_n} awards)")
    else:
        print("Unadjusted Form D rate (build_nano_cohort):  n/a — sig_form_d_detected column absent")
    print(f"Temporally-filtered rate (this script):      {100*n_match/total:.1f}% ({n_match} awards)")
    print(f"Mature-only (strongest claim):               {100*n_mature/total:.1f}% ({n_mature} awards)")
    print()

    # By agency
    agency_counts: dict[str, dict] = defaultdict(lambda: {"total": 0, "post_p2": 0})
    for r in results:
        ag = r.get("agency", "Unknown")
        agency_counts[ag]["total"] += 1
        if r.get("form_d_post_p2") == True:
            agency_counts[ag]["post_p2"] += 1

    print("Post-Phase II Form D by agency:")
    for ag, c in sorted(agency_counts.items(), key=lambda x: -x[1]["post_p2"]):
        if c["post_p2"] > 0:
            print(f"  {ag[:45]:<45} {c['post_p2']:>4} / {c['total']:>4} ({100*c['post_p2']/c['total']:.1f}%)")

    # Capital raised distribution
    amounts = [
        float(r.get("form_d_post_p2_total_raised", 0) or 0)
        for r in post_p2
        if r.get("form_d_post_p2_total_raised")
    ]
    if amounts:
        amounts_sorted = sorted(amounts)
        n = len(amounts_sorted)
        print()
        print("Post-Phase II capital raised:")
        print(f"  Median:  ${amounts_sorted[n//2]/1e6:.2f}M")
        print(f"  75th:    ${amounts_sorted[int(n*0.75)]/1e6:.2f}M")
        print(f"  90th:    ${amounts_sorted[int(n*0.90)]/1e6:.2f}M")
        print(f"  Total:   ${sum(amounts)/1e6:.1f}M across {n} awards")

    # Lag distribution
    lags = [
        int(r.get("form_d_post_p2_lag_days", 0) or 0)
        for r in post_p2
        if r.get("form_d_post_p2_lag_days")
    ]
    if lags:
        lags_sorted = sorted(lags)
        n = len(lags_sorted)
        print()
        print("Lag from Phase II end to first Form D offering:")
        print(f"  Median:  {lags_sorted[n//2]} days ({lags_sorted[n//2]//365:.1f} yr)")
        print(f"  25th:    {lags_sorted[n//4]} days")
        print(f"  75th:    {lags_sorted[int(n*0.75)]} days ({lags_sorted[int(n*0.75)]//365:.1f} yr)")
        neg = sum(1 for l in lags if l < 0)
        if neg:
            print(f"  NOTE: {neg} negative lags — Phase II end_date is fallback estimate")

    # Figure: lag histogram
    if lags:
        fig, axes = plt.subplots(1, 2, figsize=(12, 5))

        # Left: lag histogram
        ax = axes[0]
        ax.hist([l / 365 for l in lags], bins=30, color="#2196F3", alpha=0.8, edgecolor="white")
        ax.axvline(0, color="red", linestyle="--", linewidth=1.5, label="Phase II ends")
        ax.set_xlabel("Years after Phase II end date", fontsize=11)
        ax.set_ylabel("Number of awards", fontsize=11)
        ax.set_title("Time from Phase II end to first\npost-Phase II Form D filing", fontsize=11)
        ax.legend(fontsize=9)

        # Right: by agency
        ax2 = axes[1]
        ag_labels = []
        ag_rates = []
        for ag, c in sorted(agency_counts.items(), key=lambda x: -x[1]["post_p2"]):
            if c["total"] >= 10:  # only agencies with meaningful sample
                short = ag.replace("Department of ", "").replace("National ", "")[:25]
                ag_labels.append(f"{short}\n(n={c['total']})")
                ag_rates.append(100 * c["post_p2"] / c["total"])
        bars = ax2.barh(ag_labels, ag_rates, color="#FF9800", alpha=0.85)
        ax2.set_xlabel("% with post-Phase II Form D", fontsize=11)
        ax2.set_title("Post-Phase II Form D rate by agency\n(high-confidence matches, temporally filtered)", fontsize=10)
        ax2.axvline(100 * n_match / total, color="gray", linestyle="--", linewidth=1,
                    label=f"Cohort avg {100*n_match/total:.1f}%")
        ax2.legend(fontsize=9)
        for bar, rate in zip(bars, ag_rates):
            ax2.text(rate + 0.3, bar.get_y() + bar.get_height() / 2,
                     f"{rate:.1f}%", va="center", fontsize=9)

        fig.suptitle(
            f"{paths.area_id}: Form D private investment (temporally filtered)",
            fontsize=12, fontweight="bold",
        )
        fig.tight_layout()
        fig_path = paths.analysis_dir / fig_name
        fig.savefig(fig_path, dpi=150)
        plt.close(fig)
        print()
        print(f"Figure saved: {fig_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
