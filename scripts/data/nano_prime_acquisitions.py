#!/usr/bin/env python3
"""
Targeted acquisition analysis: nanotech SBIR Phase II firms acquired by
large defense or pharma/medtech primes, with temporal filtering.

Detection method:
  sec_edgar_scan.jsonl mention_filers in M&A-typed filings → match against
  curated prime acquirer list. Cross-references enriched_sbir_ma_events.jsonl
  acquirer field as a secondary signal.

Temporal filter:
  ma_latest_date > phase_ii_end_date. Note: ma_latest_date is the most recent
  SEC mention date, not the exact acquisition date. It is an upper bound on
  when the acquisition became visible in filings. For mature awards this is
  a necessary (not sufficient) condition for post-Phase-II acquisition.

Inputs:
  data/nano_cohort_keyword.csv          — 2,849 nanotech Phase II awards
  data/sec_edgar_scan.jsonl             — full EDGAR scan, 35k firms
  data/enriched_sbir_ma_events.jsonl    — M&A enrichment with confidence/acquirer
  data/nano_form_d_post_phase2.csv      — phase_ii_end_date per award

Outputs:
  data/nano_prime_acquisitions.csv      — award-grain rows with prime match
  data/analysis/nano_prime_acquisitions.png

Usage:
  python scripts/data/nano_prime_acquisitions.py
"""

import csv
import json
import sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

REPO = Path(__file__).resolve().parents[2]
DATA = REPO / "data"
ANALYSIS_DIR = DATA / "analysis"
ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)

# --- Prime acquirer registry ---
# Maps exact SEC filer name (uppercase) → (category, short label)
# These are the filer names as they appear in sec_edgar_scan.jsonl mention_filers.
# CIK normalization is not available, so each variant gets its own entry.
PRIME_FILERS: dict[str, tuple[str, str]] = {
    # ── Defense primes ──
    "L 3 COMMUNICATIONS HOLDINGS INC":  ("defense", "L3 Technologies"),
    "L3 COMMUNICATIONS CORP":           ("defense", "L3 Technologies"),
    "L3HARRIS TECHNOLOGIES, INC. /DE/": ("defense", "L3Harris"),
    "HARRIS CORP /DE/":                 ("defense", "Harris Corp"),
    "MERCURY SYSTEMS INC":              ("defense", "Mercury Systems"),
    "MERCURY COMPUTER SYSTEMS INC":     ("defense", "Mercury Systems"),
    "CUBIC CORP /DE/":                  ("defense", "Cubic Corp"),
    "FLIR SYSTEMS INC":                 ("defense", "FLIR Systems"),
    "TELEDYNE TECHNOLOGIES INC":        ("defense", "Teledyne"),
    "TELEDYNE TECHNOLOGIES":            ("defense", "Teledyne"),
    "LOCKHEED MARTIN CORP":             ("defense", "Lockheed Martin"),
    "RAYTHEON CO":                      ("defense", "Raytheon"),
    "RAYTHEON TECHNOLOGIES CORP":       ("defense", "RTX"),
    "RTX CORP":                         ("defense", "RTX"),
    "BOEING CO":                        ("defense", "Boeing"),
    "NORTHROP GRUMMAN CORP":            ("defense", "Northrop Grumman"),
    "GENERAL DYNAMICS CORP":            ("defense", "General Dynamics"),
    "BAE SYSTEMS PLC":                  ("defense", "BAE Systems"),
    "LEIDOS HOLDINGS, INC.":            ("defense", "Leidos"),
    "SCIENCE APPLICATIONS INTERNATIONAL CORP": ("defense", "SAIC"),
    "TEXTRON INC":                      ("defense", "Textron"),
    "DRS TECHNOLOGIES INC":             ("defense", "DRS Technologies"),
    "LEONARDO DRS, INC.":               ("defense", "Leonardo DRS"),
    "ELBIT SYSTEMS OF AMERICA LLC":     ("defense", "Elbit Systems"),
    "VIAVI SOLUTIONS INC.":             ("defense", "Viavi Solutions"),
    "CURTISS-WRIGHT CORP":              ("defense", "Curtiss-Wright"),
    # ── Pharma / MedTech primes ──
    "BARD C R INC /NJ/":               ("pharma", "C.R. Bard"),
    "BECTON DICKINSON AND CO":          ("pharma", "Becton Dickinson"),
    "MERCK & CO INC":                   ("pharma", "Merck"),
    "PFIZER INC":                       ("pharma", "Pfizer"),
    "JOHNSON & JOHNSON":                ("pharma", "Johnson & Johnson"),
    "ABBOTT LABORATORIES":              ("pharma", "Abbott"),
    "MEDTRONIC PLC":                    ("pharma", "Medtronic"),
    "MEDTRONIC INC":                    ("pharma", "Medtronic"),
    "STRYKER CORP":                     ("pharma", "Stryker"),
    "BOSTON SCIENTIFIC CORP":           ("pharma", "Boston Scientific"),
    "EDWARDS LIFESCIENCES CORP":        ("pharma", "Edwards Lifesciences"),
    "THERMO FISHER SCIENTIFIC INC.":    ("pharma", "Thermo Fisher"),
    "ILLUMINA, INC.":                   ("pharma", "Illumina"),
    "LUMINEX CORP":                     ("pharma", "Luminex"),
    "PERKINELMER INC":                  ("pharma", "PerkinElmer"),
    "AGILENT TECHNOLOGIES INC":         ("pharma", "Agilent"),
    "DANAHER CORP":                     ("pharma", "Danaher"),
    "HOLOGIC INC":                      ("pharma", "Hologic"),
    "BRUKER CORP":                      ("pharma", "Bruker"),
    "BIORAD LABORATORIES INC":          ("pharma", "Bio-Rad"),
    "ROPER TECHNOLOGIES, INC.":         ("pharma", "Roper Technologies"),
}

# M&A mention types that indicate the SBIR firm is the transaction target
MA_SIGNAL_TYPES = frozenset({
    "ma_definitive", "ma_proxy", "acquisition", "subsidiary", "ownership_active",
})

# Only count definitive / strongest evidence for high-confidence flag
MA_HIGH_CONF_TYPES = frozenset({"ma_definitive", "acquisition"})


def parse_date(s: str) -> date | None:
    if not s or not str(s).strip():
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(str(s).strip(), fmt).date()
        except ValueError:
            continue
    return None


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
    """Load enriched_sbir_ma_events.jsonl indexed by uppercase company name."""
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


def find_prime_filers(filers: list[str]) -> list[tuple[str, str, str]]:
    """
    Check a list of SEC filer names against the prime registry.
    Returns list of (filer_name, category, label).
    HARRIS & HARRIS GROUP is excluded — it's a VC firm, not Harris Corp.
    """
    hits = []
    for filer in filers:
        fu = filer.strip().upper()
        if fu in PRIME_FILERS and "HARRIS & HARRIS" not in fu:
            cat, label = PRIME_FILERS[fu]
            hits.append((filer.strip(), cat, label))
    return hits


def load_temporal_anchors(path: Path) -> dict[str, dict[str, str]]:
    """
    Load phase_ii_end_date per award from nano_form_d_post_phase2.csv.
    Returns {award_id → {phase_ii_end_date, phase_ii_end_source}}.
    """
    anchors: dict[str, dict[str, str]] = {}
    if not path.exists():
        return anchors
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            aid = row.get("award_id", "")
            if aid:
                anchors[aid] = {
                    "phase_ii_end_date": row.get("phase_ii_end_date", ""),
                    "phase_ii_end_source": row.get("phase_ii_end_source", ""),
                }
    return anchors


def main() -> int:
    cohort_csv = DATA / "nano_cohort_keyword.csv"
    scan_jsonl  = DATA / "sec_edgar_scan.jsonl"
    enriched_jsonl = DATA / "enriched_sbir_ma_events.jsonl"
    temporal_csv = DATA / "nano_form_d_post_phase2.csv"

    for p in (cohort_csv,):
        if not p.exists():
            print(f"ERROR: {p} not found — run build_nano_cohort.py first", file=sys.stderr)
            return 1

    print("Loading nanotech keyword cohort...")
    with open(cohort_csv, newline="", encoding="utf-8") as f:
        awards = list(csv.DictReader(f))
    print(f"  {len(awards):,} Phase II awards, "
          f"{len({r['company'].upper() for r in awards}):,} unique firms")

    print("Loading EDGAR full scan...")
    scan = load_scan(scan_jsonl)
    print(f"  {len(scan):,} firms in scan")

    print("Loading enriched M&A events...")
    enriched = load_enriched(enriched_jsonl)
    print(f"  {len(enriched):,} firms in enriched index")

    print("Loading temporal anchors from nano_form_d_post_phase2.csv...")
    temporal = load_temporal_anchors(temporal_csv)
    print(f"  {len(temporal):,} awards with phase_ii_end_date")

    print("Scanning for prime acquisitions...")
    results: list[dict] = []

    for aw in awards:
        name_upper = aw.get("company", "").strip().upper()
        award_id   = aw.get("award_id", "")

        scan_rec     = scan.get(name_upper)
        enriched_rec = enriched.get(name_upper)
        temporal_rec = temporal.get(award_id, {})

        # ── Phase II end date ──
        phase_ii_end_str = temporal_rec.get("phase_ii_end_date", "")
        phase_ii_end_src = temporal_rec.get("phase_ii_end_source", "")
        # Fallback: infer from award_year if temporal CSV didn't have it
        if not phase_ii_end_str:
            yr = int(float(aw.get("award_year", 0) or 0))
            if yr >= 1980:
                phase_ii_end_str = f"{yr + 2}-09-30"
                phase_ii_end_src = "award_year_plus_2_fallback"

        phase_ii_end_d = parse_date(phase_ii_end_str)

        # ── EDGAR scan: find prime filers ──
        prime_hits: list[tuple[str, str, str]] = []
        ma_date_str = ""
        ma_mention_types: list[str] = []

        if scan_rec:
            all_types = set(scan_rec.get("mention_types") or [])
            ma_mention_types = sorted(all_types & MA_SIGNAL_TYPES)
            if ma_mention_types:
                filers = scan_rec.get("mention_filers") or []
                prime_hits = find_prime_filers(filers)
                ma_date_str = scan_rec.get("latest_mention_date", "") or ""

        # ── Enriched: secondary acquirer check ──
        enriched_acquirer = ""
        enriched_confidence = ""
        if enriched_rec:
            enriched_acquirer = enriched_rec.get("acquirer", "") or ""
            enriched_confidence = enriched_rec.get("confidence", "") or ""
            # Also check if enriched acquirer itself is a prime
            ea_upper = enriched_acquirer.strip().upper()
            if ea_upper in PRIME_FILERS and not any(h[2] == PRIME_FILERS[ea_upper][1] for h in prime_hits):
                cat, label = PRIME_FILERS[ea_upper]
                prime_hits.append((enriched_acquirer.strip(), cat, label, "enriched_acquirer"))

        if not prime_hits:
            continue  # Skip awards with no prime match

        # ── Temporal filter ──
        ma_date_d = parse_date(ma_date_str)
        temporal_ok: bool | None = None  # None = cannot determine
        temporal_note = ""

        if phase_ii_end_d and ma_date_d:
            temporal_ok = ma_date_d > phase_ii_end_d
            if temporal_ok:
                lag_days = (ma_date_d - phase_ii_end_d).days
                temporal_note = f"POST_PHASE_II (lag {lag_days}d)"
            else:
                lag_days = (phase_ii_end_d - ma_date_d).days
                temporal_note = f"PREDATES_PHASE_II_END ({lag_days}d before)"
        elif not phase_ii_end_d:
            temporal_note = "NO_PHASE_II_END_DATE"
        else:
            temporal_note = "NO_MA_DATE"

        # ── Confidence level ──
        # High: ma_definitive or acquisition type + prime in scan filers
        # Medium: ma_proxy or subsidiary + prime in scan filers, or enriched high conf
        high_conf_types = set(ma_mention_types) & MA_HIGH_CONF_TYPES
        if high_conf_types and prime_hits:
            confidence = "high"
        elif ma_mention_types and prime_hits:
            confidence = "medium"
        elif enriched_confidence == "high":
            confidence = "medium"  # enriched acquirer match without scan corroboration
        else:
            confidence = "low"

        # Emit one row per prime hit (firm can be acquired by multiple primes in different filings)
        for hit in prime_hits:
            filer_name = hit[0]
            prime_cat  = hit[1]
            prime_label = hit[2]
            signal_src  = hit[3] if len(hit) > 3 else "scan_filer"

            results.append({
                "award_id":              award_id,
                "company":               aw.get("company", ""),
                "agency":                aw.get("agency", ""),
                "award_year":            aw.get("award_year", ""),
                "award_amount":          aw.get("award_amount", ""),
                "title":                 aw.get("title", "")[:80],
                "phase_ii_end_date":     phase_ii_end_str,
                "phase_ii_end_source":   phase_ii_end_src,
                "acquiring_prime":       prime_label,
                "acquiring_prime_filer": filer_name,
                "prime_category":        prime_cat,
                "ma_date":               ma_date_str,
                "ma_mention_types":      "|".join(ma_mention_types),
                "signal_source":         signal_src,
                "temporal_ok":           "" if temporal_ok is None else str(temporal_ok),
                "temporal_note":         temporal_note,
                "confidence":            confidence,
                "enriched_acquirer":     enriched_acquirer,
                "enriched_confidence":   enriched_confidence,
            })

    if not results:
        print("No prime acquisitions found.")
        return 0

    # Write output CSV
    out_csv = DATA / "nano_prime_acquisitions.csv"
    fieldnames = list(results[0].keys())
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(results)
    print(f"  Written: {out_csv} ({len(results):,} rows)")

    # ── Summary ──
    print()
    print("=" * 65)
    print("PRIME ACQUISITION SUMMARY — NANOTECH KEYWORD COHORT")
    print("=" * 65)

    total_awards = len(awards)
    unique_firms = len({r["company"].upper() for r in results})
    unique_awards = len({r["award_id"] for r in results})
    post_p2 = [r for r in results if r["temporal_ok"] == "True"]
    pre_p2  = [r for r in results if r["temporal_ok"] == "False"]
    no_date = [r for r in results if r["temporal_ok"] == ""]

    print(f"Nanotech Phase II cohort size:      {total_awards:,} awards")
    print(f"Awards with prime match (any):      {unique_awards:,}  ({100*unique_awards/total_awards:.1f}%)")
    print(f"Unique firms with prime match:       {unique_firms:,}")
    print()
    print("Temporal filter breakdown (rows, not awards):")
    print(f"  Post-Phase II (temporal_ok):       {len(post_p2):,}")
    print(f"  Predates Phase II end:             {len(pre_p2):,}")
    print(f"  Cannot determine (no dates):       {len(no_date):,}")

    # By confidence
    conf_counts: dict[str, int] = defaultdict(int)
    for r in results:
        conf_counts[r["confidence"]] += 1
    print()
    print("By confidence tier:")
    for conf, n in sorted(conf_counts.items(), key=lambda x: -x[1]):
        print(f"  {conf:<10} {n:>3}")

    # By prime
    print()
    print("By acquiring prime:")
    prime_firms: dict[str, set] = defaultdict(set)
    prime_post_p2: dict[str, int] = defaultdict(int)
    prime_cat_map: dict[str, str] = {}
    for r in results:
        prime_firms[r["acquiring_prime"]].add(r["company"].upper())
        prime_cat_map[r["acquiring_prime"]] = r["prime_category"]
        if r["temporal_ok"] == "True":
            prime_post_p2[r["acquiring_prime"]] += 1

    for prime, firms in sorted(prime_firms.items(), key=lambda x: -len(x[1])):
        cat = prime_cat_map[prime]
        n_firms = len(firms)
        n_post = prime_post_p2.get(prime, 0)
        print(f"  [{cat:7}] {prime:<25}  {n_firms} firm(s)  post-P2:{n_post}")

    # By agency
    print()
    print("By funding agency (post-Phase II temporal filter):")
    ag_firms: dict[str, set] = defaultdict(set)
    for r in post_p2:
        ag_firms[r["agency"]].add(r["company"].upper())
    for ag, firms in sorted(ag_firms.items(), key=lambda x: -len(x[1])):
        print(f"  {ag[:50]:<50}  {len(firms)} firm(s)")

    # Detailed listing
    print()
    print("Detailed matches (post-Phase II, or unknown temporal):")
    print("-" * 65)
    shown: set[tuple] = set()
    for r in sorted(results, key=lambda x: (x["prime_category"], x["acquiring_prime"], x["company"])):
        if r["temporal_ok"] == "False":
            continue  # skip confirmed pre-Phase-II
        key = (r["company"].upper(), r["acquiring_prime"])
        if key in shown:
            continue
        shown.add(key)
        print(f"  [{r['prime_category']:7}] {r['acquiring_prime']:<25}  ←  {r['company']}")
        print(f"           Agency: {r['agency'][:45]}  Year: {r['award_year']}")
        print(f"           Phase II end: {r['phase_ii_end_date'] or '?'} ({r['phase_ii_end_source']})")
        print(f"           MA date: {r['ma_date'] or '?'}   Types: {r['ma_mention_types']}")
        print(f"           Temporal: {r['temporal_note']}   Confidence: {r['confidence']}")
        if r["enriched_acquirer"]:
            print(f"           Enriched acquirer: {r['enriched_acquirer']} [{r['enriched_confidence']}]")
        print()

    # Figure
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))

    # Left: prime bar chart (unique firms)
    ax = axes[0]
    primes_sorted = sorted(prime_firms.items(), key=lambda x: len(x[1]))
    plabels = [f"{p} [{prime_cat_map[p][0].upper()}]" for p, _ in primes_sorted]
    pvals   = [len(firms) for _, firms in primes_sorted]
    colors  = ["#1565C0" if prime_cat_map[p] == "defense" else "#6A1B9A"
               for p, _ in primes_sorted]
    bars = ax.barh(plabels, pvals, color=colors, alpha=0.85)
    ax.set_xlabel("Unique nanotech SBIR firms", fontsize=10)
    ax.set_title("SBIR firm acquisitions by prime\n[D]=defense  [P]=pharma/medtech", fontsize=10)
    for bar, val in zip(bars, pvals):
        ax.text(val + 0.03, bar.get_y() + bar.get_height() / 2,
                str(val), va="center", fontsize=9)
    # Custom legend
    from matplotlib.patches import Patch
    ax.legend(handles=[
        Patch(color="#1565C0", alpha=0.85, label="Defense prime"),
        Patch(color="#6A1B9A", alpha=0.85, label="Pharma/MedTech prime"),
    ], fontsize=9)

    # Right: agency breakdown (post-P2 only)
    ax2 = axes[1]
    if post_p2:
        ag_awards: dict[str, int] = defaultdict(int)
        for r in post_p2:
            ag_awards[r["agency"]] += 1
        ag_data = sorted(ag_awards.items(), key=lambda x: x[1])
        alabels = [ag.replace("Department of ", "").replace("National ", "")[:30]
                   for ag, _ in ag_data]
        avals = [n for _, n in ag_data]
        ax2.barh(alabels, avals, color="#00897B", alpha=0.85)
        ax2.set_xlabel("Awards (post-Phase II temporal filter)", fontsize=10)
        ax2.set_title("Post-Phase II prime acquisitions\nby funding agency", fontsize=10)
        for i, (bar, val) in enumerate(zip(ax2.patches, avals)):
            ax2.text(val + 0.03, bar.get_y() + bar.get_height() / 2,
                     str(val), va="center", fontsize=9)
    else:
        ax2.text(0.5, 0.5, "No post-Phase II matches\nwith known temporal ordering",
                 ha="center", va="center", transform=ax2.transAxes, fontsize=10)

    fig.suptitle(
        "Nanotech SBIR Phase II: Acquisitions by defense and pharma/medtech primes\n"
        "(EDGAR mention_filers in M&A-typed filings, matched to curated prime list)",
        fontsize=11, fontweight="bold",
    )
    fig.tight_layout()
    fig_path = ANALYSIS_DIR / "nano_prime_acquisitions.png"
    fig.savefig(fig_path, dpi=150)
    plt.close(fig)
    print(f"Figure saved: {fig_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
