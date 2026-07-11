#!/usr/bin/env python3
"""
Extract USPTO CPC B82Y/B82B (nanotechnology) patents with assignees and dates.

Streams the PatentsView PVGPATDIS zip archives without extracting them,
filters ~60M CPC rows to the B82 subclasses, and joins assignee organizations
and grant dates for the matched patents. Output feeds Method C of the
nanotech cohort analysis (build_nano_cohort.py).

CPC scope:
  B82B — nanostructures formed by manipulation of individual atoms/molecules
  B82Y — specific uses or applications of nanostructures

Inputs (download via: python scripts/data/download_uspto.py --dataset patentsview
        --table {cpc,assignee,patent,application} --local data/raw/uspto/patentsview):
  data/raw/uspto/patentsview/g_cpc_current.tsv.zip
  data/raw/uspto/patentsview/g_assignee_disambiguated.tsv.zip
  data/raw/uspto/patentsview/g_patent.tsv.zip
  data/raw/uspto/patentsview/g_application.tsv.zip   — filing dates (capability-vs-outcome timing)

Outputs:
  data/processed/uspto/b82_patents.csv — one row per (patent, org assignee)

Usage:
  python scripts/data/extract_b82_patents.py
"""

import csv
import io
import sys
import zipfile
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RAW = REPO / "data/raw/uspto/patentsview"
OUT_CSV = REPO / "data/processed/uspto/b82_patents.csv"

B82_SUBCLASS_PREFIX = "B82"


def tsv_rows(zip_path: Path):
    """Yield (header_index, row) tuples streaming a single-member TSV zip."""
    z = zipfile.ZipFile(zip_path)
    member = z.infolist()[0].filename
    with z.open(member) as f:
        reader = csv.reader(io.TextIOWrapper(f, encoding="utf-8", newline=""), delimiter="\t")
        header = next(reader)
        idx = {c: i for i, c in enumerate(header)}
        for row in reader:
            yield idx, row


def main() -> int:
    required = {
        "cpc": RAW / "g_cpc_current.tsv.zip",
        "assignee": RAW / "g_assignee_disambiguated.tsv.zip",
        "patent": RAW / "g_patent.tsv.zip",
        "application": RAW / "g_application.tsv.zip",
    }
    for table, p in required.items():
        if not p.exists():
            print(
                f"ERROR: {p} not found — run scripts/data/download_uspto.py "
                f"--dataset patentsview --table {table} --local {RAW}",
                file=sys.stderr,
            )
            return 1

    print("Pass 1/4: scanning g_cpc_current for B82 subclasses...")
    subclasses: dict[str, set[str]] = defaultdict(set)
    rows_seen = 0
    for idx, row in tsv_rows(required["cpc"]):
        rows_seen += 1
        sub = row[idx["cpc_subclass"]]
        if sub.startswith(B82_SUBCLASS_PREFIX):
            subclasses[row[idx["patent_id"]]].add(sub)
    b82_ids = set(subclasses)
    print(f"  {rows_seen:,} CPC rows scanned; {len(b82_ids):,} unique B82 patents")

    print("Pass 2/4: joining assignee organizations...")
    org_rows: dict[str, list[tuple[str, str]]] = defaultdict(list)  # patent_id → [(org, type)]
    individual_only = set(b82_ids)
    for idx, row in tsv_rows(required["assignee"]):
        pid = row[idx["patent_id"]]
        if pid not in b82_ids:
            continue
        org = row[idx["disambig_assignee_organization"]].strip()
        if org:
            org_rows[pid].append((org, row[idx["assignee_type"]]))
            individual_only.discard(pid)
    print(
        f"  {len(org_rows):,} B82 patents with ≥1 organization assignee; "
        f"{len(individual_only):,} individual-only or unassigned"
    )

    print("Pass 3/4: joining grant dates and titles...")
    meta: dict[str, tuple[str, str]] = {}
    for idx, row in tsv_rows(required["patent"]):
        pid = row[idx["patent_id"]]
        if pid in b82_ids:
            meta[pid] = (row[idx["patent_date"]], row[idx["patent_title"]][:120])
    print(f"  {len(meta):,} B82 patents matched in g_patent")

    print("Pass 4/4: joining filing dates...")
    filing: dict[str, str] = {}
    for idx, row in tsv_rows(required["application"]):
        pid = row[idx["patent_id"]]
        if pid in b82_ids:
            fd = row[idx["filing_date"]]
            # g_application contains typo'd dates (e.g. year 1074); keep plausible only
            if len(fd) == 10 and "1900" <= fd[:4] <= "2030":
                filing[pid] = fd
    print(f"  {len(filing):,} B82 patents with plausible filing dates")

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    n_out = 0
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            ["patent_id", "grant_date", "filing_date", "assignee_organization", "assignee_type",
             "cpc_subclasses", "patent_title"]
        )
        for pid in sorted(org_rows):
            date, title = meta.get(pid, ("", ""))
            for org, a_type in org_rows[pid]:
                w.writerow(
                    [pid, date, filing.get(pid, ""), org, a_type,
                     "|".join(sorted(subclasses[pid])), title]
                )
                n_out += 1
    print(f"  Written: {OUT_CSV} ({n_out:,} patent-assignee rows)")

    unique_orgs = {org.upper() for rows in org_rows.values() for org, _ in rows}
    print()
    print("=" * 60)
    print("B82 EXTRACTION SUMMARY")
    print("=" * 60)
    print(f"Unique B82 patents:                  {len(b82_ids):,}")
    print(f"  with organization assignee:        {len(org_rows):,}")
    print(f"  individual-only / unassigned:      {len(individual_only):,}")
    print(f"Unique assignee organizations:       {len(unique_orgs):,}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
