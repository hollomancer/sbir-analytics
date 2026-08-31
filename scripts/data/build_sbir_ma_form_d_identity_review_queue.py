#!/usr/bin/env python3
"""Build the private human-review queue authorized by Amendment 8.

Epistemic tier: exploratory. This script selects only Amendment 7 predicate-
positive filings and copies bounded source-native comparison fields. It makes no
identity determination; every output row begins unreviewed.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from xml.etree import ElementTree

from sbir_etl.identity import CompanyNameProfile, normalize_company_name


EPISTEMIC_TIER = "exploratory"
QUEUE_VERSION = "form_d_identity_review_queue_v1"


def _records(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _candidates(path: Path) -> dict[str, dict]:
    result: dict[str, dict] = {}
    for record in _records(path):
        accession = record["form_d_index"]["accession_number"]
        if accession in result:
            raise ValueError(f"Duplicate candidate accession: {accession}")
        result[accession] = record
    return result


def _issuer_fields(xml_path: Path) -> tuple[str | None, str | None]:
    try:
        root = ElementTree.fromstring(xml_path.read_bytes())
    except ElementTree.ParseError:
        return None, None
    issuer = root.find("primaryIssuer")
    if issuer is None:
        return None, None
    name = issuer.findtext("entityName")
    cik = issuer.findtext("cik")
    return (name.strip() if name else None, cik.strip() if cik else None)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--observations", type=Path, required=True)
    parser.add_argument("--xml-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    candidates = _candidates(args.candidates)
    observations = _records(args.observations)
    args.output.parent.mkdir(parents=True, exist_ok=True)

    with args.output.open("w", encoding="utf-8") as output:
        for observation in observations:
            if observation["predicate_status"] != "true":
                continue
            accession = observation["accession_number"]
            candidate = candidates.get(accession)
            if candidate is None:
                raise ValueError(f"Observation without candidate: {accession}")
            issuer_name, issuer_cik = _issuer_fields(args.xml_dir / f"{accession}.xml")
            evidence_codes = ["exact_key_candidate"]
            if issuer_name:
                issuer_key = normalize_company_name(
                    issuer_name, profile=CompanyNameProfile.FORM_D_JOIN_V1
                )
                if issuer_key == candidate["name_key"]:
                    evidence_codes.append("issuer_name_alias_agreement")

            filing = candidate["form_d_index"]
            record = {
                "accession_number": accession,
                "claim_status": "identity_review_queue",
                "form_d_filer_name": filing["filer_name"],
                "form_d_issuer_cik": issuer_cik,
                "form_d_issuer_name": issuer_name,
                "form_type": filing["form_type"],
                "index_cik": filing["cik"],
                "name_key": candidate["name_key"],
                "name_key_profile": candidate["name_key_profile"],
                "prefilled_evidence_codes": evidence_codes,
                "queue_version": QUEUE_VERSION,
                "review_outcome": "unreviewed",
                "review_rationale": None,
                "reviewed_at_utc": None,
                "reviewer_id": None,
                "sbir_aliases": candidate["sbir_aliases"],
                "sbir_award_identifiers": candidate["sbir_award_identifiers"],
                "xml_sha256": observation["xml_sha256"],
            }
            output.write(json.dumps(record, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
