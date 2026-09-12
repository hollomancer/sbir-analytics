#!/usr/bin/env python3
"""Build a private, exact-key SBIR-to-Form-D candidate ledger.

Epistemic tier: exploratory. This script creates candidate linkages only; it
does not resolve firm identity, retrieve XML, evaluate Form D predicates, or
produce a numerical result.
"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import date
from pathlib import Path

from sbir_etl.identity import CompanyNameProfile, normalize_company_name


EPISTEMIC_TIER = "exploratory"
SELECTION_CUTOFF = date(2026, 8, 29)


def _source_key(value: object) -> str:
    return normalize_company_name(value, profile=CompanyNameProfile.FORM_D_JOIN_V1)


def _load_sbir_aliases(path: Path) -> dict[str, dict[str, object]]:
    candidates: dict[str, dict[str, object]] = {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            company = (row.get("Company") or "").strip()
            try:
                proposal_date = date.fromisoformat((row.get("Proposal Award Date") or "").strip())
            except ValueError:
                continue
            if not company or proposal_date > SELECTION_CUTOFF:
                continue
            key = _source_key(company)
            if not key:
                continue
            entry = candidates.setdefault(
                key,
                {"aliases": set(), "award_identifiers": set(), "source_row_count": 0},
            )
            entry["aliases"].add(company)  # type: ignore[index,union-attr]
            entry["award_identifiers"].add(  # type: ignore[index,union-attr]
                (
                    (row.get("UEI") or "").strip(),
                    (row.get("Duns") or "").strip(),
                    (row.get("Agency Tracking Number") or "").strip(),
                    (row.get("Contract") or "").strip(),
                )
            )
            entry["source_row_count"] += 1  # type: ignore[index,operator]
    return candidates


def _form_d_entries(index_dir: Path):
    for path in sorted(index_dir.glob("*.idx")):
        with path.open(encoding="latin-1") as handle:
            for line in handle:
                parts = line.rstrip().split()
                if len(parts) < 5 or parts[0] not in {"D", "D/A"}:
                    continue
                try:
                    filed = date.fromisoformat(parts[-2])
                except ValueError:
                    continue
                if filed > SELECTION_CUTOFF:
                    continue
                cik = parts[-3]
                filename = parts[-1]
                accession = filename.rsplit("/", 1)[-1].removesuffix(".txt")
                filer_name = line[len(parts[0]) : line.rfind(cik, 0, line.rfind(parts[-2]))].strip()
                key = _source_key(filer_name)
                if key:
                    yield key, {
                        "filer_name": filer_name,
                        "cik": cik,
                        "filing_date": filed.isoformat(),
                        "form_type": parts[0],
                        "accession_number": accession,
                        "index_path": str(path),
                    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--awards", type=Path, required=True)
    parser.add_argument("--form-d-index-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    sbir = _load_sbir_aliases(args.awards)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    seen: set[tuple[str, str]] = set()
    written = 0
    with args.output.open("w", encoding="utf-8") as output:
        for key, filing in _form_d_entries(args.form_d_index_dir):
            source = sbir.get(key)
            if source is None:
                continue
            dedupe_key = (key, str(filing["accession_number"]))
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            identifiers = sorted(source["award_identifiers"])  # type: ignore[arg-type,index]
            record = {
                "claim_status": "candidate",
                "match_rationale": "exact_form_d_join_v1_name_key",
                "name_key_profile": CompanyNameProfile.FORM_D_JOIN_V1.value,
                "name_key": key,
                "sbir_aliases": sorted(source["aliases"]),  # type: ignore[arg-type,index]
                "sbir_source_row_count": source["source_row_count"],
                "sbir_award_identifiers": [
                    {"uei": uei, "duns": duns, "agency_tracking_number": tracking, "contract": contract}
                    for uei, duns, tracking, contract in identifiers
                ],
                "form_d_index": filing,
            }
            output.write(json.dumps(record, sort_keys=True) + "\n")
            written += 1
    print(f"SBIR exact-name keys: {len(sbir):,}")
    print(f"Candidate Form D filings: {written:,}")
    print(f"Output: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
