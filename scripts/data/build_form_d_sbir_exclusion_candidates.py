#!/usr/bin/env python3
"""Build a review-only possible-SBIR contamination queue for Form D controls.

The producer consumes the pinned provisional control identities from the
maintained Form D universe and compares every retained issuer alias with every
historical SBIR company-name key reachable through three frozen retrieval
rules. Results are candidates for review, never automatic exclusions.
"""

import argparse
import csv
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from collections.abc import Mapping
from pathlib import Path
from typing import Any, BinaryIO, cast

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


DEFAULT_SOURCE_MANIFEST = (
    REPO_ROOT / "docs/research/agency-private-capital-form-d-control-universe.manifest.json"
)
DEFAULT_CONTROL_DIR = REPO_ROOT / "data/processed/agency_private_capital/control_universe"
DEFAULT_PROVISIONAL_CONTROLS = (
    DEFAULT_CONTROL_DIR / "form_d_control_identity_universe.provisional.jsonl"
)
DEFAULT_EXACT_EXCLUSIONS = (
    DEFAULT_CONTROL_DIR / "sbir_cik_exclusion_candidates.identity-staging.jsonl"
)
DEFAULT_AWARDS_CSV = REPO_ROOT / "data/raw/sbir/award_data.csv"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "data/processed/agency_private_capital/sbir_contamination_audit"

CONTRACT_VERSION = "form-d-sbir-exclusion-candidate-v1"
NORMALIZER = CompanyNameProfile.ORGANIZATION_KEY_V1
GEOGRAPHY_PROFILE = USJurisdictionProfile.STRICT_V1
PREFIX_LENGTH = 2
MINIMUM_NORMALIZED_NAME_LENGTH = 6
STRONG_NAME_THRESHOLD = 0.95
STATE_SUPPORTED_THRESHOLD = 0.85
ZIP_SUPPORTED_THRESHOLD = 0.80
ROUTE_ORDER = ("strong_name", "state_supported", "zip_supported")
SHA256_RE = re.compile(r"[0-9a-f]{64}")
ZIP5_RE = re.compile(r"^\s*(\d{5})(?:-\d{4})?\s*$")


class BuildError(RuntimeError):
    """Raised when an input or invariant would make the audit unreliable."""


def normalize_zip5(value: object) -> str | None:
    """Return a strict ZIP5 from ZIP5 or ZIP+4 source text."""

    if value is None:
        return None
    match = ZIP5_RE.fullmatch(str(value))
    return match.group(1) if match else None


def candidate_id(cik: str, sbir_name_normalized: str) -> str:
    """Return the stable candidate-pair identifier."""

    payload = f"{CONTRACT_VERSION}\0{cik}\0{sbir_name_normalized}".encode()
    return hashlib.sha256(payload).hexdigest()


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
        raise BuildError(f"Source manifest does not pin {label}")
    path = value.get("path")
    sha256 = value.get("sha256")
    size_bytes = value.get("size_bytes")
    row_count = value.get("row_count")
    if not isinstance(path, str) or not path:
        raise BuildError(f"Pinned {label} has no path")
    if not isinstance(sha256, str) or not SHA256_RE.fullmatch(sha256):
        raise BuildError(f"Pinned {label} has an invalid SHA-256")
    _non_negative_int(size_bytes, label=f"Pinned {label} size_bytes")
    _non_negative_int(row_count, label=f"Pinned {label} row_count")
    return dict(value)


def _load_source_manifest(path: Path) -> tuple[dict[str, Any], bytes]:
    if not path.is_file():
        raise BuildError(f"Required source manifest is missing: {path}")
    try:
        data = path.read_bytes()
        manifest = json.loads(data)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BuildError(f"Invalid source manifest JSON: {exc}") from exc
    if not isinstance(manifest, dict):
        raise BuildError("Source manifest must be a JSON object")
    if manifest.get("complete") is not True:
        raise BuildError("Source manifest is incomplete")
    required_gates = {
        "complete_sbir_exclusion": False,
        "covariates_ready": False,
        "exclusion_recall": "unknown",
        "identity_only": True,
        "ready_for_matching": False,
    }
    for field, expected in required_gates.items():
        actual = manifest.get(field)
        if isinstance(expected, bool):
            valid = actual is expected
        else:
            valid = actual == expected
        if not valid:
            raise BuildError(f"Source manifest has unexpected {field}")
    if manifest.get("schema_version") != 1 or isinstance(manifest.get("schema_version"), bool):
        raise BuildError("Source manifest has an unsupported schema_version")
    invariants = manifest.get("invariants")
    if not isinstance(invariants, Mapping):
        raise BuildError("Source manifest has no invariants object")
    overlap_count = _non_negative_int(
        invariants.get("control_exclusion_overlap_count"),
        label="Source control_exclusion_overlap_count",
    )
    if overlap_count != 0:
        raise BuildError("Source manifest does not establish disjoint controls and exclusions")
    if invariants.get("control_ciks_unique") is not True:
        raise BuildError("Source manifest does not establish unique provisional control CIKs")
    outputs = manifest.get("outputs")
    if not isinstance(outputs, Mapping):
        raise BuildError("Source manifest has no outputs object")
    controls = _pinned_product(
        outputs.get("provisional_control_identity_universe"),
        label="provisional controls",
    )
    exclusions = _pinned_product(
        outputs.get("candidate_sbir_cik_exclusions"), label="exact exclusion ledger"
    )
    exclusion = manifest.get("exclusion")
    if not isinstance(exclusion, Mapping):
        raise BuildError("Source manifest has no exclusion object")
    awards = exclusion.get("awards_csv")
    awards_product = _pinned_product(awards, label="SBIR awards CSV")
    if controls["row_count"] == 0:
        raise BuildError("Source manifest pins an empty provisional control universe")
    if awards_product["row_count"] == 0:
        raise BuildError("Source manifest pins an empty SBIR awards CSV")
    source_counts = manifest.get("source_counts")
    if not isinstance(source_counts, Mapping):
        raise BuildError("Source manifest has no source_counts object")
    provisional_count = _non_negative_int(
        source_counts.get("provisional_control_ciks"),
        label="Source provisional_control_ciks",
    )
    if provisional_count != controls["row_count"]:
        raise BuildError("Source provisional control count does not match its product pin")
    excluded_broad_count = _non_negative_int(
        source_counts.get("excluded_broad_ciks"),
        label="Source excluded_broad_ciks",
    )
    if excluded_broad_count > exclusions["row_count"]:
        raise BuildError("Source excluded broad CIK count exceeds the exact exclusion ledger")
    explicit_cik_inputs = exclusion.get("explicit_cik_inputs")
    if not isinstance(explicit_cik_inputs, list):
        raise BuildError("Source manifest has no explicit-CIK input ledger")
    if not explicit_cik_inputs and excluded_broad_count != exclusions["row_count"]:
        raise BuildError("Source exact exclusion count does not match its product pin")
    exact_match = exclusion.get("exact_match")
    if not isinstance(exact_match, Mapping):
        raise BuildError("Source manifest has no exact-match exclusion policy")
    if exact_match.get("normalizer_version") != NORMALIZER.value:
        raise BuildError("Source exclusion normalizer does not match the candidate audit")
    return manifest, data


def _validate_pin(path: Path, product: Mapping[str, Any], *, label: str) -> None:
    if not path.is_file():
        raise BuildError(f"Pinned {label} is missing: {path}")
    if path.stat().st_size != product["size_bytes"]:
        raise BuildError(f"Pinned {label} byte count does not match the source manifest")


def _load_exact_exclusions(path: Path, product: Mapping[str, Any]) -> tuple[set[str], str, int]:
    _validate_pin(path, product, label="exact exclusion ledger")
    digest = hashlib.sha256()
    ciks: set[str] = set()
    rows = 0
    size = 0
    with path.open("rb") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            digest.update(raw_line)
            size += len(raw_line)
            if not raw_line.strip():
                raise BuildError(f"Exact exclusion ledger has a blank line at {line_number}")
            rows += 1
            try:
                row = json.loads(raw_line)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise BuildError(f"Invalid exact exclusion JSON at line {line_number}") from exc
            if not isinstance(row, Mapping):
                raise BuildError(f"Exact exclusion line {line_number} must be an object")
            cik = row.get("cik")
            if not isinstance(cik, str) or not cik.isdigit() or cik.startswith("0"):
                raise BuildError(f"Exact exclusion line {line_number} has an invalid CIK")
            if row.get("firm_key") != f"form_d_cik:{cik}":
                raise BuildError(f"Exact exclusion line {line_number} has an invalid firm_key")
            if cik in ciks:
                raise BuildError(f"Exact exclusion ledger repeats CIK {cik}")
            ciks.add(cik)
    if rows != product["row_count"]:
        raise BuildError("Exact exclusion ledger row count does not match its pin")
    if size != product["size_bytes"]:
        raise BuildError("Exact exclusion ledger byte count does not match its pin")
    if digest.hexdigest() != product["sha256"]:
        raise BuildError("Exact exclusion ledger SHA-256 does not match its pin")
    return ciks, digest.hexdigest(), size


def _normalized_name(value: object) -> str:
    return normalize_company_name(value, profile=NORMALIZER)


def _name_is_eligible(value: str) -> bool:
    return sum(character.isalnum() for character in value) >= MINIMUM_NORMALIZED_NAME_LENGTH


def _prefix(value: str) -> str:
    return "".join(character for character in value if character.isalnum())[:PREFIX_LENGTH]


def _parse_year(value: object) -> int | None:
    text = str(value or "").strip()
    return int(text) if re.fullmatch(r"(?:19|20)\d{2}", text) else None


def _load_award_names(
    path: Path, product: Mapping[str, Any]
) -> tuple[dict[str, dict[str, Any]], dict[str, set[str]], dict[str, set[str]], dict[str, Any]]:
    _validate_pin(path, product, label="SBIR awards CSV")
    before = path.stat()
    sha256, raw_size = _sha256_path(path)
    if raw_size != product["size_bytes"]:
        raise BuildError("SBIR awards CSV byte count does not match its pin")
    if sha256 != product["sha256"]:
        raise BuildError("SBIR awards CSV SHA-256 does not match its pin")
    raw_rows = 0
    profiles: dict[str, dict[str, Any]] = {}
    try:
        with path.open(encoding="utf-8-sig", errors="strict", newline="") as handle:
            reader = csv.DictReader(handle, strict=True)
            fieldnames = reader.fieldnames or []
            if any(not isinstance(column, str) or not column.strip() for column in fieldnames):
                raise BuildError("SBIR awards CSV has a blank column name")
            normalized_columns = [column.strip().casefold() for column in fieldnames]
            if len(normalized_columns) != len(set(normalized_columns)):
                raise BuildError("SBIR awards CSV has duplicate column names")
            columns = dict(zip(normalized_columns, fieldnames, strict=True))
            name_column = columns.get("company") or columns.get("company_name")
            state_column = columns.get("state")
            zip_column = columns.get("zip") or columns.get("zip_code")
            year_column = columns.get("award year") or columns.get("award_year")
            if name_column is None:
                raise BuildError("SBIR awards CSV has no Company/company_name column")
            for row in reader:
                raw_rows += 1
                if None in row:
                    raise BuildError(
                        f"SBIR awards CSV record near line {reader.line_num} has extra fields"
                    )
                raw_name = str(row.get(name_column) or "").strip()
                normalized = _normalized_name(raw_name)
                if not normalized or not _name_is_eligible(normalized):
                    continue
                profile = profiles.setdefault(
                    normalized,
                    {
                        "award_row_count": 0,
                        "first_award_year": None,
                        "last_award_year": None,
                        "raw_names": set(),
                        "states": set(),
                        "zip5s": set(),
                    },
                )
                profile["award_row_count"] += 1
                profile["raw_names"].add(raw_name)
                state = (
                    normalize_us_jurisdiction(row.get(state_column), profile=GEOGRAPHY_PROFILE)
                    if state_column
                    else None
                )
                if state:
                    profile["states"].add(state)
                zip5 = normalize_zip5(row.get(zip_column)) if zip_column else None
                if zip5:
                    profile["zip5s"].add(zip5)
                year = _parse_year(row.get(year_column)) if year_column else None
                if year is not None:
                    first = profile["first_award_year"]
                    last = profile["last_award_year"]
                    profile["first_award_year"] = year if first is None else min(first, year)
                    profile["last_award_year"] = year if last is None else max(last, year)
    except (UnicodeDecodeError, csv.Error) as exc:
        line_number = reader.line_num if "reader" in locals() else 1
        raise BuildError(f"Invalid SBIR awards CSV near line {line_number}: {exc}") from exc

    after = path.stat()
    if (
        after.st_size != before.st_size
        or after.st_mtime_ns != before.st_mtime_ns
        or after.st_ino != before.st_ino
    ):
        raise BuildError("SBIR awards CSV changed while it was being parsed")

    if raw_rows != product["row_count"]:
        raise BuildError("SBIR awards CSV row count does not match its pin")

    prefix_index: dict[str, set[str]] = defaultdict(set)
    zip_index: dict[str, set[str]] = defaultdict(set)
    for normalized, profile in profiles.items():
        prefix_index[_prefix(normalized)].add(normalized)
        for zip5 in profile["zip5s"]:
            zip_index[zip5].add(normalized)
    metadata = {
        "eligible_normalized_names": len(profiles),
        "row_count": raw_rows,
        "sha256": sha256,
        "size_bytes": raw_size,
    }
    return profiles, prefix_index, zip_index, metadata


def _issuer_evidence(row: Mapping[str, Any], *, line_number: int) -> dict[str, Any]:
    cik = row.get("cik")
    if not isinstance(cik, str) or not cik.isdigit() or cik.startswith("0") or len(cik) > 10:
        raise BuildError(f"Provisional control line {line_number} has an invalid CIK")
    firm_key = f"form_d_cik:{cik}"
    if row.get("firm_key") != firm_key:
        raise BuildError(f"Provisional control line {line_number} has an invalid firm_key")
    filings = row.get("filings")
    if not isinstance(filings, list) or not filings:
        raise BuildError(f"Provisional control line {line_number} has no filing evidence")
    filing_count = row.get("filing_count")
    if isinstance(filing_count, bool) or not isinstance(filing_count, int):
        raise BuildError(f"Provisional control line {line_number} has an invalid filing_count")
    if filing_count != len(filings):
        raise BuildError(f"Provisional control line {line_number} filing_count does not match")

    raw_aliases: set[str] = set()
    states: set[str] = set()
    zip5s: set[str] = set()

    def add_name(value: object) -> None:
        text = str(value or "").strip()
        if text:
            raw_aliases.add(text)

    def add_state(value: object) -> None:
        state = normalize_us_jurisdiction(value, profile=GEOGRAPHY_PROFILE)
        if state:
            states.add(state)

    def add_zip(value: object) -> None:
        zip5 = normalize_zip5(value)
        if zip5:
            zip5s.add(zip5)

    add_name(row.get("issuer_name"))
    aliases = row.get("issuer_name_aliases")
    if not isinstance(aliases, list):
        raise BuildError(f"Provisional control line {line_number} has invalid aliases")
    for alias in aliases:
        add_name(alias)
    add_state(row.get("state"))
    add_zip(row.get("zip_code"))
    for filing in filings:
        if not isinstance(filing, Mapping):
            raise BuildError(f"Provisional control line {line_number} has a non-object filing")
        if filing.get("cik") != cik:
            raise BuildError(f"Provisional control line {line_number} has a filing CIK mismatch")
        add_name(filing.get("issuer_name"))
        filing_aliases = filing.get("issuer_name_aliases", [])
        if not isinstance(filing_aliases, list):
            raise BuildError(f"Provisional control line {line_number} has invalid filing aliases")
        for alias in filing_aliases:
            add_name(alias)
        add_state(filing.get("state"))
        add_zip(filing.get("zip_code"))

    normalized_aliases: dict[str, set[str]] = defaultdict(set)
    for alias in raw_aliases:
        normalized = _normalized_name(alias)
        if normalized and _name_is_eligible(normalized):
            normalized_aliases[normalized].add(alias)
    canonical = str(row.get("issuer_name") or "").strip()
    canonical_evidence = {
        "aliases": {key: sorted(values) for key, values in sorted(normalized_aliases.items())},
        "cik": cik,
        "states": sorted(states),
        "zip5s": sorted(zip5s),
    }
    fingerprint = hashlib.sha256(
        json.dumps(canonical_evidence, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return {
        "cik": cik,
        "firm_key": firm_key,
        "fingerprint": fingerprint,
        "issuer_name": canonical,
        "normalized_aliases": normalized_aliases,
        "states": states,
        "zip5s": zip5s,
    }


def _candidate_rows_for_issuer(
    issuer: Mapping[str, Any],
    *,
    award_profiles: Mapping[str, Mapping[str, Any]],
    prefix_index: Mapping[str, set[str]],
    zip_index: Mapping[str, set[str]],
) -> list[dict[str, Any]]:
    normalized_aliases = issuer["normalized_aliases"]
    possible_award_names: set[str] = set()
    for alias in normalized_aliases:
        possible_award_names.update(prefix_index.get(_prefix(alias), set()))
    for zip5 in issuer["zip5s"]:
        possible_award_names.update(zip_index.get(zip5, set()))

    candidates: list[dict[str, Any]] = []
    for sbir_normalized in sorted(possible_award_names):
        award = award_profiles[sbir_normalized]
        matched_states = sorted(issuer["states"] & award["states"])
        matched_zip5s = sorted(issuer["zip5s"] & award["zip5s"])
        evidence: list[tuple[float, str, str, set[str]]] = []
        routes: set[str] = set()
        sbir_prefix = _prefix(sbir_normalized)
        for alias_normalized, raw_aliases in normalized_aliases.items():
            ratio = company_name_similarity(
                alias_normalized, sbir_normalized, metric=CompanyNameMetric.RATIO
            )
            alias_routes: set[str] = set()
            same_prefix = _prefix(alias_normalized) == sbir_prefix
            if same_prefix and ratio >= STRONG_NAME_THRESHOLD:
                alias_routes.add("strong_name")
            if same_prefix and matched_states and ratio >= STATE_SUPPORTED_THRESHOLD:
                alias_routes.add("state_supported")
            if matched_zip5s and ratio >= ZIP_SUPPORTED_THRESHOLD:
                alias_routes.add("zip_supported")
            routes.update(alias_routes)
            for raw_alias in raw_aliases:
                evidence.append((ratio, alias_normalized, raw_alias, alias_routes))
        if not routes:
            continue
        routed_evidence = [item for item in evidence if item[3]]
        if not routed_evidence:
            raise AssertionError("candidate routes have no supporting alias evidence")
        best_ratio, best_normalized, best_raw, _ = sorted(
            routed_evidence, key=lambda item: (-item[0], item[1], item[2])
        )[0]
        token_sort = company_name_similarity(
            best_normalized, sbir_normalized, metric=CompanyNameMetric.TOKEN_SORT
        )
        token_set = company_name_similarity(
            best_normalized, sbir_normalized, metric=CompanyNameMetric.TOKEN_SET
        )
        sbir_raw_names = sorted(award["raw_names"])
        candidates.append(
            {
                "adjudication_status": "unreviewed",
                "candidate_id": candidate_id(str(issuer["cik"]), sbir_normalized),
                "candidate_only": True,
                "candidate_routes": [route for route in ROUTE_ORDER if route in routes],
                "cik": issuer["cik"],
                "firm_key": issuer["firm_key"],
                "issuer_alias": best_raw,
                "issuer_name": issuer["issuer_name"],
                "issuer_name_normalized": best_normalized,
                "issuer_states": sorted(issuer["states"]),
                "issuer_zip5s": sorted(issuer["zip5s"]),
                "matched_states": matched_states,
                "matched_zip5s": matched_zip5s,
                "ratio_similarity": round(best_ratio, 6),
                "sbir_award_row_count": award["award_row_count"],
                "sbir_company_name": sbir_raw_names[0],
                "sbir_first_award_year": award["first_award_year"],
                "sbir_last_award_year": award["last_award_year"],
                "sbir_name_normalized": sbir_normalized,
                "sbir_raw_names": sbir_raw_names,
                "sbir_states": sorted(award["states"]),
                "sbir_zip5s": sorted(award["zip5s"]),
                "schema_version": 1,
                "source_control_fingerprint": issuer["fingerprint"],
                "token_set_similarity": round(token_set, 6),
                "token_sort_similarity": round(token_sort, 6),
            }
        )
    return candidates


def _temporary_output(path: Path) -> tuple[BinaryIO, Path]:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="w+b", dir=path.parent, prefix=f".{path.name}.", delete=False
    )
    return cast(BinaryIO, handle), Path(handle.name)


def _write_candidate_product(
    output_dir: Path, rows: list[dict[str, Any]]
) -> tuple[dict[str, Any], Path]:
    staging_hint = output_dir / "form_d_possible_sbir_contamination_candidates.jsonl"
    handle, temp_path = _temporary_output(staging_hint)
    digest = hashlib.sha256()
    size = 0
    try:
        with handle:
            for row in rows:
                data = (
                    json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
                    + "\n"
                ).encode("utf-8")
                handle.write(data)
                digest.update(data)
                size += len(data)
    except BaseException:
        temp_path.unlink(missing_ok=True)
        raise
    sha256 = digest.hexdigest()
    final_path = output_dir / f"form_d_possible_sbir_contamination_candidates.{sha256}.jsonl"
    return {
        "path": final_path.name,
        "row_count": len(rows),
        "sha256": sha256,
        "size_bytes": size,
    }, temp_path


def _git_commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            cwd=REPO_ROOT,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def build(args: argparse.Namespace) -> dict[str, Any]:
    source_manifest_path = Path(args.source_manifest)
    controls_path = Path(args.provisional_controls)
    exclusions_path = Path(args.exact_exclusions)
    awards_path = Path(args.awards_csv)
    output_dir = Path(args.output_dir)
    source_manifest, source_manifest_data = _load_source_manifest(source_manifest_path)
    outputs = source_manifest["outputs"]
    controls_product = _pinned_product(
        outputs["provisional_control_identity_universe"], label="provisional controls"
    )
    exclusions_product = _pinned_product(
        outputs["candidate_sbir_cik_exclusions"], label="exact exclusion ledger"
    )
    awards_product = _pinned_product(
        source_manifest["exclusion"]["awards_csv"], label="SBIR awards CSV"
    )
    _validate_pin(controls_path, controls_product, label="provisional controls")
    exact_ciks, _, _ = _load_exact_exclusions(exclusions_path, exclusions_product)
    award_profiles, prefix_index, zip_index, award_metadata = _load_award_names(
        awards_path, awards_product
    )

    control_digest = hashlib.sha256()
    control_size = 0
    control_rows = 0
    previous_cik: str | None = None
    provisional_ciks: set[str] = set()
    candidate_rows: list[dict[str, Any]] = []
    with controls_path.open("rb") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            control_digest.update(raw_line)
            control_size += len(raw_line)
            if not raw_line.strip():
                raise BuildError(f"Provisional controls have a blank line at {line_number}")
            control_rows += 1
            try:
                row = json.loads(raw_line)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise BuildError(f"Invalid provisional control JSON at line {line_number}") from exc
            if not isinstance(row, Mapping):
                raise BuildError(f"Provisional control line {line_number} must be an object")
            issuer = _issuer_evidence(row, line_number=line_number)
            cik = str(issuer["cik"])
            if previous_cik is not None and cik <= previous_cik:
                raise BuildError("Provisional control CIKs must be unique and ordered")
            previous_cik = cik
            if cik in exact_ciks:
                raise BuildError(f"Provisional controls overlap exact exclusion CIK {cik}")
            provisional_ciks.add(cik)
            candidate_rows.extend(
                _candidate_rows_for_issuer(
                    issuer,
                    award_profiles=award_profiles,
                    prefix_index=prefix_index,
                    zip_index=zip_index,
                )
            )

    if control_rows != controls_product["row_count"]:
        raise BuildError("Provisional control row count does not match its pin")
    if control_size != controls_product["size_bytes"]:
        raise BuildError("Provisional control byte count does not match its pin")
    if control_digest.hexdigest() != controls_product["sha256"]:
        raise BuildError("Provisional control SHA-256 does not match its pin")

    candidate_rows.sort(key=lambda row: (str(row["cik"]), str(row["sbir_name_normalized"])))
    ids = [str(row["candidate_id"]) for row in candidate_rows]
    if len(ids) != len(set(ids)):
        raise BuildError("Possible-contamination queue contains duplicate candidate IDs")
    candidate_ciks = {str(row["cik"]) for row in candidate_rows}
    if not candidate_ciks <= provisional_ciks:
        raise BuildError("Possible-contamination queue contains a non-control CIK")
    if candidate_ciks & exact_ciks:
        raise BuildError("Possible-contamination queue overlaps exact exclusions")

    route_counts: Counter[str] = Counter()
    for row in candidate_rows:
        route_counts.update(row["candidate_routes"])
    product, staged_product = _write_candidate_product(output_dir, candidate_rows)
    product_temp: Path | None = staged_product
    product_path = output_dir / product["path"]
    manifest_path = output_dir / "form_d_sbir_exclusion_candidates.manifest.json"
    source_manifest_sha = hashlib.sha256(source_manifest_data).hexdigest()
    manifest = {
        "applied_exclusion_count": 0,
        "candidate_only": True,
        "code_commit": args.code_version or _git_commit(),
        "complete": True,
        "complete_sbir_exclusion": False,
        "counts": {
            "candidate_ciks": len(candidate_ciks),
            "candidate_pairs": len(candidate_rows),
            "eligible_sbir_normalized_names": len(award_profiles),
            "exact_exclusion_ciks": len(exact_ciks),
            "provisional_control_ciks": len(provisional_ciks),
            "routes": dict(sorted(route_counts.items())),
            "sbir_award_rows": award_metadata["row_count"],
        },
        "covariates_ready": False,
        "exclusion_recall": "unknown",
        "identity_only": True,
        "inputs": {
            "awards_csv": {
                "path": awards_path.name,
                "row_count": award_metadata["row_count"],
                "sha256": award_metadata["sha256"],
                "size_bytes": award_metadata["size_bytes"],
            },
            "exact_exclusions": {
                "path": exclusions_path.name,
                "row_count": exclusions_product["row_count"],
                "sha256": exclusions_product["sha256"],
                "size_bytes": exclusions_product["size_bytes"],
            },
            "provisional_controls": {
                "path": controls_path.name,
                "row_count": controls_product["row_count"],
                "sha256": controls_product["sha256"],
                "size_bytes": controls_product["size_bytes"],
            },
            "source_manifest": {
                "path": source_manifest_path.name,
                "sha256": source_manifest_sha,
                "size_bytes": len(source_manifest_data),
            },
        },
        "invariants": {
            "all_candidates_unreviewed": all(
                row["adjudication_status"] == "unreviewed" for row in candidate_rows
            ),
            "candidate_ciks_disjoint_exact_exclusions": not bool(candidate_ciks & exact_ciks),
            "candidate_ciks_subset_provisional_controls": candidate_ciks <= provisional_ciks,
            "candidate_ids_unique": len(ids) == len(set(ids)),
            "content_addressed_output": product["sha256"] in product["path"],
            "no_automatic_exclusions": True,
            "source_inputs_hash_rows_bytes_verified": True,
        },
        "outputs": {"possible_sbir_contamination_candidates": product},
        "parameters": {
            "candidate_contract_version": CONTRACT_VERSION,
            "geography_profile": GEOGRAPHY_PROFILE.value,
            "minimum_normalized_name_length": MINIMUM_NORMALIZED_NAME_LENGTH,
            "name_metrics": [
                CompanyNameMetric.RATIO.value,
                CompanyNameMetric.TOKEN_SORT.value,
                CompanyNameMetric.TOKEN_SET.value,
            ],
            "name_normalizer": NORMALIZER.value,
            "prefix_length": PREFIX_LENGTH,
            "retrieval_is_exhaustive_within_declared_rules": True,
            "thresholds": {
                "state_supported_ratio": STATE_SUPPORTED_THRESHOLD,
                "strong_name_ratio": STRONG_NAME_THRESHOLD,
                "zip_supported_ratio": ZIP_SUPPORTED_THRESHOLD,
            },
        },
        "ready_for_matching": False,
        "schema_version": 1,
    }
    manifest_data = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_temp: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=manifest_path.parent, prefix=f".{manifest_path.name}.", delete=False
        ) as handle:
            manifest_temp = Path(handle.name)
            handle.write(manifest_data)
        if product_temp is None:
            raise AssertionError("candidate product staging file is missing")
        os.replace(product_temp, product_path)
        product_temp = None
        os.replace(manifest_temp, manifest_path)
        manifest_temp = None
    finally:
        if product_temp is not None:
            product_temp.unlink(missing_ok=True)
        if manifest_temp is not None:
            manifest_temp.unlink(missing_ok=True)
    return manifest


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-manifest", type=Path, default=DEFAULT_SOURCE_MANIFEST)
    parser.add_argument("--provisional-controls", type=Path, default=DEFAULT_PROVISIONAL_CONTROLS)
    parser.add_argument("--exact-exclusions", type=Path, default=DEFAULT_EXACT_EXCLUSIONS)
    parser.add_argument("--awards-csv", type=Path, default=DEFAULT_AWARDS_CSV)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--code-version", help="Pinned producer commit for the manifest")
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
