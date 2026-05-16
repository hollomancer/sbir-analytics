#!/usr/bin/env python3
"""Export the Form D high-confidence SBIR cohort.

Reproduces the cohort defined in
docs/research/sbir-form-d-fundraising-analysis.md:

  high-confidence tier in form_d_details.jsonl,
  AND (company name matches an SBIR firm OR Form D issuer ZIP matches
       an SBIR firm's ZIP)

Aggregates SBIR award history per firm. Writes
$SBIR_DATA_DIR/form_d_high_conf_cohort.jsonl.

Usage:
    python scripts/data/ucc/export_cohort.py
    python scripts/data/ucc/export_cohort.py --form-d-details path/to/form_d_details.jsonl

Field normalization notes (raw data → build_cohort_rows interface):
  - form_d_details.jsonl has no top-level issuer_zip/name_match/zip_match;
    these are derived in _normalize_form_d() from offerings[].zip_code,
    match_confidence.person_score, and match_confidence.address_score.
  - award_data.csv columns are 'Company', 'Award Year', 'Award Amount',
    'State', 'Zip'; these are normalized to snake_case in _normalize_sbir_award().
  - SBIR 'Zip' may carry a +4 suffix (e.g. '01821-3934'); only the first 5
    digits are used for ZIP matching.
"""

import argparse
import csv
import json
import sys
from collections import defaultdict
from collections.abc import Iterable, Iterator
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from ucc._common import data_path  # noqa: E402

# Threshold for treating person_score as a "name match" (matches tier rule).
_PERSON_SCORE_THRESHOLD = 0.7


def build_cohort_rows(
    form_d_records: Iterable[dict],
    sbir_awards: Iterable[dict],
) -> Iterator[dict]:
    """Build cohort rows by joining high-tier Form D records to SBIR awards.

    Expects pre-normalized records (see _normalize_form_d / _normalize_sbir_award
    for real-data normalization). Each record must have:
      - match_confidence.tier
      - name_match (bool)
      - zip_match (bool)
      - issuer_zip (str, 5-digit)
      - company_name (str)

    Each award must have: company_name, state, zip_code, agency, award_year,
    award_amount.

    Yields one row per matched firm. Award history is aggregated:
    first/last year, total amount, plus Form D totals.
    """
    awards_by_name: dict[str, list[dict]] = defaultdict(list)
    awards_by_zip: dict[str, list[dict]] = defaultdict(list)
    for a in sbir_awards:
        norm = (a.get("company_name") or "").upper().strip()
        awards_by_name[norm].append(a)
        zip_code = (a.get("zip_code") or "").strip()[:5]
        if zip_code:
            awards_by_zip[zip_code].append(a)

    seen_firms: set[str] = set()
    for rec in form_d_records:
        tier = (rec.get("match_confidence") or {}).get("tier")
        if tier != "high":
            continue
        has_name = bool(rec.get("name_match"))
        has_zip = bool(rec.get("zip_match"))
        if not (has_name or has_zip):
            continue

        norm_name = (rec.get("company_name") or "").upper().strip()
        zip_code = (rec.get("issuer_zip") or "").strip()[:5]
        joined_awards = awards_by_name.get(norm_name) or awards_by_zip.get(zip_code) or []
        if not joined_awards:
            continue

        sbir_name = joined_awards[0].get("company_name") or rec["company_name"]
        if sbir_name in seen_firms:
            continue
        seen_firms.add(sbir_name)

        years = sorted({int(a["award_year"]) for a in joined_awards if a.get("award_year")})
        amounts = [float(a.get("award_amount") or 0) for a in joined_awards]
        agencies = [a.get("agency") for a in joined_awards if a.get("agency")]
        primary_agency = max(set(agencies), key=agencies.count) if agencies else "Unknown"

        yield {
            "company_name": sbir_name,
            "state": joined_awards[0].get("state", rec.get("issuer_state", "")),
            "agency": primary_agency,
            "first_award_year": years[0] if years else 0,
            "last_award_year": years[-1] if years else 0,
            "total_award_amount": sum(amounts),
            "form_d_filing_count": 1,
            "form_d_total_raised": float(rec.get("total_amount_sold") or 0),
        }


def _normalize_form_d(raw: dict) -> dict:
    """Translate a raw form_d_details.jsonl record into build_cohort_rows shape.

    Derives:
      - issuer_zip from the first offering's zip_code (5-digit prefix)
      - issuer_state from the first offering's state
      - name_match from match_confidence.person_score >= 0.7
      - zip_match from match_confidence.address_score > 0
      - total_amount_sold from the top-level total_raised field
    """
    mc = raw.get("match_confidence") or {}
    offerings = raw.get("offerings") or []
    first_offering = offerings[0] if offerings else {}

    raw_zip = (first_offering.get("zip_code") or "").strip()
    issuer_zip = raw_zip[:5] if raw_zip else ""

    return {
        "company_name": raw.get("company_name", ""),
        "issuer_state": first_offering.get("state", ""),
        "issuer_zip": issuer_zip,
        "total_amount_sold": raw.get("total_raised", 0),
        "match_confidence": mc,
        "name_match": float(mc.get("person_score") or 0) >= _PERSON_SCORE_THRESHOLD,
        "zip_match": float(mc.get("address_score") or 0) > 0,
    }


def _normalize_sbir_award(row: dict) -> dict:
    """Translate a raw award_data.csv row into build_cohort_rows award shape.

    Maps CSV column names (Company, Award Year, Award Amount, State, Zip) to
    the snake_case names expected by build_cohort_rows. ZIP is trimmed to 5
    digits to match Form D ZIP format.
    """
    raw_zip = (row.get("Zip") or "").strip()
    zip5 = raw_zip[:5] if raw_zip else ""
    try:
        year = int(row.get("Award Year") or 0)
    except (ValueError, TypeError):
        year = 0
    try:
        amount = float(row.get("Award Amount") or 0)
    except (ValueError, TypeError):
        amount = 0.0
    return {
        "company_name": (row.get("Company") or "").strip(),
        "state": (row.get("State") or "").strip(),
        "zip_code": zip5,
        "agency": (row.get("Agency") or "").strip(),
        "award_year": year,
        "award_amount": amount,
    }


def _read_jsonl(path: Path) -> Iterator[dict]:
    with path.open() as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def _read_sbir_awards(path: Path) -> Iterator[dict]:
    """Read SBIR awards from award_data.csv (or a JSONL fallback)."""
    if path.suffix.lower() == ".jsonl":
        yield from _read_jsonl(path)
        return
    with path.open() as f:
        for row in csv.DictReader(f):
            yield _normalize_sbir_award(row)


def main() -> int:
    parser = argparse.ArgumentParser(description="Export Form D high-confidence cohort")
    parser.add_argument("--form-d-details", type=Path,
                        default=data_path("form_d_details.jsonl"))
    # Actual filename is raw/sbir/award_data.csv (not sbir_awards.csv).
    parser.add_argument("--sbir-awards", type=Path,
                        default=data_path("raw/sbir/award_data.csv"))
    parser.add_argument("--out", type=Path,
                        default=data_path("form_d_high_conf_cohort.jsonl"))
    args = parser.parse_args()

    form_d = [_normalize_form_d(r) for r in _read_jsonl(args.form_d_details)]
    awards = list(_read_sbir_awards(args.sbir_awards))
    rows = list(build_cohort_rows(form_d, awards))

    with args.out.open("w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")

    print(f"Wrote {len(rows)} cohort rows to {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
