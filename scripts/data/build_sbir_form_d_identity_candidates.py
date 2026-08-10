#!/usr/bin/env python3
"""Build a bounded, candidate-only SBIR awardee to Form D issuer review ledger.

The producer preserves every exact Phase 1 pair, adds only three frozen fuzzy
name routes, and appends CIK-local address and phone corroboration. It never
accepts legal-entity identity or opens an exclusion, matching, or rate gate.
"""

import argparse
import ctypes
import csv
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from importlib.metadata import PackageNotFoundError, version as distribution_version
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sbir_etl.identity import (
    CompanyNameMetric,
    CompanyNameProfile,
    USJurisdictionProfile,
    company_name_similarity,
    normalize_company_name,
    normalize_us_jurisdiction,
)


EPISTEMIC_TIER = "pipelines"

DEFAULT_CROSSWALK_MANIFEST = (
    REPO_ROOT / "data/processed/agency_private_capital/identity_crosswalk/"
    "sbir_form_d_identity_crosswalk.manifest.json"
)
DEFAULT_CONTROL_MANIFEST = (
    REPO_ROOT / "data/processed/agency_private_capital/control_universe/"
    "form_d_control_universe.manifest.json"
)
DEFAULT_AWARDS_CSV = REPO_ROOT / "data/raw/sbir/award_data.csv"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "data/processed/agency_private_capital/identity_candidates"

MANIFEST_SCHEMA_VERSION = 1
CANDIDATE_SCHEMA_VERSION = 2
CANDIDATE_CONTRACT = "sbir-form-d-identity-candidate-v2"
EDGE_ID_CONTRACT = "sbir-form-d-edge-id-v1"
LEDGER_CONTRACT = "sbir-firm-identity-ledger-v1"
EXACT_EDGE_CONTRACT = "sbir-form-d-candidate-edge-v1"
FIRM_ID_CONTRACT = "sbir-firm-id-v1"
NORMALIZER = CompanyNameProfile.ORGANIZATION_KEY_V1
GEOGRAPHY_PROFILE = USJurisdictionProfile.STRICT_V1
PREFIX_LENGTH = 2
MINIMUM_FUZZY_NAME_LENGTH = 6
STRONG_NAME_THRESHOLD = 0.95
STATE_SUPPORTED_THRESHOLD = 0.85
ZIP_SUPPORTED_THRESHOLD = 0.80
SIMILARITY_BACKEND = "rapidfuzz"
SIMILARITY_BACKEND_VERSION = "3.14.3"
SIMILARITY_BACKEND_SENTINEL = 0.8571428571428572
ROUTE_ORDER = ("exact_normalized_name", "strong_name", "state_supported", "zip_supported")
CONTACT_FIELDS = ("street1", "city", "state", "zip5", "phone10")
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
FORBIDDEN_OUTPUT_KEYS = frozenset(
    {
        "amount",
        "award_amount",
        "award_value",
        "company_website",
        "confidence",
        "confidence_label",
        "confidence_tier",
        "email",
        "email_address",
        "email_domain",
        "offering_amount",
        "people",
        "person",
        "person_name",
        "persons",
        "preferred_cik",
        "related_person",
        "related_persons",
        "related_people",
        "sale_amount",
        "total_amount_sold",
        "total_offering_amount",
        "website",
        "website_url",
    }
)
SHA256_RE = re.compile(r"[0-9a-f]{64}")
GIT_COMMIT_RE = re.compile(r"[0-9a-f]{40}")
ZIP5_RE = re.compile(r"^\s*(\d{5})(?:-\d{4})?\s*$")
PHONE_EXTENSION_RE = re.compile(r"\s+(?:ext(?:ension)?\.?|x)\s*\d+\s*$", re.IGNORECASE)


class BuildError(RuntimeError):
    """Raised when input evidence cannot support a deterministic release."""


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
        raise BuildError(f"Manifest does not pin {label}")
    path = value.get("path")
    sha256 = value.get("sha256")
    if (
        not isinstance(path, str)
        or not path
        or path in {".", ".."}
        or Path(path).name != path
        or Path(path).is_absolute()
    ):
        raise BuildError(f"Pinned {label} path must be one safe filename")
    if not isinstance(sha256, str) or not SHA256_RE.fullmatch(sha256):
        raise BuildError(f"Pinned {label} has an invalid SHA-256")
    _non_negative_int(value.get("size_bytes"), label=f"Pinned {label} size_bytes")
    _non_negative_int(value.get("row_count"), label=f"Pinned {label} row_count")
    return dict(value)


def _read_manifest(path: Path, *, expected_sha256: str, label: str) -> tuple[dict[str, Any], bytes]:
    expected = expected_sha256.strip().lower()
    if not SHA256_RE.fullmatch(expected):
        raise BuildError(f"--{label}-manifest-sha256 must be 64 lowercase hexadecimal characters")
    if not path.is_file():
        raise BuildError(f"Required {label} manifest is missing: {path}")
    data = path.read_bytes()
    if _sha256_bytes(data) != expected:
        raise BuildError(f"{label.title()} manifest SHA-256 does not match its external pin")
    try:
        manifest = json.loads(data)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BuildError(f"Invalid {label} manifest JSON: {exc}") from exc
    if not isinstance(manifest, dict):
        raise BuildError(f"{label.title()} manifest must be a JSON object")
    return manifest, data


def _required_false_gates(manifest: Mapping[str, Any], *, label: str) -> None:
    expected: dict[str, object] = {
        "complete_sbir_exclusion": False,
        "covariates_ready": False,
        "exclusion_recall": "unknown",
        "identity_only": True,
        "ready_for_matching": False,
    }
    for field, expected_value in expected.items():
        actual = manifest.get(field)
        valid = (
            actual is expected_value
            if isinstance(expected_value, bool)
            else actual == expected_value
        )
        if not valid:
            raise BuildError(f"{label} manifest has unexpected {field}")


def _load_crosswalk_manifest(
    path: Path, *, expected_sha256: str
) -> tuple[dict[str, Any], bytes, dict[str, Any], dict[str, Any]]:
    manifest, data = _read_manifest(path, expected_sha256=expected_sha256, label="crosswalk")
    if manifest.get("schema_version") != 1 or manifest.get("complete") is not True:
        raise BuildError("Crosswalk manifest is incomplete or unsupported")
    _required_false_gates(manifest, label="Crosswalk")
    for field, expected in {
        "candidate_only": True,
        "identity_accepted": False,
        "exclusion_eligible": False,
        "matching_eligible": False,
        "rate_eligible": False,
    }.items():
        if manifest.get(field) is not expected:
            raise BuildError(f"Crosswalk manifest has unexpected {field}")
    if manifest.get("normalizer_version") != NORMALIZER.value:
        raise BuildError("Crosswalk normalizer does not match the candidate producer")
    decision = manifest.get("decision_contract")
    if not isinstance(decision, Mapping) or decision.get("decision") != "candidate_unreviewed":
        raise BuildError("Crosswalk manifest has an unsupported decision contract")
    if decision.get("same_legal_entity") != "unknown":
        raise BuildError("Crosswalk manifest does not keep identity unknown")
    outputs = manifest.get("outputs")
    if not isinstance(outputs, Mapping):
        raise BuildError("Crosswalk manifest has no outputs object")
    ledger = _pinned_product(outputs.get("firm_identity_ledger"), label="firm identity ledger")
    edges = _pinned_product(outputs.get("candidate_edges"), label="exact candidate edges")
    inputs = manifest.get("inputs")
    if not isinstance(inputs, Mapping):
        raise BuildError("Crosswalk manifest has no inputs object")
    _pinned_product(inputs.get("broad_issuer_universe"), label="broad issuer universe")
    _pinned_product(inputs.get("sbir_awards_csv"), label="SBIR awards CSV")
    control_pin = inputs.get("control_manifest")
    if not isinstance(control_pin, Mapping):
        raise BuildError("Crosswalk manifest does not pin the control manifest")
    control_sha = control_pin.get("sha256")
    if not isinstance(control_sha, str) or not SHA256_RE.fullmatch(control_sha):
        raise BuildError("Crosswalk control-manifest pin has an invalid SHA-256")
    _non_negative_int(control_pin.get("size_bytes"), label="Crosswalk control manifest size")
    return manifest, data, ledger, edges


def _load_control_manifest(
    path: Path,
    *,
    expected_sha256: str,
    crosswalk: Mapping[str, Any],
) -> tuple[dict[str, Any], bytes, dict[str, Any]]:
    manifest, data = _read_manifest(path, expected_sha256=expected_sha256, label="control")
    if manifest.get("schema_version") != 1 or manifest.get("complete") is not True:
        raise BuildError("Control manifest is incomplete or unsupported")
    _required_false_gates(manifest, label="Control")
    control_pin = crosswalk["inputs"]["control_manifest"]
    if _sha256_bytes(data) != control_pin["sha256"] or len(data) != control_pin["size_bytes"]:
        raise BuildError("Control manifest does not match the crosswalk's upstream pin")
    contract = manifest.get("identity_evidence_contract")
    if not isinstance(contract, Mapping) or contract.get("fields") != list(
        EXPECTED_IDENTITY_FIELDS
    ):
        raise BuildError("Control manifest has an unsupported identity evidence contract")
    if (
        contract.get("grain") != "form_d_filing_accession"
        or contract.get("historical_aliases_retained") is not True
        or contract.get("source_table") != "ISSUERS.tsv"
    ):
        raise BuildError("Control manifest has an unsupported identity evidence contract")
    outputs = manifest.get("outputs")
    if not isinstance(outputs, Mapping):
        raise BuildError("Control manifest has no outputs object")
    broad = _pinned_product(outputs.get("broad_issuer_universe"), label="broad issuer universe")
    expected_broad = crosswalk["inputs"]["broad_issuer_universe"]
    for field in ("row_count", "sha256", "size_bytes"):
        if broad[field] != expected_broad[field]:
            raise BuildError("Control broad-issuer pin does not match the crosswalk")
    awards = manifest.get("exclusion", {}).get("awards_csv")
    pinned_awards = _pinned_product(awards, label="SBIR awards CSV")
    expected_awards = crosswalk["inputs"]["sbir_awards_csv"]
    for field in ("row_count", "sha256", "size_bytes"):
        if pinned_awards[field] != expected_awards[field]:
            raise BuildError("Control award pin does not match the crosswalk")
    return manifest, data, broad


def _resolve_product(manifest_path: Path, product: Mapping[str, Any]) -> Path:
    return manifest_path.parent / str(product["path"])


def _load_jsonl(path: Path, product: Mapping[str, Any], *, label: str) -> list[dict[str, Any]]:
    if not path.is_file():
        raise BuildError(f"Pinned {label} is missing: {path}")
    before = path.stat()
    if before.st_size != product["size_bytes"]:
        raise BuildError(f"Pinned {label} byte count does not match its manifest")
    digest = hashlib.sha256()
    size = 0
    rows: list[dict[str, Any]] = []
    with path.open("rb") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            digest.update(raw_line)
            size += len(raw_line)
            if not raw_line.strip():
                raise BuildError(f"{label.title()} has a blank line at {line_number}")
            try:
                row = json.loads(raw_line)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise BuildError(f"Invalid {label} JSON at line {line_number}") from exc
            if not isinstance(row, dict):
                raise BuildError(f"{label.title()} line {line_number} must be an object")
            rows.append(row)
    after = path.stat()
    if (
        after.st_size != before.st_size
        or after.st_mtime_ns != before.st_mtime_ns
        or after.st_ino != before.st_ino
    ):
        raise BuildError(f"Pinned {label} changed while it was read")
    if len(rows) != product["row_count"] or size != product["size_bytes"]:
        raise BuildError(f"Pinned {label} rows or bytes do not match its manifest")
    if digest.hexdigest() != product["sha256"]:
        raise BuildError(f"Pinned {label} SHA-256 does not match its manifest")
    return rows


def _normalizer(value: object) -> str:
    return normalize_company_name(value, profile=NORMALIZER)


def _prefix(value: str) -> str:
    return "".join(character for character in value if character.isalnum())[:PREFIX_LENGTH]


def _fuzzy_eligible(value: str) -> bool:
    return sum(character.isalnum() for character in value) >= MINIMUM_FUZZY_NAME_LENGTH


def _validate_similarity_backend() -> None:
    try:
        actual = distribution_version(SIMILARITY_BACKEND)
    except PackageNotFoundError as exc:
        raise BuildError(
            f"Candidate similarity requires {SIMILARITY_BACKEND}=={SIMILARITY_BACKEND_VERSION}"
        ) from exc
    if actual != SIMILARITY_BACKEND_VERSION:
        raise BuildError(
            "Candidate similarity requires "
            f"{SIMILARITY_BACKEND}=={SIMILARITY_BACKEND_VERSION}; found {actual}"
        )
    sentinel = company_name_similarity("ABCCCCC", "ABCBCCC", metric=CompanyNameMetric.RATIO)
    if abs(sentinel - SIMILARITY_BACKEND_SENTINEL) > 1e-12:
        raise BuildError("Shared company-name similarity is not using the pinned backend")


def _similarity(left: str, right: str, *, metric: CompanyNameMetric) -> float:
    return company_name_similarity(left, right, metric=metric)


def _normalize_zip5(value: object) -> str | None:
    if value is None:
        return None
    match = ZIP5_RE.fullmatch(str(value))
    return match.group(1) if match else None


def _simple_key(value: object) -> str | None:
    text = unicodedata.normalize("NFKD", str(value or "").strip().upper())
    text = "".join(character for character in text if not unicodedata.combining(character))
    key = " ".join(re.sub(r"[^A-Z0-9]+", " ", text).split())
    return key or None


def _normalize_phone10(value: object) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    text = PHONE_EXTENSION_RE.sub("", text)
    digits = "".join(character for character in text if character.isdigit())
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return digits if len(digits) == 10 else None


def _edge_id(sbir_firm_id: str, cik: str) -> str:
    material = "\0".join((EDGE_ID_CONTRACT, sbir_firm_id, cik))
    return f"sbir_form_d_edge:{hashlib.sha256(material.encode()).hexdigest()}"


def _column(fieldnames: Sequence[str], *aliases: str) -> str | None:
    by_name = {field.strip().casefold(): field for field in fieldnames}
    return next(
        (by_name[alias.casefold()] for alias in aliases if alias.casefold() in by_name), None
    )


def _load_ledger(
    path: Path, product: Mapping[str, Any]
) -> tuple[dict[str, dict[str, Any]], dict[int, dict[str, Any]], dict[str, set[str]]]:
    rows = _load_jsonl(path, product, label="firm identity ledger")
    components: dict[str, dict[str, Any]] = {}
    source_index: dict[int, dict[str, Any]] = {}
    exact_name_index: dict[str, set[str]] = defaultdict(set)
    previous_firm: str | None = None
    for line_number, row in enumerate(rows, start=1):
        firm_id = row.get("sbir_firm_id")
        if not isinstance(firm_id, str) or not firm_id.startswith("sbir_firm:"):
            raise BuildError(f"Ledger line {line_number} has an invalid firm ID")
        if previous_firm is not None and firm_id <= previous_firm:
            raise BuildError("Ledger firm IDs must be unique and ordered")
        previous_firm = firm_id
        if (
            row.get("schema_version") != 1
            or row.get("firm_id_contract") != FIRM_ID_CONTRACT
            or row.get("ledger_contract") != LEDGER_CONTRACT
        ):
            raise BuildError(f"Ledger line {line_number} has an unsupported contract")
        status = row.get("component_status")
        if status not in {"identifier_consistent", "name_only", "quarantined_conflict"}:
            raise BuildError(f"Ledger line {line_number} has an invalid component status")
        names = row.get("normalized_names")
        reasons = row.get("quarantine_reasons")
        sources = row.get("source_records")
        if (
            not isinstance(names, list)
            or not isinstance(reasons, list)
            or not isinstance(sources, list)
        ):
            raise BuildError(f"Ledger line {line_number} has malformed evidence")
        if row.get("source_record_count") != len(sources) or row.get("award_row_count") != len(
            sources
        ):
            raise BuildError(f"Ledger line {line_number} has inconsistent source counts")
        normalized_names: list[str] = []
        firm_source_records: set[int] = set()
        for name in names:
            if not isinstance(name, str) or not name or _normalizer(name) != name:
                raise BuildError(f"Ledger line {line_number} has an invalid normalized name")
            normalized_names.append(name)
            exact_name_index[name].add(firm_id)
        for source in sources:
            if not isinstance(source, Mapping):
                raise BuildError(f"Ledger line {line_number} has a non-object source record")
            source_record = source.get("source_record")
            if (
                isinstance(source_record, bool)
                or not isinstance(source_record, int)
                or source_record < 1
            ):
                raise BuildError(f"Ledger line {line_number} has an invalid source record")
            if source_record in source_index:
                raise BuildError(f"Ledger repeats SBIR source record {source_record}")
            normalized_name = source.get("normalized_name")
            if normalized_name is not None and normalized_name not in normalized_names:
                raise BuildError(f"Ledger source record {source_record} has an unlisted name")
            source_index[source_record] = {
                "firm_id": firm_id,
                "normalized_name": normalized_name,
                "raw_name": source.get("raw_name"),
            }
            firm_source_records.add(source_record)
        components[firm_id] = {
            "component_status": status,
            "normalized_names": sorted(normalized_names),
            "quarantine_reasons": sorted(str(reason) for reason in reasons),
            "source_records": firm_source_records,
        }
    return components, source_index, dict(exact_name_index)


def _contains_forbidden_key(value: object) -> bool:
    if isinstance(value, Mapping):
        return any(
            str(key).casefold() in FORBIDDEN_OUTPUT_KEYS or _contains_forbidden_key(child)
            for key, child in value.items()
        )
    if isinstance(value, list):
        return any(_contains_forbidden_key(child) for child in value)
    return False


def _validate_exact_lineage(
    row: Mapping[str, Any],
    *,
    line_number: int,
    firm_id: str,
    component: Mapping[str, Any],
    source_index: Mapping[int, Mapping[str, Any]],
) -> None:
    source_records = row.get("sbir_source_records")
    accessions = row.get("form_d_source_accessions")
    if (
        not isinstance(source_records, list)
        or not source_records
        or any(
            isinstance(source_record, bool)
            or not isinstance(source_record, int)
            or source_record < 1
            for source_record in source_records
        )
        or source_records != sorted(set(source_records))
        or not set(source_records) <= component["source_records"]
    ):
        raise BuildError(f"Exact edge line {line_number} has invalid SBIR lineage")
    if (
        not isinstance(accessions, list)
        or not accessions
        or any(not isinstance(accession, str) or not accession.strip() for accession in accessions)
        or accessions != sorted(set(accessions))
    ):
        raise BuildError(f"Exact edge line {line_number} has invalid Form D lineage")

    evidence_rows = row.get("name_evidence")
    if not isinstance(evidence_rows, list) or not evidence_rows:
        raise BuildError(f"Exact edge line {line_number} lacks nested name lineage")
    nested_sources: set[int] = set()
    nested_accessions: set[str] = set()
    evidence_names: list[str] = []
    for evidence in evidence_rows:
        if not isinstance(evidence, Mapping):
            raise BuildError(f"Exact edge line {line_number} has malformed name lineage")
        normalized_name = evidence.get("normalized_name")
        if (
            not isinstance(normalized_name, str)
            or normalized_name in evidence_names
            or normalized_name not in component["normalized_names"]
            or _normalizer(normalized_name) != normalized_name
        ):
            raise BuildError(f"Exact edge line {line_number} has invalid normalized-name lineage")
        evidence_names.append(normalized_name)
        form_d_rows = evidence.get("form_d")
        sbir_rows = evidence.get("sbir")
        if not isinstance(form_d_rows, list) or not form_d_rows:
            raise BuildError(f"Exact edge line {line_number} lacks Form D name lineage")
        if not isinstance(sbir_rows, list) or not sbir_rows:
            raise BuildError(f"Exact edge line {line_number} lacks SBIR name lineage")
        form_d_witnesses: list[tuple[str, str]] = []
        for witness in form_d_rows:
            if not isinstance(witness, Mapping):
                raise BuildError(f"Exact edge line {line_number} has malformed Form D lineage")
            accession = witness.get("accession_number")
            raw_alias = witness.get("raw_alias")
            if (
                not isinstance(accession, str)
                or accession not in accessions
                or not isinstance(raw_alias, str)
                or not raw_alias.strip()
                or _normalizer(raw_alias) != normalized_name
            ):
                raise BuildError(f"Exact edge line {line_number} has invalid Form D name lineage")
            nested_accessions.add(accession)
            form_d_witnesses.append((accession, raw_alias))
        if form_d_witnesses != sorted(set(form_d_witnesses)):
            raise BuildError(f"Exact edge line {line_number} has unordered Form D lineage")
        sbir_witnesses: list[tuple[int, str]] = []
        for witness in sbir_rows:
            if not isinstance(witness, Mapping):
                raise BuildError(f"Exact edge line {line_number} has malformed SBIR lineage")
            source_record = witness.get("source_record")
            raw_name = witness.get("raw_name")
            if (
                isinstance(source_record, bool)
                or not isinstance(source_record, int)
                or source_record not in source_records
                or not isinstance(raw_name, str)
                or not raw_name.strip()
            ):
                raise BuildError(f"Exact edge line {line_number} has invalid SBIR name lineage")
            frozen = source_index.get(source_record)
            if (
                frozen is None
                or frozen["firm_id"] != firm_id
                or frozen["normalized_name"] != normalized_name
                or frozen["raw_name"] != raw_name
            ):
                raise BuildError(f"Exact edge line {line_number} has cross-firm SBIR lineage")
            nested_sources.add(source_record)
            sbir_witnesses.append((source_record, raw_name))
        if sbir_witnesses != sorted(set(sbir_witnesses)):
            raise BuildError(f"Exact edge line {line_number} has unordered SBIR lineage")
    if evidence_names != sorted(evidence_names):
        raise BuildError(f"Exact edge line {line_number} has unordered name lineage")
    if nested_sources != set(source_records) or nested_accessions != set(accessions):
        raise BuildError(f"Exact edge line {line_number} does not reconcile nested lineage")


def _load_exact_edges(
    path: Path,
    product: Mapping[str, Any],
    *,
    components: Mapping[str, Mapping[str, Any]],
    source_index: Mapping[int, Mapping[str, Any]],
) -> tuple[dict[tuple[str, str], dict[str, Any]], dict[str, set[str]]]:
    rows = _load_jsonl(path, product, label="exact candidate edges")
    edges: dict[tuple[str, str], dict[str, Any]] = {}
    exact_by_cik: dict[str, set[str]] = defaultdict(set)
    previous_pair: tuple[str, str] | None = None
    for line_number, row in enumerate(rows, start=1):
        firm_id = row.get("sbir_firm_id")
        cik = row.get("form_d_cik")
        if not isinstance(firm_id, str) or firm_id not in components:
            raise BuildError(f"Exact edge line {line_number} has an unknown firm")
        if not isinstance(cik, str) or not cik.isdigit() or cik.startswith("0") or len(cik) > 10:
            raise BuildError(f"Exact edge line {line_number} has an invalid CIK")
        pair = (firm_id, cik)
        if previous_pair is not None and pair <= previous_pair:
            raise BuildError("Exact edge pairs must be unique and ordered")
        previous_pair = pair
        if (
            row.get("schema_version") != 1
            or row.get("edge_contract") != EXACT_EDGE_CONTRACT
            or row.get("edge_id_contract") != EDGE_ID_CONTRACT
            or row.get("edge_id") != _edge_id(firm_id, cik)
            or row.get("match_method") != "exact_normalized_name"
        ):
            raise BuildError(f"Exact edge line {line_number} has an unsupported contract")
        if row.get("component_status") != components[firm_id]["component_status"]:
            raise BuildError(f"Exact edge line {line_number} disagrees with the firm ledger")
        if (
            row.get("normalizer_version") != NORMALIZER.value
            or row.get("quarantine_reasons") != components[firm_id]["quarantine_reasons"]
        ):
            raise BuildError(f"Exact edge line {line_number} disagrees with firm provenance")
        if (
            row.get("decision") != "candidate_unreviewed"
            or row.get("same_legal_entity") is not None
        ):
            raise BuildError(f"Exact edge line {line_number} contains an identity decision")
        for gate in (
            "identity_accepted",
            "exclusion_eligible",
            "matching_eligible",
            "rate_eligible",
        ):
            if row.get(gate) is not False:
                raise BuildError(f"Exact edge line {line_number} opens {gate}")
        _validate_exact_lineage(
            row,
            line_number=line_number,
            firm_id=firm_id,
            component=components[firm_id],
            source_index=source_index,
        )
        if _contains_forbidden_key(row):
            raise BuildError(f"Exact edge line {line_number} contains a forbidden field")
        edges[pair] = row
        exact_by_cik[cik].add(firm_id)
    return edges, dict(exact_by_cik)


def _new_value_map() -> dict[str, dict[str, set[int]]]:
    return {field: defaultdict(set) for field in CONTACT_FIELDS}


def _load_award_profiles(
    path: Path,
    product: Mapping[str, Any],
    *,
    components: Mapping[str, Mapping[str, Any]],
    source_index: Mapping[int, Mapping[str, Any]],
) -> tuple[
    dict[str, dict[str, Any]], dict[str, set[tuple[str, str]]], dict[str, set[tuple[str, str]]]
]:
    if not path.is_file():
        raise BuildError(f"Pinned SBIR awards CSV is missing: {path}")
    before = path.stat()
    sha256, size = _sha256_path(path)
    if size != product["size_bytes"] or sha256 != product["sha256"]:
        raise BuildError("SBIR awards CSV bytes do not match the manifest pin")
    profiles: dict[str, dict[str, Any]] = {
        firm_id: {"contacts": _new_value_map(), "names": {}} for firm_id in components
    }
    reader: csv.DictReader[str] | None = None
    row_count = 0
    try:
        with path.open(encoding="utf-8-sig", errors="strict", newline="") as handle:
            reader = csv.DictReader(handle, strict=True)
            fieldnames = reader.fieldnames or []
            if any(not isinstance(field, str) or not field.strip() for field in fieldnames):
                raise BuildError("SBIR awards CSV has a blank column name")
            folded = [field.strip().casefold() for field in fieldnames]
            if len(folded) != len(set(folded)):
                raise BuildError("SBIR awards CSV has duplicate column names")
            columns = {
                "name": _column(fieldnames, "Company", "company_name"),
                "street1": _column(fieldnames, "Address1", "address_1"),
                "city": _column(fieldnames, "City"),
                "state": _column(fieldnames, "State"),
                "zip5": _column(fieldnames, "Zip", "zip_code"),
                "contact_phone": _column(fieldnames, "Contact Phone", "contact_phone"),
                "pi_phone": _column(fieldnames, "PI Phone", "pi_phone"),
            }
            missing = [name for name, column in columns.items() if column is None]
            if missing:
                raise BuildError("SBIR awards CSV lacks identity columns: " + ", ".join(missing))
            for source_record, row in enumerate(reader, start=1):
                row_count += 1
                if None in row:
                    raise BuildError(f"SBIR award record {source_record} has extra fields")
                frozen = source_index.get(source_record)
                if frozen is None:
                    raise BuildError(f"SBIR award record {source_record} is absent from the ledger")
                firm_id = str(frozen["firm_id"])
                raw_name = str(row.get(columns["name"]) or "")
                normalized_name = _normalizer(raw_name) or None
                if (
                    normalized_name != frozen["normalized_name"]
                    or (raw_name if raw_name.strip() else None) != frozen["raw_name"]
                ):
                    raise BuildError(f"SBIR award record {source_record} disagrees with the ledger")
                profile = profiles[firm_id]
                name_profile = profile["names"].setdefault(
                    normalized_name,
                    {"raw_names": defaultdict(set), "contacts": _new_value_map()},
                )
                if raw_name.strip():
                    name_profile["raw_names"][raw_name].add(source_record)
                values = {
                    "street1": _simple_key(row.get(columns["street1"])),
                    "city": _simple_key(row.get(columns["city"])),
                    "state": normalize_us_jurisdiction(
                        row.get(columns["state"]), profile=GEOGRAPHY_PROFILE
                    ),
                    "zip5": _normalize_zip5(row.get(columns["zip5"])),
                }
                phones = {
                    value
                    for value in (
                        _normalize_phone10(row.get(columns["contact_phone"])),
                        _normalize_phone10(row.get(columns["pi_phone"])),
                    )
                    if value
                }
                for field, value in values.items():
                    if value:
                        profile["contacts"][field][value].add(source_record)
                        name_profile["contacts"][field][value].add(source_record)
                for phone in phones:
                    profile["contacts"]["phone10"][phone].add(source_record)
                    name_profile["contacts"]["phone10"][phone].add(source_record)
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
        raise BuildError("SBIR awards CSV changed while it was parsed")
    if row_count != product["row_count"] or set(source_index) != set(range(1, row_count + 1)):
        raise BuildError("SBIR award rows do not reconcile to the firm ledger")

    prefix_index: dict[str, set[tuple[str, str]]] = defaultdict(set)
    zip_index: dict[str, set[tuple[str, str]]] = defaultdict(set)
    for firm_id, profile in profiles.items():
        for name, name_profile in profile["names"].items():
            if not isinstance(name, str) or not _fuzzy_eligible(name):
                continue
            prefix = _prefix(name)
            if len(prefix) == PREFIX_LENGTH:
                prefix_index[prefix].add((firm_id, name))
            for zip5 in name_profile["contacts"]["zip5"]:
                zip_index[zip5].add((firm_id, name))
    return profiles, dict(prefix_index), dict(zip_index)


def _validated_aliases(value: object, *, label: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise BuildError(f"{label} must be a non-empty list")
    aliases: list[str] = []
    for alias in value:
        if not isinstance(alias, str) or not alias.strip():
            raise BuildError(f"{label} contains an invalid alias")
        aliases.append(alias)
    return aliases


def _new_candidate(
    firm_id: str,
    cik: str,
    component: Mapping[str, Any],
    *,
    exact_edge: Mapping[str, Any] | None,
) -> dict[str, Any]:
    routes: set[str] = {"exact_normalized_name"} if exact_edge is not None else set()
    source_records = set(exact_edge["sbir_source_records"]) if exact_edge is not None else set()
    accessions = set(exact_edge["form_d_source_accessions"]) if exact_edge is not None else set()
    best: dict[str, Any] | None = None
    route_evidence: dict[str, dict[str, Any]] = {}
    if exact_edge is not None:
        evidence = exact_edge.get("name_evidence")
        if not isinstance(evidence, list) or not evidence:
            raise BuildError("Exact edge lacks name evidence")
        chosen_index, chosen = min(
            enumerate(evidence),
            key=lambda indexed: (str(indexed[1].get("normalized_name") or ""), indexed[0]),
        )
        best = {
            "form_d": chosen["form_d"],
            "form_d_normalized_alias": chosen["normalized_name"],
            "ratio_similarity": 1.0,
            "sbir": chosen["sbir"],
            "sbir_normalized_name": chosen["normalized_name"],
            "token_set_similarity": 1.0,
            "token_sort_similarity": 1.0,
        }
        route_evidence["exact_normalized_name"] = {
            "evidence_path": f"exact_source_edge.name_evidence[{chosen_index}]",
            "normalized_name": chosen["normalized_name"],
            "ratio_similarity": 1.0,
        }
    return {
        "best_name_evidence": best,
        "candidate_routes": routes,
        "component_status": component["component_status"],
        "contact_evidence": {field: [] for field in CONTACT_FIELDS},
        "exact_source_edge": dict(exact_edge) if exact_edge is not None else None,
        "form_d_cik": cik,
        "form_d_source_accessions": accessions,
        "quarantine_reasons": list(component["quarantine_reasons"]),
        "route_evidence": route_evidence,
        "sbir_firm_id": firm_id,
        "sbir_source_records": source_records,
    }


def _name_evidence_rank(value: Mapping[str, Any]) -> tuple[float, str, str, str]:
    return (
        -float(value["ratio_similarity"]),
        str(value["sbir_normalized_name"]),
        str(value["form_d_normalized_alias"]),
        json.dumps(value["form_d"], sort_keys=True, separators=(",", ":")),
    )


def _contact_intersections(
    sbir_contacts: Mapping[str, Mapping[str, set[int]]],
    form_d_contacts: Mapping[str, Mapping[str, set[str]]],
) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for field in CONTACT_FIELDS:
        shared = sorted(set(sbir_contacts[field]) & set(form_d_contacts[field]))
        result[field] = [
            {
                "form_d_accessions": sorted(form_d_contacts[field][value]),
                "sbir_source_records": sorted(sbir_contacts[field][value]),
                "value": value,
            }
            for value in shared
        ]
    return result


def _fuzzy_route_evidence(
    route: str,
    *,
    name_evidence: Mapping[str, Any],
    prefix: str,
    sbir_contacts: Mapping[str, Mapping[str, set[int]]],
    form_d_contacts: Mapping[str, Mapping[str, set[str]]],
) -> dict[str, Any]:
    support: dict[str, Any] = {}
    if route in {"strong_name", "state_supported"}:
        support["prefix"] = prefix
    if route in {"state_supported", "zip_supported"}:
        field = "state" if route == "state_supported" else "zip5"
        support[field] = _contact_intersections(sbir_contacts, form_d_contacts)[field]
        if not support[field]:
            raise BuildError(f"{route} lacks its required {field} witness")
    return {"name_evidence": dict(name_evidence), "route_support": support}


def _stream_candidates(
    path: Path,
    product: Mapping[str, Any],
    *,
    components: Mapping[str, Mapping[str, Any]],
    exact_name_index: Mapping[str, set[str]],
    exact_edges: Mapping[tuple[str, str], Mapping[str, Any]],
    exact_by_cik: Mapping[str, set[str]],
    profiles: Mapping[str, Mapping[str, Any]],
    prefix_index: Mapping[str, set[tuple[str, str]]],
    zip_index: Mapping[str, set[tuple[str, str]]],
) -> tuple[dict[tuple[str, str], dict[str, Any]], dict[str, Any]]:
    if not path.is_file():
        raise BuildError(f"Pinned broad issuer universe is missing: {path}")
    before = path.stat()
    if before.st_size != product["size_bytes"]:
        raise BuildError("Broad issuer universe byte count does not match its pin")
    candidates = {
        pair: _new_candidate(pair[0], pair[1], components[pair[0]], exact_edge=edge)
        for pair, edge in exact_edges.items()
    }
    digest = hashlib.sha256()
    size = 0
    row_count = 0
    filing_count = 0
    previous_cik: str | None = None
    exact_accessions = {
        accession for edge in exact_edges.values() for accession in edge["form_d_source_accessions"]
    }
    seen_accessions: set[str] = set()
    exact_accession_ciks: dict[str, str] = {}
    accession_aliases: dict[str, set[str]] = {}
    exact_reconstructed: set[tuple[str, str]] = set()
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
                raise BuildError("Broad issuer CIKs must be unique and ordered")
            previous_cik = cik
            if row.get("firm_key") != f"form_d_cik:{cik}" or row.get("schema_version") != 1:
                raise BuildError(f"Broad issuer line {line_number} has an invalid contract")
            filings = row.get("filings")
            if (
                not isinstance(filings, list)
                or not filings
                or row.get("filing_count") != len(filings)
            ):
                raise BuildError(f"Broad issuer line {line_number} has invalid filing evidence")
            aggregate_aliases = set(
                _validated_aliases(row.get("issuer_name_aliases"), label=f"Issuer {cik} aliases")
            )
            traceable_aliases: set[str] = set()
            alias_sources: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
            issuer_contacts: dict[str, dict[str, set[str]]] = {
                field: defaultdict(set) for field in CONTACT_FIELDS
            }
            for filing in filings:
                filing_count += 1
                if not isinstance(filing, Mapping) or filing.get("cik") != cik:
                    raise BuildError(f"Broad issuer {cik} pools evidence across CIKs")
                missing = [field for field in EXPECTED_IDENTITY_FIELDS if field not in filing]
                if missing:
                    raise BuildError(
                        f"Broad issuer {cik} lacks identity fields: {', '.join(missing)}"
                    )
                accession = filing.get("accession_number")
                if not isinstance(accession, str) or not accession.strip():
                    raise BuildError(f"Broad issuer {cik} has an invalid accession")
                accession = accession.strip()
                if accession in seen_accessions:
                    raise BuildError(f"Broad issuer universe repeats accession {accession}")
                seen_accessions.add(accession)
                aliases = _validated_aliases(
                    filing.get("issuer_name_aliases"), label=f"Filing {accession} aliases"
                )
                if accession in exact_accessions:
                    exact_accession_ciks[accession] = cik
                    accession_aliases[accession] = set(aliases)
                issuer_name = filing.get("issuer_name")
                if not isinstance(issuer_name, str) or issuer_name not in aliases:
                    raise BuildError(f"Filing {accession} has an untraceable issuer name")
                for raw_alias in aliases:
                    traceable_aliases.add(raw_alias)
                    normalized = _normalizer(raw_alias)
                    if normalized:
                        alias_sources[normalized][raw_alias].add(accession)
                values = {
                    "street1": _simple_key(filing.get("street1")),
                    "city": _simple_key(filing.get("city")),
                    "state": normalize_us_jurisdiction(
                        filing.get("state"), profile=GEOGRAPHY_PROFILE
                    ),
                    "zip5": _normalize_zip5(filing.get("zip_code")),
                    "phone10": _normalize_phone10(filing.get("issuer_phone")),
                }
                for field, value in values.items():
                    if value:
                        issuer_contacts[field][value].add(accession)
            if aggregate_aliases != traceable_aliases:
                raise BuildError(f"Broad issuer {cik} has untraceable aggregate aliases")

            for alias in alias_sources:
                for firm_id in exact_name_index.get(alias, set()):
                    exact_reconstructed.add((firm_id, cik))

            possible: set[tuple[str, str]] = set()
            for alias in alias_sources:
                prefix = _prefix(alias)
                if len(prefix) == PREFIX_LENGTH:
                    possible.update(prefix_index.get(prefix, set()))
            for zip5 in issuer_contacts["zip5"]:
                possible.update(zip_index.get(zip5, set()))

            pairs_for_cik: set[tuple[str, str]] = {
                (firm_id, cik) for firm_id in exact_by_cik.get(cik, set())
            }
            for firm_id, sbir_name in sorted(possible):
                pair = (firm_id, cik)
                if pair in exact_edges or not _fuzzy_eligible(sbir_name):
                    continue
                name_profile = profiles[firm_id]["names"].get(sbir_name)
                if not isinstance(name_profile, Mapping):
                    raise BuildError("Fuzzy index points at missing SBIR name evidence")
                matched_states = set(name_profile["contacts"]["state"]) & set(
                    issuer_contacts["state"]
                )
                matched_zip5s = set(name_profile["contacts"]["zip5"]) & set(issuer_contacts["zip5"])
                sbir_prefix = _prefix(sbir_name)
                for alias, raw_sources in sorted(alias_sources.items()):
                    if alias == sbir_name or not _fuzzy_eligible(alias):
                        continue
                    ratio = _similarity(alias, sbir_name, metric=CompanyNameMetric.RATIO)
                    same_prefix = (
                        len(sbir_prefix) == PREFIX_LENGTH and _prefix(alias) == sbir_prefix
                    )
                    routes: set[str] = set()
                    if same_prefix and ratio >= STRONG_NAME_THRESHOLD:
                        routes.add("strong_name")
                    if same_prefix and matched_states and ratio >= STATE_SUPPORTED_THRESHOLD:
                        routes.add("state_supported")
                    if matched_zip5s and ratio >= ZIP_SUPPORTED_THRESHOLD:
                        routes.add("zip_supported")
                    if not routes:
                        continue
                    candidate = candidates.setdefault(
                        pair,
                        _new_candidate(firm_id, cik, components[firm_id], exact_edge=None),
                    )
                    candidate["candidate_routes"].update(routes)
                    form_d_rows = [
                        {"accession_numbers": sorted(accessions), "raw_alias": raw_alias}
                        for raw_alias, accessions in sorted(raw_sources.items())
                    ]
                    sbir_rows = [
                        {"raw_name": raw_name, "source_records": sorted(source_records)}
                        for raw_name, source_records in sorted(name_profile["raw_names"].items())
                    ]
                    evidence = {
                        "form_d": form_d_rows,
                        "form_d_normalized_alias": alias,
                        "ratio_similarity": round(ratio, 6),
                        "sbir": sbir_rows,
                        "sbir_normalized_name": sbir_name,
                        "token_set_similarity": round(
                            _similarity(alias, sbir_name, metric=CompanyNameMetric.TOKEN_SET), 6
                        ),
                        "token_sort_similarity": round(
                            _similarity(alias, sbir_name, metric=CompanyNameMetric.TOKEN_SORT), 6
                        ),
                    }
                    if candidate["best_name_evidence"] is None or _name_evidence_rank(
                        evidence
                    ) < _name_evidence_rank(candidate["best_name_evidence"]):
                        candidate["best_name_evidence"] = evidence
                    for route in routes:
                        witness = _fuzzy_route_evidence(
                            route,
                            name_evidence=evidence,
                            prefix=sbir_prefix,
                            sbir_contacts=name_profile["contacts"],
                            form_d_contacts=issuer_contacts,
                        )
                        previous_witness = candidate["route_evidence"].get(route)
                        if previous_witness is None or _name_evidence_rank(
                            witness["name_evidence"]
                        ) < _name_evidence_rank(previous_witness["name_evidence"]):
                            candidate["route_evidence"][route] = witness
                    for accessions in raw_sources.values():
                        candidate["form_d_source_accessions"].update(accessions)
                    for source_records in name_profile["raw_names"].values():
                        candidate["sbir_source_records"].update(source_records)
                    pairs_for_cik.add(pair)

            for pair in sorted(pairs_for_cik):
                candidate = candidates[pair]
                contact = _contact_intersections(profiles[pair[0]]["contacts"], issuer_contacts)
                candidate["contact_evidence"] = contact
                for evidence_rows in contact.values():
                    for evidence in evidence_rows:
                        candidate["form_d_source_accessions"].update(evidence["form_d_accessions"])
                        candidate["sbir_source_records"].update(evidence["sbir_source_records"])

    after = path.stat()
    if (
        after.st_size != before.st_size
        or after.st_mtime_ns != before.st_mtime_ns
        or after.st_ino != before.st_ino
    ):
        raise BuildError("Broad issuer universe changed while it was parsed")
    if row_count != product["row_count"] or size != product["size_bytes"]:
        raise BuildError("Broad issuer rows or bytes do not match their pin")
    if digest.hexdigest() != product["sha256"]:
        raise BuildError("Broad issuer SHA-256 does not match its pin")
    if exact_reconstructed != set(exact_edges):
        missing_exact_count = len(set(exact_edges) - exact_reconstructed)
        extra_exact_count = len(exact_reconstructed - set(exact_edges))
        raise BuildError(
            "Reconstructed exact pairs disagree with Phase 1: "
            f"missing={missing_exact_count}, extra={extra_exact_count}"
        )
    for pair, edge in exact_edges.items():
        for accession in edge["form_d_source_accessions"]:
            if exact_accession_ciks.get(accession) != pair[1]:
                raise BuildError(f"Exact edge {edge['edge_id']} has cross-CIK accession evidence")
        for evidence in edge["name_evidence"]:
            for witness in evidence["form_d"]:
                accession = witness["accession_number"]
                if witness["raw_alias"] not in accession_aliases.get(accession, set()):
                    raise BuildError(
                        f"Exact edge {edge['edge_id']} has untraceable Form D alias evidence"
                    )
    return candidates, {
        "filing_rows_validated": filing_count,
        "row_count": row_count,
        "sha256": digest.hexdigest(),
        "size_bytes": size,
    }


def _finalize_candidates(
    candidates: Mapping[tuple[str, str], Mapping[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for (firm_id, cik), candidate in sorted(candidates.items()):
        routes = candidate["candidate_routes"]
        if not routes or candidate["best_name_evidence"] is None:
            raise BuildError(f"Candidate {firm_id}/{cik} has no name route or evidence")
        route_evidence = candidate["route_evidence"]
        if set(route_evidence) != set(routes):
            raise BuildError(f"Candidate {firm_id}/{cik} lacks route-specific evidence")
        exact_edge = candidate["exact_source_edge"]
        if (exact_edge is not None) != ("exact_normalized_name" in routes):
            raise BuildError(f"Candidate {firm_id}/{cik} has inconsistent exact evidence")
        row = {
            "best_name_evidence": candidate["best_name_evidence"],
            "candidate_contract": CANDIDATE_CONTRACT,
            "candidate_only": True,
            "candidate_routes": [route for route in ROUTE_ORDER if route in routes],
            "component_status": candidate["component_status"],
            "complete_sbir_exclusion": False,
            "contact_evidence": candidate["contact_evidence"],
            "covariates_ready": False,
            "decision": "candidate_unreviewed",
            "edge_id": _edge_id(firm_id, cik),
            "edge_id_contract": EDGE_ID_CONTRACT,
            "exact_source_edge": exact_edge,
            "exclusion_eligible": False,
            "exclusion_recall": "unknown",
            "form_d_cik": cik,
            "form_d_source_accessions": sorted(candidate["form_d_source_accessions"]),
            "identity_accepted": False,
            "matching_eligible": False,
            "normalizer_version": NORMALIZER.value,
            "quarantine_reasons": candidate["quarantine_reasons"],
            "rate_eligible": False,
            "route_evidence": {
                route: route_evidence[route] for route in ROUTE_ORDER if route in routes
            },
            "same_legal_entity": None,
            "sbir_firm_id": firm_id,
            "sbir_source_records": sorted(candidate["sbir_source_records"]),
            "schema_version": CANDIDATE_SCHEMA_VERSION,
        }
        if _contains_forbidden_key(row):
            raise BuildError(f"Candidate {firm_id}/{cik} contains a forbidden field")
        rows.append(row)
    pairs = [(row["sbir_firm_id"], row["form_d_cik"]) for row in rows]
    edge_ids = [row["edge_id"] for row in rows]
    if len(pairs) != len(set(pairs)) or len(edge_ids) != len(set(edge_ids)):
        raise BuildError("Candidate pairs or stable edge IDs are not unique")
    return rows


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
    path = directory / "sbir_form_d_identity_candidates.manifest.json"
    data = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    with path.open("wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def _atomic_exchange_directories(left: Path, right: Path) -> None:
    """Atomically exchange two directories on supported deployment platforms."""

    if sys.platform == "darwin":
        function_name = "renameatx_np"
        at_fdcwd = -2
    elif sys.platform.startswith("linux"):
        function_name = "renameat2"
        at_fdcwd = -100
    else:
        raise BuildError(f"Atomic directory exchange is unsupported on {sys.platform}")
    libc = ctypes.CDLL(None, use_errno=True)
    exchange = getattr(libc, function_name, None)
    if exchange is None:
        raise BuildError(f"Atomic directory exchange function {function_name} is unavailable")
    exchange.argtypes = [
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    ]
    exchange.restype = ctypes.c_int
    if exchange(at_fdcwd, os.fsencode(left), at_fdcwd, os.fsencode(right), 2) != 0:
        error = ctypes.get_errno()
        raise OSError(error, f"Atomic release exchange failed: {os.strerror(error)}")


def _publish_release(staging: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_symlink() or (target.exists() and not target.is_dir()):
        raise BuildError(f"Output target must be a directory, not a file or symlink: {target}")
    if staging.parent.resolve() != target.parent.resolve():
        raise BuildError("Release staging and target directories must be siblings")
    if not target.exists():
        os.replace(staging, target)
        return
    _atomic_exchange_directories(staging, target)
    # After the atomic exchange, staging names the prior complete release. Its
    # cleanup cannot expose a partial target and is safe to retry/remove later.
    shutil.rmtree(staging, ignore_errors=True)


def _ensure_output_disjoint(output_dir: Path, *, inputs: Iterable[Path]) -> None:
    resolved_output = output_dir.resolve(strict=False)
    for input_path in inputs:
        resolved_input = input_path.resolve(strict=False)
        if resolved_input == resolved_output or resolved_output in resolved_input.parents:
            raise BuildError(f"Output directory would replace pinned input: {input_path}")


def _input_record(
    path: Path, *, sha256: str, size_bytes: int, row_count: int | None = None
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "path": path.name,
        "sha256": sha256,
        "size_bytes": size_bytes,
    }
    if row_count is not None:
        record["row_count"] = row_count
    return record


def build(args: argparse.Namespace) -> dict[str, Any]:
    code_version = str(args.code_version or "").strip()
    if not GIT_COMMIT_RE.fullmatch(code_version):
        raise BuildError("--code-version must be a full lowercase 40-character git commit")
    _validate_similarity_backend()
    crosswalk_manifest_path = Path(args.crosswalk_manifest)
    control_manifest_path = Path(args.control_manifest)
    awards_path = Path(args.awards_csv)
    output_dir = Path(args.output_dir)
    crosswalk, crosswalk_data, ledger_product, edge_product = _load_crosswalk_manifest(
        crosswalk_manifest_path,
        expected_sha256=args.crosswalk_manifest_sha256,
    )
    control, control_data, broad_product = _load_control_manifest(
        control_manifest_path,
        expected_sha256=args.control_manifest_sha256,
        crosswalk=crosswalk,
    )
    ledger_path = _resolve_product(crosswalk_manifest_path, ledger_product)
    edge_path = _resolve_product(crosswalk_manifest_path, edge_product)
    broad_path = _resolve_product(control_manifest_path, broad_product)
    award_product = crosswalk["inputs"]["sbir_awards_csv"]
    _ensure_output_disjoint(
        output_dir,
        inputs=(
            crosswalk_manifest_path,
            control_manifest_path,
            ledger_path,
            edge_path,
            broad_path,
            awards_path,
        ),
    )
    components, source_index, exact_name_index = _load_ledger(ledger_path, ledger_product)
    if len(source_index) != crosswalk["counts"]["award_rows"]:
        raise BuildError("Firm ledger source rows do not reconcile to the crosswalk manifest")
    exact_edges, exact_by_cik = _load_exact_edges(
        edge_path,
        edge_product,
        components=components,
        source_index=source_index,
    )
    profiles, prefix_index, zip_index = _load_award_profiles(
        awards_path,
        award_product,
        components=components,
        source_index=source_index,
    )
    candidates, broad_metadata = _stream_candidates(
        broad_path,
        broad_product,
        components=components,
        exact_name_index=exact_name_index,
        exact_edges=exact_edges,
        exact_by_cik=exact_by_cik,
        profiles=profiles,
        prefix_index=prefix_index,
        zip_index=zip_index,
    )
    rows = _finalize_candidates(candidates)
    exact_pairs = set(exact_edges)
    emitted_exact = {
        (row["sbir_firm_id"], row["form_d_cik"])
        for row in rows
        if row["exact_source_edge"] is not None
    }
    if emitted_exact != exact_pairs:
        raise BuildError("Enriched product does not preserve the exact Phase 1 pair set")

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.staging-", dir=output_dir.parent))
    try:
        product_out = _write_jsonl_product(
            staging,
            stem="sbir_form_d_identity_candidates.v2",
            rows=rows,
        )
        route_counts: Counter[str] = Counter()
        contact_pair_counts: Counter[str] = Counter()
        firms_to_ciks: dict[str, set[str]] = defaultdict(set)
        ciks_to_firms: dict[str, set[str]] = defaultdict(set)
        for row in rows:
            route_counts.update(row["candidate_routes"])
            for field, evidence in row["contact_evidence"].items():
                if evidence:
                    contact_pair_counts[field] += 1
            firms_to_ciks[row["sbir_firm_id"]].add(row["form_d_cik"])
            ciks_to_firms[row["form_d_cik"]].add(row["sbir_firm_id"])
        producer_path = Path(__file__)
        producer_sha, producer_size = _sha256_path(producer_path)
        manifest = {
            "candidate_only": True,
            "complete": True,
            "complete_sbir_exclusion": False,
            "counts": {
                "candidate_ciks": len(ciks_to_firms),
                "candidate_firms": len(firms_to_ciks),
                "candidate_pairs": len(rows),
                "contact_supported_pairs": {
                    field: contact_pair_counts.get(field, 0) for field in CONTACT_FIELDS
                },
                "exact_pairs": len(exact_pairs),
                "firms_with_multiple_candidate_ciks": sum(
                    len(ciks) > 1 for ciks in firms_to_ciks.values()
                ),
                "form_d_ciks_with_multiple_candidate_firms": sum(
                    len(firms) > 1 for firms in ciks_to_firms.values()
                ),
                "fuzzy_only_pairs": len(rows) - len(exact_pairs),
                "max_candidate_ciks_per_firm": max(map(len, firms_to_ciks.values()), default=0),
                "max_candidate_firms_per_cik": max(map(len, ciks_to_firms.values()), default=0),
                "routes": {route: route_counts.get(route, 0) for route in ROUTE_ORDER},
            },
            "covariates_ready": False,
            "decision_contract": {
                "decision": "candidate_unreviewed",
                "same_legal_entity": "unknown",
            },
            "exclusion_eligible": False,
            "exclusion_recall": "unknown",
            "identity_accepted": False,
            "identity_only": True,
            "inputs": {
                "broad_issuer_universe": _input_record(
                    broad_path,
                    sha256=broad_product["sha256"],
                    size_bytes=broad_product["size_bytes"],
                    row_count=broad_product["row_count"],
                ),
                "control_manifest": _input_record(
                    control_manifest_path,
                    sha256=_sha256_bytes(control_data),
                    size_bytes=len(control_data),
                ),
                "crosswalk_manifest": _input_record(
                    crosswalk_manifest_path,
                    sha256=_sha256_bytes(crosswalk_data),
                    size_bytes=len(crosswalk_data),
                ),
                "exact_candidate_edges": _input_record(
                    edge_path,
                    sha256=edge_product["sha256"],
                    size_bytes=edge_product["size_bytes"],
                    row_count=edge_product["row_count"],
                ),
                "firm_identity_ledger": _input_record(
                    ledger_path,
                    sha256=ledger_product["sha256"],
                    size_bytes=ledger_product["size_bytes"],
                    row_count=ledger_product["row_count"],
                ),
                "sbir_awards_csv": _input_record(
                    awards_path,
                    sha256=award_product["sha256"],
                    size_bytes=award_product["size_bytes"],
                    row_count=award_product["row_count"],
                ),
            },
            "invariants": {
                "all_candidates_atomic_by_sbir_firm_and_cik": True,
                "all_candidates_unreviewed": all(
                    row["decision"] == "candidate_unreviewed" for row in rows
                ),
                "all_downstream_gates_closed": all(
                    not row[gate]
                    for row in rows
                    for gate in (
                        "identity_accepted",
                        "exclusion_eligible",
                        "covariates_ready",
                        "matching_eligible",
                        "rate_eligible",
                    )
                ),
                "all_routes_have_traceable_evidence": all(
                    set(row["candidate_routes"]) == set(row["route_evidence"]) for row in rows
                ),
                "broad_form_d_evidence_cik_local": True,
                "contact_evidence_never_generates_pairs": True,
                "exact_phase1_pairs_preserved": emitted_exact == exact_pairs,
                "no_forbidden_output_fields": not any(_contains_forbidden_key(row) for row in rows),
                "source_records_reconcile_to_phase1_ledger": True,
            },
            "matching_eligible": False,
            "outputs": {"identity_candidates": product_out},
            "parameters": {
                "candidate_contract": CANDIDATE_CONTRACT,
                "contact_normalizers": {
                    "city": "alphanumeric-key-v1",
                    "phone10": "us-phone10-v1",
                    "state": GEOGRAPHY_PROFILE.value,
                    "street1": "alphanumeric-key-v1",
                    "zip5": "strict-zip5-v1",
                },
                "fuzzy_minimum_alphanumeric_length": MINIMUM_FUZZY_NAME_LENGTH,
                "name_metrics": [
                    CompanyNameMetric.RATIO.value,
                    CompanyNameMetric.TOKEN_SORT.value,
                    CompanyNameMetric.TOKEN_SET.value,
                ],
                "name_normalizer": NORMALIZER.value,
                "prefix_length": PREFIX_LENGTH,
                "retrieval_is_exhaustive_within_declared_rules": True,
                "similarity_backend": {
                    "name": SIMILARITY_BACKEND,
                    "version": SIMILARITY_BACKEND_VERSION,
                },
                "routes": {
                    "state_supported": {
                        "same_prefix": True,
                        "strict_state_intersection": True,
                        "threshold": STATE_SUPPORTED_THRESHOLD,
                    },
                    "strong_name": {
                        "same_prefix": True,
                        "threshold": STRONG_NAME_THRESHOLD,
                    },
                    "zip_supported": {
                        "strict_zip5_intersection": True,
                        "threshold": ZIP_SUPPORTED_THRESHOLD,
                    },
                },
            },
            "producer": {
                "code_commit": code_version,
                "path": str(producer_path.relative_to(REPO_ROOT)),
                "sha256": producer_sha,
                "size_bytes": producer_size,
            },
            "rate_eligible": False,
            "ready_for_matching": False,
            "schema_version": MANIFEST_SCHEMA_VERSION,
            "source_validation": {
                "form_d_filing_rows": broad_metadata["filing_rows_validated"],
                "form_d_issuer_rows": broad_metadata["row_count"],
                "sbir_award_rows": len(source_index),
            },
        }
        _write_manifest(staging, manifest)
        _publish_release(staging, output_dir)
        return manifest
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--crosswalk-manifest", type=Path, default=DEFAULT_CROSSWALK_MANIFEST)
    parser.add_argument("--crosswalk-manifest-sha256", required=True)
    parser.add_argument("--control-manifest", type=Path, default=DEFAULT_CONTROL_MANIFEST)
    parser.add_argument("--control-manifest-sha256", required=True)
    parser.add_argument("--awards-csv", type=Path, default=DEFAULT_AWARDS_CSV)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--code-version", required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        manifest = build(parse_args(argv))
    except BuildError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"counts": manifest["counts"], "outputs": manifest["outputs"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
