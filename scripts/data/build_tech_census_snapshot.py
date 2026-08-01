#!/usr/bin/env python3
"""
Run a tech-census area through ComputeTechCensusTool and persist the result
as an API-servable snapshot (packages/sbir-analytics/sbir_analytics/api/snapshots.py).

Unlike build_tech_census.py, which writes a human-readable CSV/JSON report
under data/tech_census/<area>/, this script produces the machine-readable
AnalyticsSnapshot the private analytics API reads from
SBIR_ANALYTICS_SNAPSHOT_DIR (default reports/analytics_snapshots/) and serves
at GET /v1/snapshots/<analysis_kind>/<period>.

Usage:
  python scripts/data/build_tech_census_snapshot.py --area drone_manufacturing --period 2026
  python scripts/data/build_tech_census_snapshot.py --area drone_manufacturing --period 2026 --overwrite
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DATA = REPO / "data"

sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "packages" / "sbir-analytics"))

import pandas as pd  # noqa: E402

from sbir_etl.utils.tech_census import load_award_data_csv  # noqa: E402
from sbir_analytics.api.snapshots import (  # noqa: E402
    AnalysisKind,
    SnapshotStoreError,
    snapshot_from_tool_result,
    write_snapshot,
)
from sbir_analytics.tools.tech_census import ComputeTechCensusTool  # noqa: E402

# One AnalysisKind per tech-census area -- keep in sync with AnalysisKind and
# config/tech_census/<area_id>.yaml as areas are added.
_AREA_TO_KIND = {
    "drone_manufacturing": AnalysisKind.TECH_CENSUS_DRONE_MANUFACTURING,
    "uas_relevance": AnalysisKind.TECH_CENSUS_UAS_RELEVANCE,
}


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
    parser.add_argument(
        "--area", required=True, choices=sorted(_AREA_TO_KIND), help="tech-census area_id"
    )
    parser.add_argument(
        "--period",
        required=True,
        help="Snapshot identifier/as-of period, e.g. 2026 or 2026-Q1; not a data filter",
    )
    parser.add_argument(
        "--awards",
        default=str(DATA / "raw" / "sbir" / "award_data.csv"),
        help="SBIR.gov award_data.csv path",
    )
    parser.add_argument(
        "--snapshot-dir",
        default=str(REPO / "reports" / "analytics_snapshots"),
        help="Snapshot store root (must match SBIR_ANALYTICS_SNAPSHOT_DIR the API reads)",
    )
    parser.add_argument(
        "--overwrite", action="store_true", help="Replace an existing snapshot for this period"
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
        help="Limit the reporting window to a fiscal year; repeat for multiple years",
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

    print(f"Loading SBIR/STTR awards (all phases) from {awards_csv}...")
    awards = load_award_data_csv(awards_csv)
    awards_df = pd.DataFrame(awards)
    print(f"  {len(awards_df):,} total awards")

    source_timestamp = _source_timestamp(awards_csv)
    tool = ComputeTechCensusTool()
    result = tool.run(
        awards_df=awards_df,
        area_id=args.area,
        programs=args.programs,
        fiscal_years=args.fiscal_years,
        source_path=str(awards_csv.resolve()),
        source_sha256=_sha256(awards_csv),
        source_timestamp=source_timestamp,
        data_vintage=args.data_vintage,
    )
    if result.metadata.warnings:
        for warning in result.metadata.warnings:
            print(f"ERROR: {warning}", file=sys.stderr)
        print("ERROR: snapshot was not written because census validation failed", file=sys.stderr)
        return 1

    grand = result.data["summary"]["grand_total"]
    print(f"Classified {grand['n']:,} in-scope awards (${grand['usd'] / 1e6:,.1f}M)")

    snapshot = snapshot_from_tool_result(
        _AREA_TO_KIND[args.area],
        args.period,
        result,
        as_of=datetime.now(UTC),
    )

    try:
        path = write_snapshot(Path(args.snapshot_dir), snapshot, overwrite=args.overwrite)
    except SnapshotStoreError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"Wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
