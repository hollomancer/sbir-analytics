#!/usr/bin/env python3
"""Extract historical USAspending contracts for the three-agency Phase II cohort.

Epistemic tier: exploratory. The command scans downloaded Contracts_Full ZIPs
with the repository's bounded archive extractor and writes one filtered parquet
per fiscal year. It never operates Dagster or the live deployment checkout.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from datetime import date
from pathlib import Path

import pyarrow.parquet as pq

from sbir_etl.extractors.usaspending_award_archive import AwardArchiveContractExtractor


REPO_ROOT = Path(__file__).resolve().parents[2]
ANALYSIS_SCRIPT = REPO_ROOT / "scripts/data/three_agency_commercialization_outcomes.py"
ARCHIVE_PATTERN = re.compile(r"^FY(?P<year>\d{4})_All_Contracts_Full_\d{8}\.zip$")


def load_analysis_module():
    spec = importlib.util.spec_from_file_location("three_agency_commercialization_outcomes", ANALYSIS_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {ANALYSIS_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def selected_archives(directory: Path, start_fy: int, end_fy: int) -> list[tuple[int, Path]]:
    by_year: dict[int, list[Path]] = {}
    for path in directory.glob("FY*_All_Contracts_Full_*.zip"):
        match = ARCHIVE_PATTERN.fullmatch(path.name)
        if not match:
            continue
        year = int(match["year"])
        if start_fy <= year <= end_fy:
            by_year.setdefault(year, []).append(path)
    missing = [year for year in range(start_fy, end_fy + 1) if year not in by_year]
    if missing:
        raise FileNotFoundError("missing fiscal-year archives: " + ", ".join(map(str, missing)))
    return [(year, sorted(by_year[year])[-1]) for year in range(start_fy, end_fy + 1)]


def build_filter(cohort, output: Path) -> None:
    values = {"uei": [], "duns": [], "company_names": []}
    for alias in sorted(cohort.alias_to_firm):
        basis, _, value = alias.partition(":")
        if basis == "name":
            values["company_names"].append(value)
        elif basis in values:
            values[basis].append(value)
    values["company_names"] = sorted(cohort.raw_company_names)
    values["stats"] = {key: len(value) for key, value in values.items()}
    output.write_text(json.dumps(values, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--awards", type=Path, required=True)
    parser.add_argument("--archive-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--start-fy", type=int, default=2009)
    parser.add_argument("--end-fy", type=int, default=2025)
    parser.add_argument("--cutoff", type=date.fromisoformat, default=date(2024, 12, 31))
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    module = load_analysis_module()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    cohort = module.build_cohort(args.awards, args.cutoff)
    filter_path = args.output_dir / "cohort_vendor_filters.json"
    build_filter(cohort, filter_path)

    manifest_rows = []
    for fiscal_year, archive in selected_archives(args.archive_dir, args.start_fy, args.end_fy):
        output = args.output_dir / f"contracts_fy{fiscal_year}.parquet"
        if output.is_file() and not args.force:
            rows = pq.ParquetFile(output).metadata.num_rows
            print(f"FY{fiscal_year}: reusing {output} ({rows:,} rows)")
            manifest_rows.append(
                {
                    "fiscal_year": fiscal_year,
                    "archive": archive.name,
                    "archive_sha256": module.sha256_file(archive),
                    "output": output.name,
                    "output_sha256": module.sha256_file(output),
                    "rows": rows,
                }
            )
            continue
        print(f"FY{fiscal_year}: scanning {archive.name}")
        extractor = AwardArchiveContractExtractor(filter_path)
        rows = extractor.extract_from_archive(archive, output)
        manifest_rows.append(
            {
                "fiscal_year": fiscal_year,
                "archive": archive.name,
                "archive_sha256": module.sha256_file(archive),
                "output": output.name,
                "output_sha256": module.sha256_file(output),
                "rows": rows,
                "source_provenance": extractor.source_provenance,
            }
        )
    manifest = {
        "epistemic_tier": "exploratory",
        "citable": False,
        "cutoff": args.cutoff.isoformat(),
        "awards": str(args.awards.resolve()),
        "awards_sha256": module.sha256_file(args.awards),
        "archives": manifest_rows,
    }
    (args.output_dir / "extraction_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
