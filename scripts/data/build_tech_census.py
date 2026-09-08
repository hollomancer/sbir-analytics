#!/usr/bin/env python3
"""
Build an all-phase, subset-taxonomy technology-relevance census over SBIR
awards, driven by a config/tech_census/<area>.yaml.

This is a different question from build_tech_area_cohort.py's Phase II
cohort work: no Method A/B overlap, no external-reference reconciliation, no
transition-channel signals -- just "how many awards, and how many dollars,
are relevant to this technology area, broken into technology subsets, by
fiscal year." All phases in the profile's configured program scope are included.

Usage:
  python scripts/data/build_tech_census.py --area drone_manufacturing
  python scripts/data/build_tech_census.py --area drone_manufacturing --recent-fys 3
  python scripts/data/build_tech_census.py --area unmanned_systems_manufacturing --state MA
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DATA = REPO / "data"

sys.path.insert(0, str(REPO))
from sbir_etl.utils.tech_census import (  # noqa: E402
    CompiledCensus,
    load_award_data_csv,
    load_census_config,
    normalize_state_code,
    normalize_state_codes,
    run_census,
    write_census_artifacts,
)


def main() -> int:
    import warnings

    warnings.warn(
        "build_tech_census.py is a compatibility shim; prefer "
        "scripts/data/run_analysis.py --profile <area_id>",
        DeprecationWarning,
        stacklevel=2,
    )
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--area", required=True, help="area_id under config/tech_census/")
    parser.add_argument(
        "--awards",
        default=str(DATA / "raw" / "sbir" / "award_data.csv"),
        help="SBIR.gov award_data.csv path",
    )
    parser.add_argument(
        "--recent-fys",
        type=int,
        default=3,
        help="Number of most-recent fiscal years to print individually (default 3)",
    )
    parser.add_argument(
        "--program",
        dest="programs",
        action="append",
        choices=("SBIR", "STTR"),
        help="Override configured program scope; repeat to select both",
    )
    parser.add_argument(
        "--fiscal-year",
        dest="fiscal_years",
        action="append",
        type=int,
        help="Limit the report to a fiscal year; repeat for multiple years",
    )
    parser.add_argument(
        "--state",
        dest="states",
        action="append",
        help="Limit by awardee state name or USPS code; repeat for multiple states",
    )
    parser.add_argument(
        "--data-vintage",
        help="Optional source-data release/download vintage (not inferred from local file mtime)",
    )
    args = parser.parse_args()

    awards_csv = Path(args.awards)
    if not awards_csv.exists():
        print(f"ERROR: awards CSV not found: {awards_csv}", file=sys.stderr)
        return 1

    cfg = load_census_config(args.area)
    compiled = CompiledCensus(cfg)
    print(f"Area: {compiled.display_name} ({compiled.area_id})")

    print("Loading SBIR/STTR awards (all phases)...")
    awards = load_award_data_csv(awards_csv)
    print(f"  {len(awards):,} total awards")

    selected_fys = sorted(set(args.fiscal_years or []))
    try:
        selected_states = normalize_state_codes(args.states or [])
    except ValueError as exc:
        parser.error(str(exc))
    reporting_awards = awards
    if selected_fys:
        reporting_awards = [
            award for award in reporting_awards if award.get("award_year") in selected_fys
        ]
    if selected_states:
        reporting_awards = [
            award
            for award in reporting_awards
            if normalize_state_code(award.get("state")) in selected_states
        ]
    result = run_census(reporting_awards, compiled, programs=args.programs)
    epistemic = result["_epistemic"]
    print("\nStatus: EXPLORATORY / NON-CITABLE")
    print(f"  {epistemic['notice']}")
    grand = result["grand_total"]
    print(f"\nIn-scope awards: {grand['n']:,}  (${grand['usd'] / 1e6:,.1f}M)")
    if result["exclusion_counts"]:
        print("Excluded (adjacent, not in scope):")
        for name, n in sorted(result["exclusion_counts"].items()):
            print(f"  {name}: {n:,}")
    if result["adjacent_counts"]:
        print("Adjacent non-gate-passing categories (context only):")
        for name, n in sorted(result["adjacent_counts"].items()):
            print(f"  {name}: {n:,}")

    years = sorted({r["year"] for r in result["classified_awards"] if r["year"]})
    if not years:
        print("\nNo in-scope awards found.")
    if selected_fys:
        recent_fys = sorted(selected_fys, reverse=True)
    elif years:
        current_fy = years[-1]
        recent_fys = [current_fy - i for i in range(args.recent_fys)]
    else:
        recent_fys = []

    print()
    print("=" * 100)
    program_label = "/".join(result.get("programs", [])) or "ALL PROGRAM"
    print(
        f"{compiled.display_name.upper()} -- {program_label} AWARDS "
        "BY TECHNOLOGY SUBSET x FISCAL YEAR"
    )
    print("=" * 100)
    subset_names = [name for name, _ in compiled.subsets] + [compiled.fallback_subset]
    aggregate_label = "SELECTED TOTAL" if selected_fys else "ALL-TIME"
    header = (
        f"{'Subset':<48}"
        + "".join(f"{'FY' + str(fy):>16}" for fy in recent_fys)
        + f"{aggregate_label:>18}"
    )
    print(header)
    for subset in subset_names:
        cells = []
        for fy in recent_fys:
            d = result["by_fy_subset"].get((fy, subset), {"n": 0, "usd": 0.0})
            cells.append(f"{d['n']:>5,} (${d['usd'] / 1e6:>6.1f}M)")
        tot = result["subset_totals"].get(subset, {"n": 0, "usd": 0.0})
        print(
            f"{subset:<48}"
            + "".join(f"{c:>16}" for c in cells)
            + f"{tot['n']:>7,} (${tot['usd'] / 1e6:>7.1f}M)"
        )
    print("-" * 100)
    fy_cells = []
    for fy in recent_fys:
        d = result["fy_totals"].get(fy, {"n": 0, "usd": 0.0})
        fy_cells.append(f"{d['n']:>5,} (${d['usd'] / 1e6:>6.1f}M)")
    print(
        f"{'TOTAL':<48}"
        + "".join(f"{c:>16}" for c in fy_cells)
        + f"{grand['n']:>7,} (${grand['usd'] / 1e6:>7.1f}M)"
    )

    written = write_census_artifacts(
        result,
        DATA / "tech_census" / compiled.area_id,
        awards_csv=awards_csv,
        source_row_count=len(awards),
        reporting_row_count=len(reporting_awards),
        data_vintage=args.data_vintage,
        selected_fys=selected_fys,
        selected_states=selected_states,
    )

    print(f"\nWrote {written['classified_awards']} ({grand['n']:,} rows)")
    print(f"Wrote {written['summary']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
