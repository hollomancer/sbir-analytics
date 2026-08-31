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


def _candidate_filings(path: Path) -> dict[str, dict[str, str]]:
    filings: dict[str, dict[str, str]] = {}
    for record in _records(path):
        filing = record["form_d_index"]
        accession = filing["accession_number"]
        if accession in filings:
            raise ValueError(f"Duplicate candidate accession: {accession}")
        filings[accession] = {
            "accession_number": accession,
            "cik": filing["cik"],
            "filing_date": filing["filing_date"],
            "form_type": filing["form_type"],
        }
    return filings


def _xml_provenance(path: Path) -> dict[str, dict[str, str]]:
    provenance: dict[str, dict[str, str]] = {}
    for record in _records(path):
        if record.get("status") != 200:
            continue
        accession = record["accession_number"]
        if accession in provenance:
            raise ValueError(f"Duplicate successful XML retrieval: {accession}")
        provenance[accession] = {"sha256": record["sha256"]}
    return provenance


def _predicate(xml_bytes: bytes) -> str:
    """Return the tri-state source-field observation authorized by Amendment 7."""
    try:
        root = ElementTree.fromstring(xml_bytes)
    except ElementTree.ParseError:
        return "unavailable"

    element = root.find(PREDICATE_PATH)
    if element is None or element.text is None:
        return "unavailable"
    return "true" if element.text.strip().lower() == "true" else "false"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--xml-dir", type=Path, required=True)
    parser.add_argument("--xml-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    candidates = _candidate_filings(args.candidates)
    provenance = _xml_provenance(args.xml_manifest)
    args.output.parent.mkdir(parents=True, exist_ok=True)

    with args.output.open("w", encoding="utf-8") as output:
        for accession, filing in candidates.items():
            xml_path = args.xml_dir / f"{accession}.xml"
            status = "unavailable"
            xml_sha256 = None
            expected = provenance.get(accession)
            if expected and xml_path.exists():
                xml_bytes = xml_path.read_bytes()
                xml_sha256 = hashlib.sha256(xml_bytes).hexdigest()
                if xml_sha256 == expected["sha256"]:
                    status = _predicate(xml_bytes)

            record = {
                **filing,
                "claim_status": "source_field_observation",
                "predicate_path": PREDICATE_PATH,
                "predicate_status": status,
                "predicate_version": PREDICATE_VERSION,
                "xml_sha256": xml_sha256,
            }
            output.write(json.dumps(record, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
