#!/usr/bin/env python3
"""Record the Form D business-combination field for private candidate XML.

Epistemic tier: exploratory. This private accession-grain audit records only
the source-declared XML field authorized by Amendment 7. It does not resolve an
identity, create an event, or produce an aggregate result.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from xml.etree import ElementTree


EPISTEMIC_TIER = "exploratory"
PREDICATE_VERSION = "form_d_business_combination_v1"
PREDICATE_PATH = "offeringData/businessCombinationTransaction/isBusinessCombinationTransaction"


def _records(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _candidate_filings(path: Path) -> tuple[dict[str, dict[str, str]], int]:
    """Return one filing per accession, and how many ledger rows were collapsed.

    The ledger is written at ``(name_key, accession)`` grain, so one accession
    appears once per filer-name spelling that normalized to a distinct key --
    EDGAR emits one index line per filer on a multi-filer submission. Rejecting
    the repeat would abort the pipeline on any cut that contains one. Collapse
    to the lowest name_key so the choice is deterministic, and return the
    collapsed count so the caller can report it.
    """
    filings: dict[str, dict[str, str]] = {}
    chosen_key: dict[str, str] = {}
    collapsed = 0
    for record in _records(path):
        filing = record["form_d_index"]
        accession = filing["accession_number"]
        name_key = str(record.get("name_key", ""))
        if accession in filings:
            collapsed += 1
            if name_key >= chosen_key[accession]:
                continue
        chosen_key[accession] = name_key
        filings[accession] = {
            "accession_number": accession,
            "cik": filing["cik"],
            "filing_date": filing["filing_date"],
            "form_type": filing["form_type"],
        }
    return filings, collapsed


def _successful_xml_retrieval(record: dict) -> bool:
    """True when a manifest line is a complete retrieval (HTTP 200 with bytes).

    Mirrors fetch_sbir_ma_form_d_xml._successful_xml_retrieval: an empty-body
    200 is incomplete, and a later retry may append another status-200 line.
    """
    return bool(record.get("status") == 200 and record.get("bytes") and record.get("sha256"))


def _xml_provenance(path: Path) -> dict[str, dict[str, str]]:
    provenance: dict[str, dict[str, str]] = {}
    for record in _records(path):
        if not _successful_xml_retrieval(record):
            continue
        # Last complete retrieval wins. Do not treat an empty-body 200 as unique.
        provenance[record["accession_number"]] = {"sha256": record["sha256"]}
    return provenance


# `isBusinessCombinationTransaction` is an XML Schema boolean, whose lexical
# space is {true, false, 1, 0}. Reading anything other than "true" as false
# would record a filing that encodes `1` as a negative observation, in a study
# whose manifest sets negative_evidence_allowed: false. A value outside the
# lexical space is not evidence either way and stays `unavailable`.
_XSD_BOOLEAN_TRUE = frozenset({"true", "1"})
_XSD_BOOLEAN_FALSE = frozenset({"false", "0"})


def _predicate(xml_bytes: bytes) -> str:
    """Return the tri-state source-field observation authorized by Amendment 7."""
    try:
        root = ElementTree.fromstring(xml_bytes)
    except ElementTree.ParseError:
        return "unavailable"

    element = root.find(PREDICATE_PATH)
    if element is None or element.text is None:
        return "unavailable"
    text = element.text.strip().lower()
    if text in _XSD_BOOLEAN_TRUE:
        return "true"
    if text in _XSD_BOOLEAN_FALSE:
        return "false"
    return "unavailable"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--xml-dir", type=Path, required=True)
    parser.add_argument("--xml-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    candidates, collapsed_rows = _candidate_filings(args.candidates)
    provenance = _xml_provenance(args.xml_manifest)
    args.output.parent.mkdir(parents=True, exist_ok=True)

    # Counts that carry no predicate information. Without them a run in which
    # PREDICATE_PATH never resolves -- a namespaced primary_doc.xml, a schema
    # change, a fetched error page -- writes `unavailable` for every row and is
    # indistinguishable from a clean run that observed nothing.
    counts = {
        "rows": 0,
        "no_provenance_line": 0,
        "missing_xml_file": 0,
        "sha_mismatch": 0,
        "predicate_unresolved": 0,
    }

    with args.output.open("w", encoding="utf-8") as output:
        for accession, filing in candidates.items():
            xml_path = args.xml_dir / f"{accession}.xml"
            status = "unavailable"
            xml_sha256 = None
            expected = provenance.get(accession)
            counts["rows"] += 1
            if expected is None:
                counts["no_provenance_line"] += 1
            elif not xml_path.exists():
                counts["missing_xml_file"] += 1
            else:
                xml_bytes = xml_path.read_bytes()
                xml_sha256 = hashlib.sha256(xml_bytes).hexdigest()
                if xml_sha256 != expected["sha256"]:
                    counts["sha_mismatch"] += 1
                else:
                    status = _predicate(xml_bytes)
                    if status == "unavailable":
                        counts["predicate_unresolved"] += 1

            record = {
                **filing,
                "claim_status": "source_field_observation",
                "predicate_path": PREDICATE_PATH,
                "predicate_status": status,
                "predicate_version": PREDICATE_VERSION,
                "xml_sha256": xml_sha256,
            }
            output.write(json.dumps(record, sort_keys=True) + "\n")

    print(f"Candidate rows: {counts['rows']}")
    print(f"Ledger rows collapsed to a single accession: {collapsed_rows}")
    print(f"Rows with no complete provenance line: {counts['no_provenance_line']}")
    print(f"Rows with a missing XML file: {counts['missing_xml_file']}")
    print(f"Rows with an XML SHA mismatch: {counts['sha_mismatch']}")
    print(f"Rows where the predicate element did not resolve: {counts['predicate_unresolved']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
