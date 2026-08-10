#!/usr/bin/env python3
"""Build an atomic, candidate-only SBIR awardee to Form D issuer crosswalk.

The producer validates the pinned full-history inputs, builds deterministic
SBIR firm components from exact UEI/DUNS evidence, and expands exact normalized
names to every matching Form D CIK.  It does not accept legal-entity identity or
open any downstream exclusion, matching, or rate gate.
"""

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import uuid
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sbir_etl.identity import CompanyNameProfile, normalize_company_name
from sbir_etl.utils.identifiers import normalize_duns, normalize_uei


EPISTEMIC_TIER = "pipelines"

DEFAULT_CONTROL_MANIFEST = (
    REPO_ROOT
    / "data/processed/agency_private_capital/control_universe/form_d_control_universe.manifest.json"
)
DEFAULT_AWARDS_CSV = REPO_ROOT / "data/raw/sbir/award_data.csv"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "data/processed/agency_private_capital/identity_crosswalk"

MANIFEST_SCHEMA_VERSION = 1
LEDGER_SCHEMA_VERSION = 1
EDGE_SCHEMA_VERSION = 1
FIRM_ID_CONTRACT = "sbir-firm-id-v1"
EDGE_ID_CONTRACT = "sbir-form-d-edge-id-v1"
LEDGER_CONTRACT = "sbir-firm-identity-ledger-v1"
EDGE_CONTRACT = "sbir-form-d-candidate-edge-v1"
NORMALIZER = CompanyNameProfile.ORGANIZATION_KEY_V1
EXPECTED_IDENTITY_FIELDS = (
    "issuer_name",
    "street1",
    "street2",
    "city",
    "state",
    "zip_code",
    "issuer_phone",
    "jurisdiction_of_incorporation",
    "year_of_incorporation",
)
SHA256_RE = re.compile(r"[0-9a-f]{64}")
GIT_COMMIT_RE = re.compile(r"[0-9a-f]{40}")


class BuildError(RuntimeError):
    """Raised when a source or invariant cannot support a reliable release."""


class UnionFind:
    """Minimal disjoint-set structure for exact UEI/DUNS components."""

    def __init__(self) -> None:
        self.parent: dict[str, str] = {}
        self.rank: dict[str, int] = {}

    def add(self, value: str) -> None:
        if value not in self.parent:
            self.parent[value] = value
            self.rank[value] = 0

    def find(self, value: str) -> str:
        parent = self.parent[value]
        if parent != value:
            self.parent[value] = self.find(parent)
        return self.parent[value]

    def union(self, left: str, right: str) -> None:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root == right_root:
            return
        if self.rank[left_root] < self.rank[right_root]:
            left_root, right_root = right_root, left_root
        self.parent[right_root] = left_root
        if self.rank[left_root] == self.rank[right_root]:
            self.rank[left_root] += 1


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_path(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
            size += len(block)
    return digest.hexdigest(), size


def _non_negative_int(value: object, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise BuildError(f"{label} must be a non-negative integer")
    return value


def _pinned_product(value: object, *, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise BuildError(f"Control manifest does not pin {label}")
    path = value.get("path")
    sha256 = value.get("sha256")
    if not isinstance(path, str) or not path or Path(path).name != path or Path(path).is_absolute():
        raise BuildError(f"Pinned {label} path must be one safe filename")
    if not isinstance(sha256, str) or not SHA256_RE.fullmatch(sha256):
        raise BuildError(f"Pinned {label} has an invalid SHA-256")
    _non_negative_int(value.get("size_bytes"), label=f"Pinned {label} size_bytes")
    _non_negative_int(value.get("row_count"), label=f"Pinned {label} row_count")
    return dict(value)


def _quarters() -> list[str]:
    return [f"{year}Q{quarter}" for year in range(2009, 2025) for quarter in range(1, 5)]


def _load_control_manifest(
    path: Path, *, expected_sha256: str
) -> tuple[dict[str, Any], bytes, dict[str, Any], dict[str, Any]]:
    expected = expected_sha256.strip().lower()
    if not SHA256_RE.fullmatch(expected):
        raise BuildError("--control-manifest-sha256 must be 64 lowercase hexadecimal characters")
    if not path.is_file():
        raise BuildError(f"Required control manifest is missing: {path}")
    data = path.read_bytes()
    if _sha256_bytes(data) != expected:
        raise BuildError("Control manifest SHA-256 does not match the required external pin")
    try:
        manifest = json.loads(data)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BuildError(f"Invalid control manifest JSON: {exc}") from exc
    if not isinstance(manifest, dict):
        raise BuildError("Control manifest must be a JSON object")
    if manifest.get("schema_version") != 1 or isinstance(manifest.get("schema_version"), bool):
        raise BuildError("Control manifest has an unsupported schema_version")
    if manifest.get("complete") is not True:
        raise BuildError("Control manifest is incomplete")
    required_gates: dict[str, object] = {
        "complete_sbir_exclusion": False,
        "covariates_ready": False,
        "exclusion_recall": "unknown",
        "identity_only": True,
        "ready_for_matching": False,
    }
    for field, expected_value in required_gates.items():
        actual = manifest.get(field)
        valid = (
            actual is expected_value
            if isinstance(expected_value, bool)
            else actual == expected_value
        )
        if not valid:
            raise BuildError(f"Control manifest has unexpected {field}")

    parameters = manifest.get("parameters")
    if not isinstance(parameters, Mapping):
        raise BuildError("Control manifest has no parameters object")
    expected_quarters = _quarters()
    if (
        parameters.get("start_quarter") != "2009Q1"
        or parameters.get("end_quarter") != "2024Q4"
        or parameters.get("quarter_count") != 64
        or parameters.get("quarters") != expected_quarters
    ):
        raise BuildError("Control manifest does not pin the closed 2009Q1-2024Q4 window")

    contract = manifest.get("identity_evidence_contract")
    if not isinstance(contract, Mapping):
        raise BuildError("Control manifest has no identity evidence contract")
    if (
        contract.get("grain") != "form_d_filing_accession"
        or contract.get("source_table") != "ISSUERS.tsv"
        or contract.get("historical_aliases_retained") is not True
        or contract.get("fields") != list(EXPECTED_IDENTITY_FIELDS)
    ):
        raise BuildError("Control manifest has an unsupported identity evidence contract")

    outputs = manifest.get("outputs")
    if not isinstance(outputs, Mapping):
        raise BuildError("Control manifest has no outputs object")
    broad = _pinned_product(outputs.get("broad_issuer_universe"), label="broad issuer universe")
    source_counts = manifest.get("source_counts")
    if not isinstance(source_counts, Mapping):
        raise BuildError("Control manifest has no source_counts object")
    if (
        _non_negative_int(source_counts.get("issuer_ciks"), label="Source issuer_ciks")
        != broad["row_count"]
    ):
        raise BuildError("Control manifest issuer count does not match the broad product")

    invariants = manifest.get("invariants")
    if not isinstance(invariants, Mapping) or invariants.get("broad_ciks_unique") is not True:
        raise BuildError("Control manifest does not establish unique broad-universe CIKs")
    exclusion = manifest.get("exclusion")
    if not isinstance(exclusion, Mapping):
        raise BuildError("Control manifest has no exclusion object")
    awards = _pinned_product(exclusion.get("awards_csv"), label="SBIR awards CSV")
    exact_match = exclusion.get("exact_match")
    if (
        not isinstance(exact_match, Mapping)
        or exact_match.get("normalizer_version") != NORMALIZER.value
    ):
        raise BuildError("Control manifest uses an unsupported exact-name normalizer")
    _non_negative_int(
        exact_match.get("candidate_cik_count"), label="Source exact candidate CIK count"
    )
    _non_negative_int(
        exact_match.get("matched_normalized_name_count"),
        label="Source matched normalized-name count",
    )
    return manifest, data, broad, awards


def _resolve_manifest_product(manifest_path: Path, product: Mapping[str, Any]) -> Path:
    path = manifest_path.parent / str(product["path"])
    if path.parent != manifest_path.parent:
        raise BuildError("Pinned product escapes the control-manifest directory")
    return path


def _normalizer(value: object) -> str:
    return normalize_company_name(value, profile=NORMALIZER)


def _column(fieldnames: Sequence[str], *aliases: str) -> str | None:
    by_name = {field.strip().casefold(): field for field in fieldnames}
    return next(
        (by_name[alias.casefold()] for alias in aliases if alias.casefold() in by_name), None
    )


def _firm_id(*, ueis: Iterable[str], dunses: Iterable[str], name_key: str | None) -> str:
    identifiers = [
        *(f"uei:{value}" for value in sorted(ueis)),
        *(f"duns:{value}" for value in sorted(dunses)),
    ]
    if identifiers:
        material = "\0".join((FIRM_ID_CONTRACT, "identifiers", *identifiers))
    elif name_key:
        material = "\0".join((FIRM_ID_CONTRACT, "name_key", NORMALIZER.value, name_key))
    else:  # pragma: no cover - guarded by caller
        raise BuildError("Cannot build an SBIR firm ID without identifiers or a name key")
    return f"sbir_firm:{hashlib.sha256(material.encode()).hexdigest()}"


def _edge_id(sbir_firm_id: str, cik: str) -> str:
    material = "\0".join((EDGE_ID_CONTRACT, sbir_firm_id, cik))
    return f"sbir_form_d_edge:{hashlib.sha256(material.encode()).hexdigest()}"


def _load_award_components(
    path: Path, product: Mapping[str, Any]
) -> tuple[list[dict[str, Any]], dict[str, list[str]], dict[str, Any]]:
    if not path.is_file():
        raise BuildError(f"Pinned SBIR awards CSV is missing: {path}")
    before = path.stat()
    sha256, size = _sha256_path(path)
    if size != product["size_bytes"] or sha256 != product["sha256"]:
        raise BuildError("SBIR awards CSV bytes do not match the control-manifest pin")

    union_find = UnionFind()
    records: list[dict[str, Any]] = []
    valid_identifier_rows = 0
    malformed_identifier_rows = 0
    reader: csv.DictReader[str] | None = None
    try:
        with path.open(encoding="utf-8-sig", errors="strict", newline="") as handle:
            reader = csv.DictReader(handle, strict=True)
            fieldnames = reader.fieldnames or []
            if any(not isinstance(field, str) or not field.strip() for field in fieldnames):
                raise BuildError("SBIR awards CSV has a blank column name")
            folded = [field.strip().casefold() for field in fieldnames]
            if len(folded) != len(set(folded)):
                raise BuildError("SBIR awards CSV has duplicate column names")
            name_column = _column(fieldnames, "Company", "company_name")
            uei_column = _column(fieldnames, "UEI", "recipient_uei")
            duns_column = _column(fieldnames, "Duns", "DUNS", "recipient_duns")
            if name_column is None or uei_column is None or duns_column is None:
                raise BuildError("SBIR awards CSV must contain Company, UEI, and Duns columns")

            for source_record, row in enumerate(reader, start=1):
                if None in row:
                    raise BuildError(
                        f"SBIR awards CSV record {source_record} has fields beyond its header"
                    )
                raw_name = str(row.get(name_column) or "")
                normalized_name = _normalizer(raw_name)
                uei_raw = str(row.get(uei_column) or "")
                duns_raw = str(row.get(duns_column) or "")
                uei = normalize_uei(uei_raw)
                duns = normalize_duns(duns_raw)
                malformed: list[str] = []
                if uei_raw.strip() and uei is None:
                    malformed.append("malformed_uei")
                if duns_raw.strip() and duns is None:
                    malformed.append("malformed_duns")
                if malformed:
                    malformed_identifier_rows += 1
                identifiers = [
                    value
                    for value in (f"uei:{uei}" if uei else None, f"duns:{duns}" if duns else None)
                    if value
                ]
                if identifiers:
                    valid_identifier_rows += 1
                    for identifier in identifiers:
                        union_find.add(identifier)
                    if len(identifiers) == 2:
                        union_find.union(identifiers[0], identifiers[1])
                elif not normalized_name:
                    raise BuildError(
                        f"SBIR awards record {source_record} has neither a valid identifier nor a name key"
                    )
                records.append(
                    {
                        "duns": duns,
                        "duns_raw": duns_raw if duns_raw.strip() else None,
                        "malformed_identifier_fields": malformed,
                        "normalized_name": normalized_name or None,
                        "raw_name": raw_name if raw_name.strip() else None,
                        "source_record": source_record,
                        "uei": uei,
                        "uei_raw": uei_raw if uei_raw.strip() else None,
                    }
                )
    except (UnicodeDecodeError, csv.Error) as exc:
        line_number = reader.line_num if reader is not None else 1
        raise BuildError(
            f"Invalid SBIR awards CSV near physical line {line_number}: {exc}"
        ) from exc

    after = path.stat()
    if (
        after.st_size != before.st_size
        or after.st_mtime_ns != before.st_mtime_ns
        or after.st_ino != before.st_ino
    ):
        raise BuildError("SBIR awards CSV changed while it was being parsed")
    if len(records) != product["row_count"]:
        raise BuildError("SBIR awards CSV row count does not match the control-manifest pin")

    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        component_identifier: str | None = f"uei:{record['uei']}" if record["uei"] else None
        if component_identifier is None and record["duns"]:
            component_identifier = f"duns:{record['duns']}"
        if component_identifier:
            grouped[("identifiers", union_find.find(component_identifier))].append(record)
        else:
            grouped[("name_key", str(record["normalized_name"]))].append(record)

    components: list[dict[str, Any]] = []
    referenced_records: set[int] = set()
    for (basis, key), component_records in grouped.items():
        ueis = sorted({str(record["uei"]) for record in component_records if record["uei"]})
        dunses = sorted({str(record["duns"]) for record in component_records if record["duns"]})
        names = sorted(
            {
                str(record["normalized_name"])
                for record in component_records
                if record["normalized_name"]
            }
        )
        raw_names = sorted(
            {str(record["raw_name"]) for record in component_records if record["raw_name"]}
        )
        reasons = {
            reason
            for record in component_records
            for reason in record["malformed_identifier_fields"]
        }
        if len(ueis) > 1:
            reasons.add("multiple_ueis")
        if len(dunses) > 1:
            reasons.add("multiple_duns")
        name_key = key if basis == "name_key" else None
        sbir_firm_id = _firm_id(ueis=ueis, dunses=dunses, name_key=name_key)
        status = (
            "quarantined_conflict"
            if reasons
            else "identifier_consistent"
            if basis == "identifiers"
            else "name_only"
        )
        ordered_records = sorted(component_records, key=lambda record: record["source_record"])
        source_record_numbers = [int(record["source_record"]) for record in ordered_records]
        if referenced_records.intersection(source_record_numbers):
            raise BuildError("An SBIR source record occurs in more than one identity component")
        referenced_records.update(source_record_numbers)
        components.append(
            {
                "award_row_count": len(ordered_records),
                "component_status": status,
                "dunses": dunses,
                "firm_id_contract": FIRM_ID_CONTRACT,
                "identity_basis": basis,
                "ledger_contract": LEDGER_CONTRACT,
                "normalized_names": names,
                "quarantine_reasons": sorted(reasons),
                "raw_names": raw_names,
                "sbir_firm_id": sbir_firm_id,
                "schema_version": LEDGER_SCHEMA_VERSION,
                "source_record_count": len(ordered_records),
                "source_records": ordered_records,
                "ueis": ueis,
            }
        )
    components.sort(key=lambda component: component["sbir_firm_id"])
    firm_ids = [str(component["sbir_firm_id"]) for component in components]
    if len(firm_ids) != len(set(firm_ids)):
        raise BuildError("Stable SBIR firm IDs are not unique")
    if referenced_records != set(range(1, len(records) + 1)):
        raise BuildError("SBIR source-record preservation invariant failed")

    name_index: dict[str, list[str]] = defaultdict(list)
    for component in components:
        for name in component["normalized_names"]:
            name_index[str(name)].append(str(component["sbir_firm_id"]))
    for firm_ids_for_name in name_index.values():
        firm_ids_for_name.sort()

    metadata = {
        "award_rows": len(records),
        "award_rows_with_malformed_identifier": malformed_identifier_rows,
        "award_rows_with_valid_identifier": valid_identifier_rows,
        "component_status_counts": dict(
            sorted(Counter(component["component_status"] for component in components).items())
        ),
        "normalized_name_count": len(name_index),
        "sha256": sha256,
        "size_bytes": size,
    }
    return components, dict(name_index), metadata


def _validated_aliases(value: object, *, label: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise BuildError(f"{label} must be a non-empty list")
    aliases: list[str] = []
    for alias in value:
        if not isinstance(alias, str) or not alias.strip():
            raise BuildError(f"{label} contains an invalid alias")
        aliases.append(alias)
    return aliases


def _stream_form_d_candidates(
    path: Path,
    product: Mapping[str, Any],
    *,
    name_index: Mapping[str, list[str]],
) -> tuple[dict[tuple[str, str], dict[str, set[tuple[str, str]]]], dict[str, Any]]:
    if not path.is_file():
        raise BuildError(f"Pinned broad Form D issuer universe is missing: {path}")
    before = path.stat()
    if before.st_size != product["size_bytes"]:
        raise BuildError("Broad Form D issuer universe byte count does not match its pin")
    digest = hashlib.sha256()
    size = 0
    row_count = 0
    filing_count = 0
    previous_cik: str | None = None
    matched_names: set[str] = set()
    matched_ciks: set[str] = set()
    all_accessions: set[str] = set()
    candidates: dict[tuple[str, str], dict[str, set[tuple[str, str]]]] = defaultdict(
        lambda: defaultdict(set)
    )

    with path.open("rb") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            digest.update(raw_line)
            size += len(raw_line)
            if not raw_line.strip():
                raise BuildError(f"Broad issuer universe has a blank line at {line_number}")
            row_count += 1
            try:
                row = json.loads(raw_line)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise BuildError(f"Invalid broad issuer JSON at line {line_number}") from exc
            if not isinstance(row, Mapping):
                raise BuildError(f"Broad issuer line {line_number} must be an object")
            cik = row.get("cik")
            if (
                not isinstance(cik, str)
                or not cik.isdigit()
                or cik.startswith("0")
                or len(cik) > 10
            ):
                raise BuildError(f"Broad issuer line {line_number} has an invalid CIK")
            if previous_cik is not None and cik <= previous_cik:
                raise BuildError("Broad issuer CIKs must be unique and deterministically ordered")
            previous_cik = cik
            if row.get("firm_key") != f"form_d_cik:{cik}":
                raise BuildError(f"Broad issuer line {line_number} has an invalid firm_key")
            if row.get("schema_version") != 1:
                raise BuildError(
                    f"Broad issuer line {line_number} has an unsupported schema_version"
                )
            filings = row.get("filings")
            if not isinstance(filings, list) or not filings:
                raise BuildError(f"Broad issuer line {line_number} has no filing evidence")
            if row.get("filing_count") != len(filings):
                raise BuildError(f"Broad issuer line {line_number} has an invalid filing_count")
            aggregate_aliases = set(
                _validated_aliases(
                    row.get("issuer_name_aliases"), label=f"Broad issuer line {line_number} aliases"
                )
            )
            traceable_aliases: set[str] = set()
            accessions: set[str] = set()
            for filing in filings:
                filing_count += 1
                if not isinstance(filing, Mapping):
                    raise BuildError(f"Broad issuer line {line_number} has a non-object filing")
                if filing.get("cik") != cik:
                    raise BuildError(f"Broad issuer line {line_number} pools evidence across CIKs")
                missing_fields = [
                    field for field in EXPECTED_IDENTITY_FIELDS if field not in filing
                ]
                if missing_fields:
                    raise BuildError(
                        f"Broad issuer line {line_number} filing lacks identity fields: "
                        + ", ".join(missing_fields)
                    )
                accession = filing.get("accession_number")
                if not isinstance(accession, str) or not accession.strip():
                    raise BuildError(f"Broad issuer line {line_number} has an invalid accession")
                accession = accession.strip()
                if accession in all_accessions:
                    raise BuildError(f"Broad issuer universe repeats accession {accession}")
                accessions.add(accession)
                all_accessions.add(accession)
                filing_aliases = _validated_aliases(
                    filing.get("issuer_name_aliases"),
                    label=f"Broad issuer line {line_number} filing aliases",
                )
                issuer_name = filing.get("issuer_name")
                if not isinstance(issuer_name, str) or not issuer_name.strip():
                    raise BuildError(f"Broad issuer line {line_number} has a blank filing name")
                if issuer_name not in filing_aliases:
                    raise BuildError(
                        f"Broad issuer line {line_number} filing name is not traceable"
                    )
                for raw_alias in filing_aliases:
                    traceable_aliases.add(raw_alias)
                    normalized = _normalizer(raw_alias)
                    if not normalized or normalized not in name_index:
                        continue
                    matched_names.add(normalized)
                    matched_ciks.add(cik)
                    for sbir_firm_id in name_index[normalized]:
                        candidates[(sbir_firm_id, cik)][normalized].add((accession, raw_alias))
            if aggregate_aliases != traceable_aliases:
                raise BuildError(
                    f"Broad issuer line {line_number} has untraceable aggregate aliases"
                )

    after = path.stat()
    if (
        after.st_size != before.st_size
        or after.st_mtime_ns != before.st_mtime_ns
        or after.st_ino != before.st_ino
    ):
        raise BuildError("Broad Form D issuer universe changed while it was being parsed")
    if row_count != product["row_count"]:
        raise BuildError("Broad Form D issuer row count does not match its pin")
    if size != product["size_bytes"] or digest.hexdigest() != product["sha256"]:
        raise BuildError("Broad Form D issuer bytes do not match the control-manifest pin")
    return dict(candidates), {
        "filing_rows_validated": filing_count,
        "matched_form_d_ciks": len(matched_ciks),
        "matched_normalized_names": len(matched_names),
        "row_count": row_count,
        "sha256": digest.hexdigest(),
        "size_bytes": size,
    }


def _build_edge_rows(
    components: Sequence[Mapping[str, Any]],
    candidates: Mapping[tuple[str, str], Mapping[str, set[tuple[str, str]]]],
) -> list[dict[str, Any]]:
    components_by_id = {str(component["sbir_firm_id"]): component for component in components}
    source_by_name: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for component in components:
        firm_id = str(component["sbir_firm_id"])
        for source in component["source_records"]:
            normalized_name = source.get("normalized_name")
            if normalized_name:
                source_by_name[(firm_id, str(normalized_name))].append(
                    {
                        "raw_name": source.get("raw_name"),
                        "source_record": source["source_record"],
                    }
                )

    edges: list[dict[str, Any]] = []
    for (firm_id, cik), evidence_by_name in sorted(candidates.items()):
        component = components_by_id[firm_id]
        name_evidence: list[dict[str, Any]] = []
        accessions: set[str] = set()
        source_records: set[int] = set()
        for normalized_name, form_d_evidence in sorted(evidence_by_name.items()):
            sbir_evidence = sorted(
                source_by_name[(firm_id, normalized_name)],
                key=lambda item: (item["source_record"], str(item["raw_name"] or "")),
            )
            if not sbir_evidence:
                raise BuildError("Candidate edge lacks traceable SBIR source evidence")
            form_d_rows = [
                {"accession_number": accession, "raw_alias": alias}
                for accession, alias in sorted(form_d_evidence)
            ]
            if not form_d_rows:
                raise BuildError("Candidate edge lacks traceable Form D filing evidence")
            source_records.update(int(item["source_record"]) for item in sbir_evidence)
            accessions.update(str(item["accession_number"]) for item in form_d_rows)
            name_evidence.append(
                {
                    "form_d": form_d_rows,
                    "normalized_name": normalized_name,
                    "sbir": sbir_evidence,
                }
            )
        edges.append(
            {
                "component_status": component["component_status"],
                "decision": "candidate_unreviewed",
                "edge_contract": EDGE_CONTRACT,
                "edge_id": _edge_id(firm_id, cik),
                "edge_id_contract": EDGE_ID_CONTRACT,
                "exclusion_eligible": False,
                "form_d_cik": cik,
                "form_d_source_accessions": sorted(accessions),
                "identity_accepted": False,
                "match_method": "exact_normalized_name",
                "matching_eligible": False,
                "name_evidence": name_evidence,
                "normalizer_version": NORMALIZER.value,
                "quarantine_reasons": component["quarantine_reasons"],
                "rate_eligible": False,
                "same_legal_entity": None,
                "sbir_firm_id": firm_id,
                "sbir_source_records": sorted(source_records),
                "schema_version": EDGE_SCHEMA_VERSION,
            }
        )
    edge_ids = [edge["edge_id"] for edge in edges]
    pairs = [(edge["sbir_firm_id"], edge["form_d_cik"]) for edge in edges]
    if len(edge_ids) != len(set(edge_ids)) or len(pairs) != len(set(pairs)):
        raise BuildError("Atomic candidate edge IDs or pairs are not unique")
    return edges


def _write_jsonl_product(
    directory: Path, *, stem: str, rows: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    temporary_path = directory / f".{stem}.jsonl"
    digest = hashlib.sha256()
    size = 0
    with temporary_path.open("wb") as handle:
        for row in rows:
            data = (
                json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
            ).encode("utf-8")
            handle.write(data)
            digest.update(data)
            size += len(data)
        handle.flush()
        os.fsync(handle.fileno())
    sha256 = digest.hexdigest()
    final_path = directory / f"{stem}.{sha256}.jsonl"
    os.replace(temporary_path, final_path)
    return {
        "path": final_path.name,
        "row_count": len(rows),
        "sha256": sha256,
        "size_bytes": size,
    }


def _write_manifest(directory: Path, manifest: Mapping[str, Any]) -> None:
    path = directory / "sbir_form_d_identity_crosswalk.manifest.json"
    data = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    with path.open("wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def _publish_release(staging: Path, target: Path) -> None:
    """Replace one complete release directory, restoring the prior one on failure."""

    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_symlink() or (target.exists() and not target.is_dir()):
        raise BuildError(f"Output target must be a directory, not a file or symlink: {target}")
    backup = target.parent / f".{target.name}.backup-{uuid.uuid4().hex}"
    had_previous = target.exists()
    try:
        if had_previous:
            os.replace(target, backup)
        os.replace(staging, target)
    except BaseException:
        if had_previous and backup.exists():
            os.replace(backup, target)
        if staging.exists():
            shutil.rmtree(staging)
        raise
    if had_previous:
        # Publication is already complete. Backup cleanup is best-effort and
        # must never turn a valid new release into a corrupt rollback.
        shutil.rmtree(backup, ignore_errors=True)


def _ensure_output_disjoint(output_dir: Path, *, inputs: Iterable[Path]) -> None:
    """Refuse a release target whose replacement could remove a pinned input."""

    resolved_output = output_dir.resolve(strict=False)
    for input_path in inputs:
        if input_path.resolve().is_relative_to(resolved_output):
            raise BuildError(f"Output directory contains a pinned input: {input_path}")


def build(args: argparse.Namespace) -> dict[str, Any]:
    control_manifest_path = Path(args.control_manifest).resolve()
    awards_path = Path(args.awards_csv).resolve()
    output_dir = Path(args.output_dir).expanduser().absolute()
    if not GIT_COMMIT_RE.fullmatch(args.code_version):
        raise BuildError("--code-version must be one full lowercase Git commit SHA")
    manifest, manifest_data, broad_product, awards_product = _load_control_manifest(
        control_manifest_path,
        expected_sha256=args.control_manifest_sha256,
    )
    broad_path = _resolve_manifest_product(control_manifest_path, broad_product)
    _ensure_output_disjoint(
        output_dir,
        inputs=(control_manifest_path, broad_path, awards_path),
    )
    components, name_index, award_metadata = _load_award_components(awards_path, awards_product)
    candidates, form_d_metadata = _stream_form_d_candidates(
        broad_path,
        broad_product,
        name_index=name_index,
    )
    edges = _build_edge_rows(components, candidates)

    exact_match = manifest["exclusion"]["exact_match"]
    candidate_ciks = {str(edge["form_d_cik"]) for edge in edges}
    candidate_names = {
        evidence["normalized_name"] for edge in edges for evidence in edge["name_evidence"]
    }
    if len(candidate_ciks) != exact_match["candidate_cik_count"]:
        raise BuildError("Atomic candidates do not reconcile to the upstream exact CIK count")
    if len(candidate_names) != exact_match["matched_normalized_name_count"]:
        raise BuildError("Atomic candidates do not reconcile to the upstream exact-name count")

    firm_degrees = Counter(str(edge["sbir_firm_id"]) for edge in edges)
    cik_degrees = Counter(str(edge["form_d_cik"]) for edge in edges)
    code_path = Path(__file__).resolve()
    producer_sha256, producer_size = _sha256_path(code_path)
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.staging-", dir=output_dir.parent))
    try:
        ledger_product = _write_jsonl_product(
            staging,
            stem="sbir_firm_identity_ledger.v1",
            rows=components,
        )
        edge_product = _write_jsonl_product(
            staging,
            stem="sbir_form_d_candidate_edges.v1",
            rows=edges,
        )
        manifest_sha256 = _sha256_bytes(manifest_data)
        component_status_counts = award_metadata["component_status_counts"]
        output_manifest: dict[str, Any] = {
            "candidate_only": True,
            "caveats": [
                "Exact normalized-name equality is candidate generation, not legal-entity proof.",
                "Parent, subsidiary, acquirer, successor, fund, and shared-person relationships are not identity.",
                "Unresolved and quarantined pairs remain unknown and cannot support exclusion or rates.",
            ],
            "complete": True,
            "complete_sbir_exclusion": False,
            "covariates_ready": False,
            "counts": {
                "award_rows": award_metadata["award_rows"],
                "award_rows_with_malformed_identifier": award_metadata[
                    "award_rows_with_malformed_identifier"
                ],
                "award_rows_with_valid_identifier": award_metadata[
                    "award_rows_with_valid_identifier"
                ],
                "candidate_ciks": len(candidate_ciks),
                "candidate_edges": len(edges),
                "candidate_firms": len(firm_degrees),
                "candidate_normalized_names": len(candidate_names),
                "component_status_counts": component_status_counts,
                "firm_components": len(components),
                "firms_with_multiple_candidate_ciks": sum(
                    degree > 1 for degree in firm_degrees.values()
                ),
                "form_d_ciks_with_multiple_candidate_firms": sum(
                    degree > 1 for degree in cik_degrees.values()
                ),
                "identifier_components": component_status_counts.get("identifier_consistent", 0)
                + sum(
                    component["identity_basis"] == "identifiers"
                    and component["component_status"] == "quarantined_conflict"
                    for component in components
                ),
                "name_only_components": sum(
                    component["identity_basis"] == "name_key" for component in components
                ),
                "normalized_name_count": award_metadata["normalized_name_count"],
                "quarantined_components": component_status_counts.get("quarantined_conflict", 0),
            },
            "decision_contract": {
                "decision": "candidate_unreviewed",
                "same_legal_entity": "unknown",
            },
            "exclusion_eligible": False,
            "exclusion_recall": "unknown",
            "identity_accepted": False,
            "identity_only": True,
            "inputs": {
                "broad_issuer_universe": dict(broad_product),
                "control_manifest": {
                    "path": control_manifest_path.name,
                    "sha256": manifest_sha256,
                    "size_bytes": len(manifest_data),
                },
                "sbir_awards_csv": dict(awards_product),
            },
            "invariants": {
                "all_edges_atomic_by_sbir_firm_and_cik": True,
                "all_edges_candidate_unreviewed": all(
                    edge["decision"] == "candidate_unreviewed" for edge in edges
                ),
                "all_edges_have_closed_downstream_gates": all(
                    edge["identity_accepted"] is False
                    and edge["exclusion_eligible"] is False
                    and edge["matching_eligible"] is False
                    and edge["rate_eligible"] is False
                    and edge["same_legal_entity"] is None
                    for edge in edges
                ),
                "all_form_d_evidence_is_cik_local": True,
                "all_sbir_source_records_preserved_once": sum(
                    component["source_record_count"] for component in components
                )
                == awards_product["row_count"],
                "candidate_ciks_reconcile_to_upstream_exact_stage": True,
                "candidate_names_reconcile_to_upstream_exact_stage": True,
                "firm_ids_unique": len(components)
                == len({component["sbir_firm_id"] for component in components}),
                "pair_ids_unique": len(edges) == len({edge["edge_id"] for edge in edges}),
                "pairs_unique": len(edges)
                == len({(edge["sbir_firm_id"], edge["form_d_cik"]) for edge in edges}),
            },
            "matching_eligible": False,
            "normalizer_version": NORMALIZER.value,
            "outputs": {
                "candidate_edges": edge_product,
                "firm_identity_ledger": ledger_product,
            },
            "producer": {
                "code_commit": args.code_version,
                "path": str(code_path.relative_to(REPO_ROOT)),
                "sha256": producer_sha256,
                "size_bytes": producer_size,
            },
            "rate_eligible": False,
            "ready_for_matching": False,
            "schema_version": MANIFEST_SCHEMA_VERSION,
            "source_validation": {
                "form_d": form_d_metadata,
                "sbir_awards": {
                    "row_count": award_metadata["award_rows"],
                    "sha256": award_metadata["sha256"],
                    "size_bytes": award_metadata["size_bytes"],
                },
            },
        }
        _write_manifest(staging, output_manifest)
        _publish_release(staging, output_dir)
        return output_manifest
    except BaseException:
        if staging.exists():
            shutil.rmtree(staging)
        raise


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--control-manifest", type=Path, default=DEFAULT_CONTROL_MANIFEST)
    parser.add_argument("--control-manifest-sha256", required=True)
    parser.add_argument("--awards-csv", type=Path, default=DEFAULT_AWARDS_CSV)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--code-version", required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    try:
        manifest = build(parse_args(argv))
    except (BuildError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
