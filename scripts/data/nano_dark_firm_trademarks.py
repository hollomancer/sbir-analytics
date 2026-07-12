#!/usr/bin/env python3
"""
T8 — trademark-filing check for the dark firm buckets.

Trademarks are the most commercialization-specific public instrument in the
triage ladder: a firm registering a product mark is going to market, which is
closer to §638 commercialization than a patent filing. Match dark firms
against USPTO Trademark Case Files (TRCFECO2, research edition) owner names,
join filing/registration dates, and tier confidence like the patent check
(state agreement + name specificity; the owner file carries no person names,
so no inventor/PI signal exists here).

Data currency: the 2023 vintage — filings after 2023 are invisible.

Inputs:
  data/nano_dark_firm_liveness.csv                  — dark firm list + first award year
  data/raw/sbir/award_data.csv                      — firm states
  data/raw/uspto/trademarks/owner.csv.zip           — TRCFECO2/2023
  data/raw/uspto/trademarks/case_file.csv.zip       — TRCFECO2/2023

Outputs:
  data/nano_dark_firm_trademarks.csv — one row per dark firm

Usage:
  python scripts/data/nano_dark_firm_trademarks.py
"""

import csv
import importlib.util
import io
import re
import sys
import zipfile
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DATA = REPO / "data"
TM = DATA / "raw/uspto/trademarks"

sys.path.insert(0, str(REPO))
from sbir_etl.utils.text_normalization import normalize_name  # noqa: E402

_liv_spec = importlib.util.spec_from_file_location(
    "nano_liveness", Path(__file__).parent / "nano_dark_firm_liveness.py"
)
liv = importlib.util.module_from_spec(_liv_spec)
_liv_spec.loader.exec_module(liv)

YEAR = re.compile(r"(19|20)\d\d")


def year_of(s: str) -> int:
    m = YEAR.search(s or "")
    return int(m.group(0)) if m else 0


def csv_rows(zip_path: Path):
    z = zipfile.ZipFile(zip_path)
    with z.open(z.infolist()[0].filename) as f:
        reader = csv.reader(io.TextIOWrapper(f, encoding="utf-8", errors="replace"))
        header = next(reader)
        idx = {c: i for i, c in enumerate(header)}
        for row in reader:
            yield idx, row


def main() -> int:
    liveness_csv = DATA / "nano_dark_firm_liveness.csv"
    awards_csv = DATA / "raw/sbir/award_data.csv"
    owner_zip = TM / "owner.csv.zip"
    case_zip = TM / "case_file.csv.zip"
    for p, hint in {
        liveness_csv: "run nano_dark_firm_liveness.py first",
        awards_csv: "SBIR.gov bulk CSV expected",
        owner_zip: "download via download_uspto.py --product-file TRCFECO2/2023/owner.csv.zip "
                   f"--local {TM}",
        case_zip: "download via download_uspto.py --product-file TRCFECO2/2023/case_file.csv.zip "
                  f"--local {TM}",
    }.items():
        if not p.exists():
            print(f"ERROR: {p} not found — {hint}", file=sys.stderr)
            return 1

    csv.field_size_limit(sys.maxsize)
    firms: dict[str, dict] = {}
    for r in csv.DictReader(open(liveness_csv, newline="", encoding="utf-8")):
        firms[r["normalized_name"]] = {
            "company": r["company"], "bucket": r["bucket"],
            "first_award_year": int(r["first_award_year"]),
        }
    print(f"Dark firms: {len(firms):,}")

    print("Loading firm states from SBIR.gov...")
    firm_states: dict[str, set[str]] = defaultdict(set)
    with open(awards_csv, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            norm = normalize_name(row.get("Company", ""), remove_suffixes=True)
            if norm in firms:
                st = liv.state_code(row.get("State", ""))
                if st:
                    firm_states[norm].add(st)

    print("Pass 1/2: scanning trademark owners (3.2 GB)...")
    firm_serials: dict[str, set[str]] = defaultdict(set)
    firm_tm_states: dict[str, set[str]] = defaultdict(set)
    for idx, row in csv_rows(owner_zip):
        name = row[idx["own_name"]]
        if not name:
            continue
        norm = normalize_name(name, remove_suffixes=True)
        if norm in firms:
            firm_serials[norm].add(row[idx["serial_no"]])
            st = (row[idx["own_addr_state_cd"]] or "").strip().upper()
            if st:
                firm_tm_states[norm].add(st)
    print(f"  {len(firm_serials):,} dark firms match ≥1 trademark owner")

    print("Pass 2/2: joining case files (3.25 GB)...")
    wanted = set().union(*firm_serials.values()) if firm_serials else set()
    serial_case: dict[str, tuple[int, bool, str]] = {}  # serial → (filing_year, registered, mark)
    for idx, row in csv_rows(case_zip):
        sn = row[idx["serial_no"]]
        if sn in wanted:
            reg_no = (row[idx["registration_no"]] or "").strip()
            serial_case[sn] = (
                year_of(row[idx["filing_dt"]]),
                bool(reg_no) and set(reg_no) != {"0"},  # '0000000' = never registered
                (row[idx["mark_id_char"]] or "")[:60],
            )

    out_csv = DATA / "nano_dark_firm_trademarks.csv"
    fields = ["company", "normalized_name", "bucket", "first_award_year", "tm_marks_n",
              "tm_registered_n", "tm_first_filing", "tm_last_filing", "tm_filed_post_award",
              "state_match", "name_generic", "match_confidence", "sample_marks"]
    rows_out: list[dict] = []
    for norm, rec in sorted(firms.items()):
        serials = firm_serials.get(norm, set())
        cases = [serial_case[s] for s in serials if s in serial_case]
        years = [y for y, _, _ in cases if y]
        registered = sum(1 for _, reg, _ in cases if reg)
        first_yr = rec["first_award_year"]
        tokens = norm.split()
        name_generic = len(tokens) <= 1 or all(t in liv.GENERIC_TOKENS for t in tokens)
        state_match = bool(firm_states.get(norm) and firm_tm_states.get(norm)
                           and firm_states[norm] & firm_tm_states[norm])
        if serials:
            confidence = ("high" if state_match and not name_generic
                          else "medium" if state_match or not name_generic
                          else "low")
        else:
            confidence = ""
        rows_out.append({
            "company": rec["company"],
            "normalized_name": norm,
            "bucket": rec["bucket"],
            "first_award_year": first_yr,
            "tm_marks_n": len(serials),
            "tm_registered_n": registered,
            "tm_first_filing": min(years) if years else "",
            "tm_last_filing": max(years) if years else "",
            "tm_filed_post_award": bool(years) and max(years) > first_yr,
            "state_match": state_match,
            "name_generic": name_generic,
            "match_confidence": confidence,
            "sample_marks": " | ".join(m for _, _, m in cases[:3] if m),
        })
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows_out)
    print(f"  Written: {out_csv} ({len(rows_out):,} rows)")

    print()
    print("=" * 70)
    print("DARK-FIRM TRADEMARK SUMMARY (TRCFECO2 2023 vintage)")
    print("=" * 70)
    for bucket in ("FIRM_ACTIVITY_ABSENT", "ENTITY_RESOLUTION_FAILURE"):
        sub = [r for r in rows_out if r["bucket"] == bucket]
        n = len(sub)
        hold = sum(1 for r in sub if r["tm_marks_n"])
        post = sum(1 for r in sub if r["tm_filed_post_award"])
        post_hi = sum(1 for r in sub if r["tm_filed_post_award"] and r["match_confidence"] == "high")
        reg = sum(1 for r in sub if r["tm_registered_n"])
        print(f"{bucket}: {n} firms")
        print(f"  ≥1 trademark: {hold} ({100*hold/n:.0f}%)   registered mark: {reg} ({100*reg/n:.0f}%)")
        print(f"  filed post-award: {post} ({100*post/n:.0f}%)   at high confidence: {post_hi} ({100*post_hi/n:.0f}%)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
