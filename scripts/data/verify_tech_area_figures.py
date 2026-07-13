#!/usr/bin/env python3
"""
Audit pass for the tech-area findings reports (quantum, hypersonics, …).

Recomputes every load-bearing composition figure — agency mix, dollar totals,
unique-firm counts, program split, decade distribution, recency censoring, firm
concentration, no-UEI share — fresh from the cohort CSV that
``build_tech_area_cohort.py`` writes, and diffs it against the numbers
hand-authored into ``docs/<area>_sbir_transition_findings.md``.

This is the generalized analogue of ``nano_verify_report_figures.py``. It needs a
data-bearing run (the cohort CSV under ``data/reports/<area>/``, gitignored), so it
does not run in a source-only checkout; the pure ``verify_composition`` diff logic
is unit-tested with synthetic input in
``tests/unit/scripts/test_verify_tech_area_figures.py``.

Usage:
  python scripts/data/build_tech_area_cohort.py --area quantum_information_science
  python scripts/data/verify_tech_area_figures.py --area quantum_information_science

The EXPECTED tables below are transcribed from the published findings docs
(2026-07-13). Where a doc used the raw row count (e.g. QIS 138) rather than the
award_id-deduplicated count (135), this audit intentionally flags the gap — that
row-vs-unique inconsistency is the point of the check, not a transcription error.
"""

import argparse
import csv
import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
csv.field_size_limit(min(sys.maxsize, 2**31 - 1))

_spec = importlib.util.spec_from_file_location(
    "build_tech_area_cohort", REPO / "scripts" / "data" / "build_tech_area_cohort.py"
)
_btac = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_btac)
aggregate_composition = _btac.aggregate_composition


# Transcribed from docs/<area>_sbir_transition_findings.md (2026-07-13).
# Agency keys use the canonical award_data.csv agency strings; reconcile on the
# first data-bearing run if a key comes back "missing".
EXPECTED: dict[str, dict] = {
    "quantum_information_science": {
        "totals_awards": 138,  # published row count; dedupe → 135 (audit flags this)
        "by_agency": {
            "Department of Defense": (82, 59.4, 90.9, 51),
            "Department of Energy": (32, 23.2, 39.9, 29),
            "National Aeronautics and Space Administration": (13, 9.4, 9.9, 9),
            "National Science Foundation": (6, 4.3, 4.9, 6),
            "Department of Commerce": (3, 2.2, 0.9, 3),
            "Department of Health and Human Services": (2, 1.4, 3.4, 2),
        },
        "program": (81, 57, 41.0),  # SBIR, STTR, STTR%
        "decade": {"1990s": 1, "2000s": 12, "2010s": 36, "2020s": 89},
        "censoring": (97, 41),  # mature ≤2022, censored ≥2023
        "no_uei": (4, 2.9),
        "top10_share_pct": 38.0,
    },
    "hypersonics": {
        "totals_awards": 813,
        "by_agency": {
            "Department of Defense": (713, 87.7, 900.3, 319),
            "National Aeronautics and Space Administration": (87, 10.7, 54.4, 64),
            "Department of Energy": (12, 1.5, 12.3, 9),
            "National Science Foundation": (1, 0.1, 1.0, 1),
        },
        "program": (682, 131, 16.0),
        "decade": {"1980s": 20, "1990s": 67, "2000s": 136, "2010s": 188, "2020s": 402},
        "censoring": (558, 255),
        "no_uei": (68, 8.4),
        "top10_share_pct": 24.0,
    },
}


def verify_composition(comp: dict, exp: dict) -> list[str]:
    """Diff a computed composition dict against expected report figures.

    Returns a list of human-readable failure strings (empty = all pass). Pure and
    data-free so it is unit-testable without a cohort CSV.
    """
    fails: list[str] = []

    def check(label, actual, expected, tol=0.0):
        if isinstance(expected, (int, float)) and not isinstance(expected, bool):
            ok = abs(actual - expected) <= tol
        else:
            ok = actual == expected
        mark = "OK  " if ok else "FAIL"
        print(f"[{mark}] {label}: computed={actual!r}  report={expected!r}")
        if not ok:
            fails.append(f"{label}: computed={actual!r} != report={expected!r}")

    check("total awards (unique)", comp["n_unique_awards"], exp["totals_awards"])

    for agency, (rn, rshare, rdollar, rfirms) in exp["by_agency"].items():
        row = comp["by_agency"].get(agency)
        if row is None:
            fails.append(f"{agency}: MISSING from computed agency table")
            print(f"[FAIL] {agency}: MISSING from computed agency table")
            continue
        short = agency[:22]
        check(f"{short} awards", row["awards"], rn)
        check(f"{short} share%", row["share_pct"], rshare, 0.15)
        check(f"{short} $M", row["phase2_dollars_m"], rdollar, max(0.1, rdollar * 0.02))
        check(f"{short} firms", row["unique_firms"], rfirms)

    sbir, sttr, sttr_pct = exp["program"]
    check("SBIR n", comp["program_split"]["SBIR"], sbir)
    check("STTR n", comp["program_split"]["STTR"], sttr)
    check("STTR %", comp["program_split"]["sttr_pct"], sttr_pct, 0.5)

    for dec, rn in exp["decade"].items():
        check(f"decade {dec}", comp["by_decade"].get(dec, 0), rn)

    mature, censored = exp["censoring"]
    check("mature (≤2022)", comp["censoring"]["mature_awards"], mature)
    check("censored (≥2023)", comp["censoring"]["censored_awards"], censored)

    no_uei_n, no_uei_pct = exp["no_uei"]
    check("no-UEI awards", comp["entity_resolution"]["no_uei_awards"], no_uei_n)
    check("no-UEI %", comp["entity_resolution"]["no_uei_pct"], no_uei_pct, 0.15)

    check(
        "top-10 firm award share %",
        comp["firm_concentration"]["top10_award_share_pct"],
        exp["top10_share_pct"],
        0.5,
    )
    return fails


def _load_cohort(area_id: str) -> list[dict]:
    from sbir_etl.utils.transition_report_paths import ReportPaths

    path = ReportPaths.for_area(area_id).artifact("cohort_keyword")
    if not path.exists() or not path.read_text(encoding="utf-8").strip():
        raise FileNotFoundError(
            f"No cohort at {path}. Run: "
            f"python scripts/data/build_tech_area_cohort.py --area {area_id}"
        )
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--area", required=True, choices=sorted(EXPECTED))
    args = parser.parse_args()

    print("=" * 78)
    print(f"AUDIT: {args.area} findings-report composition figures")
    print("=" * 78)
    try:
        cohort = _load_cohort(args.area)
    except FileNotFoundError as e:
        print(e, file=sys.stderr)
        return 2
    comp = aggregate_composition(cohort)
    fails = verify_composition(comp, EXPECTED[args.area])

    print()
    print("=" * 78)
    if fails:
        print(f"AUDIT RESULT: {len(fails)} DISCREPANCY(IES) FOUND")
        for f in fails:
            print(f"  - {f}")
        return 1
    print("AUDIT RESULT: ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
