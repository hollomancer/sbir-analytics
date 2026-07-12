#!/usr/bin/env python3
"""
T11 — stratified survey sample frame for the "disappeared" firm population.

Strata over the 651 FIRM_ACTIVITY_ABSENT firms, defined by patent-instrument
outcomes (see survey-design.md for rationale and allocation):

  S1_active_evidence   high-confidence post-award patent activity
  S2_holder_only       patent holder without high-confidence post-award signal
  S3_dark_core         no patent match at all

Within-stratum simple random sampling with a FIXED SEED so the frame is
reproducible; each sampled firm gets ranked replacement backups for
unreachable cases.

Inputs:  data/nano_dark_firm_liveness.csv
Outputs: data/nano_survey_frame.csv

Usage:
  python scripts/data/nano_survey_frame.py
"""

import csv
import random
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DATA = REPO / "data"

SEED = 20260712
ALLOCATION = {"S1_active_evidence": 20, "S2_holder_only": 20, "S3_dark_core": 35}
BACKUPS_PER_PRIMARY = 2


def stratum(row: dict) -> str:
    if row["match_confidence"] == "high" and row["any_filed_post_award"] == "True":
        return "S1_active_evidence"
    if int(row["any_patents_n"] or 0) > 0:
        return "S2_holder_only"
    return "S3_dark_core"


def main() -> int:
    src = DATA / "nano_dark_firm_liveness.csv"
    if not src.exists():
        print(f"ERROR: {src} not found — run nano_dark_firm_liveness.py first", file=sys.stderr)
        return 1

    csv.field_size_limit(sys.maxsize)
    firms = [r for r in csv.DictReader(open(src, newline="", encoding="utf-8"))
             if r["bucket"] == "FIRM_ACTIVITY_ABSENT"]

    strata: dict[str, list[dict]] = {s: [] for s in ALLOCATION}
    for r in firms:
        strata[stratum(r)].append(r)

    rng = random.Random(SEED)
    out_rows: list[dict] = []
    for s, members in strata.items():
        pool = sorted(members, key=lambda r: r["normalized_name"])
        rng.shuffle(pool)
        n = min(ALLOCATION[s], len(pool))
        n_backup = min(n * BACKUPS_PER_PRIMARY, len(pool) - n)
        for i, r in enumerate(pool[: n + n_backup]):
            out_rows.append({
                "company": r["company"],
                "stratum": s,
                "role": "primary" if i < n else "backup",
                "backup_rank": 0 if i < n else i - n + 1,
                "first_award_year": r["first_award_year"],
                "awards_n": r["awards_n"],
                "any_patents_n": r["any_patents_n"],
                "any_latest_filing_year": r["any_latest_filing_year"],
            })

    out_csv = DATA / "nano_survey_frame.csv"
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(out_rows[0].keys()))
        w.writeheader()
        w.writerows(out_rows)

    print(f"Written: {out_csv} (seed {SEED})")
    for s in ALLOCATION:
        total = len(strata[s])
        prim = sum(1 for r in out_rows if r["stratum"] == s and r["role"] == "primary")
        back = sum(1 for r in out_rows if r["stratum"] == s and r["role"] == "backup")
        print(f"  {s:<20} population {total:>3}   primary {prim:>2}   backups {back:>2}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
