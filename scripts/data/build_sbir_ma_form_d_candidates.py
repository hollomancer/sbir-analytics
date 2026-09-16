#!/usr/bin/env python3
"""Build a private SBIR-to-Form-D candidate ledger.

Epistemic tier: exploratory. This script creates candidate linkages only; it
does not resolve firm identity, retrieve XML, evaluate Form D predicates, or
produce a numerical result.

Ledger grain is ``(name_key, accession)``, not one row per filing. EDGAR emits
one index line per filer on a multi-filer submission, so one accession can
appear under two filer-name spellings that normalize to different keys. Row
count is therefore not a filing count; the consumers collapse to one row per
accession and report how many rows they collapsed.

Two name keys are available, and the second is opt-in:

``form-d-join-v1`` (always) is the exact key: trim, upper-case, collapse
interior whitespace. A legal-form difference defeats it, so ``"Luna
Innovations, LLC"`` and ``"LUNA INNOVATIONS"`` do not meet.

``recipient-v1`` (``--include-legal-form-variants``) drops legal designators,
which is what most SBIR-to-EDGAR name differences are. It is not a pure
legal-form strip: it also lower-cases, folds diacritics and removes punctuation,
so it is a broader key than the exact one in more than one respect. Measured
against the full EDGAR Form D filer universe it raises the share of SBIR firms
finding a filer from 5.46% to 12.28% — 2,349 more firms — at the cost of 56
keys that reach more than one CIK, versus 5 under the exact key.

The widened pass is opt-in and additive because this ledger backs a dated study
cut. With the flag off, output is byte-identical to the exact-key ledger; with
it on, exact rows are unchanged and widened rows are appended, each carrying
``match_rationale`` and the ambiguity fields a reviewer needs. Filtering to
``match_rationale == "exact_form_d_join_v1_name_key"`` therefore reproduces the
frozen ledger exactly.

A widened row is a candidate, not a resolution. ``name_key_ambiguous`` marks a
key reaching several CIKs, and ``sbir_exact_key_count`` marks an SBIR side that
collapsed several exact keys into one widened key. Both are for adjudication
downstream: whether two SBIR spellings are one firm is a separate question this
script does not answer.
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


EXACT_PROFILE = CompanyNameProfile.FORM_D_JOIN_V1
LEGAL_FORM_PROFILE = CompanyNameProfile.RECIPIENT_V1
EXACT_RATIONALE = "exact_form_d_join_v1_name_key"
LEGAL_FORM_RATIONALE = "legal_form_stripped_recipient_v1_name_key"


def _source_key(value: object) -> str:
    return normalize_company_name(value, profile=EXACT_PROFILE)


def _legal_form_key(value: object) -> str:
    """Key with legal designators stripped, so "X, LLC" and "X" can meet."""
    return normalize_company_name(value, profile=LEGAL_FORM_PROFILE)


def _widen_sbir_index(
    exact: dict[str, dict[str, object]],
) -> dict[str, dict[str, object]]:
    """Group exact SBIR keys by their legal-form-stripped key.

    An entry whose ``exact_keys`` holds more than one member means two SBIR
    spellings collapsed. That is recorded, not resolved: this script does not
    decide whether they are one firm.
    """
    widened: dict[str, dict[str, object]] = {}
    for exact_key, entry in exact.items():
        key = _legal_form_key(exact_key)
        if not key:
            continue
        merged = widened.setdefault(
            key,
            {
                "aliases": set(),
                "award_identifiers": set(),
                "source_row_count": 0,
                "exact_keys": set(),
            },
        )
        merged["aliases"] |= entry["aliases"]  # type: ignore[operator,index]
        merged["award_identifiers"] |= entry["award_identifiers"]  # type: ignore[operator,index]
        merged["source_row_count"] += entry["source_row_count"]  # type: ignore[index,operator]
        merged["exact_keys"].add(exact_key)  # type: ignore[index,union-attr]
    return widened


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


def _form_d_entries(index_dir: Path, *, widen: bool = False):
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
                    yield (
                        key,
                        _legal_form_key(filer_name),
                        {
                            "filer_name": filer_name,
                            "cik": cik,
                            "filing_date": filed.isoformat(),
                            "form_type": parts[0],
                            "accession_number": accession,
                            "index_path": str(path),
                        },
                    )


def _record(
    profile: CompanyNameProfile,
    rationale: str,
    key: str,
    source: dict[str, object],
    filing: dict[str, object],
) -> dict[str, object]:
    identifiers = sorted(source["award_identifiers"])  # type: ignore[arg-type,index]
    return {
        "claim_status": "candidate",
        "match_rationale": rationale,
        "name_key_profile": profile.value,
        "name_key": key,
        "sbir_aliases": sorted(source["aliases"]),  # type: ignore[arg-type,index]
        "sbir_source_row_count": source["source_row_count"],
        "sbir_award_identifiers": [
            {"uei": uei, "duns": duns, "agency_tracking_number": tracking, "contract": contract}
            for uei, duns, tracking, contract in identifiers
        ],
        "form_d_index": filing,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--awards", type=Path, required=True)
    parser.add_argument("--form-d-index-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--include-legal-form-variants",
        action="store_true",
        help=(
            "also emit candidates whose names meet only after legal designators "
            "are stripped (recipient-v1). Exact rows are unchanged; widened rows "
            "are appended and labelled."
        ),
    )
    args = parser.parse_args()

    sbir = _load_sbir_aliases(args.awards)
    widened_sbir = _widen_sbir_index(sbir) if args.include_legal_form_variants else {}

    exact_rows: list[dict[str, object]] = []
    widened_lines: list[tuple[str, dict[str, object]]] = []
    widened_hits: list[tuple[str, dict[str, object]]] = []
    seen: set[tuple[str, str]] = set()
    matched_keys: set[str] = set()
    matched_accessions: set[str] = set()
    exact_accessions: set[str] = set()
    # Ambiguity is scored over matched filings only: a key reaching several CIKs
    # is what makes attribution unsafe, and an unmatched key cannot mislead.
    ciks_by_widened_key: dict[str, set[str]] = {}
    filers_by_widened_key: dict[str, set[str]] = {}

    for key, widened_key, filing in _form_d_entries(
        args.form_d_index_dir, widen=args.include_legal_form_variants
    ):
        source = sbir.get(key)
        if source is not None:
            dedupe_key = (key, str(filing["accession_number"]))
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            exact_rows.append(_record(EXACT_PROFILE, EXACT_RATIONALE, key, source, filing))
            matched_keys.add(key)
            matched_accessions.add(str(filing["accession_number"]))
            exact_accessions.add(str(filing["accession_number"]))
            continue
        if not args.include_legal_form_variants:
            continue
        if widened_sbir.get(widened_key) is None:
            continue
        widened_lines.append((widened_key, filing))

    # Exact precedence is a property of the submission, not of one index line.
    # EDGAR writes one line per filer, so a submission can match exactly on one
    # filer name and only by legal form on another; the exact candidate wins for
    # the whole accession. The exact line may arrive after the widened one, so
    # this cannot be decided while streaming.
    widened_lines = [
        (widened_key, filing)
        for widened_key, filing in widened_lines
        if str(filing["accession_number"]) not in exact_accessions
    ]

    # Ambiguity is counted over every surviving line, before the output dedupe.
    # Two filer lines in one accession can carry different CIKs under the same
    # widened key; deduping first would drop the second CIK and report the key
    # as unambiguous when it is not.
    for widened_key, filing in widened_lines:
        ciks_by_widened_key.setdefault(widened_key, set()).add(str(filing["cik"]))
        filers_by_widened_key.setdefault(widened_key, set()).add(str(filing["filer_name"]))

    for widened_key, filing in widened_lines:
        dedupe_key = (widened_key, str(filing["accession_number"]))
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        widened_hits.append((widened_key, filing))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    ambiguous_rows = 0
    with args.output.open("w", encoding="utf-8") as output:
        for record in exact_rows:
            output.write(json.dumps(record, sort_keys=True) + "\n")
        for widened_key, filing in widened_hits:
            widened_source = widened_sbir[widened_key]
            ciks = ciks_by_widened_key.get(widened_key, set())
            filers = filers_by_widened_key.get(widened_key, set())
            record = _record(
                LEGAL_FORM_PROFILE, LEGAL_FORM_RATIONALE, widened_key, widened_source, filing
            )
            record["name_key_ambiguous"] = len(ciks) > 1
            record["form_d_cik_count"] = len(ciks)
            record["form_d_filer_name_count"] = len(filers)
            record["sbir_exact_key_count"] = len(widened_source["exact_keys"])  # type: ignore[arg-type]
            record["sbir_exact_keys"] = sorted(widened_source["exact_keys"])  # type: ignore[arg-type]
            if len(ciks) > 1 or len(widened_source["exact_keys"]) > 1:  # type: ignore[arg-type]
                ambiguous_rows += 1
            output.write(json.dumps(record, sort_keys=True) + "\n")
            matched_accessions.add(str(filing["accession_number"]))

    # Three distinct quantities that were previously collapsed into two labels.
    # `written` is the ledger row count at (name_key, accession) grain, which is
    # not a filing count when one accession matches two filer-name spellings.
    written = len(exact_rows) + len(widened_hits)
    print(f"Selected-row name keys: {len(sbir):,}")
    print(f"Name keys with at least one candidate: {len(matched_keys):,}")
    print(f"Candidate ledger rows (name_key, accession): {written:,}")
    print(f"Distinct candidate accessions: {len(matched_accessions):,}")
    if args.include_legal_form_variants:
        widened_keys = {k for k, _ in widened_hits}
        print(f"  exact-key rows: {len(exact_rows):,}")
        print(f"  legal-form-variant rows: {len(widened_hits):,} across {len(widened_keys):,} keys")
        print(f"  legal-form-variant rows needing adjudication: {ambiguous_rows:,}")
    print(f"Output: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
