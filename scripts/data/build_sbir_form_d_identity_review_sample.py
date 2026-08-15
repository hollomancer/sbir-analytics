#!/usr/bin/env python3
"""Build the private, route-masked SBIR↔Form D identity-review instrument.

The review packet exposes only neutral case IDs and frozen administrative
identity histories. A separate private case map retains routes and lineage.
This producer does not accept identity or publish human-review results.
"""

import argparse
import csv
import hashlib
import json
import os
import re
import sys
import tempfile
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
EPISTEMIC_TIER = "pipelines"

DEFAULT_CANDIDATE_MANIFEST = (
    REPO_ROOT / "data/processed/agency_private_capital/identity_candidates/"
    "sbir_form_d_identity_candidates.manifest.json"
)
DEFAULT_CROSSWALK_MANIFEST = (
    REPO_ROOT / "data/processed/agency_private_capital/identity_crosswalk/"
    "sbir_form_d_identity_crosswalk.manifest.json"
)
DEFAULT_CONTROL_MANIFEST = (
    REPO_ROOT / "data/processed/agency_private_capital/control_universe/"
    "form_d_control_universe.manifest.json"
)
DEFAULT_AWARDS_CSV = REPO_ROOT / "data/raw/sbir/award_data.csv"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "data/private/agency_private_capital/identity_review"

MANIFEST_SCHEMA_VERSION = 1
PACKET_SCHEMA_VERSION = 1
CASE_MAP_SCHEMA_VERSION = 1
PACKET_CONTRACT = "sbir-form-d-organizational-identity-review-packet-v1"
CASE_MAP_CONTRACT = "sbir-form-d-organizational-identity-review-case-map-v1"
CANDIDATE_CONTRACT = "sbir-form-d-identity-candidate-v2"
LEDGER_CONTRACT = "sbir-firm-identity-ledger-v1"
FIRM_ID_CONTRACT = "sbir-firm-id-v1"
EDGE_ID_CONTRACT = "sbir-form-d-edge-id-v1"
ESTIMAND = "same organization under frozen administrative evidence"
ROUTE_ORDER = (
    "exact_normalized_name",
    "strong_name",
    "state_supported",
    "zip_supported",
)
SAMPLE_PER_STRATUM = 100
TOTAL_SAMPLE_SIZE = SAMPLE_PER_STRATUM * len(ROUTE_ORDER)
SELECTION_RANK_DOMAIN = "sbir-form-d-review-selection-rank-v1"
POOL_ORDER_DOMAIN = "sbir-form-d-review-pool-order-v1"
SHA256_RE = re.compile(r"[0-9a-f]{64}")
GIT_COMMIT_RE = re.compile(r"[0-9a-f]{40}")
CIK_RE = re.compile(r"[1-9][0-9]{0,9}")

# These fragments are checked recursively against every packet key. Case IDs
# are the sole permitted IDs; all source IDs live only in the private map.
FORBIDDEN_PACKET_KEY_FRAGMENTS = (
    "accession",
    "amount",
    "award_title",
    "cik",
    "confidence",
    "duns",
    "edge_id",
    "email",
    "firm_id",
    "outcome",
    "people",
    "person",
    "route",
    "score",
    "similarity",
    "source_record",
    "uei",
    "website",
)


class BuildError(RuntimeError):
    """Raised when pinned evidence cannot support a review instrument."""


def _canonical_json(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


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
    expected = str(expected_sha256).strip().lower()
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


def _resolve_product(manifest_path: Path, product: Mapping[str, Any]) -> Path:
    resolved = manifest_path.parent / str(product["path"])
    if resolved.parent != manifest_path.parent:
        raise BuildError("Pinned product escapes its manifest directory")
    return resolved


def _require_closed_gates(manifest: Mapping[str, Any], *, label: str) -> None:
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


def _manifest_pin(value: object, *, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise BuildError(f"Candidate manifest does not pin {label}")
    sha256 = value.get("sha256")
    size_bytes = value.get("size_bytes")
    path = value.get("path")
    if not isinstance(path, str) or Path(path).name != path:
        raise BuildError(f"Candidate {label} pin has an unsafe path")
    if not isinstance(sha256, str) or not SHA256_RE.fullmatch(sha256):
        raise BuildError(f"Candidate {label} pin has an invalid SHA-256")
    _non_negative_int(size_bytes, label=f"Candidate {label} size_bytes")
    return dict(value)


def _load_prerequisites(args: argparse.Namespace) -> dict[str, Any]:
    candidate_path = Path(args.candidate_manifest)
    crosswalk_path = Path(args.crosswalk_manifest)
    control_path = Path(args.control_manifest)
    candidate, candidate_data = _read_manifest(
        candidate_path,
        expected_sha256=args.candidate_manifest_sha256,
        label="candidate",
    )
    crosswalk, crosswalk_data = _read_manifest(
        crosswalk_path,
        expected_sha256=args.crosswalk_manifest_sha256,
        label="crosswalk",
    )
    control, control_data = _read_manifest(
        control_path,
        expected_sha256=args.control_manifest_sha256,
        label="control",
    )
    for label, manifest in (
        ("Candidate", candidate),
        ("Crosswalk", crosswalk),
        ("Control", control),
    ):
        if manifest.get("schema_version") != 1 or manifest.get("complete") is not True:
            raise BuildError(f"{label} manifest is incomplete or unsupported")
        _require_closed_gates(manifest, label=label)
    for field in (
        "candidate_only",
        "identity_accepted",
        "exclusion_eligible",
        "matching_eligible",
        "rate_eligible",
    ):
        expected = field == "candidate_only"
        if candidate.get(field) is not expected:
            raise BuildError(f"Candidate manifest has unexpected {field}")
    decision = candidate.get("decision_contract")
    if not isinstance(decision, Mapping) or decision.get("decision") != "candidate_unreviewed":
        raise BuildError("Candidate manifest does not preserve unreviewed decisions")
    if decision.get("same_legal_entity") != "unknown":
        raise BuildError("Candidate manifest does not preserve unknown identity")

    candidate_inputs = candidate.get("inputs")
    candidate_outputs = candidate.get("outputs")
    crosswalk_outputs = crosswalk.get("outputs")
    control_outputs = control.get("outputs")
    if not isinstance(candidate_inputs, Mapping):
        raise BuildError("Candidate manifest lacks inputs")
    if not isinstance(candidate_outputs, Mapping):
        raise BuildError("Candidate manifest lacks outputs")
    if not isinstance(crosswalk_outputs, Mapping):
        raise BuildError("Crosswalk manifest lacks outputs")
    if not isinstance(control_outputs, Mapping):
        raise BuildError("A prerequisite manifest lacks inputs or outputs")
    candidate_product = _pinned_product(
        candidate_outputs.get("identity_candidates"), label="identity candidates"
    )
    candidate_parameters = candidate.get("parameters")
    if not isinstance(candidate_parameters, Mapping):
        raise BuildError("Candidate manifest lacks parameters")
    candidate_contract = candidate_parameters.get("candidate_contract")
    if candidate_contract != CANDIDATE_CONTRACT:
        raise BuildError("Candidate manifest has an unsupported candidate contract")
    candidate_crosswalk = _manifest_pin(
        candidate_inputs.get("crosswalk_manifest"), label="crosswalk manifest"
    )
    candidate_control = _manifest_pin(
        candidate_inputs.get("control_manifest"), label="control manifest"
    )
    if candidate_crosswalk["sha256"] != _sha256_bytes(crosswalk_data) or candidate_crosswalk[
        "size_bytes"
    ] != len(crosswalk_data):
        raise BuildError("Supplied crosswalk manifest disagrees with the candidate pin")
    if candidate_control["sha256"] != _sha256_bytes(control_data) or candidate_control[
        "size_bytes"
    ] != len(control_data):
        raise BuildError("Supplied control manifest disagrees with the candidate pin")

    ledger_product = _pinned_product(
        crosswalk_outputs.get("firm_identity_ledger"), label="firm identity ledger"
    )
    broad_product = _pinned_product(
        control_outputs.get("broad_issuer_universe"), label="broad issuer universe"
    )
    candidate_ledger = _pinned_product(
        candidate_inputs.get("firm_identity_ledger"), label="candidate firm ledger"
    )
    candidate_broad = _pinned_product(
        candidate_inputs.get("broad_issuer_universe"), label="candidate broad universe"
    )
    for field in ("row_count", "sha256", "size_bytes"):
        if ledger_product[field] != candidate_ledger[field]:
            raise BuildError("Firm-ledger pins disagree across manifests")
        if broad_product[field] != candidate_broad[field]:
            raise BuildError("Broad-universe pins disagree across manifests")

    crosswalk_inputs = crosswalk.get("inputs")
    exclusion = control.get("exclusion")
    if not isinstance(crosswalk_inputs, Mapping) or not isinstance(exclusion, Mapping):
        raise BuildError("Upstream manifests do not pin the award CSV")
    crosswalk_awards = _pinned_product(
        crosswalk_inputs.get("sbir_awards_csv"), label="crosswalk award CSV"
    )
    control_awards = _pinned_product(exclusion.get("awards_csv"), label="control award CSV")
    candidate_awards = _pinned_product(
        candidate_inputs.get("sbir_awards_csv"), label="candidate award CSV"
    )
    for field in ("row_count", "sha256", "size_bytes"):
        if not (crosswalk_awards[field] == control_awards[field] == candidate_awards[field]):
            raise BuildError("Award-CSV pins disagree across manifests")

    return {
        "award_product": candidate_awards,
        "broad_path": _resolve_product(control_path, broad_product),
        "broad_product": broad_product,
        "candidate_data": candidate_data,
        "candidate_manifest": candidate,
        "candidate_path": candidate_path,
        "candidate_product": candidate_product,
        "candidate_product_path": _resolve_product(candidate_path, candidate_product),
        "control_data": control_data,
        "control_path": control_path,
        "crosswalk_data": crosswalk_data,
        "crosswalk_path": crosswalk_path,
        "ledger_path": _resolve_product(crosswalk_path, ledger_product),
        "ledger_product": ledger_product,
    }


def _stable_jsonl_rows(
    path: Path, product: Mapping[str, Any], *, label: str
) -> Iterable[tuple[int, dict[str, Any]]]:
    if not path.is_file():
        raise BuildError(f"Pinned {label} is missing: {path}")
    before = path.stat()
    if before.st_size != product["size_bytes"]:
        raise BuildError(f"Pinned {label} byte count does not match its manifest")
    digest = hashlib.sha256()
    size = 0
    rows = 0
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
            rows += 1
            yield line_number, row
    after = path.stat()
    if (
        after.st_size != before.st_size
        or after.st_mtime_ns != before.st_mtime_ns
        or after.st_ino != before.st_ino
    ):
        raise BuildError(f"Pinned {label} changed while it was read")
    if rows != product["row_count"] or size != product["size_bytes"]:
        raise BuildError(f"Pinned {label} rows or bytes do not match its manifest")
    if digest.hexdigest() != product["sha256"]:
        raise BuildError(f"Pinned {label} SHA-256 does not match its manifest")


def _exclusive_stratum(routes: object, *, line_number: int) -> str:
    if (
        not isinstance(routes, list)
        or not routes
        or any(not isinstance(route, str) or route not in ROUTE_ORDER for route in routes)
        or routes != [route for route in ROUTE_ORDER if route in routes]
        or len(routes) != len(set(routes))
    ):
        raise BuildError(f"Candidate line {line_number} has invalid routes")
    return next(route for route in ROUTE_ORDER if route in routes)


def _edge_id(firm_id: str, cik: str) -> str:
    material = "\0".join((EDGE_ID_CONTRACT, firm_id, cik))
    return f"sbir_form_d_edge:{hashlib.sha256(material.encode()).hexdigest()}"


def _load_and_sample_candidates(
    path: Path,
    product: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    firm_degree: Counter[str] = Counter()
    cik_degree: Counter[str] = Counter()
    pairs: set[tuple[str, str]] = set()
    edge_ids: set[str] = set()
    for line_number, row in _stable_jsonl_rows(path, product, label="identity candidates"):
        firm_id = row.get("sbir_firm_id")
        cik = row.get("form_d_cik")
        edge_id = row.get("edge_id")
        if not isinstance(firm_id, str) or not firm_id.startswith("sbir_firm:"):
            raise BuildError(f"Candidate line {line_number} has an invalid firm ID")
        if not isinstance(cik, str) or not CIK_RE.fullmatch(cik):
            raise BuildError(f"Candidate line {line_number} has an invalid CIK")
        if row.get("edge_id_contract") != EDGE_ID_CONTRACT or edge_id != _edge_id(firm_id, cik):
            raise BuildError(f"Candidate line {line_number} has an invalid edge ID")
        pair = (firm_id, cik)
        if pair in pairs:
            raise BuildError("Candidate pairs must be unique")
        pairs.add(pair)
        if edge_id in edge_ids:
            raise BuildError("Candidate edge IDs must be unique")
        edge_ids.add(edge_id)
        if (
            row.get("schema_version") != 2
            or row.get("candidate_contract") != CANDIDATE_CONTRACT
            or row.get("candidate_only") is not True
            or row.get("decision") != "candidate_unreviewed"
            or row.get("same_legal_entity") is not None
        ):
            raise BuildError(f"Candidate line {line_number} has an unsupported decision contract")
        for gate in (
            "complete_sbir_exclusion",
            "covariates_ready",
            "exclusion_eligible",
            "identity_accepted",
            "matching_eligible",
            "rate_eligible",
        ):
            if row.get(gate) is not False:
                raise BuildError(f"Candidate line {line_number} unexpectedly opens {gate}")
        if row.get("exclusion_recall") != "unknown":
            raise BuildError(f"Candidate line {line_number} has known exclusion recall")
        component_status = row.get("component_status")
        if component_status not in {
            "identifier_consistent",
            "name_only",
            "quarantined_conflict",
        }:
            raise BuildError(f"Candidate line {line_number} has an invalid component status")
        stratum = _exclusive_stratum(row.get("candidate_routes"), line_number=line_number)
        sbir_sources = row.get("sbir_source_records")
        accessions = row.get("form_d_source_accessions")
        if (
            not isinstance(sbir_sources, list)
            or not sbir_sources
            or any(
                isinstance(value, bool) or not isinstance(value, int) or value < 1
                for value in sbir_sources
            )
            or sbir_sources != sorted(set(sbir_sources))
        ):
            raise BuildError(f"Candidate line {line_number} has invalid SBIR lineage")
        if (
            not isinstance(accessions, list)
            or not accessions
            or any(not isinstance(value, str) or not value.strip() for value in accessions)
            or accessions != sorted(set(accessions))
        ):
            raise BuildError(f"Candidate line {line_number} has invalid Form D lineage")
        candidates.append({**row, "_exclusive_stratum": stratum})
        firm_degree[firm_id] += 1
        cik_degree[cik] += 1

    manifest_count = product["row_count"]
    if len(candidates) != manifest_count:
        raise BuildError("Candidate rows do not reconcile to their product pin")

    population_counts: Counter[str] = Counter()
    eligible: dict[str, list[dict[str, Any]]] = {route: [] for route in ROUTE_ORDER}
    exclusion_reason_counts: Counter[str] = Counter()
    exclusion_union = 0
    either_fanout_pairs = 0
    for row in candidates:
        stratum = row["_exclusive_stratum"]
        population_counts[stratum] += 1
        reasons: list[str] = []
        if row["component_status"] == "quarantined_conflict":
            reasons.append("quarantined_conflict")
        firm_fanout = firm_degree[row["sbir_firm_id"]] > 1
        cik_fanout = cik_degree[row["form_d_cik"]] > 1
        if firm_fanout:
            reasons.append("firm_to_multiple_ciks")
        if cik_fanout:
            reasons.append("cik_to_multiple_firms")
        either_fanout_pairs += firm_fanout or cik_fanout
        exclusion_reason_counts.update(reasons)
        if reasons:
            exclusion_union += 1
            continue
        rank_material = "\0".join((SELECTION_RANK_DOMAIN, row["edge_id"]))
        row["_selection_rank_sha256"] = hashlib.sha256(rank_material.encode()).hexdigest()
        eligible[stratum].append(row)

    selected: list[dict[str, Any]] = []
    eligible_counts: dict[str, int] = {}
    for stratum in ROUTE_ORDER:
        pool = sorted(
            eligible[stratum],
            key=lambda row: (row["_selection_rank_sha256"], row["edge_id"]),
        )
        eligible_counts[stratum] = len(pool)
        if len(pool) < SAMPLE_PER_STRATUM:
            raise BuildError(
                f"Exclusive stratum {stratum} has {len(pool)} eligible cases; "
                f"{SAMPLE_PER_STRATUM} required"
            )
        selected.extend(pool[:SAMPLE_PER_STRATUM])

    for row in selected:
        rank_material = "\0".join((POOL_ORDER_DOMAIN, row["edge_id"]))
        row["_pool_order_rank_sha256"] = hashlib.sha256(rank_material.encode()).hexdigest()
    selected.sort(key=lambda row: (row["_pool_order_rank_sha256"], row["edge_id"]))
    for index, row in enumerate(selected, start=1):
        row["_case_id"] = f"case_{index:04d}"

    audit: dict[str, Any] = {
        "candidate_pairs": len(candidates),
        "eligible_pairs": sum(eligible_counts.values()),
        "eligible_pairs_by_exclusive_stratum": eligible_counts,
        "excluded_pairs": exclusion_union,
        "either_fanout_pairs": either_fanout_pairs,
        "exclusion_reason_pair_counts": {
            reason: exclusion_reason_counts.get(reason, 0)
            for reason in (
                "quarantined_conflict",
                "firm_to_multiple_ciks",
                "cik_to_multiple_firms",
            )
        },
        "population_pairs_by_exclusive_stratum": {
            route: population_counts.get(route, 0) for route in ROUTE_ORDER
        },
        "selected_pairs": len(selected),
        "selected_pairs_by_exclusive_stratum": dict.fromkeys(ROUTE_ORDER, SAMPLE_PER_STRATUM),
    }
    if audit["eligible_pairs"] + audit["excluded_pairs"] != audit["candidate_pairs"]:
        raise BuildError("Eligibility counts do not reconcile to the candidate universe")
    return selected, audit


def _load_selected_ledger(
    path: Path,
    product: Mapping[str, Any],
    *,
    selected_firms: set[str],
) -> tuple[dict[str, dict[str, Any]], dict[int, tuple[str, dict[str, Any]]]]:
    selected_rows: dict[str, dict[str, Any]] = {}
    selected_sources: dict[int, tuple[str, dict[str, Any]]] = {}
    previous_firm: str | None = None
    for line_number, row in _stable_jsonl_rows(path, product, label="firm identity ledger"):
        firm_id = row.get("sbir_firm_id")
        if not isinstance(firm_id, str) or not firm_id.startswith("sbir_firm:"):
            raise BuildError(f"Firm-ledger line {line_number} has an invalid firm ID")
        if previous_firm is not None and firm_id <= previous_firm:
            raise BuildError("Firm-ledger IDs must be unique and ordered")
        previous_firm = firm_id
        sources = row.get("source_records")
        if (
            row.get("schema_version") != 1
            or row.get("firm_id_contract") != FIRM_ID_CONTRACT
            or row.get("ledger_contract") != LEDGER_CONTRACT
            or not isinstance(sources, list)
            or not sources
            or row.get("source_record_count") != len(sources)
            or row.get("award_row_count") != len(sources)
        ):
            raise BuildError(f"Firm-ledger row {firm_id} has an unsupported contract")
        if firm_id not in selected_firms:
            continue
        for source in sources:
            if not isinstance(source, dict):
                raise BuildError(f"Selected ledger row {firm_id} has malformed lineage")
            source_record = source.get("source_record")
            if (
                isinstance(source_record, bool)
                or not isinstance(source_record, int)
                or source_record < 1
                or source_record in selected_sources
            ):
                raise BuildError(f"Selected ledger row {firm_id} has invalid source lineage")
            selected_sources[source_record] = (firm_id, source)
        selected_rows[firm_id] = row
    missing = selected_firms - set(selected_rows)
    if missing:
        raise BuildError(f"Firm ledger is missing {len(missing)} selected firms")
    return selected_rows, selected_sources


def _column(fieldnames: Sequence[str], *aliases: str) -> str | None:
    by_name = {field.strip().casefold(): field for field in fieldnames}
    return next(
        (by_name[alias.casefold()] for alias in aliases if alias.casefold() in by_name), None
    )


def _text(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def _date(value: object) -> str | None:
    text = _text(value)
    if text is None:
        return None
    if re.fullmatch(r"[12][0-9]{3}", text):
        return text
    for pattern in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, pattern).date().isoformat()
        except ValueError:
            continue
    raise BuildError(f"Unsupported identity observation date: {text!r}")


def _snapshot(
    *,
    organization_names: Iterable[object],
    line_1: object,
    line_2: object,
    city: object,
    region: object,
    postal_code: object,
    organization_phone: object,
    incorporation_jurisdiction: object = None,
    incorporation_year: object = None,
) -> dict[str, Any]:
    names = sorted({name for value in organization_names if (name := _text(value))})
    if not names:
        raise BuildError("An identity snapshot has no organization name")
    if isinstance(incorporation_year, bool) or (
        incorporation_year is not None and not isinstance(incorporation_year, int | str)
    ):
        raise BuildError("An identity snapshot has an invalid incorporation year")
    year = _text(incorporation_year)
    return {
        "address": {
            "city": _text(city),
            "line_1": _text(line_1),
            "line_2": _text(line_2),
            "postal_code": _text(postal_code),
            "region": _text(region),
        },
        "incorporation_jurisdiction": _text(incorporation_jurisdiction),
        "incorporation_year": year,
        "organization_names": names,
        "organization_phone": _text(organization_phone),
    }


def _aggregate_snapshots(
    observations: Iterable[tuple[dict[str, Any], str | None]], *, label: str
) -> list[dict[str, Any]]:
    grouped: dict[bytes, dict[str, Any]] = {}
    for snapshot, observation_date in observations:
        key = _canonical_json(snapshot)
        aggregate = grouped.setdefault(
            key,
            {"count": 0, "dates": [], "snapshot": snapshot},
        )
        aggregate["count"] += 1
        if observation_date is not None:
            aggregate["dates"].append(observation_date)
    if not grouped:
        raise BuildError(f"No {label} identity observations were reconstructed")
    output: list[dict[str, Any]] = []
    for key in sorted(grouped):
        aggregate = grouped[key]
        dates = sorted(aggregate["dates"])
        output.append(
            {
                **aggregate["snapshot"],
                "first_observed_date": dates[0] if dates else None,
                "last_observed_date": dates[-1] if dates else None,
                "observation_count": aggregate["count"],
            }
        )
    return output


def _load_award_histories(
    path: Path,
    product: Mapping[str, Any],
    *,
    selected_sources: Mapping[int, tuple[str, Mapping[str, Any]]],
) -> dict[str, list[dict[str, Any]]]:
    if not path.is_file():
        raise BuildError(f"Pinned award CSV is missing: {path}")
    before = path.stat()
    sha256, size = _sha256_path(path)
    if sha256 != product["sha256"] or size != product["size_bytes"]:
        raise BuildError("Award CSV does not match its pinned bytes")
    observations: dict[str, list[tuple[dict[str, Any], str | None]]] = defaultdict(list)
    seen_selected: set[int] = set()
    row_count = 0
    with path.open(encoding="utf-8-sig", errors="strict", newline="") as handle:
        reader = csv.DictReader(handle, strict=True)
        fieldnames = reader.fieldnames or []
        if any(not isinstance(field, str) or not field.strip() for field in fieldnames):
            raise BuildError("Award CSV has a blank column name")
        folded = [field.strip().casefold() for field in fieldnames]
        if len(folded) != len(set(folded)):
            raise BuildError("Award CSV has duplicate column names")
        columns = {
            "name": _column(fieldnames, "Company", "company_name"),
            "line_1": _column(fieldnames, "Address1", "address_line_1"),
            "line_2": _column(fieldnames, "Address2", "address_line_2"),
            "city": _column(fieldnames, "City"),
            "region": _column(fieldnames, "State", "state_code"),
            "postal_code": _column(fieldnames, "Zip", "ZIP", "postal_code"),
            "date": _column(fieldnames, "Proposal Award Date", "award_date"),
            "year": _column(fieldnames, "Award Year", "award_year"),
        }
        if any(columns[key] is None for key in ("name", "line_1", "city", "region", "postal_code")):
            raise BuildError("Award CSV lacks required identity-history columns")
        for source_record, row in enumerate(reader, start=1):
            row_count += 1
            if None in row:
                raise BuildError(f"Award CSV record {source_record} has fields beyond its header")
            selected = selected_sources.get(source_record)
            if selected is None:
                continue
            firm_id, frozen = selected
            raw_name = str(row.get(columns["name"]) or "")
            if raw_name != str(frozen.get("raw_name") or ""):
                raise BuildError(f"Award record {source_record} disagrees with firm-ledger lineage")
            observation_date = _date(row.get(columns["date"])) if columns["date"] else None
            if observation_date is None and columns["year"]:
                observation_date = _date(row.get(columns["year"]))
            observations[firm_id].append(
                (
                    _snapshot(
                        organization_names=[raw_name],
                        line_1=row.get(columns["line_1"]),
                        line_2=row.get(columns["line_2"]) if columns["line_2"] else None,
                        city=row.get(columns["city"]),
                        region=row.get(columns["region"]),
                        postal_code=row.get(columns["postal_code"]),
                        # The pinned SBIR export exposes a person's Contact Phone, not a
                        # reliably corporate number. Keep it out of the review packet.
                        organization_phone=None,
                    ),
                    observation_date,
                )
            )
            seen_selected.add(source_record)
    after = path.stat()
    if (
        after.st_size != before.st_size
        or after.st_mtime_ns != before.st_mtime_ns
        or after.st_ino != before.st_ino
    ):
        raise BuildError("Award CSV changed while it was read")
    if row_count != product["row_count"]:
        raise BuildError("Award CSV row count does not match its pin")
    missing = set(selected_sources) - seen_selected
    if missing:
        raise BuildError(f"Award CSV is missing {len(missing)} selected source records")
    return {
        firm_id: _aggregate_snapshots(rows, label=f"SBIR firm {firm_id}")
        for firm_id, rows in observations.items()
    }


def _load_form_d_histories(
    path: Path,
    product: Mapping[str, Any],
    *,
    selected_ciks: set[str],
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, list[str]]]:
    observations: dict[str, list[tuple[dict[str, Any], str | None]]] = defaultdict(list)
    accessions_by_cik: dict[str, list[str]] = {}
    found: set[str] = set()
    seen_accessions: set[str] = set()
    previous_cik: str | None = None
    for line_number, row in _stable_jsonl_rows(path, product, label="broad issuer universe"):
        cik = row.get("cik")
        if not isinstance(cik, str) or not CIK_RE.fullmatch(cik):
            raise BuildError(f"Broad issuer line {line_number} has an invalid CIK")
        if previous_cik is not None and cik <= previous_cik:
            raise BuildError("Broad issuer CIKs must be unique and ordered")
        previous_cik = cik
        filings = row.get("filings")
        if (
            row.get("schema_version") != 1
            or row.get("firm_key") != f"form_d_cik:{cik}"
            or not isinstance(filings, list)
            or not filings
            or row.get("filing_count") != len(filings)
        ):
            raise BuildError(f"Broad issuer {cik} has invalid filing evidence")
        if cik not in selected_ciks:
            continue
        accessions: list[str] = []
        for filing in filings:
            if not isinstance(filing, Mapping) or filing.get("cik") != cik:
                raise BuildError(f"Selected broad issuer {cik} pools evidence across CIKs")
            accession = filing.get("accession_number")
            aliases = filing.get("issuer_name_aliases")
            issuer_name = filing.get("issuer_name")
            if (
                not isinstance(accession, str)
                or not accession.strip()
                or accession != accession.strip()
                or accession in seen_accessions
                or not isinstance(aliases, list)
                or not aliases
                or any(not isinstance(alias, str) or not alias.strip() for alias in aliases)
                or not isinstance(issuer_name, str)
                or issuer_name not in aliases
            ):
                raise BuildError(f"Selected broad issuer {cik} has malformed identity lineage")
            filing_date = _date(filing.get("filing_date"))
            if filing_date is None:
                raise BuildError(f"Selected broad issuer {cik} has no filing date")
            seen_accessions.add(accession)
            accessions.append(accession)
            observations[cik].append(
                (
                    _snapshot(
                        organization_names=aliases,
                        line_1=filing.get("street1"),
                        line_2=filing.get("street2"),
                        city=filing.get("city"),
                        region=filing.get("state"),
                        postal_code=filing.get("zip_code"),
                        organization_phone=filing.get("issuer_phone"),
                        incorporation_jurisdiction=filing.get("jurisdiction_of_incorporation"),
                        incorporation_year=filing.get("year_of_incorporation"),
                    ),
                    filing_date,
                )
            )
        accessions_by_cik[cik] = sorted(accessions)
        found.add(cik)
    missing = selected_ciks - found
    if missing:
        raise BuildError(f"Broad issuer universe is missing {len(missing)} selected CIKs")
    return (
        {
            cik: _aggregate_snapshots(rows, label=f"Form D issuer {cik}")
            for cik, rows in observations.items()
        },
        accessions_by_cik,
    )


def _contains_forbidden_packet_content(value: object) -> bool:
    if isinstance(value, Mapping):
        for key, child in value.items():
            folded = re.sub(r"[^a-z0-9]+", "_", str(key).casefold()).strip("_")
            if folded != "case_id" and (
                folded.endswith("_id")
                or any(fragment in folded for fragment in FORBIDDEN_PACKET_KEY_FRAGMENTS)
            ):
                return True
            if _contains_forbidden_packet_content(child):
                return True
        return False
    if isinstance(value, list):
        return any(_contains_forbidden_packet_content(child) for child in value)
    return isinstance(value, str) and value in ROUTE_ORDER


def _assemble_products(
    selected: Sequence[Mapping[str, Any]],
    *,
    award_histories: Mapping[str, list[dict[str, Any]]],
    form_d_histories: Mapping[str, list[dict[str, Any]]],
    ledger_rows: Mapping[str, Mapping[str, Any]],
    form_d_accessions: Mapping[str, list[str]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    packet: list[dict[str, Any]] = []
    case_map: list[dict[str, Any]] = []
    for candidate in selected:
        firm_id = candidate["sbir_firm_id"]
        cik = candidate["form_d_cik"]
        case_id = candidate["_case_id"]
        packet_row = {
            "case_id": case_id,
            "organization_a_history": award_histories[firm_id],
            "organization_b_history": form_d_histories[cik],
            "review_contract": PACKET_CONTRACT,
            "schema_version": PACKET_SCHEMA_VERSION,
        }
        if _contains_forbidden_packet_content(packet_row):
            raise BuildError(f"Review packet {case_id} contains forbidden evidence")
        packet.append(packet_row)
        ledger_sources = sorted(
            source["source_record"] for source in ledger_rows[firm_id]["source_records"]
        )
        case_map.append(
            {
                "candidate_routes": list(candidate["candidate_routes"]),
                "candidate_source_lineage": {
                    "form_d_accessions": list(candidate["form_d_source_accessions"]),
                    "sbir_source_records": list(candidate["sbir_source_records"]),
                },
                "case_id": case_id,
                "case_map_contract": CASE_MAP_CONTRACT,
                "edge_id": candidate["edge_id"],
                "exclusive_stratum": candidate["_exclusive_stratum"],
                "form_d_cik": cik,
                "pool_order_rank_sha256": candidate["_pool_order_rank_sha256"],
                "review_history_lineage": {
                    "form_d_accessions": form_d_accessions[cik],
                    "sbir_source_records": ledger_sources,
                },
                "sbir_firm_id": firm_id,
                "schema_version": CASE_MAP_SCHEMA_VERSION,
                "selection_rank_sha256": candidate["_selection_rank_sha256"],
            }
        )
    expected_ids = [f"case_{index:04d}" for index in range(1, TOTAL_SAMPLE_SIZE + 1)]
    if [row["case_id"] for row in packet] != expected_ids:
        raise BuildError("Neutral case IDs are incomplete or unordered")
    if [row["case_id"] for row in case_map] != expected_ids:
        raise BuildError("Private case-map IDs do not reconcile to the packet")
    return packet, case_map


def _product_bytes(rows: Iterable[Mapping[str, Any]]) -> bytes:
    return b"".join(_canonical_json(row) for row in rows)


def _publish_bytes(output_dir: Path, *, filename: str, data: bytes) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / filename
    if target.exists():
        if target.read_bytes() != data:
            raise BuildError(f"Existing content-addressed artifact disagrees: {target}")
        return
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{filename}.", dir=output_dir)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()


def _product_record(filename: str, data: bytes, row_count: int) -> dict[str, Any]:
    return {
        "path": filename,
        "row_count": row_count,
        "sha256": _sha256_bytes(data),
        "size_bytes": len(data),
    }


def _input_record(path: Path, data: bytes, *, row_count: int | None = None) -> dict[str, Any]:
    record: dict[str, Any] = {
        "path": path.name,
        "sha256": _sha256_bytes(data),
        "size_bytes": len(data),
    }
    if row_count is not None:
        record["row_count"] = row_count
    return record


def _ensure_output_disjoint(output_dir: Path, inputs: Iterable[Path]) -> None:
    resolved_output = output_dir.resolve(strict=False)
    for path in inputs:
        resolved_input = path.resolve(strict=False)
        if resolved_input == resolved_output or resolved_output in resolved_input.parents:
            raise BuildError(f"Output directory would replace pinned input: {path}")


def build(args: argparse.Namespace) -> dict[str, Any]:
    code_version = str(args.code_version or "").strip()
    if not GIT_COMMIT_RE.fullmatch(code_version):
        raise BuildError("--code-version must be a full lowercase 40-character git commit")
    prerequisites = _load_prerequisites(args)
    awards_path = Path(args.awards_csv)
    output_dir = Path(args.output_dir)
    _ensure_output_disjoint(
        output_dir,
        (
            prerequisites["candidate_path"],
            prerequisites["candidate_product_path"],
            prerequisites["crosswalk_path"],
            prerequisites["ledger_path"],
            prerequisites["control_path"],
            prerequisites["broad_path"],
            awards_path,
        ),
    )
    selected, audit = _load_and_sample_candidates(
        prerequisites["candidate_product_path"],
        prerequisites["candidate_product"],
    )
    selected_firms = {row["sbir_firm_id"] for row in selected}
    selected_ciks = {row["form_d_cik"] for row in selected}
    ledger_rows, selected_sources = _load_selected_ledger(
        prerequisites["ledger_path"],
        prerequisites["ledger_product"],
        selected_firms=selected_firms,
    )
    for candidate in selected:
        firm_id = candidate["sbir_firm_id"]
        ledger_row = ledger_rows[firm_id]
        if ledger_row.get("component_status") != candidate["component_status"]:
            raise BuildError(f"Candidate component status disagrees with firm ledger: {firm_id}")
        ledger_sources = {source["source_record"] for source in ledger_row["source_records"]}
        if not set(candidate["sbir_source_records"]) <= ledger_sources:
            raise BuildError(f"Candidate SBIR lineage escapes firm ledger: {firm_id}")
    award_histories = _load_award_histories(
        awards_path,
        prerequisites["award_product"],
        selected_sources=selected_sources,
    )
    form_d_histories, accessions_by_cik = _load_form_d_histories(
        prerequisites["broad_path"],
        prerequisites["broad_product"],
        selected_ciks=selected_ciks,
    )
    for candidate in selected:
        cik = candidate["form_d_cik"]
        if not set(candidate["form_d_source_accessions"]) <= set(accessions_by_cik[cik]):
            raise BuildError(f"Candidate Form D lineage escapes selected CIK: {cik}")
    packet_rows, case_map_rows = _assemble_products(
        selected,
        award_histories=award_histories,
        form_d_histories=form_d_histories,
        ledger_rows=ledger_rows,
        form_d_accessions=accessions_by_cik,
    )
    packet_data = _product_bytes(packet_rows)
    case_map_data = _product_bytes(case_map_rows)
    packet_sha = _sha256_bytes(packet_data)
    case_map_sha = _sha256_bytes(case_map_data)
    packet_name = f"sbir_form_d_identity_review_packet.v1.{packet_sha}.jsonl"
    case_map_name = f"sbir_form_d_identity_review_case_map.v1.{case_map_sha}.jsonl"
    packet_product = _product_record(packet_name, packet_data, len(packet_rows))
    case_map_product = _product_record(case_map_name, case_map_data, len(case_map_rows))
    producer_path = Path(__file__).resolve()
    producer_sha, producer_size = _sha256_path(producer_path)
    manifest = {
        "complete": True,
        "complete_sbir_exclusion": False,
        "counts": audit,
        "covariates_ready": False,
        "estimand": ESTIMAND,
        "exclusion_eligible": False,
        "exclusion_recall": "unknown",
        "exclusive_route_validation_passed": dict.fromkeys(ROUTE_ORDER, False),
        "human_labels_present": False,
        "identity_accepted": False,
        "identity_only": True,
        "inputs": {
            "broad_issuer_universe": dict(prerequisites["broad_product"]),
            "candidate_manifest": _input_record(
                prerequisites["candidate_path"], prerequisites["candidate_data"]
            ),
            "candidate_product": dict(prerequisites["candidate_product"]),
            "control_manifest": _input_record(
                prerequisites["control_path"], prerequisites["control_data"]
            ),
            "crosswalk_manifest": _input_record(
                prerequisites["crosswalk_path"], prerequisites["crosswalk_data"]
            ),
            "firm_identity_ledger": dict(prerequisites["ledger_product"]),
            "sbir_awards_csv": dict(prerequisites["award_product"]),
        },
        "instrument_only": True,
        "invariants": {
            "case_ids_assigned_after_stratified_selection": True,
            "degrees_computed_on_full_candidate_graph": True,
            "downstream_gates_closed": True,
            "histories_use_unique_identity_snapshots": True,
            "packet_contains_no_forbidden_fields": not any(
                _contains_forbidden_packet_content(row) for row in packet_rows
            ),
            "packet_is_outcome_blind": True,
            "packet_is_route_masked": True,
            "packet_map_case_ids_reconcile": [row["case_id"] for row in packet_rows]
            == [row["case_id"] for row in case_map_rows],
        },
        "matching_eligible": False,
        "outputs": {
            "private_case_map": case_map_product,
            "private_review_packet": packet_product,
        },
        "parameters": {
            "allowed_decisions": [
                "same_organization",
                "different_organization",
                "insufficient_evidence",
            ],
            "case_map_contract": CASE_MAP_CONTRACT,
            "exclusive_route_priority": list(ROUTE_ORDER),
            "fanout_degree_basis": "full_pinned_candidate_graph_before_exclusions",
            "packet_contract": PACKET_CONTRACT,
            "pool_order_rank_domain": POOL_ORDER_DOMAIN,
            "review_rubric": {
                "different_organization": "affirmative contradictory evidence",
                "insufficient_evidence": ("missing evidence or merely changed contact information"),
                "same_organization": ESTIMAND,
            },
            "sample_per_exclusive_stratum": SAMPLE_PER_STRATUM,
            "selection_rank_domain": SELECTION_RANK_DOMAIN,
        },
        "producer": {
            "code_commit": code_version,
            "path": str(producer_path.relative_to(REPO_ROOT)),
            "sha256": producer_sha,
            "size_bytes": producer_size,
        },
        "rate_eligible": False,
        "ready_for_matching": False,
        "recall": "unknown",
        "schema_version": MANIFEST_SCHEMA_VERSION,
    }
    manifest_data = json.dumps(manifest, indent=2, sort_keys=True).encode() + b"\n"
    _publish_bytes(output_dir, filename=packet_name, data=packet_data)
    _publish_bytes(output_dir, filename=case_map_name, data=case_map_data)
    _publish_bytes(
        output_dir,
        filename="sbir_form_d_identity_review_sample.manifest.json",
        data=manifest_data,
    )
    return manifest


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-manifest", type=Path, default=DEFAULT_CANDIDATE_MANIFEST)
    parser.add_argument("--candidate-manifest-sha256", required=True)
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
