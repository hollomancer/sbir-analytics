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
    unrelated assignees). Any-class matches therefore carry a CONFIDENCE TIER
    built from three corroboration signals (same pattern as the Form D matcher):
      state_match        assignee location state ∩ firm's SBIR award state(s)
      inventor_pi_match  inventor last names on matched patents ∩ PI last names
                         on the firm's SBIR awards
      name_generic       normalized name is a single token or entirely generic
                         vocabulary ("advanced", "systems", "technologies", ...)
    high   = inventor_pi_match, or state_match with a non-generic name
    medium = state_match, or a non-generic name alone
    low    = generic name with no corroboration
    High-confidence post-award liveness is the defensible floor for the
    any-class channel.

"Filed post-award" means the firm's latest matched filing year exceeds its
first Phase II award year — activity evidence, not survival-to-present.

Path convention (same as nano_form_d_temporal.py / nano_ws1):
  --area <id>   → data/reports/<id>/dark_firm_liveness.csv
  (no flag)     → data/nano_dark_firm_liveness.csv  (legacy PR #428)

The cohort input is area-scoped; the SBIR bulk CSV, B82 extract, and USPTO
PatentsView zips are shared global inputs and stay under data/.

Inputs:
  cohort_keyword.csv / nano_cohort_keyword.csv             — deficiency classes
  data/raw/sbir/award_data.csv                              — firm states + PI names
  data/processed/uspto/b82_patents.csv                      — B82 extract
  data/raw/uspto/patentsview/g_assignee_disambiguated.tsv.zip
  data/raw/uspto/patentsview/g_application.tsv.zip
  data/raw/uspto/patentsview/g_location_disambiguated.tsv.zip
  data/raw/uspto/patentsview/g_inventor_disambiguated.tsv.zip

Outputs:
  dark_firm_liveness.csv — one row per dark firm

Usage:
  python scripts/data/nano_dark_firm_liveness.py [--area AREA] [--legacy]
"""

import argparse
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
from sbir_etl.utils.transition_report_paths import (  # noqa: E402
    add_area_args,
    resolve_area_paths,
)

DARK_BUCKETS = ("FIRM_ACTIVITY_ABSENT", "ENTITY_RESOLUTION_FAILURE")

# Tokens so common in R&D firm names that a name made only of them cannot
# support an exact-match identity claim on its own.
GENERIC_TOKENS = frozenset(
    "advanced applied technologies technology systems system research engineering "
    "scientific solutions industries laboratories laboratory labs materials sciences "
    "science associates development corporation company group international national "
    "american general precision dynamics innovations innovative instruments micro "
    "tech usa enterprises products design designs optics optical".split()
)


# SBIR.gov stores full state names; USPTO tables store USPS codes. Normalize to codes.
STATE_TO_CODE = {
    "ALABAMA": "AL", "ALASKA": "AK", "ARIZONA": "AZ", "ARKANSAS": "AR", "CALIFORNIA": "CA",
    "COLORADO": "CO", "CONNECTICUT": "CT", "DELAWARE": "DE", "FLORIDA": "FL", "GEORGIA": "GA",
    "HAWAII": "HI", "IDAHO": "ID", "ILLINOIS": "IL", "INDIANA": "IN", "IOWA": "IA",
    "KANSAS": "KS", "KENTUCKY": "KY", "LOUISIANA": "LA", "MAINE": "ME", "MARYLAND": "MD",
    "MASSACHUSETTS": "MA", "MICHIGAN": "MI", "MINNESOTA": "MN", "MISSISSIPPI": "MS",
    "MISSOURI": "MO", "MONTANA": "MT", "NEBRASKA": "NE", "NEVADA": "NV",
    "NEW HAMPSHIRE": "NH", "NEW JERSEY": "NJ", "NEW MEXICO": "NM", "NEW YORK": "NY",
    "NORTH CAROLINA": "NC", "NORTH DAKOTA": "ND", "OHIO": "OH", "OKLAHOMA": "OK",
    "OREGON": "OR", "PENNSYLVANIA": "PA", "RHODE ISLAND": "RI", "SOUTH CAROLINA": "SC",
    "SOUTH DAKOTA": "SD", "TENNESSEE": "TN", "TEXAS": "TX", "UTAH": "UT", "VERMONT": "VT",
    "VIRGINIA": "VA", "WASHINGTON": "WA", "WEST VIRGINIA": "WV", "WISCONSIN": "WI",
    "WYOMING": "WY", "DISTRICT OF COLUMBIA": "DC", "PUERTO RICO": "PR", "GUAM": "GU",
    "VIRGIN ISLANDS": "VI", "AMERICAN SAMOA": "AS", "NORTHERN MARIANA ISLANDS": "MP",
}


def state_code(raw: str) -> str:
    """Normalize an SBIR.gov state value (full name or code) to a USPS code."""
    s = (raw or "").strip().upper()
    return STATE_TO_CODE.get(s, s if len(s) == 2 else "")


def pi_last_name(raw: str) -> str:
    """Extract a comparable last name from an SBIR 'PI Name' field."""
    s = (raw or "").strip()
    if not s:
        return ""
    last = s.split(",")[0].strip() if "," in s else s.split()[-1]
    last = "".join(ch for ch in last.upper() if ch.isalpha())
    return last if len(last) >= 3 else ""


def tsv_rows(zip_path: Path):
    z = zipfile.ZipFile(zip_path)
    with z.open(z.infolist()[0].filename) as f:
        reader = csv.reader(io.TextIOWrapper(f, encoding="utf-8", newline=""), delimiter="\t")
        header = next(reader)
        idx = {c: i for i, c in enumerate(header)}
        for row in reader:
            yield idx, row


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    add_area_args(parser)
    args = parser.parse_args(argv)
    paths = resolve_area_paths(args, argv)

    cohort_csv = paths.artifact("cohort_keyword")
    awards_csv = DATA / "raw/sbir/award_data.csv"
    b82_csv = DATA / "processed/uspto/b82_patents.csv"
    assignee_zip = RAW / "g_assignee_disambiguated.tsv.zip"
    application_zip = RAW / "g_application.tsv.zip"
    location_zip = RAW / "g_location_disambiguated.tsv.zip"
    inventor_zip = RAW / "g_inventor_disambiguated.tsv.zip"
    required = {
        cohort_csv: f"run build_tech_area_cohort.py --area {paths.area_id} first",
        awards_csv: "SBIR.gov bulk CSV expected at this path",
        b82_csv: "run scripts/data/extract_b82_patents.py first",
        assignee_zip: "download via download_uspto.py --table assignee --local " + str(RAW),
        application_zip: "download via download_uspto.py --table application --local " + str(RAW),
        location_zip: "download via download_uspto.py --table location --local " + str(RAW),
        inventor_zip: "download via download_uspto.py --table inventor --local " + str(RAW),
    }
    for p, hint in required.items():
        if not p.exists():
            print(f"ERROR: {p} not found — {hint}", file=sys.stderr)
            return 1

    out_csv = paths.artifact("dark_firm_liveness")
    print(
        f"area={paths.area_id}{', legacy' if paths.legacy else ''}  out={out_csv}",
        file=sys.stderr,
    )

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

    print("Loading firm states and PI last names from SBIR.gov...")
    firm_states: dict[str, set[str]] = defaultdict(set)
    firm_pis: dict[str, set[str]] = defaultdict(set)
    with open(awards_csv, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            norm = normalize_name(row.get("Company", ""), remove_suffixes=True)
            if norm not in firms:
                continue
            state = state_code(row.get("State", ""))
            if state:
                firm_states[norm].add(state)
            pi = pi_last_name(row.get("PI Name", ""))
            if pi:
                firm_pis[norm].add(pi)
    print(f"  states for {len(firm_states):,} firms, PI names for {len(firm_pis):,}")

    print("Matching B82 extract (floor: nanotech patents, domain-consistent)...")
    b82_by_firm: dict[str, list[str]] = defaultdict(list)  # norm → filing dates
    with open(b82_csv, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            norm = normalize_name(row["assignee_organization"], remove_suffixes=True)
            if norm in firms:
                b82_by_firm[norm].append(row.get("filing_date", ""))

    print("Scanning full assignee table (upper bound: any patent class)...")
    firm_patents: dict[str, set[str]] = defaultdict(set)
    firm_loc_ids: dict[str, set[str]] = defaultdict(set)
    for idx, row in tsv_rows(assignee_zip):
        org = row[idx["disambig_assignee_organization"]]
        if not org:
            continue
        norm = normalize_name(org, remove_suffixes=True)
        if norm in firms:
            firm_patents[norm].add(row[idx["patent_id"]])
            loc = row[idx["location_id"]]
            if loc:
                firm_loc_ids[norm].add(loc)
    print(f"  {len(firm_patents):,} dark firms match ≥1 patent assignee")

    print("Resolving assignee states via location table...")
    wanted_locs = set().union(*firm_loc_ids.values()) if firm_loc_ids else set()
    loc_state: dict[str, str] = {}
    for idx, row in tsv_rows(location_zip):
        lid = row[idx["location_id"]]
        if lid in wanted_locs and (row[idx["disambig_country"]] or "").upper() in ("US", "USA", "UNITED STATES"):
            st = (row[idx["disambig_state"]] or "").strip().upper()
            if st:
                loc_state[lid] = st
    firm_assignee_states = {
        f: {loc_state[l] for l in locs if l in loc_state} for f, locs in firm_loc_ids.items()
    }

    print("Joining filing years for matched patents...")
    wanted = set().union(*firm_patents.values()) if firm_patents else set()
    pat_year: dict[str, int] = {}
    for idx, row in tsv_rows(application_zip):
        pid = row[idx["patent_id"]]
        if pid in wanted:
            fd = row[idx["filing_date"]]
            if len(fd) == 10 and "1900" <= fd[:4] <= "2030":
                pat_year[pid] = int(fd[:4])

    print("Collecting inventor last names for matched patents (2.3 GB scan)...")
    pid_owner: dict[str, list[str]] = defaultdict(list)
    for f, pids in firm_patents.items():
        for p in pids:
            pid_owner[p].append(f)
    firm_inventors: dict[str, set[str]] = defaultdict(set)
    for idx, row in tsv_rows(inventor_zip):
        pid = row[idx["patent_id"]]
        owners = pid_owner.get(pid)
        if not owners:
            continue
        last = "".join(ch for ch in (row[idx["disambig_inventor_name_last"]] or "").upper()
                       if ch.isalpha())
        if len(last) >= 3:
            for f in owners:
                firm_inventors[f].add(last)

    def score_confidence(norm: str) -> tuple[bool, bool, bool, str]:
        """Return (state_match, inventor_pi_match, name_generic, tier) for a matched firm."""
        state_match = bool(firm_states.get(norm) and firm_assignee_states.get(norm)
                           and firm_states[norm] & firm_assignee_states[norm])
        pi_match = bool(firm_pis.get(norm) and firm_inventors.get(norm)
                        and firm_pis[norm] & firm_inventors[norm])
        tokens = norm.split()
        name_generic = len(tokens) <= 1 or all(t in GENERIC_TOKENS for t in tokens)
        if pi_match or (state_match and not name_generic):
            tier = "high"
        elif state_match or not name_generic:
            tier = "medium"
        else:
            tier = "low"
        return state_match, pi_match, name_generic, tier

    fields = ["company", "normalized_name", "name_tokens", "bucket", "awards_n",
              "first_award_year", "b82_patents_n", "b82_filed_post_award",
              "any_patents_n", "any_latest_filing_year", "any_filed_post_award",
              "state_match", "inventor_pi_match", "name_generic", "match_confidence"]
    confidence: dict[str, str] = {}
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for norm, rec in sorted(firms.items()):
            first_yr = rec["first_award_year"]
            b82_filings = [d for d in b82_by_firm.get(norm, []) if d]
            b82_post = any(int(d[:4]) > first_yr for d in b82_filings)
            years = [pat_year[p] for p in firm_patents.get(norm, set()) if p in pat_year]
            latest = max(years) if years else ""
            matched = norm in firm_patents
            if matched:
                state_match, pi_match, name_generic, tier = score_confidence(norm)
                confidence[norm] = tier
            else:
                state_match = pi_match = name_generic = False
                tier = ""
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
                "state_match": state_match,
                "inventor_pi_match": pi_match,
                "name_generic": name_generic,
                "match_confidence": tier,
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
        def _post(f: str) -> bool:
            return any(pat_year.get(p, 0) > sub[f]["first_award_year"]
                       for p in firm_patents.get(f, set()))
        any_post = sum(1 for f in sub if _post(f))
        print(f"{bucket}: {n} firms")
        print(f"  B82 patents (floor):      hold {b82_hold} ({100*b82_hold/n:.0f}%)   filed post-award {b82_post} ({100*b82_post/n:.0f}%)")
        print(f"  Any patents (upper bound): hold {any_hold} ({100*any_hold/n:.0f}%)   filed post-award {any_post} ({100*any_post/n:.0f}%)")
        for tier in ("high", "medium", "low"):
            t_hold = sum(1 for f in sub if confidence.get(f) == tier)
            t_post = sum(1 for f in sub if confidence.get(f) == tier and _post(f))
            print(f"    any-class {tier:<6} confidence: hold {t_hold:>3} ({100*t_hold/n:.0f}%)   post-award {t_post:>3} ({100*t_post/n:.0f}%)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
