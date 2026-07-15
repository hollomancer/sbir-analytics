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
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DATA = REPO / "data"

sys.path.insert(0, str(REPO))
from sbir_etl.utils.tech_census import (  # noqa: E402
    CompiledCensus,
    load_award_data_csv,
    load_census_config,
    run_census,
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _source_timestamp(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat()


def main() -> int:
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
    reporting_awards = (
        [award for award in awards if award.get("award_year") in selected_fys]
        if selected_fys
        else awards
    )
    result = run_census(reporting_awards, compiled, programs=args.programs)
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

    out_dir = DATA / "tech_census" / compiled.area_id
    out_dir.mkdir(parents=True, exist_ok=True)

    awards_csv_path = out_dir / "classified_awards.csv"
    rows = result["classified_awards"]
    preferred_columns = [
        "company",
        "title",
        "agency",
        "program",
        "phase",
        "year",
        "amount",
        "subset",
        "scope_class",
        "agency_tracking_number",
        "contract",
        "source_row",
        "gate_evidence",
        "physical_evidence",
        "subset_evidence",
        "scope_evidence",
        "classification_source",
        "override_reason",
    ]
    extra_columns = [key for row in rows for key in row if key not in preferred_columns]
    cols = list(dict.fromkeys(preferred_columns + extra_columns))
    with open(awards_csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    summary_path = out_dir / "summary.json"
    source_timestamp = _source_timestamp(awards_csv)
    json_safe = {
        "area_id": result["area_id"],
        "display_name": result["display_name"],
        "grand_total": result["grand_total"],
        "fy_totals": {str(k): v for k, v in result["fy_totals"].items()},
        "subset_totals": result["subset_totals"],
        "by_fy_subset": {f"{fy}|{subset}": v for (fy, subset), v in result["by_fy_subset"].items()},
        "exclusion_counts": result["exclusion_counts"],
        "adjacent_counts": result["adjacent_counts"],
        "program_exclusion_counts": result["program_exclusion_counts"],
        "rejection_counts": result["rejection_counts"],
        "config_version": result["config_version"],
        "override_version": result["override_version"],
        "programs": result["programs"],
        "scope_totals": result["scope_totals"],
        "reporting_window": {
            "fiscal_years": selected_fys or None,
            "programs": result["programs"],
        },
        "provenance": {
            "source_path": str(awards_csv.resolve()),
            "sha256": _sha256(awards_csv),
            "source_timestamp": source_timestamp,
            "data_vintage": args.data_vintage,
            "source_row_count": len(awards),
            "reporting_row_count": len(reporting_awards),
        },
    }
    summary_path.write_text(json.dumps(json_safe, indent=2) + "\n", encoding="utf-8")

    print(f"\nWrote {awards_csv_path} ({grand['n']:,} rows)")
    print(f"Wrote {summary_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
