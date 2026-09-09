#!/usr/bin/env python3
"""Draw a stratified adjudication sample of the Form D business-combination join.

`detect_sbir_ma_events.py` keeps only `match_confidence.tier == "high"` records
from `form_d_details.jsonl`. This script samples those survivors so a human can
label whether the SEC filer really is the SBIR firm.

`form_d_scoring.py` grants "high" on a PI-to-officer name score >= 0.7 **or** a
ZIP match, so "high" hides two very different joins. The strata are those two
qualifying signals:

- `person_only`   — a person confirmed the match; no ZIP match.
- `zip_only`      — only the ZIP matched. The risk stratum: business parks and
                    incubators put many unrelated SBIR firms at one ZIP.
- `person_and_zip` — both signals fired.

`zip_sbir_firm_count` counts distinct SBIR companies at the matched ZIP, so an
adjudicator can see when a ZIP match proves almost nothing. Measured 2026-09-09
over the 84 zip_only survivors: 58 share a ZIP with 5 or more SBIR firms, and
the busiest shared ZIP holds 380.

`matched_zip` is null when no ZIP in `award_data.csv` for that firm equals a
Form D ZIP — 16 of the 84. The scorer still set `address_score` to 1.0, so
those rows rest on a ZIP this script cannot reproduce from the awards CSV.
Treat a null `matched_zip` as an unverified ZIP claim, not as a passing one.

Rows carry `label: "UNREVIEWED"` and `rationale: null`. This script never labels.

Exploratory tier. The output is a labeling worksheet, not a citable artifact.

Usage:
    python scripts/data/sample_form_d_join_adjudication.py
    python scripts/data/sample_form_d_join_adjudication.py --per-stratum 30 --seed 0
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

# form_d_scoring.py:339 — either signal alone earns the "high" tier.
PERSON_MATCH_MIN = 0.7
ADDRESS_MATCH_MIN = 1.0


def stratum_of(confidence: dict) -> str | None:
    """Return which qualifying signal earned the high tier, or None if neither."""
    person_score = confidence.get("person_score")
    address_score = confidence.get("address_score")
    person = person_score is not None and person_score >= PERSON_MATCH_MIN
    address = address_score is not None and address_score >= ADDRESS_MATCH_MIN
    if person and address:
        return "person_and_zip"
    if person:
        return "person_only"
    if address:
        return "zip_only"
    return None


def load_sbir_firms_by_zip(awards_csv: Path) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    """Return distinct SBIR company names per 5-digit ZIP, and each firm's ZIPs.

    A firm holds awards across years and can move, so it has a set of ZIPs, not
    one. The scorer compares the Form D ZIPs against all of them; taking only
    the first would report a ZIP that never matched.

    Company names are keyed upper-cased to match the SEC-derived naming in
    ``form_d_details.jsonl``.
    """
    firms_by_zip: dict[str, set[str]] = defaultdict(set)
    zips_by_firm: dict[str, set[str]] = defaultdict(set)
    csv.field_size_limit(10_000_000)
    with awards_csv.open(encoding="utf-8", errors="replace") as f:
        for row in csv.DictReader(f):
            name = (row.get("Company") or "").strip()
            zip_5 = (row.get("Zip") or "").strip()[:5]
            if not name or not zip_5:
                continue
            firms_by_zip[zip_5].add(name.upper())
            zips_by_firm[name.upper()].add(zip_5)
    return firms_by_zip, zips_by_firm


def survivors(form_d_path: Path) -> list[dict]:
    """Return the business-combination records detect_sbir_ma_events.py keeps."""
    kept = []
    with form_d_path.open() as f:
        for line in f:
            record = json.loads(line)
            combos = [o for o in record.get("offerings") or [] if o.get("is_business_combination")]
            if not combos:
                continue
            if (record.get("match_confidence") or {}).get("tier") != "high":
                continue
            record["_combos"] = sorted(combos, key=lambda o: str(o.get("filing_date", "")))
            kept.append(record)
    return kept


def build_row(
    record: dict,
    stratum: str,
    stratum_size: int,
    firms_by_zip: dict[str, set[str]],
    zips_by_firm: dict[str, set[str]],
) -> dict:
    """Build one adjudication worksheet row."""
    confidence = record["match_confidence"]
    earliest = record["_combos"][0]
    sbir_zips = zips_by_firm.get(record["company_name"].strip().upper(), set())
    form_d_zips = {(o.get("zip_code") or "").strip()[:5] for o in record["_combos"]} - {""}
    shared = sorted(sbir_zips & form_d_zips)
    # The crowding of the busiest shared ZIP: the weakest reading of the match.
    matched_zip = max(shared, key=lambda z: len(firms_by_zip.get(z, ()))) if shared else None
    return {
        "sbir_company": record["company_name"],
        "cik": record.get("form_d_cik"),
        "sec_filer": earliest.get("entity_name"),
        "filing_date": str(earliest.get("filing_date", ""))[:10],
        "sec_city": earliest.get("city"),
        "sec_state": earliest.get("state"),
        "sec_revenue": earliest.get("revenue_range"),
        "combo_count": len(record["_combos"]),
        "stratum": stratum,
        "stratum_size": stratum_size,
        "person_score": confidence.get("person_score"),
        "person_detail": confidence.get("person_match_detail"),
        "address_score": confidence.get("address_score"),
        "state_score": confidence.get("state_score"),
        "name_score": confidence.get("name_score"),
        "score": confidence.get("score"),
        "sbir_zips": sorted(sbir_zips),
        "form_d_zips": sorted(form_d_zips),
        "matched_zip": matched_zip,
        "zip_sbir_firm_count": len(firms_by_zip.get(matched_zip, ())) if matched_zip else None,
        "label": "UNREVIEWED",
        "rationale": None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--form-d", type=Path, default=Path("data/form_d_details.jsonl"))
    parser.add_argument("--awards", type=Path, default=Path("data/raw/sbir/award_data.csv"))
    parser.add_argument(
        "--output", type=Path, default=Path("data/processed/form_d_join_adjudication.jsonl")
    )
    parser.add_argument(
        "--per-stratum",
        type=int,
        default=30,
        help="Maximum rows per stratum. A smaller stratum is taken whole.",
    )
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    for path in (args.form_d, args.awards):
        if not path.exists():
            print(f"missing input: {path}", file=sys.stderr)
            return 1

    firms_by_zip, zips_by_firm = load_sbir_firms_by_zip(args.awards)
    kept = survivors(args.form_d)

    strata: dict[str, list[dict]] = defaultdict(list)
    unclassified = 0
    for record in kept:
        stratum = stratum_of(record["match_confidence"])
        if stratum is None:
            # Should not happen: the tier is granted by one of these two signals.
            unclassified += 1
            continue
        strata[stratum].append(record)

    rng = random.Random(args.seed)
    rows = []
    for stratum in sorted(strata):
        population = sorted(strata[stratum], key=lambda r: (r["company_name"], r["form_d_cik"]))
        take = min(args.per_stratum, len(population))
        for record in rng.sample(population, take):
            rows.append(build_row(record, stratum, len(population), firms_by_zip, zips_by_firm))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w") as out:
        for row in rows:
            out.write(json.dumps(row, default=str) + "\n")

    print(f"High-tier business-combination survivors: {len(kept)}")
    for stratum in sorted(strata):
        sampled = sum(1 for r in rows if r["stratum"] == stratum)
        print(f"  {stratum:<15} population {len(strata[stratum]):>4}  sampled {sampled:>4}")
    if unclassified:
        print(f"  unclassified (neither signal): {unclassified}")
    print(f"Wrote {len(rows)} UNREVIEWED rows to {args.output} (seed {args.seed})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
