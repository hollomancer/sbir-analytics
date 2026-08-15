#!/usr/bin/env python3
"""Audit exact-name SBIR candidate CIKs against Form D filing-proxy evidence.

This producer is an identity/evidence audit only. It joins already-materialized
exact-name candidate CIKs to the symmetric Form D business-combination filing
proxy and emits no cohort classification, denominator, rate, or legal-event
claim.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import tempfile
from collections import Counter, defaultdict
from collections.abc import Iterator, Mapping
from datetime import date
from pathlib import Path
from typing import Any

from sbir_etl.identity import CompanyNameProfile, normalize_company_name


EVENT_TYPE = "form_d_business_combination_filing_proxy"
EVIDENCE_KIND = "proxy"
SOURCE = "sec_dera_form_d_quarterly_bulk"
SOURCE_START_DATE = date(2009, 1, 1)
SOURCE_END_DATE = date(2024, 12, 31)
OUTPUT_SCHEMA_VERSION = 1
NORMALIZER = CompanyNameProfile.ORGANIZATION_KEY_V1
MATERIALIZED_START_FY = 2010
MATERIALIZED_END_FY = 2024
BOUNDARY_FISCAL_YEARS = frozenset({2009, 2025})
SHA256_RE = re.compile(r"[0-9a-f]{64}")
CIK_RE = re.compile(r"[1-9][0-9]{0,9}")

AGENCY_TAG_BY_NAME = {
    "Department of Agriculture": "USDA",
    "Department of Commerce": "DOC",
    "Department of Defense": "DOD",
    "Department of Education": "ED",
    "Department of Energy": "DOE",
    "Department of Health and Human Services": "HHS",
    "Department of Homeland Security": "DHS",
    "Department of Transportation": "DOT",
    "Department of the Interior": "DOI",
    "Environmental Protection Agency": "EPA",
    "National Aeronautics and Space Administration": "NASA",
    "National Science Foundation": "NSF",
    "Nuclear Regulatory Commission": "NRC",
}
HEADLINE_AGENCIES = ("NSF", "DOE", "HHS", "DOD")


class AuditError(RuntimeError):
    """Raised when an input contract or audit invariant fails closed."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _positive_int(value: object, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise AuditError(f"{label} must be a positive integer")
    return value


def _non_negative_int(value: object, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise AuditError(f"{label} must be a non-negative integer")
    return value


def _required_text(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AuditError(f"{label} must be non-empty text")
    return value.strip()


def _canonical_cik(value: object, *, label: str) -> str:
    cik = _required_text(value, label=label)
    if CIK_RE.fullmatch(cik) is None:
        raise AuditError(f"{label} is not a canonical CIK")
    return cik


def _mapping(value: object, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise AuditError(f"{label} must be a JSON object")
    return value


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise AuditError(f"duplicate JSON key {key!r}")
        value[key] = item
    return value


def _reject_nonstandard_constant(value: str) -> None:
    raise AuditError(f"non-standard JSON constant {value!r}")


def _loads_json(value: str | bytes, *, label: str) -> Any:
    try:
        return json.loads(
            value,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_nonstandard_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, AuditError) as exc:
        raise AuditError(f"Invalid JSON in {label}: {exc}") from exc


def _load_manifest(path: Path, *, label: str) -> tuple[dict[str, Any], dict[str, Any]]:
    if not path.is_file() or path.is_symlink():
        raise AuditError(f"Required {label} is missing or not a regular file: {path}")
    data = path.read_bytes()
    value = _loads_json(data, label=f"{label} {path}")
    if not isinstance(value, dict):
        raise AuditError(f"{label} must contain a JSON object")
    return value, {
        "path": path.name,
        "sha256": hashlib.sha256(data).hexdigest(),
        "size_bytes": len(data),
    }


def _product_reference(value: object, *, label: str) -> dict[str, Any]:
    product = _mapping(value, label=label)
    path = _required_text(product.get("path"), label=f"{label}.path")
    sha = _required_text(product.get("sha256"), label=f"{label}.sha256")
    if SHA256_RE.fullmatch(sha) is None:
        raise AuditError(f"{label}.sha256 is invalid")
    return {
        "path": path,
        "row_count": _positive_int(product.get("row_count"), label=f"{label}.row_count"),
        "sha256": sha,
        "size_bytes": _positive_int(product.get("size_bytes"), label=f"{label}.size_bytes"),
    }


def _verify_product(path: Path, reference: Mapping[str, Any], *, label: str) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise AuditError(f"Required {label} is missing or not a regular file: {path}")
    if path.name != reference["path"]:
        raise AuditError(f"{label} filename does not match its manifest")
    size = path.stat().st_size
    if size != reference["size_bytes"]:
        raise AuditError(f"{label} byte size does not match its manifest")
    sha = _sha256(path)
    if sha != reference["sha256"]:
        raise AuditError(f"{label} SHA-256 does not match its manifest")
    return {
        "path": path.name,
        "row_count": reference["row_count"],
        "sha256": sha,
        "size_bytes": size,
    }


def _iter_jsonl(path: Path, *, label: str) -> Iterator[tuple[int, Mapping[str, Any]]]:
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                raise AuditError(f"{label} line {line_number} is blank")
            value = _loads_json(line, label=f"{label} line {line_number}")
            yield line_number, _mapping(value, label=f"{label} line {line_number}")


def _validate_manifests(
    control: Mapping[str, Any],
    control_meta: Mapping[str, Any],
    proxy: Mapping[str, Any],
) -> tuple[
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    dict[str, int],
]:
    if control.get("complete") is not True or control.get("schema_version") != 1:
        raise AuditError("Control manifest is not a complete schema-v1 materialization")
    if control.get("complete_sbir_exclusion") is not False:
        raise AuditError("Control manifest must preserve complete_sbir_exclusion=false")
    if control.get("exclusion_recall") != "unknown":
        raise AuditError("Control manifest must preserve exclusion_recall=unknown")
    control_outputs = _mapping(control.get("outputs"), label="control outputs")
    candidate_ref = _product_reference(
        control_outputs.get("candidate_sbir_cik_exclusions"),
        label="candidate-exclusion product",
    )
    exclusion = _mapping(control.get("exclusion"), label="control exclusion metadata")
    awards_ref = _product_reference(exclusion.get("awards_csv"), label="control awards snapshot")
    exact_match = _mapping(exclusion.get("exact_match"), label="control exact-match metadata")
    identity_contract = {
        "candidate_cik_count": _positive_int(
            exact_match.get("candidate_cik_count"), label="candidate CIK count"
        ),
        "matched_normalized_name_count": _positive_int(
            exact_match.get("matched_normalized_name_count"),
            label="matched normalized-name count",
        ),
        "ambiguous_normalized_name_count": _non_negative_int(
            exact_match.get("normalized_names_mapping_to_multiple_ciks"),
            label="ambiguous normalized-name count",
        ),
    }
    if exact_match.get("normalizer_version") != NORMALIZER.value:
        raise AuditError("Control manifest exact-name metadata uses an unexpected normalizer")
    if identity_contract["candidate_cik_count"] != candidate_ref["row_count"]:
        raise AuditError("Control manifest candidate CIK counts do not reconcile")
    broad_ref = _product_reference(
        control_outputs.get("broad_issuer_universe"), label="broad issuer-universe product"
    )

    if proxy.get("complete") is not True or proxy.get("schema_version") != 1:
        raise AuditError("Proxy manifest is not a complete schema-v1 materialization")
    if proxy.get("event_type") != EVENT_TYPE:
        raise AuditError("Proxy manifest has an unexpected event type")
    proxy_inputs = _mapping(proxy.get("inputs"), label="proxy inputs")
    proxy_input = _mapping(
        proxy_inputs.get("source_manifest"),
        label="proxy source-manifest input",
    )
    if proxy_input.get("path") != control_meta["path"]:
        raise AuditError("Proxy manifest does not pin the supplied control-manifest filename")
    if proxy_input.get("sha256") != control_meta["sha256"]:
        raise AuditError("Proxy manifest does not pin the supplied control-manifest bytes")
    if proxy_input.get("size_bytes") != control_meta["size_bytes"]:
        raise AuditError("Proxy manifest control-manifest byte size is inconsistent")
    proxy_issuer_ref = _product_reference(
        proxy_inputs.get("issuer_universe"), label="proxy issuer-universe input"
    )
    if proxy_issuer_ref != broad_ref:
        raise AuditError("Proxy manifest issuer-universe pin does not match the control manifest")
    proxy_source = _mapping(proxy.get("source"), label="proxy source")
    expected_source = {
        "coverage_start_date": SOURCE_START_DATE.isoformat(),
        "coverage_end_date": SOURCE_END_DATE.isoformat(),
        "source_snapshot_date": SOURCE_END_DATE.isoformat(),
        "source": SOURCE,
        "source_complete": True,
    }
    for key, expected in expected_source.items():
        if proxy_source.get(key) != expected:
            raise AuditError(f"Proxy manifest has unexpected source field {key}")
    source_snapshot_id = _required_text(
        proxy_source.get("source_snapshot_id"), label="proxy source_snapshot_id"
    )
    expected_snapshot_id = f"form_d_control_universe_manifest_sha256:{control_meta['sha256']}"
    if source_snapshot_id != expected_snapshot_id:
        raise AuditError("Proxy source snapshot does not identify the supplied control manifest")
    proxy_outputs = _mapping(proxy.get("outputs"), label="proxy outputs")
    event_ref = _product_reference(proxy_outputs.get("events"), label="proxy-event product")
    coverage_ref = _product_reference(proxy_outputs.get("coverage"), label="coverage product")
    proxy_counters = _mapping(proxy.get("counters"), label="proxy counters")
    if proxy_counters.get("event_rows") != event_ref["row_count"]:
        raise AuditError("Proxy manifest event rows do not reconcile")
    if proxy_counters.get("coverage_rows") != coverage_ref["row_count"]:
        raise AuditError("Proxy manifest coverage rows do not reconcile")
    return candidate_ref, event_ref, coverage_ref, awards_ref, identity_contract


def _load_candidates(
    path: Path,
    *,
    expected_rows: int,
    identity_contract: Mapping[str, int],
) -> dict[str, dict[str, Any]]:
    candidates: dict[str, dict[str, Any]] = {}
    ciks_by_name: dict[str, set[str]] = defaultdict(set)
    claimed_counts_by_name: dict[str, set[int]] = defaultdict(set)
    row_count = 0
    for line_number, row in _iter_jsonl(path, label="candidate-exclusion product"):
        row_count += 1
        if row.get("schema_version") != 1 or row.get("candidate_exclusion") is not True:
            raise AuditError(f"Candidate line {line_number} has an unexpected schema or status")
        cik = _canonical_cik(row.get("cik"), label=f"Candidate line {line_number} CIK")
        if row.get("firm_key") != f"form_d_cik:{cik}":
            raise AuditError(f"Candidate line {line_number} has a noncanonical firm key")
        if cik in candidates:
            raise AuditError(f"Candidate CIK {cik} occurs more than once")
        evidence = row.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            raise AuditError(f"Candidate line {line_number} has no identity evidence")
        exact_evidence: list[Mapping[str, Any]] = []
        for index, item in enumerate(evidence):
            item_map = _mapping(item, label=f"Candidate line {line_number} evidence {index}")
            if item_map.get("resolution_method") != "candidate_exact_normalized_name":
                continue
            if item_map.get("normalizer_version") != NORMALIZER.value:
                raise AuditError(f"Candidate line {line_number} uses an unexpected normalizer")
            normalized_name = _required_text(
                item_map.get("normalized_name"),
                label=f"Candidate line {line_number} normalized_name",
            )
            issuer_count = _positive_int(
                item_map.get("issuer_cik_count_for_normalized_name"),
                label=f"Candidate line {line_number} issuer-CIK count",
            )
            exact_evidence.append(
                {"normalized_name": normalized_name, "issuer_cik_count": issuer_count}
            )
        if not exact_evidence:
            raise AuditError(f"Candidate line {line_number} has no exact-name evidence route")
        names = sorted({str(item["normalized_name"]) for item in exact_evidence})
        for item in exact_evidence:
            normalized_name = str(item["normalized_name"])
            ciks_by_name[normalized_name].add(cik)
            claimed_counts_by_name[normalized_name].add(int(item["issuer_cik_count"]))
        candidates[cik] = {
            "cik": cik,
            "firm_key": f"form_d_cik:{cik}",
            "matched_normalized_names": names,
        }
    if row_count != expected_rows:
        raise AuditError("Candidate-exclusion JSONL row count does not match its manifest")
    for name, ciks in ciks_by_name.items():
        if claimed_counts_by_name[name] != {len(ciks)}:
            raise AuditError(f"Exact-name evidence has an inconsistent issuer-CIK count for {name}")
    ambiguous_names = sum(len(ciks) > 1 for ciks in ciks_by_name.values())
    if len(candidates) != identity_contract["candidate_cik_count"]:
        raise AuditError("Physical candidate CIK count does not reconcile")
    if len(ciks_by_name) != identity_contract["matched_normalized_name_count"]:
        raise AuditError("Physical normalized-name count does not reconcile")
    if ambiguous_names != identity_contract["ambiguous_normalized_name_count"]:
        raise AuditError("Physical ambiguous-name count does not reconcile")
    for candidate in candidates.values():
        candidate["mapping_class"] = (
            "unique_within_materialized_name_map"
            if any(len(ciks_by_name[name]) == 1 for name in candidate["matched_normalized_names"])
            else "ambiguous_name_only"
        )
    return candidates


def _load_agency_tags(
    path: Path,
    *,
    expected_rows: int,
    candidates: Mapping[str, Mapping[str, Any]],
) -> dict[str, list[str]]:
    relevant_names = {
        name for candidate in candidates.values() for name in candidate["matched_normalized_names"]
    }
    tags_by_name: dict[str, set[str]] = defaultdict(set)
    row_count = 0
    with path.open(encoding="utf-8-sig", errors="strict", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = {str(field).lower(): str(field) for field in (reader.fieldnames or [])}
        company_column = fields.get("company") or fields.get("company_name")
        agency_column = fields.get("agency")
        if company_column is None or agency_column is None:
            raise AuditError("Awards CSV must contain Company and Agency columns")
        for row in reader:
            row_count += 1
            normalized = normalize_company_name(
                str(row.get(company_column) or "").strip(), profile=NORMALIZER
            )
            if not normalized or normalized not in relevant_names:
                continue
            agency_name = str(row.get(agency_column) or "").strip()
            tag = AGENCY_TAG_BY_NAME.get(agency_name)
            if tag is None:
                raise AuditError(f"Matched award name has an unknown agency label: {agency_name!r}")
            tags_by_name[normalized].add(tag)
    if row_count != expected_rows:
        raise AuditError("Awards CSV row count does not match the control manifest")
    missing_names = sorted(relevant_names - set(tags_by_name))
    if missing_names:
        raise AuditError("Exact-name evidence is absent from the pinned awards snapshot")
    tags_by_cik: dict[str, list[str]] = {}
    for cik, candidate in candidates.items():
        tags = sorted(
            {tag for name in candidate["matched_normalized_names"] for tag in tags_by_name[name]}
        )
        if not tags:
            raise AuditError(f"Candidate CIK {cik} has no agency tag")
        tags_by_cik[cik] = tags
    return tags_by_cik


def _validate_coverage(
    path: Path,
    *,
    expected_rows: int,
    candidates: Mapping[str, Mapping[str, Any]],
    source_snapshot_id: str,
) -> None:
    firm_keys: set[str] = set()
    row_count = 0
    for line_number, row in _iter_jsonl(path, label="coverage product"):
        row_count += 1
        firm_key = _required_text(row.get("firm_key"), label=f"Coverage line {line_number} key")
        if not firm_key.startswith("form_d_cik:"):
            raise AuditError(f"Coverage line {line_number} has a noncanonical firm key")
        cik = _canonical_cik(
            firm_key.removeprefix("form_d_cik:"), label=f"Coverage line {line_number} CIK"
        )
        if firm_key != f"form_d_cik:{cik}" or firm_key in firm_keys:
            raise AuditError(f"Coverage line {line_number} has a duplicate/noncanonical key")
        firm_keys.add(firm_key)
        expected = {
            "schema_version": 1,
            "metric": EVENT_TYPE,
            "source": SOURCE,
            "source_complete": True,
            "coverage_start_date": SOURCE_START_DATE.isoformat(),
            "coverage_end_date": SOURCE_END_DATE.isoformat(),
            "source_snapshot_date": SOURCE_END_DATE.isoformat(),
            "source_snapshot_id": source_snapshot_id,
        }
        if any(row.get(key) != value for key, value in expected.items()):
            raise AuditError(f"Coverage line {line_number} violates the proxy coverage contract")
    if row_count != expected_rows:
        raise AuditError("Coverage JSONL row count does not match its manifest")
    missing = sorted(
        candidate["firm_key"]
        for candidate in candidates.values()
        if candidate["firm_key"] not in firm_keys
    )
    if missing:
        raise AuditError("At least one exact-name candidate CIK lacks proxy coverage")


def federal_fiscal_year(value: date) -> int:
    """Return the U.S. federal fiscal year containing ``value``."""

    return value.year + (1 if value.month >= 10 else 0)


def _validated_event(
    row: Mapping[str, Any], *, line_number: int, source_snapshot_id: str
) -> tuple[str, str, date]:
    if row.get("schema_version") != 1:
        raise AuditError(f"Event line {line_number} has an unexpected schema version")
    firm_key = _required_text(row.get("firm_key"), label=f"Event line {line_number} firm_key")
    if not firm_key.startswith("form_d_cik:"):
        raise AuditError(f"Event line {line_number} has a noncanonical firm key")
    cik = _canonical_cik(
        firm_key.removeprefix("form_d_cik:"), label=f"Event line {line_number} CIK"
    )
    if firm_key != f"form_d_cik:{cik}":
        raise AuditError(f"Event line {line_number} has a noncanonical firm key")
    accession = _required_text(
        row.get("accession_number"), label=f"Event line {line_number} accession"
    )
    expected = {
        "event_id": f"form_d_accession:{accession}",
        "event_type": EVENT_TYPE,
        "evidence_kind": EVIDENCE_KIND,
        "source": SOURCE,
        "source_snapshot_id": source_snapshot_id,
        "date_basis": "filing_date",
    }
    if any(row.get(key) != value for key, value in expected.items()):
        raise AuditError(f"Event line {line_number} violates the proxy event contract")
    filing_date_text = _required_text(
        row.get("filing_date"), label=f"Event line {line_number} filing_date"
    )
    if row.get("event_date") != filing_date_text:
        raise AuditError(f"Event line {line_number} event_date is not its filing_date")
    try:
        filing_date = date.fromisoformat(filing_date_text)
    except ValueError as exc:
        raise AuditError(f"Event line {line_number} has an invalid filing_date") from exc
    if filing_date.isoformat() != filing_date_text:
        raise AuditError(f"Event line {line_number} filing_date is not exact ISO YYYY-MM-DD")
    if not SOURCE_START_DATE <= filing_date <= SOURCE_END_DATE:
        raise AuditError(f"Event line {line_number} falls outside source coverage")
    source_quarter = _required_text(
        row.get("source_quarter"), label=f"Event line {line_number} source_quarter"
    )
    expected_quarter = f"{filing_date.year}Q{((filing_date.month - 1) // 3) + 1}"
    if source_quarter != expected_quarter:
        raise AuditError(f"Event line {line_number} has an inconsistent source quarter")
    submission_type = row.get("submission_type")
    is_amendment = row.get("is_amendment")
    if submission_type not in {"D", "D/A"} or not isinstance(is_amendment, bool):
        raise AuditError(f"Event line {line_number} has invalid filing lineage")
    if (submission_type == "D/A") is not is_amendment:
        raise AuditError(f"Event line {line_number} submission/amendment fields disagree")
    previous = row.get("previous_accession_number")
    if previous is not None and not isinstance(previous, str):
        raise AuditError(f"Event line {line_number} has invalid prior-accession lineage")
    return cik, accession, filing_date


def _audit_events(
    path: Path,
    *,
    expected_rows: int,
    candidates: Mapping[str, Mapping[str, Any]],
    agency_tags: Mapping[str, list[str]],
    source_snapshot_id: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    output_rows: list[dict[str, Any]] = []
    seen_accessions: set[str] = set()
    seen_event_ids: set[str] = set()
    full_join_ciks: set[str] = set()
    boundary_filings: Counter[int] = Counter()
    boundary_ciks: dict[int, set[str]] = defaultdict(set)
    row_count = 0
    for line_number, row in _iter_jsonl(path, label="proxy-event product"):
        row_count += 1
        cik, accession, filing_date = _validated_event(
            row, line_number=line_number, source_snapshot_id=source_snapshot_id
        )
        event_id = str(row["event_id"])
        if accession in seen_accessions or event_id in seen_event_ids:
            raise AuditError("Proxy-event accessions and event IDs must be globally unique")
        seen_accessions.add(accession)
        seen_event_ids.add(event_id)
        candidate = candidates.get(cik)
        if candidate is None:
            continue
        full_join_ciks.add(cik)
        fiscal_year = federal_fiscal_year(filing_date)
        if fiscal_year in BOUNDARY_FISCAL_YEARS:
            boundary_filings[fiscal_year] += 1
            boundary_ciks[fiscal_year].add(cik)
            continue
        if not MATERIALIZED_START_FY <= fiscal_year <= MATERIALIZED_END_FY:
            raise AuditError(
                "Joined event falls outside complete or declared boundary fiscal years"
            )
        previous = row.get("previous_accession_number")
        output_rows.append(
            {
                "accession_number": accession,
                "agency_tags": agency_tags[cik],
                "audit_record_id": "sbir_form_d_proxy_audit:"
                + hashlib.sha256(f"exact-cik|{accession}".encode()).hexdigest(),
                "cik": cik,
                "date_basis": "filing_date",
                "event_date": filing_date.isoformat(),
                "event_id": event_id,
                "event_type": EVENT_TYPE,
                "evidence_kind": EVIDENCE_KIND,
                "filing_date": filing_date.isoformat(),
                "filing_fiscal_year": fiscal_year,
                "firm_key": candidate["firm_key"],
                "identity_evidence_class": candidate["mapping_class"],
                "is_amendment": row["is_amendment"],
                "matched_normalized_names": candidate["matched_normalized_names"],
                "previous_accession_number": previous.strip()
                if isinstance(previous, str) and previous.strip()
                else None,
                "schema_version": OUTPUT_SCHEMA_VERSION,
                "source": SOURCE,
                "source_quarter": row["source_quarter"],
                "source_snapshot_id": source_snapshot_id,
                "submission_type": row["submission_type"],
            }
        )
    if row_count != expected_rows:
        raise AuditError("Proxy-event JSONL row count does not match its manifest")
    output_rows.sort(key=lambda item: (item["filing_date"], item["accession_number"]))
    diagnostics = {
        "full_source_join": {
            "proxy_filings": len(output_rows) + sum(boundary_filings.values()),
            "proxy_bearing_ciks": len(full_join_ciks),
        },
        "incomplete_boundary_fiscal_years": {
            str(fy): {
                "proxy_filings": boundary_filings[fy],
                "proxy_bearing_ciks": len(boundary_ciks[fy]),
            }
            for fy in sorted(BOUNDARY_FISCAL_YEARS)
        },
    }
    return output_rows, diagnostics


def _counts(rows: list[dict[str, Any]], diagnostics: Mapping[str, Any]) -> dict[str, Any]:
    ciks = {str(row["cik"]) for row in rows}
    fiscal_years: dict[str, dict[str, Any]] = {}
    for fiscal_year in range(MATERIALIZED_START_FY, MATERIALIZED_END_FY + 1):
        fy_rows = [row for row in rows if row["filing_fiscal_year"] == fiscal_year]
        fiscal_years[str(fiscal_year)] = {
            "proxy_filings": len(fy_rows),
            "proxy_bearing_ciks": len({str(row["cik"]) for row in fy_rows}),
        }
    mapping_classes: dict[str, dict[str, Any]] = {}
    for mapping_class in (
        "unique_within_materialized_name_map",
        "ambiguous_name_only",
    ):
        selected = [row for row in rows if row["identity_evidence_class"] == mapping_class]
        mapping_classes[mapping_class] = {
            "proxy_filings": len(selected),
            "proxy_bearing_ciks": len({str(row["cik"]) for row in selected}),
        }
    agency_membership: dict[str, dict[str, Any]] = {}
    for agency in sorted({tag for row in rows for tag in row["agency_tags"]}):
        selected = [row for row in rows if agency in row["agency_tags"]]
        agency_membership[agency] = {
            "proxy_filings": len(selected),
            "proxy_bearing_ciks": len({str(row["cik"]) for row in selected}),
        }
    return {
        "candidate_ciks": None,
        "complete_filing_fiscal_year_window": {
            "end_fy": MATERIALIZED_END_FY,
            "proxy_filings": len(rows),
            "proxy_bearing_ciks": len(ciks),
            "start_fy": MATERIALIZED_START_FY,
        },
        "filing_fiscal_years": fiscal_years,
        "identity_evidence_classes": mapping_classes,
        "agency_membership_nonexclusive": agency_membership,
        "submission_types": dict(
            sorted(Counter(str(row["submission_type"]) for row in rows).items())
        ),
        "amendment_proxy_filings": sum(bool(row["is_amendment"]) for row in rows),
        **diagnostics,
    }


def _write_jsonl_product(
    output_dir: Path,
    rows: list[dict[str, Any]],
    *,
    forbidden_paths: set[Path],
) -> tuple[dict[str, Any], Path, bool]:
    output_dir.mkdir(parents=True, exist_ok=True)
    if not output_dir.is_dir() or output_dir.is_symlink():
        raise AuditError("Output directory must be a real directory")
    digest = hashlib.sha256()
    size_bytes = 0
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=output_dir, prefix=".sbir-form-d-proxy-audit.", delete=False
        ) as handle:
            temp_path = Path(handle.name)
            for row in rows:
                data = (
                    json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
                    + "\n"
                ).encode("utf-8")
                handle.write(data)
                digest.update(data)
                size_bytes += len(data)
        sha = digest.hexdigest()
        destination = output_dir / f"sbir_form_d_proxy_audit.{sha}.jsonl"
        if destination.resolve() in forbidden_paths:
            raise AuditError("Content-addressed output must not alias an input or manifest")
        destination_preexisted = destination.exists()
        if destination_preexisted and (not destination.is_file() or destination.is_symlink()):
            raise AuditError("Content-addressed output target must be a regular file or absent")
        os.replace(temp_path, destination)
        temp_path = None
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
    return (
        {
            "path": destination.name,
            "row_count": len(rows),
            "sha256": sha,
            "size_bytes": size_bytes,
        },
        destination,
        destination_preexisted,
    )


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and (path.is_symlink() or not path.is_file()):
        raise AuditError("Audit manifest target must be a regular file or absent")
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=path.parent, prefix=f".{path.name}.", delete=False
        ) as handle:
            temp_path = Path(handle.name)
            handle.write(data)
        os.replace(temp_path, path)
        temp_path = None
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def build(args: argparse.Namespace) -> dict[str, Any]:
    """Validate pinned inputs, perform the exact-CIK join, and publish the audit."""

    code_version = _required_text(args.code_version, label="code-version")
    input_paths = [
        Path(args.control_manifest),
        Path(args.candidate_jsonl),
        Path(args.proxy_manifest),
        Path(args.event_jsonl),
        Path(args.coverage_jsonl),
        Path(args.awards_csv),
    ]
    audit_manifest_path = Path(args.audit_manifest)
    if audit_manifest_path.resolve() in {path.resolve() for path in input_paths}:
        raise AuditError("Audit manifest must not alias an input")

    control, control_meta = _load_manifest(input_paths[0], label="control manifest")
    proxy, proxy_meta = _load_manifest(input_paths[2], label="proxy manifest")
    candidate_ref, event_ref, coverage_ref, awards_ref, identity_contract = _validate_manifests(
        control, control_meta, proxy
    )
    candidate_meta = _verify_product(input_paths[1], candidate_ref, label="candidate product")
    event_meta = _verify_product(input_paths[3], event_ref, label="event product")
    coverage_meta = _verify_product(input_paths[4], coverage_ref, label="coverage product")
    awards_meta = _verify_product(input_paths[5], awards_ref, label="awards snapshot")

    candidates = _load_candidates(
        input_paths[1],
        expected_rows=candidate_ref["row_count"],
        identity_contract=identity_contract,
    )
    agency_tags = _load_agency_tags(
        input_paths[5], expected_rows=awards_ref["row_count"], candidates=candidates
    )
    proxy_source = _mapping(proxy["source"], label="proxy source")
    source_snapshot_id = str(proxy_source["source_snapshot_id"])
    _validate_coverage(
        input_paths[4],
        expected_rows=coverage_ref["row_count"],
        candidates=candidates,
        source_snapshot_id=source_snapshot_id,
    )
    rows, diagnostics = _audit_events(
        input_paths[3],
        expected_rows=event_ref["row_count"],
        candidates=candidates,
        agency_tags=agency_tags,
        source_snapshot_id=source_snapshot_id,
    )
    counts = _counts(rows, diagnostics)
    counts["candidate_ciks"] = len(candidates)
    product, product_path, product_preexisted = _write_jsonl_product(
        Path(args.output_dir),
        rows,
        forbidden_paths={path.resolve() for path in [*input_paths, audit_manifest_path]},
    )

    invariants = {
        "agency_tags_nonempty_and_sorted": all(
            row["agency_tags"] and row["agency_tags"] == sorted(set(row["agency_tags"]))
            for row in rows
        ),
        "candidate_ciks_have_complete_proxy_coverage": True,
        "complete_fiscal_years_only": all(
            MATERIALIZED_START_FY <= row["filing_fiscal_year"] <= MATERIALIZED_END_FY
            for row in rows
        ),
        "content_addressed_output": product["path"]
        == f"sbir_form_d_proxy_audit.{product['sha256']}.jsonl",
        "exact_cik_join_only": True,
        "identity_classes_exhaustive_and_exclusive": sum(
            item["proxy_filings"] for item in counts["identity_evidence_classes"].values()
        )
        == len(rows),
        "input_hash_rows_bytes_verified": True,
        "one_row_per_unique_accession": len({row["accession_number"] for row in rows}) == len(rows),
        "per_fiscal_year_filings_reconcile": sum(
            item["proxy_filings"] for item in counts["filing_fiscal_years"].values()
        )
        == len(rows),
    }
    try:
        if not all(invariants.values()):
            raise AuditError(f"Audit invariant failed: {invariants}")

        manifest = {
            "caveats": [
                "Exact-name candidate identities are not verified SBIR identities.",
                "Exact-name identity recall is unknown.",
                "The event is a filer-supplied Form D filing proxy, not a verified legal event.",
                "Filing dates are evidence dates and are not transaction or exit dates.",
                "Agency memberships overlap and must not be summed.",
                "No count in this audit is an outcome, prevalence, or match rate.",
            ],
            "code_commit": code_version,
            "complete": True,
            "complete_sbir_exclusion": False,
            "complete_sbir_identity": False,
            "counts": counts,
            "covariates_ready": False,
            "exclusion_recall": "unknown",
            "identity_status": "exact_name_candidate",
            "inputs": {
                "awards_snapshot": awards_meta,
                "candidate_exclusions": candidate_meta,
                "control_manifest": control_meta,
                "proxy_coverage": coverage_meta,
                "proxy_events": event_meta,
                "proxy_manifest": proxy_meta,
            },
            "invariants": invariants,
            "outcome_kind": "filing_proxy",
            "outputs": {"filing_evidence_audit": product},
            "ready_for_matching": False,
            "schema_version": OUTPUT_SCHEMA_VERSION,
            "source": {
                "coverage_end_date": SOURCE_END_DATE.isoformat(),
                "coverage_start_date": SOURCE_START_DATE.isoformat(),
                "date_basis": "filing_date",
                "event_type": EVENT_TYPE,
                "source": SOURCE,
                "source_snapshot_id": source_snapshot_id,
            },
            "verified_ma": False,
            "window": {
                "complete_filing_fiscal_years": list(
                    range(MATERIALIZED_START_FY, MATERIALIZED_END_FY + 1)
                ),
                "excluded_incomplete_boundary_fiscal_years": sorted(BOUNDARY_FISCAL_YEARS),
            },
        }
        manifest_data = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
        _atomic_write(audit_manifest_path, manifest_data)
    except Exception:
        if not product_preexisted:
            product_path.unlink(missing_ok=True)
        raise
    return manifest


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--control-manifest", type=Path, required=True)
    parser.add_argument("--candidate-jsonl", type=Path, required=True)
    parser.add_argument("--proxy-manifest", type=Path, required=True)
    parser.add_argument("--event-jsonl", type=Path, required=True)
    parser.add_argument("--coverage-jsonl", type=Path, required=True)
    parser.add_argument("--awards-csv", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--audit-manifest", type=Path, required=True)
    parser.add_argument("--code-version", required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        manifest = build(parse_args(argv))
    except AuditError as exc:
        print(f"error: {exc}")
        return 1
    print(json.dumps({"counts": manifest["counts"], "outputs": manifest["outputs"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
