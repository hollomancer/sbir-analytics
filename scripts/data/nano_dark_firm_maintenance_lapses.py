#!/usr/bin/env python3
"""
Patent maintenance-fee lapse check for the dark firm buckets.

Utility patents require maintenance fees at 3.5, 7.5, and 11.5 years post-grant
to remain in force; missing one (past a 6-month late-with-surcharge grace
period) produces an EXP. ("Patent Expired for Failure to Pay Maintenance
Fees") event. This is the first WEAK NEGATIVE signal in the dark-majority
instrument set — every prior instrument (patent liveness, trademarks, aliases,
subawards, sector registries) is a POSITIVE detector that can only ever raise
the observed floor. A firm that lets its entire patent portfolio lapse, with
no other channel showing activity, is evidence *suggestive of* disengagement —
not proof of dissolution (a firm can deliberately abandon patents while
remaining a healthy, pivoted, or trade-secret-based business).

Signal design:
  - Per-patent: lapsed = has an EXP. event with no LATER EXPX (reinstated)
    event for that same patent. (EXPX after EXP. means the owner paid late
    with surcharge and recovered the patent — not lapsed.)
  - Per-firm: computed only over patents old enough to have crossed their
    first fee checkpoint (grant date >= ~3.5 years before data currency);
    younger patents contribute no signal either way.
  - Firm-level dormancy flag: >=80% of a firm's checkpoint-eligible patents
    lapsed AND >=2 such patents (avoids single-patent noise).

Firm universe: restricted to the 582 dark firms already matched to patents at
HIGH CONFIDENCE in nano_dark_firm_liveness.py (state or inventor-PI
corroborated) — this reuses that script's verified name-matching rather than
re-deriving it, and keeps the assignee re-scan scoped to firms we already
trust the identity match for.

Path convention (same as nano_form_d_temporal.py / nano_ws1):
  --area <id>   → data/reports/<id>/dark_firm_maintenance_lapses.csv
  (no flag)     → data/nano_dark_firm_maintenance_lapses.csv  (legacy PR #428)

Inputs:
  dark_firm_liveness.csv (area-scoped)                — high-confidence firm matches
  data/raw/uspto/patentsview/g_assignee_disambiguated.tsv.zip  (global)
  data/raw/uspto/maintenance_fees/MaintFeeEvents_20260707.zip  (global)

Outputs:
  dark_firm_maintenance_lapses.csv          — one row per matched firm

Usage:
  python scripts/data/nano_dark_firm_maintenance_lapses.py [--area AREA] [--legacy]
"""

import argparse
import csv
import importlib.util
import io
import sys
import zipfile
from collections import defaultdict
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DATA = REPO / "data"
PV = DATA / "raw/uspto/patentsview"
MAINT_ZIP = DATA / "raw/uspto/maintenance_fees/MaintFeeEvents_20260707.zip"

sys.path.insert(0, str(REPO))
from sbir_etl.utils.text_normalization import normalize_name  # noqa: E402
from sbir_etl.utils.transition_report_paths import (  # noqa: E402
    ReportPaths,
    add_area_args,
    resolve_area_paths,
)

_liv_spec = importlib.util.spec_from_file_location(
    "nano_liveness", Path(__file__).parent / "nano_dark_firm_liveness.py"
)
liv_mod = importlib.util.module_from_spec(_liv_spec)
_liv_spec.loader.exec_module(liv_mod)

DATA_CURRENCY = date(2026, 7, 6)  # MaintFeeEvents_20260707.zip covers data through this date
FIRST_FEE_DUE_YEARS = 3.5
LAPSE_SHARE_THRESHOLD = 0.80
MIN_ELIGIBLE_PATENTS = 2


def _norm(s: str) -> str:
    return normalize_name(s, remove_suffixes=True)


def load_high_confidence_firms(paths: ReportPaths) -> dict[str, dict]:
    """High-confidence any-class patent matches from the liveness check."""
    path = paths.artifact("dark_firm_liveness")
    firms = {}
    for r in csv.DictReader(open(path, newline="", encoding="utf-8")):
        if r["match_confidence"] == "high":
            firms[r["normalized_name"]] = r
    return firms


def load_firm_patents(firm_norms: set[str]) -> dict[str, set[str]]:
    """Re-scan the assignee table for each matched firm's full patent portfolio."""
    firm_patents: dict[str, set[str]] = defaultdict(set)
    z = zipfile.ZipFile(PV / "g_assignee_disambiguated.tsv.zip")
    with z.open(z.infolist()[0].filename) as f:
        reader = csv.reader(io.TextIOWrapper(f, encoding="utf-8", newline=""), delimiter="\t")
        header = next(reader)
        idx = {c: i for i, c in enumerate(header)}
        for row in reader:
            org = row[idx["disambig_assignee_organization"]]
            if not org:
                continue
            norm = _norm(org)
            if norm in firm_norms:
                firm_patents[norm].add(row[idx["patent_id"]])
    return firm_patents


def load_grant_dates(patent_ids: set[str]) -> dict[str, date]:
    """Grant dates for the target patents, from the g_patent table."""
    grants: dict[str, date] = {}
    z = zipfile.ZipFile(PV / "g_patent.tsv.zip")
    with z.open(z.infolist()[0].filename) as f:
        reader = csv.reader(io.TextIOWrapper(f, encoding="utf-8", newline=""), delimiter="\t")
        header = next(reader)
        idx = {c: i for i, c in enumerate(header)}
        for row in reader:
            pid = row[idx["patent_id"]]
            if pid in patent_ids:
                try:
                    grants[pid] = date.fromisoformat(row[idx["patent_date"]])
                except ValueError:
                    pass
    return grants


def scan_maintenance_events(patent_ids: set[str]) -> dict[str, dict]:
    """Stream the fixed-width maintenance-fee file, filtered to target patents.

    Returns {patent_id: {"last_exp": date|None, "last_expx": date|None}}.
    Record layout (57 chars, positions 1-indexed per USPTO doc):
      1-13 patent#, 15-22 app#, 24 small-entity, 26-33 filing date,
      35-42 grant date, 44-51 event entry date, 53-57 event code.
    """
    result: dict[str, dict] = defaultdict(lambda: {"last_exp": None, "last_expx": None})
    z = zipfile.ZipFile(MAINT_ZIP)
    name = [n for n in z.namelist() if n.startswith("MaintFeeEvents_") and n.endswith(".txt")][0]
    n_lines = 0
    with z.open(name) as f:
        for raw in io.TextIOWrapper(f, encoding="ascii", errors="replace"):
            n_lines += 1
            line = raw.rstrip("\r\n")
            if len(line) < 57:
                continue
            patent_field = line[0:13].lstrip("0") or "0"
            if patent_field not in patent_ids:
                continue
            event_code = line[52:57].strip()
            event_date_s = line[43:51]
            try:
                event_date = date(int(event_date_s[:4]), int(event_date_s[4:6]), int(event_date_s[6:8]))
            except ValueError:
                continue
            if event_code == "EXP.":
                cur = result[patent_field]["last_exp"]
                if cur is None or event_date > cur:
                    result[patent_field]["last_exp"] = event_date
            elif event_code == "EXPX":
                cur = result[patent_field]["last_expx"]
                if cur is None or event_date > cur:
                    result[patent_field]["last_expx"] = event_date
    print(f"  Scanned {n_lines:,} maintenance-fee event records")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    add_area_args(parser)
    args = parser.parse_args(argv)
    paths = resolve_area_paths(args, argv)

    if not MAINT_ZIP.exists():
        print(f"ERROR: {MAINT_ZIP} not found — download via download_uspto.py "
              f"--product-file PTMNFEE2/MaintFeeEvents_20260707.zip --local {MAINT_ZIP.parent}",
              file=sys.stderr)
        return 1

    print("Loading high-confidence dark-firm patent matches...")
    firms = load_high_confidence_firms(paths)
    print(f"  {len(firms):,} high-confidence firms")

    print("Re-scanning assignee table for full patent portfolios...")
    firm_patents = load_firm_patents(set(firms))
    all_patents = set().union(*firm_patents.values()) if firm_patents else set()
    print(f"  {len(all_patents):,} distinct patents across {len(firm_patents):,} firms")

    print("Loading grant dates...")
    grants = load_grant_dates(all_patents)
    print(f"  {len(grants):,} grant dates resolved")

    print("Scanning maintenance-fee events (large file, streamed)...")
    events = scan_maintenance_events(all_patents)
    n_with_exp = sum(1 for v in events.values() if v["last_exp"])
    print(f"  {n_with_exp:,} patents have ≥1 EXP. event")

    def eligible(pid: str) -> bool:
        g = grants.get(pid)
        return g is not None and (DATA_CURRENCY - g).days >= FIRST_FEE_DUE_YEARS * 365.25

    def lapsed(pid: str) -> bool:
        ev = events.get(pid)
        if not ev or not ev["last_exp"]:
            return False
        return ev["last_expx"] is None or ev["last_expx"] < ev["last_exp"]

    out_rows = []
    for norm, rec in sorted(firms.items()):
        patents = firm_patents.get(norm, set())
        elig = [p for p in patents if eligible(p)]
        n_lapsed = sum(1 for p in elig if lapsed(p))
        share = n_lapsed / len(elig) if elig else None
        dormant = (share is not None and share >= LAPSE_SHARE_THRESHOLD
                  and len(elig) >= MIN_ELIGIBLE_PATENTS)
        out_rows.append({
            "company": rec["company"],
            "normalized_name": norm,
            "bucket": rec["bucket"],
            "total_patents": len(patents),
            "fee_eligible_patents": len(elig),
            "lapsed_patents": n_lapsed,
            "lapse_share": round(share, 3) if share is not None else "",
            "portfolio_dormant": dormant,
        })

    out_csv = paths.artifact("dark_firm_maintenance_lapses")
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(out_rows[0].keys()))
        w.writeheader()
        w.writerows(out_rows)
    print(f"\nWritten: {out_csv} ({len(out_rows):,} firms)")

    print()
    print("=" * 70)
    print("MAINTENANCE-FEE LAPSE SUMMARY")
    print("=" * 70)
    with_eligible = [r for r in out_rows if r["fee_eligible_patents"] > 0]
    dormant = [r for r in out_rows if r["portfolio_dormant"]]
    print(f"High-confidence firms: {len(out_rows):,}")
    print(f"  with >=1 fee-checkpoint-eligible patent: {len(with_eligible):,}")
    print(f"  flagged portfolio-dormant (>={LAPSE_SHARE_THRESHOLD:.0%} lapsed, "
          f">={MIN_ELIGIBLE_PATENTS} eligible patents): {len(dormant):,}")
    for bucket in ("FIRM_ACTIVITY_ABSENT", "ENTITY_RESOLUTION_FAILURE"):
        sub = [r for r in dormant if r["bucket"] == bucket]
        print(f"    {bucket}: {len(sub)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
