"""Fail-closed PatentsView source and candidate-bridge contracts.

This module deliberately stops below the study-outcome layer. It validates a
local three-table PVGPATDIS bundle, reduces it to assignee-native patent-grant
events, and validates candidate-only CIK-to-assignee evidence. It does not
download data, establish identity links, evaluate coverage, or report rates.
"""

import csv
import hashlib
import io
import json
import re
import zipfile
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from sbir_etl.identity import CompanyNameProfile, normalize_company_name


SCHEMA_VERSION = 1
BRIDGE_SCHEMA_VERSION = 1
PRODUCT = "PVGPATDIS"
EVENT_TYPE = "patent_grant"
SOURCE_RELEASE_DOMAIN = "patentsview-source-release-v1"
NORMALIZER_PROFILE = CompanyNameProfile.ORGANIZATION_KEY_V1
EVIDENCE_METHOD = "exact_normalized_name"
VALID_CANDIDATE_STATUSES = frozenset({"candidate", "ambiguous"})
SHA256_RE = re.compile(r"[0-9a-f]{64}")
CIK_RE = re.compile(r"[1-9][0-9]{0,9}")

ROLE_MEMBERS = {
    "application": "g_application.tsv",
    "assignee": "g_assignee_disambiguated.tsv",
    "patent": "g_patent.tsv",
}

REQUIRED_HEADERS = {
    "application": (
        "application_id",
        "patent_id",
        "patent_application_type",
        "filing_date",
        "series_code",
        "rule_47_flag",
    ),
    "assignee": (
        "patent_id",
        "assignee_sequence",
        "assignee_id",
        "disambig_assignee_individual_name_first",
        "disambig_assignee_individual_name_last",
        "disambig_assignee_organization",
        "assignee_type",
        "location_id",
    ),
    "patent": (
        "patent_id",
        "patent_type",
        "patent_date",
        "patent_title",
        "wipo_kind",
        "num_claims",
        "withdrawn",
        "filename",
    ),
}

EVENT_FIELDS = frozenset(
    {
        "application_filing_date",
        "assignee_id",
        "assignee_organization",
        "assignee_type",
        "event_date",
        "event_type",
        "patent_id",
        "patent_title",
        "schema_version",
        "source_release_id",
    }
)

BRIDGE_FIELDS = frozenset(
    {
        "assignee_id",
        "bridge_schema_version",
        "candidate_status",
        "evidence_method",
        "form_d_cik",
        "normalized_name_key",
        "normalizer_profile",
        "source_release_id",
    }
)


class PatentSourceContractError(ValueError):
    """Raised when source evidence cannot satisfy the patent contract."""


@dataclass(frozen=True)
class ValidatedPatentFile:
    """One content-pinned ZIP role in a validated source release."""

    role: str
    path: Path
    archive_member: str
    sha256: str
    size_bytes: int
    headers: tuple[str, ...]


@dataclass(frozen=True)
class ValidatedPatentBundle:
    """A verified local PVGPATDIS release."""

    source_release_id: str
    release_date: date
    data_through_date: date
    source_url: str
    license_url: str
    files: Mapping[str, ValidatedPatentFile]


def _required_text(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PatentSourceContractError(f"{label} must be a nonblank string")
    return value.strip()


def _strict_int(value: object, *, label: str, positive: bool = False) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise PatentSourceContractError(f"{label} must be an integer")
    if value < (1 if positive else 0):
        qualifier = "positive" if positive else "non-negative"
        raise PatentSourceContractError(f"{label} must be {qualifier}")
    return value


def _iso_date(value: object, *, label: str, optional: bool = False) -> date | None:
    if optional and (value is None or (isinstance(value, str) and not value.strip())):
        return None
    text = _required_text(value, label=label)
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise PatentSourceContractError(f"{label} must be an ISO date") from exc


def _https_url(value: object, *, label: str) -> str:
    url = _required_text(value, label=label)
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise PatentSourceContractError(f"{label} must be an HTTPS URL")
    return url


def _sha256_path(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
            size += len(block)
    return digest.hexdigest(), size


def _safe_local_path(base_dir: Path, value: object, *, role: str) -> Path:
    raw_path = _required_text(value, label=f"{role} local_path")
    relative = Path(raw_path)
    if relative.is_absolute() or ".." in relative.parts:
        raise PatentSourceContractError(f"{role} local_path must stay within base_dir")
    base = base_dir.resolve()
    resolved = (base / relative).resolve()
    if resolved != base and base not in resolved.parents:
        raise PatentSourceContractError(f"{role} local_path escapes base_dir")
    if not resolved.is_file():
        raise PatentSourceContractError(f"{role} archive is missing: {resolved}")
    return resolved


def _declared_headers(value: object, *, role: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise PatentSourceContractError(f"{role} headers must be a nonempty list")
    headers: list[str] = []
    for header in value:
        canonical_header = _required_text(header, label=f"{role} header")
        if header != canonical_header:
            raise PatentSourceContractError(
                f"{role} declared headers must not contain surrounding whitespace"
            )
        headers.append(canonical_header)
    normalized = [header.casefold() for header in headers]
    if len(normalized) != len(set(normalized)):
        raise PatentSourceContractError(f"{role} headers contain duplicates")
    return tuple(headers)


def _observed_headers(path: Path, *, role: str, member: str) -> tuple[str, ...]:
    try:
        with zipfile.ZipFile(path) as archive:
            matches = [info for info in archive.infolist() if info.filename == member]
            if len(matches) != 1:
                raise PatentSourceContractError(
                    f"{role} archive must contain declared member exactly once: {member}"
                )
            if matches[0].flag_bits & 0x1:
                raise PatentSourceContractError(f"{role} archive member must not be encrypted")
            with archive.open(matches[0]) as raw:
                with io.TextIOWrapper(
                    raw, encoding="utf-8-sig", errors="strict", newline=""
                ) as text:
                    reader = csv.reader(text, delimiter="\t", strict=True)
                    try:
                        raw_headers = next(reader)
                    except StopIteration as exc:
                        raise PatentSourceContractError(f"{role} archive member is empty") from exc
    except (OSError, UnicodeDecodeError, csv.Error, zipfile.BadZipFile) as exc:
        raise PatentSourceContractError(f"{role} archive is not a readable UTF-8 TSV ZIP") from exc

    headers = tuple(raw_headers)
    if any(not header for header in headers):
        raise PatentSourceContractError(f"{role} archive has a blank header")
    if any(header != header.strip() for header in headers):
        raise PatentSourceContractError(
            f"{role} archive headers must not contain surrounding whitespace"
        )
    normalized = [header.casefold() for header in headers]
    if len(normalized) != len(set(normalized)):
        raise PatentSourceContractError(f"{role} archive has duplicate headers")
    missing = set(REQUIRED_HEADERS[role]) - set(headers)
    if missing:
        raise PatentSourceContractError(f"{role} archive is missing headers: {sorted(missing)}")
    return headers


def _canonical_release_payload(
    *,
    release_date: date,
    data_through_date: date,
    files: Mapping[str, ValidatedPatentFile],
) -> bytes:
    payload = {
        "data_through_date": data_through_date.isoformat(),
        "files": [
            {
                "archive_member": files[role].archive_member,
                "headers": list(files[role].headers),
                "role": role,
                "sha256": files[role].sha256,
                "size_bytes": files[role].size_bytes,
            }
            for role in sorted(files)
        ],
        "product": PRODUCT,
        "release_date": release_date.isoformat(),
        "schema_version": SCHEMA_VERSION,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()


def _derive_release_id(
    *,
    release_date: date,
    data_through_date: date,
    files: Mapping[str, ValidatedPatentFile],
) -> str:
    release_payload = _canonical_release_payload(
        release_date=release_date,
        data_through_date=data_through_date,
        files=files,
    )
    return hashlib.sha256(SOURCE_RELEASE_DOMAIN.encode() + b"\0" + release_payload).hexdigest()


def validate_patent_source_bundle(
    manifest: Mapping[str, Any], *, base_dir: Path
) -> ValidatedPatentBundle:
    """Verify a local three-ZIP PVGPATDIS bundle and derive its release ID.

    ``local_path`` and optional operational fields such as ``downloaded_at`` are
    intentionally excluded from the release-ID payload.
    """

    if not isinstance(manifest, Mapping):
        raise PatentSourceContractError("manifest must be an object")
    schema_version = _strict_int(manifest.get("schema_version"), label="schema_version")
    if schema_version != SCHEMA_VERSION:
        raise PatentSourceContractError("unsupported schema_version")
    if manifest.get("product") != PRODUCT:
        raise PatentSourceContractError(f"product must be {PRODUCT}")
    release_date = _iso_date(manifest.get("release_date"), label="release_date")
    data_through_date = _iso_date(manifest.get("data_through_date"), label="data_through_date")
    if release_date is None or data_through_date is None:
        raise AssertionError("required dates were not parsed")
    if data_through_date > release_date:
        raise PatentSourceContractError("data_through_date must not follow release_date")
    source_url = _https_url(manifest.get("source_url"), label="source_url")
    license_url = _https_url(manifest.get("license_url"), label="license_url")

    raw_files = manifest.get("files")
    if not isinstance(raw_files, list):
        raise PatentSourceContractError("files must be a list")
    if len(raw_files) != len(ROLE_MEMBERS):
        raise PatentSourceContractError("files must contain exactly the three required roles")

    files: dict[str, ValidatedPatentFile] = {}
    for index, raw_file in enumerate(raw_files):
        if not isinstance(raw_file, Mapping):
            raise PatentSourceContractError(f"files[{index}] must be an object")
        role = _required_text(raw_file.get("role"), label=f"files[{index}].role")
        if role not in ROLE_MEMBERS:
            raise PatentSourceContractError(f"unknown patent source role: {role}")
        if role in files:
            raise PatentSourceContractError(f"duplicate patent source role: {role}")
        member = _required_text(raw_file.get("archive_member"), label=f"{role} archive_member")
        if member != ROLE_MEMBERS[role]:
            raise PatentSourceContractError(f"{role} archive_member must be {ROLE_MEMBERS[role]}")
        declared_sha = _required_text(raw_file.get("sha256"), label=f"{role} sha256")
        if not SHA256_RE.fullmatch(declared_sha):
            raise PatentSourceContractError(f"{role} sha256 is invalid")
        declared_size = _strict_int(
            raw_file.get("size_bytes"), label=f"{role} size_bytes", positive=True
        )
        declared_headers = _declared_headers(raw_file.get("headers"), role=role)
        path = _safe_local_path(base_dir, raw_file.get("local_path"), role=role)
        observed_sha, observed_size = _sha256_path(path)
        if observed_size != declared_size:
            raise PatentSourceContractError(f"{role} archive size does not match its pin")
        if observed_sha != declared_sha:
            raise PatentSourceContractError(f"{role} archive SHA-256 does not match its pin")
        headers = _observed_headers(path, role=role, member=member)
        if headers != declared_headers:
            raise PatentSourceContractError(f"{role} archive headers do not match their pin")
        files[role] = ValidatedPatentFile(
            role=role,
            path=path,
            archive_member=member,
            sha256=observed_sha,
            size_bytes=observed_size,
            headers=headers,
        )

    if set(files) != set(ROLE_MEMBERS):
        raise PatentSourceContractError("source bundle does not contain every required role")
    source_release_id = _derive_release_id(
        release_date=release_date,
        data_through_date=data_through_date,
        files=files,
    )
    declared_release_id = manifest.get("source_release_id")
    if declared_release_id is not None and declared_release_id != source_release_id:
        raise PatentSourceContractError("source_release_id does not match verified source content")
    return ValidatedPatentBundle(
        source_release_id=source_release_id,
        release_date=release_date,
        data_through_date=data_through_date,
        source_url=source_url,
        license_url=license_url,
        files=dict(files),
    )


def _read_verified_rows(file: ValidatedPatentFile) -> list[dict[str, str]]:
    try:
        archive_bytes = file.path.read_bytes()
        if len(archive_bytes) != file.size_bytes:
            raise PatentSourceContractError(f"{file.role} archive size changed after validation")
        if hashlib.sha256(archive_bytes).hexdigest() != file.sha256:
            raise PatentSourceContractError(f"{file.role} archive SHA-256 changed after validation")
        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
            matches = [info for info in archive.infolist() if info.filename == file.archive_member]
            if len(matches) != 1:
                raise PatentSourceContractError(
                    f"{file.role} archive member changed after validation"
                )
            rows: list[dict[str, str]] = []
            with archive.open(matches[0]) as raw:
                with io.TextIOWrapper(
                    raw, encoding="utf-8-sig", errors="strict", newline=""
                ) as text:
                    reader = csv.DictReader(text, delimiter="\t", strict=True)
                    if tuple(reader.fieldnames or ()) != file.headers:
                        raise PatentSourceContractError(
                            f"{file.role} archive headers changed after validation"
                        )
                    for row in reader:
                        if None in row or any(value is None for value in row.values()):
                            raise PatentSourceContractError(
                                f"{file.role} archive contains a malformed TSV row"
                            )
                        rows.append(dict(row))
            return rows
    except (OSError, UnicodeDecodeError, csv.Error, zipfile.BadZipFile) as exc:
        raise PatentSourceContractError(
            f"{file.role} archive changed or became unreadable after validation"
        ) from exc


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _source_id(value: object, *, label: str) -> str:
    source_id = _required_text(value, label=label)
    if value != source_id:
        raise PatentSourceContractError(f"{label} must not contain surrounding whitespace")
    return source_id


def _binary_flag(value: object, *, label: str) -> bool:
    if value not in {"0", "1"}:
        raise PatentSourceContractError(f"{label} must be 0 or 1")
    return value == "1"


def materialize_patent_grant_events(bundle: ValidatedPatentBundle) -> list[dict[str, Any]]:
    """Reduce a verified synthetic/small bundle to native patent-grant events.

    This in-memory reducer proves the contract only; it is not a production bulk
    materializer and makes no source-coverage claim.
    """

    if set(bundle.files) != set(ROLE_MEMBERS):
        raise PatentSourceContractError("validated patent bundle must contain exactly three roles")
    for role, file in bundle.files.items():
        if file.role != role or file.archive_member != ROLE_MEMBERS[role]:
            raise PatentSourceContractError(
                f"validated patent bundle has invalid {role} role metadata"
            )
    expected_release_id = _derive_release_id(
        release_date=bundle.release_date,
        data_through_date=bundle.data_through_date,
        files=bundle.files,
    )
    if bundle.source_release_id != expected_release_id:
        raise PatentSourceContractError("validated patent bundle source_release_id is stale")

    patent_rows = _read_verified_rows(bundle.files["patent"])
    application_rows = _read_verified_rows(bundle.files["application"])
    assignee_rows = _read_verified_rows(bundle.files["assignee"])

    patents: dict[str, tuple[str, str | None, bool]] = {}
    for row in patent_rows:
        patent_id = _source_id(row.get("patent_id"), label="patent patent_id")
        patent_date = _iso_date(row.get("patent_date"), label=f"patent {patent_id} date")
        if patent_date is None:
            raise AssertionError("required patent date was not parsed")
        if patent_date > bundle.data_through_date:
            raise PatentSourceContractError(
                f"patent {patent_id} date follows the bundle data_through_date"
            )
        patent_value = (
            patent_date.isoformat(),
            _optional_text(row.get("patent_title")),
            _binary_flag(row.get("withdrawn"), label=f"patent {patent_id} withdrawn"),
        )
        prior_patent = patents.get(patent_id)
        if prior_patent is not None and prior_patent != patent_value:
            raise PatentSourceContractError(f"patent {patent_id} has conflicting rows")
        patents[patent_id] = patent_value

    applications: dict[str, str | None] = {}
    for row in application_rows:
        patent_id = _source_id(row.get("patent_id"), label="application patent_id")
        if patent_id not in patents:
            raise PatentSourceContractError(f"application references unknown patent {patent_id}")
        filing_date = _iso_date(
            row.get("filing_date"), label=f"application {patent_id} filing_date", optional=True
        )
        if filing_date is not None and filing_date > date.fromisoformat(patents[patent_id][0]):
            raise PatentSourceContractError(
                f"application {patent_id} filing_date follows its patent grant date"
            )
        application_value = filing_date.isoformat() if filing_date else None
        if patent_id in applications and applications[patent_id] != application_value:
            raise PatentSourceContractError(f"patent {patent_id} has conflicting applications")
        applications[patent_id] = application_value

    assignees: dict[tuple[str, str], tuple[str | None, str | None]] = {}
    for row in assignee_rows:
        patent_id = _source_id(row.get("patent_id"), label="assignee patent_id")
        assignee_id = _source_id(row.get("assignee_id"), label=f"patent {patent_id} assignee_id")
        if patent_id not in patents:
            raise PatentSourceContractError(f"assignee references unknown patent {patent_id}")
        key = (assignee_id, patent_id)
        assignee_value = (
            _optional_text(row.get("disambig_assignee_organization")),
            _optional_text(row.get("assignee_type")),
        )
        prior_assignee = assignees.get(key)
        if prior_assignee is not None and prior_assignee != assignee_value:
            raise PatentSourceContractError(f"assignee/patent key {key!r} has conflicting rows")
        assignees[key] = assignee_value

    events: list[dict[str, Any]] = []
    for (assignee_id, patent_id), (organization, assignee_type) in sorted(assignees.items()):
        event_date, patent_title, withdrawn = patents[patent_id]
        if withdrawn:
            continue
        event = {
            "application_filing_date": applications.get(patent_id),
            "assignee_id": assignee_id,
            "assignee_organization": organization,
            "assignee_type": assignee_type,
            "event_date": event_date,
            "event_type": EVENT_TYPE,
            "patent_id": patent_id,
            "patent_title": patent_title,
            "schema_version": SCHEMA_VERSION,
            "source_release_id": bundle.source_release_id,
        }
        if set(event) != EVENT_FIELDS:
            raise AssertionError("native patent event schema drifted")
        events.append(event)
    return events


def _valid_cik(value: object) -> str:
    cik = _required_text(value, label="form_d_cik")
    if value != cik or not CIK_RE.fullmatch(cik):
        raise PatentSourceContractError("form_d_cik must be an unpadded SEC CIK")
    return cik


def validate_patent_bridge_candidates(
    rows: Iterable[Mapping[str, Any]], *, source_release_id: str
) -> list[dict[str, Any]]:
    """Validate exact-name bridge evidence without accepting an identity link."""

    expected_release_id = _required_text(source_release_id, label="source_release_id")
    if not SHA256_RE.fullmatch(expected_release_id):
        raise PatentSourceContractError("source_release_id must be a lowercase SHA-256 digest")
    candidates: dict[tuple[str, str, str], dict[str, Any]] = {}
    for index, raw_row in enumerate(rows):
        if not isinstance(raw_row, Mapping):
            raise PatentSourceContractError(f"bridge row {index} must be an object")
        if set(raw_row) != BRIDGE_FIELDS:
            raise PatentSourceContractError(
                f"bridge row {index} must contain only the candidate contract fields"
            )
        version = _strict_int(raw_row.get("bridge_schema_version"), label="bridge_schema_version")
        if version != BRIDGE_SCHEMA_VERSION:
            raise PatentSourceContractError("unsupported bridge_schema_version")
        if raw_row.get("source_release_id") != expected_release_id:
            raise PatentSourceContractError("bridge source_release_id does not match the source")
        cik = _valid_cik(raw_row.get("form_d_cik"))
        assignee_id = _source_id(raw_row.get("assignee_id"), label="assignee_id")
        if raw_row.get("normalizer_profile") != NORMALIZER_PROFILE.value:
            raise PatentSourceContractError("bridge normalizer_profile is not pinned")
        normalized_name = _required_text(
            raw_row.get("normalized_name_key"), label="normalized_name_key"
        )
        if normalize_company_name(normalized_name, profile=NORMALIZER_PROFILE) != normalized_name:
            raise PatentSourceContractError("normalized_name_key is not canonical")
        if raw_row.get("evidence_method") != EVIDENCE_METHOD:
            raise PatentSourceContractError("bridge evidence_method must be exact normalized name")
        status = raw_row.get("candidate_status")
        if not isinstance(status, str) or status not in VALID_CANDIDATE_STATUSES:
            raise PatentSourceContractError("candidate_status must be candidate or ambiguous")
        candidate = {
            "assignee_id": assignee_id,
            "bridge_schema_version": BRIDGE_SCHEMA_VERSION,
            "candidate_status": status,
            "evidence_method": EVIDENCE_METHOD,
            "form_d_cik": cik,
            "normalized_name_key": normalized_name,
            "normalizer_profile": NORMALIZER_PROFILE.value,
            "source_release_id": expected_release_id,
        }
        key = (normalized_name, cik, assignee_id)
        prior = candidates.get(key)
        if prior is not None and prior != candidate:
            raise PatentSourceContractError(f"bridge candidate {key!r} has conflicting rows")
        candidates[key] = candidate

    identities_by_name: dict[str, tuple[set[str], set[str]]] = defaultdict(lambda: (set(), set()))
    for normalized_name, cik, assignee_id in candidates:
        ciks, assignees = identities_by_name[normalized_name]
        ciks.add(cik)
        assignees.add(assignee_id)
    for key, candidate in candidates.items():
        ciks, assignees = identities_by_name[key[0]]
        if (len(ciks) > 1 or len(assignees) > 1) and candidate["candidate_status"] != "ambiguous":
            raise PatentSourceContractError(
                f"normalized name {key[0]!r} maps to multiple identities and must be ambiguous"
            )
    return [candidates[key] for key in sorted(candidates)]
