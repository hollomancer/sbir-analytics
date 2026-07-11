#!/usr/bin/env python3
"""
Patent-based liveness check for the nanotech cohort's "dark" firm buckets.

For firms whose Phase II awards fall in the FIRM_ACTIVITY_ABSENT (no federal
activity post-award) or ENTITY_RESOLUTION_FAILURE (no UEI) deficiency classes,
check USPTO patent records for evidence the firm remained active:

  - B82 (nanotech-classified) patents — high precision: domain consistency
    between a nanotech SBIR firm and nanotech patents makes name collisions
    unlikely. Treat as a FLOOR on provable liveness.
  - Patents of ANY class — exact normalized-name match against the full
    assignee universe carries collision risk (generic firm names can match
    unrelated assignees). Treat as an UPPER BOUND pending confidence scoring
    (state / inventor-vs-PI corroboration, as in the Form D matcher).

"Filed post-award" means the firm's latest matched filing year exceeds its
first Phase II award year — activity evidence, not survival-to-present.

Inputs:
  data/nano_cohort_keyword.csv                              — deficiency classes
  data/processed/uspto/b82_patents.csv                      — B82 extract
  data/raw/uspto/patentsview/g_assignee_disambiguated.tsv.zip
  data/raw/uspto/patentsview/g_application.tsv.zip

Outputs:
  data/nano_dark_firm_liveness.csv — one row per dark firm

Usage:
  python scripts/data/nano_dark_firm_liveness.py
"""

import csv
import io
import sys
import zipfile
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DATA = REPO / "data"
RAW = DATA / "raw/uspto/patentsview"

sys.path.insert(0, str(REPO))
from sbir_etl.utils.text_normalization import normalize_name  # noqa: E402

DARK_BUCKETS = ("FIRM_ACTIVITY_ABSENT", "ENTITY_RESOLUTION_FAILURE")


def tsv_rows(zip_path: Path):
    z = zipfile.ZipFile(zip_path)
    with z.open(z.infolist()[0].filename) as f:
        reader = csv.reader(io.TextIOWrapper(f, encoding="utf-8", newline=""), delimiter="\t")
        header = next(reader)
        idx = {c: i for i, c in enumerate(header)}
        for row in reader:
            yield idx, row


def main() -> int:
    cohort_csv = DATA / "nano_cohort_keyword.csv"
    b82_csv = DATA / "processed/uspto/b82_patents.csv"
    assignee_zip = RAW / "g_assignee_disambiguated.tsv.zip"
    application_zip = RAW / "g_application.tsv.zip"
    required = {
        cohort_csv: "run scripts/data/build_nano_cohort.py first",
        b82_csv: "run scripts/data/extract_b82_patents.py first",
        assignee_zip: "download via download_uspto.py --table assignee --local " + str(RAW),
        application_zip: "download via download_uspto.py --table application --local " + str(RAW),
    }
    for p, hint in required.items():
        if not p.exists():
            print(f"ERROR: {p} not found — {hint}", file=sys.stderr)
            return 1

    print("Loading dark-bucket firms from keyword cohort...")
    csv.field_size_limit(sys.maxsize)
    firms: dict[str, dict] = {}  # normalized name → record
    with open(cohort_csv, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            bucket = row.get("deficiency_class", "")
            if bucket not in DARK_BUCKETS:
                continue
            norm = normalize_name(row["company"], remove_suffixes=True)
            if not norm:
                continue
            yr = int(float(row.get("award_year") or 0))
            rec = firms.setdefault(
                norm,
                {"company": row["company"], "bucket": bucket, "first_award_year": 9999,
                 "awards_n": 0},
            )
            rec["awards_n"] += 1
            if yr:
                rec["first_award_year"] = min(rec["first_award_year"], yr)
    by_bucket: dict[str, int] = defaultdict(int)
    for rec in firms.values():
        by_bucket[rec["bucket"]] += 1
    print(f"  {len(firms):,} dark firms ({dict(by_bucket)})")

    print("Matching B82 extract (floor: nanotech patents, domain-consistent)...")
    b82_by_firm: dict[str, list[str]] = defaultdict(list)  # norm → filing dates
    with open(b82_csv, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            norm = normalize_name(row["assignee_organization"], remove_suffixes=True)
            if norm in firms:
                b82_by_firm[norm].append(row.get("filing_date", ""))

    print("Scanning full assignee table (upper bound: any patent class)...")
    firm_patents: dict[str, set[str]] = defaultdict(set)
    for idx, row in tsv_rows(assignee_zip):
        org = row[idx["disambig_assignee_organization"]]
        if not org:
            continue
        norm = normalize_name(org, remove_suffixes=True)
        if norm in firms:
            firm_patents[norm].add(row[idx["patent_id"]])
    print(f"  {len(firm_patents):,} dark firms match ≥1 patent assignee")

    print("Joining filing years for matched patents...")
    wanted = set().union(*firm_patents.values()) if firm_patents else set()
    pat_year: dict[str, int] = {}
    for idx, row in tsv_rows(application_zip):
        pid = row[idx["patent_id"]]
        if pid in wanted:
            fd = row[idx["filing_date"]]
            if len(fd) == 10 and "1900" <= fd[:4] <= "2030":
                pat_year[pid] = int(fd[:4])

    out_csv = DATA / "nano_dark_firm_liveness.csv"
    fields = ["company", "normalized_name", "name_tokens", "bucket", "awards_n",
              "first_award_year", "b82_patents_n", "b82_filed_post_award",
              "any_patents_n", "any_latest_filing_year", "any_filed_post_award"]
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for norm, rec in sorted(firms.items()):
            first_yr = rec["first_award_year"]
            b82_filings = [d for d in b82_by_firm.get(norm, []) if d]
            b82_post = any(int(d[:4]) > first_yr for d in b82_filings)
            years = [pat_year[p] for p in firm_patents.get(norm, set()) if p in pat_year]
            latest = max(years) if years else ""
            w.writerow({
                "company": rec["company"],
                "normalized_name": norm,
                "name_tokens": len(norm.split()),
                "bucket": rec["bucket"],
                "awards_n": rec["awards_n"],
                "first_award_year": first_yr,
                "b82_patents_n": len(b82_by_firm.get(norm, [])),
                "b82_filed_post_award": b82_post,
                "any_patents_n": len(firm_patents.get(norm, set())),
                "any_latest_filing_year": latest,
                "any_filed_post_award": bool(years) and latest != "" and latest > first_yr,
            })
    print(f"  Written: {out_csv} ({len(firms):,} rows)")

    print()
    print("=" * 70)
    print("DARK-FIRM PATENT LIVENESS SUMMARY")
    print("=" * 70)
    for bucket in DARK_BUCKETS:
        sub = {n: r for n, r in firms.items() if r["bucket"] == bucket}
        n = len(sub)
        b82_hold = sum(1 for f in sub if b82_by_firm.get(f))
        b82_post = sum(
            1 for f in sub
            if any(d and int(d[:4]) > sub[f]["first_award_year"] for d in b82_by_firm.get(f, []))
        )
        any_hold = sum(1 for f in sub if firm_patents.get(f))
        any_post = sum(
            1 for f in sub
            if any(pat_year.get(p, 0) > sub[f]["first_award_year"] for p in firm_patents.get(f, set()))
        )
        print(f"{bucket}: {n} firms")
        print(f"  B82 patents (floor):      hold {b82_hold} ({100*b82_hold/n:.0f}%)   filed post-award {b82_post} ({100*b82_post/n:.0f}%)")
        print(f"  Any patents (upper bound): hold {any_hold} ({100*any_hold/n:.0f}%)   filed post-award {any_post} ({100*any_post/n:.0f}%)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
