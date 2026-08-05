#!/usr/bin/env python3
"""Extract SELF-LABELED SBIR Phase III notices from the GSA archived opportunities.

Sibling to ``pull_gsa_archive.py``. Where that keeps SBIR-mentioning notices and
attributes each to a *known* firm seed, this **discovers** Phase III positives
independently of any seed: it keeps notices whose Title/Description self-declare
an SBIR/STTR Phase III (or cite 15 U.S.C. 638 sole-source authority) and
materializes firm (Awardee) + award# + text + agency.

These are self-labeling, externally-sourced ground-truth positives for the
transition validation set (specs/transition-coverage-expansion, T1) — a
machine-extractable complement to the hand-collected #481 set. Reuses the
streaming + column + opener machinery from ``pull_gsa_archive`` so only the
filter differs.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from scripts.phase3_benchmark.pull_gsa_archive import (
    ARCHIVE_URL_TEMPLATE,
    KEEP_COLUMNS,
    _default_opener,
)

# A notice self-labels as an SBIR/STTR Phase III (or cites the §638 sole-source
# authority) in its Title or Description. Kept deliberately tight to favour
# precision — these become ground-truth positives.
SELF_LABEL = re.compile(
    r"(?:sbir|sttr)\b.{0,40}phase\s*(?:iii|3)\b"
    r"|phase\s*(?:iii|3)\b.{0,40}(?:sbir|sttr)\b"
    r"|15\s*u\.?\s*s\.?\s*c\.?\s*638"
    r"|section\s*638"
    r"|sole[\s-]*source.{0,80}(?:sbir|sttr)",
    re.IGNORECASE | re.DOTALL,
)

SLIM_COLUMNS = [
    "NoticeId",
    "PostedDate",
    "Type",
    "notice_class",
    "Awardee",
    "AwardNumber",
    "Sol#",
    "Department/Ind.Agency",
    "NaicsCode",
    "Title",
]

_INTENT = re.compile(r"intent.{0,30}(?:to\s*award|sole)|notice of intent|sole[\s-]*source award", re.IGNORECASE)


def is_self_labeled(title: str, description: str) -> bool:
    """True if the notice text self-declares an SBIR/STTR Phase III / §638 award."""

    return bool(SELF_LABEL.search(f"{title}\n{description}"))


def classify_notice(row: dict[str, str]) -> str:
    """Bucket a self-labeled notice by how it serves the transition picture.

    ``award`` = a confirmed Phase III (firm + contract#) -> retrospective positive.
    ``intent_sole_source`` = pre-award intent naming the firm -> near-certain forward positive.
    ``sources_sought`` = an open Phase III need -> forward-opportunity feed (the packet's input).
    ``other`` = self-labeled but neither (e.g. a special notice with no firm).
    """

    ntype = (row.get("Type") or "").strip().lower()
    if "award notice" in ntype or (row.get("AwardNumber") or "").strip():
        return "award"
    if _INTENT.search(f"{row.get('Title', '')}\n{row.get('Description', '')}"):
        return "intent_sole_source"
    if "sources sought" in ntype:
        return "sources_sought"
    return "other"


def extract_year(
    year: int,
    output_dir: Path,
    *,
    opener: Callable[[str], io.TextIOWrapper] = _default_opener,
) -> dict[str, object]:
    """Stream one fiscal year, keep self-labeled Phase III notices, write parquet + CSV."""

    url = ARCHIVE_URL_TEMPLATE.format(year=year)
    started = datetime.now(UTC).isoformat()
    rows: list[dict[str, str]] = []
    scanned = 0
    with opener(url) as stream:
        for row in csv.DictReader(stream):
            scanned += 1
            if not is_self_labeled(row.get("Title") or "", row.get("Description") or ""):
                continue
            kept = {column: (row.get(column) or "") for column in KEEP_COLUMNS}
            kept["notice_class"] = classify_notice(row)
            rows.append(kept)

    output_dir.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(rows, columns=[*KEEP_COLUMNS, "notice_class"])
    out_parquet = output_dir / f"FY{year}_phase3_selflabeled.parquet"
    frame.to_parquet(out_parquet, index=False)
    frame[SLIM_COLUMNS].to_csv(output_dir / f"FY{year}_phase3_selflabeled.csv", index=False)
    return {
        "fiscal_year": year,
        "url": url,
        "fetched_at": started,
        "rows_scanned": scanned,
        "rows_kept": len(frame),
        "by_class": frame["notice_class"].value_counts().to_dict() if len(frame) else {},
        "output": str(out_parquet),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--years", type=int, nargs="+", required=True)
    parser.add_argument(
        "--output-dir", type=Path, default=Path("data/derived/phase3_selflabeled")
    )
    args = parser.parse_args()

    manifest: list[dict[str, object]] = []
    for year in args.years:
        entry = extract_year(year, args.output_dir)
        manifest.append(entry)
        print(
            f"FY{year}: scanned {entry['rows_scanned']:,}, self-labeled {entry['rows_kept']} "
            f"{entry['by_class']}"
        )
    (args.output_dir / "selflabel_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
