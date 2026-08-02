#!/usr/bin/env python3
"""Award-grain notice recovery: attribute each notice to the award it cites.

Streams the GSA archive, SBIR-gates, and — instead of matching a firm name —
resolves the prior-award PIID cited in the notice text against ``award_data.csv``
(:mod:`award_grain`). Each kept row carries the **specific cited award's**
abstract as the retrieval query, so the corpus is award-grain and the
attribution is dispositive (no firm-name boilerplate false positives).

Emits ``FY*_award_grain.parquet`` files consumable by ``build_notice_corpus``
with ``per_row_abstract=True``.
"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from scripts.phase3_benchmark.award_grain import attribute_by_citation, award_index_from_csv
from scripts.phase3_benchmark.pull_gsa_archive import (
    ARCHIVE_URL_TEMPLATE,
    KEEP_COLUMNS,
    _default_opener,
)


OUT_COLUMNS: tuple[str, ...] = (*KEEP_COLUMNS, "firm", "award_piid", "query_abstract", "match_rule")


def recover_fiscal_year(
    year: int,
    award_index: dict[str, dict],
    output_dir: Path,
    *,
    opener=_default_opener,
) -> dict[str, object]:
    url = ARCHIVE_URL_TEMPLATE.format(year=year)
    started = datetime.now(UTC).isoformat()
    rows: list[dict[str, str]] = []
    scanned = 0
    sbir_seen = 0
    with opener(url) as stream:
        for row in csv.DictReader(stream):
            scanned += 1
            description = row.get("Description") or ""
            if "sbir" not in description.lower():
                continue
            sbir_seen += 1
            attribution = attribute_by_citation(description, award_index)
            if attribution is None:
                continue
            piid, award = attribution
            kept = {column: (row.get(column) or "") for column in KEEP_COLUMNS}
            kept["firm"] = award["company"]
            kept["award_piid"] = piid
            kept["query_abstract"] = award["abstract"]
            kept["match_rule"] = "citation"
            rows.append(kept)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"FY{year}_award_grain.parquet"
    pd.DataFrame(rows, columns=OUT_COLUMNS).to_parquet(output_path, index=False)
    return {
        "fiscal_year": year,
        "url": url,
        "fetched_at": started,
        "rows_scanned": scanned,
        "sbir_notices": sbir_seen,
        "rows_kept": len(rows),
        "output": str(output_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--years", type=int, nargs="+", required=True)
    parser.add_argument("--award-data", type=Path, default=Path("data/raw/sbir/award_data.csv"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/raw/gsa_award_grain"))
    args = parser.parse_args()

    print("loading award index from award_data.csv ...")
    award_index = award_index_from_csv(str(args.award_data))
    print(f"{len(award_index):,} contracts indexed")
    manifest: list[dict[str, object]] = []
    for year in args.years:
        entry = recover_fiscal_year(year, award_index, args.output_dir)
        manifest.append(entry)
        print(
            f"FY{year}: scanned {entry['rows_scanned']:,}, SBIR {entry['sbir_notices']:,}, "
            f"award-grain {entry['rows_kept']:,}"
        )
    (args.output_dir / "award_grain_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
