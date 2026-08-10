"""Fail-closed USAspending prime-contract source contract.

This module validates a local, content-pinned set of closed-fiscal-year
``All_Contracts_Full`` archives and reduces synthetic/small fixtures to
transaction-native contract actions. It deliberately does not download data,
resolve firms, establish per-firm coverage, classify new awards, or emit study
outcomes.
"""

import csv
import hashlib
import io
import json
import re
import zipfile
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlsplit

from sbir_etl.utils.identifiers import normalize_duns, normalize_uei


SCHEMA_VERSION = 1
PRODUCT = "All_Contracts_Full"
EVENT_TYPE = "usaspending_prime_contract_action"
SOURCE_RELEASE_DOMAIN = "usaspending-contract-source-release-v1"
DOWNLOAD_HOST = "files.usaspending.gov"
DOWNLOAD_PATH_PREFIX = "/award_data_archive/"

SHA256_RE = re.compile(r"[0-9a-f]{64}")
ARCHIVE_FILENAME_RE = re.compile(
    r"FY(?P<fiscal_year>[0-9]{4})_All_Contracts_Full_(?P<updated>[0-9]{8})\.zip"
)
DECIMAL_RE = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?")
ASCII_YEAR_RE = re.compile(r"[0-9]{4}")
UEI_SOURCE_RE = re.compile(r"[A-Za-z0-9-]+")
DUNS_SOURCE_RE = re.compile(r"[0-9-]+")

REQUIRED_HEADERS = (
    "contract_transaction_unique_key",
    "contract_award_unique_key",
    "modification_number",
    "federal_action_obligation",
    "action_date",
    "action_date_fiscal_year",
    "period_of_performance_start_date",
    "recipient_uei",
    "recipient_duns",
    "award_or_idv_flag",
    "award_type_code",
    "idv_type_code",
    "action_type_code",
)

EVENT_FIELDS = frozenset(
    {
        "action_date",
        "action_type_code",
        "award_or_idv_flag",
        "award_type_code",
        "contract_award_unique_key",
        "contract_transaction_unique_key",
        "event_type",
        "federal_action_obligation",
        "idv_type_code",
        "modification_number",
        "period_of_performance_start_date",
        "recipient_duns",
        "recipient_uei",
        "schema_version",
        "source_fiscal_year",
        "source_release_id",
    }
)


class USAspendingContractSourceError(ValueError):
    """Raised when evidence cannot satisfy the USAspending source contract."""


@dataclass(frozen=True)
class ValidatedUSAspendingMember:
    """One pinned CSV member in an Award Data Archive ZIP."""

    member_name: str
    size_bytes: int
    crc32: int
    headers: tuple[str, ...]


@dataclass(frozen=True)
class ValidatedUSAspendingArchive:
    """One verified all-agency Contracts Full archive."""

    fiscal_year: int
    upstream_updated_date: date
    filename: str
    source_url: str
    path: Path
    sha256: str
    size_bytes: int
    members: tuple[ValidatedUSAspendingMember, ...]


@dataclass(frozen=True)
class ValidatedUSAspendingBundle:
    """A verified contiguous set of closed-fiscal-year archives."""

    source_release_id: str
    source_snapshot_date: date
    start_fiscal_year: int
    end_fiscal_year: int
    archives: Mapping[int, ValidatedUSAspendingArchive]


def _required_text(value: object, *, label: str, exact: bool = False) -> str:
    if not isinstance(value, str) or not value.strip():
        raise USAspendingContractSourceError(f"{label} must be a nonblank string")
    text = value.strip()
    if exact and value != text:
        raise USAspendingContractSourceError(f"{label} must not contain surrounding whitespace")
    return text


def _strict_int(
    value: object,
    *,
    label: str,
    positive: bool = False,
    maximum: int | None = None,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise USAspendingContractSourceError(f"{label} must be an integer")
    if value < (1 if positive else 0):
        qualifier = "positive" if positive else "non-negative"
        raise USAspendingContractSourceError(f"{label} must be {qualifier}")
    if maximum is not None and value > maximum:
        raise USAspendingContractSourceError(f"{label} exceeds its maximum")
    return value


def _iso_date(value: object, *, label: str, optional: bool = False) -> date | None:
    if optional and (value is None or value == ""):
        return None
    text = _required_text(value, label=label, exact=True)
    try:
        parsed = date.fromisoformat(text)
    except ValueError as exc:
        raise USAspendingContractSourceError(f"{label} must be an ISO date") from exc
    if parsed.isoformat() != text:
        raise USAspendingContractSourceError(f"{label} must be a canonical ISO date")
    return parsed


def _safe_local_path(base_dir: Path, value: object, *, fiscal_year: int) -> Path:
    raw_path = _required_text(value, label=f"FY{fiscal_year} local_path", exact=True)
    relative = Path(raw_path)
    if relative.is_absolute() or ".." in relative.parts:
        raise USAspendingContractSourceError(
            f"FY{fiscal_year} local_path must stay within base_dir"
        )
    base = base_dir.resolve()
    resolved = (base / relative).resolve()
    if resolved != base and base not in resolved.parents:
        raise USAspendingContractSourceError(f"FY{fiscal_year} local_path escapes base_dir")
    if not resolved.is_file():
        raise USAspendingContractSourceError(f"FY{fiscal_year} archive is missing")
    return resolved


def _sha256_path(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
            size += len(block)
    return digest.hexdigest(), size


def _declared_headers(value: object, *, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise USAspendingContractSourceError(f"{label} headers must be a nonempty list")
    headers = tuple(_required_text(item, label=f"{label} header", exact=True) for item in value)
    folded = [header.casefold() for header in headers]
    if len(folded) != len(set(folded)):
        raise USAspendingContractSourceError(f"{label} headers contain duplicates")
    missing = set(REQUIRED_HEADERS) - set(headers)
    if missing:
        raise USAspendingContractSourceError(
            f"{label} is missing required headers: {sorted(missing)}"
        )
    return headers


def _member_name(value: object, *, label: str) -> str:
    name = _required_text(value, label=label, exact=True)
    pure = PurePosixPath(name)
    if pure.is_absolute() or pure.name != name or ".." in pure.parts:
        raise USAspendingContractSourceError(f"{label} must be a flat archive member name")
    if not name.lower().endswith(".csv"):
        raise USAspendingContractSourceError(f"{label} must identify a CSV member")
    return name


def _read_member_headers(
    archive: zipfile.ZipFile, info: zipfile.ZipInfo, *, label: str
) -> tuple[str, ...]:
    if info.flag_bits & 0x1:
        raise USAspendingContractSourceError(f"{label} must not be encrypted")
    try:
        with archive.open(info) as raw:
            with io.TextIOWrapper(raw, encoding="utf-8-sig", errors="strict", newline="") as text:
                reader = csv.reader(text, strict=True)
                try:
                    raw_headers = next(reader)
                except StopIteration as exc:
                    raise USAspendingContractSourceError(f"{label} is empty") from exc
    except (OSError, UnicodeDecodeError, csv.Error, zipfile.BadZipFile) as exc:
        raise USAspendingContractSourceError(f"{label} is not a readable UTF-8 CSV") from exc
    headers = tuple(raw_headers)
    if any(not header for header in headers):
        raise USAspendingContractSourceError(f"{label} has a blank header")
    if any(header != header.strip() for header in headers):
        raise USAspendingContractSourceError(
            f"{label} headers must not contain surrounding whitespace"
        )
    folded = [header.casefold() for header in headers]
    if len(folded) != len(set(folded)):
        raise USAspendingContractSourceError(f"{label} has duplicate headers")
    missing = set(REQUIRED_HEADERS) - set(headers)
    if missing:
        raise USAspendingContractSourceError(
            f"{label} is missing required headers: {sorted(missing)}"
        )
    return headers


def _archive_filename(value: object, *, fiscal_year: int, upstream_updated_date: date) -> str:
    filename = _required_text(value, label=f"FY{fiscal_year} filename", exact=True)
    match = ARCHIVE_FILENAME_RE.fullmatch(filename)
    if match is None:
        raise USAspendingContractSourceError(
            f"FY{fiscal_year} filename must identify an all-agency Contracts Full archive"
        )
    if int(match["fiscal_year"]) != fiscal_year:
        raise USAspendingContractSourceError(f"FY{fiscal_year} filename fiscal year disagrees")
    if match["updated"] != upstream_updated_date.strftime("%Y%m%d"):
        raise USAspendingContractSourceError(f"FY{fiscal_year} filename update date disagrees")
    return filename


def _source_url(value: object, *, fiscal_year: int, filename: str) -> str:
    url = _required_text(value, label=f"FY{fiscal_year} source_url", exact=True)
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.netloc != DOWNLOAD_HOST
        or parsed.path != f"{DOWNLOAD_PATH_PREFIX}{filename}"
        or parsed.query
        or parsed.fragment
    ):
        raise USAspendingContractSourceError(
            f"FY{fiscal_year} source_url must be the official archive URL"
        )
    return url


def _validate_archive_members(
    path: Path,
    *,
    fiscal_year: int,
    declared_members: object,
) -> tuple[ValidatedUSAspendingMember, ...]:
    if not isinstance(declared_members, list) or not declared_members:
        raise USAspendingContractSourceError(f"FY{fiscal_year} members must be a nonempty list")
    declared: dict[str, tuple[int, int, tuple[str, ...]]] = {}
    for index, row in enumerate(declared_members):
        if not isinstance(row, Mapping):
            raise USAspendingContractSourceError(
                f"FY{fiscal_year} members[{index}] must be an object"
            )
        label = f"FY{fiscal_year} members[{index}]"
        name = _member_name(row.get("member_name"), label=f"{label}.member_name")
        if name in declared:
            raise USAspendingContractSourceError(f"FY{fiscal_year} has duplicate declared members")
        size = _strict_int(row.get("size_bytes"), label=f"{label}.size_bytes", positive=True)
        crc = _strict_int(row.get("crc32"), label=f"{label}.crc32", maximum=0xFFFFFFFF)
        headers = _declared_headers(row.get("headers"), label=label)
        declared[name] = (size, crc, headers)

    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            if any(info.is_dir() for info in infos):
                raise USAspendingContractSourceError(
                    f"FY{fiscal_year} archive must contain only flat CSV members"
                )
            names = [info.filename for info in infos]
            if len(names) != len(set(names)):
                raise USAspendingContractSourceError(
                    f"FY{fiscal_year} archive has duplicate member names"
                )
            if set(names) != set(declared):
                raise USAspendingContractSourceError(
                    f"FY{fiscal_year} archive members do not match their pins"
                )
            verified: list[ValidatedUSAspendingMember] = []
            archive_headers: tuple[str, ...] | None = None
            for info in sorted(infos, key=lambda item: item.filename):
                _member_name(info.filename, label=f"FY{fiscal_year} archive member")
                size, crc, declared_header = declared[info.filename]
                if info.file_size != size or info.CRC != crc:
                    raise USAspendingContractSourceError(
                        f"FY{fiscal_year} member size or CRC does not match its pin"
                    )
                headers = _read_member_headers(
                    archive,
                    info,
                    label=f"FY{fiscal_year} member {info.filename}",
                )
                if headers != declared_header:
                    raise USAspendingContractSourceError(
                        f"FY{fiscal_year} member headers do not match their pin"
                    )
                if archive_headers is not None and headers != archive_headers:
                    raise USAspendingContractSourceError(
                        f"FY{fiscal_year} archive members have different schemas"
                    )
                archive_headers = headers
                verified.append(
                    ValidatedUSAspendingMember(
                        member_name=info.filename,
                        size_bytes=info.file_size,
                        crc32=info.CRC,
                        headers=headers,
                    )
                )
    except (OSError, zipfile.BadZipFile) as exc:
        raise USAspendingContractSourceError(
            f"FY{fiscal_year} archive is not a readable ZIP"
        ) from exc
    return tuple(verified)


def _canonical_release_payload(
    *,
    source_snapshot_date: date,
    start_fiscal_year: int,
    end_fiscal_year: int,
    archives: Mapping[int, ValidatedUSAspendingArchive],
) -> bytes:
    payload = {
        "archives": [
            {
                "filename": archive.filename,
                "fiscal_year": archive.fiscal_year,
                "members": [
                    {
                        "crc32": member.crc32,
                        "headers": list(member.headers),
                        "member_name": member.member_name,
                        "size_bytes": member.size_bytes,
                    }
                    for member in archive.members
                ],
                "sha256": archive.sha256,
                "size_bytes": archive.size_bytes,
                "source_url": archive.source_url,
                "upstream_updated_date": archive.upstream_updated_date.isoformat(),
            }
            for _, archive in sorted(archives.items())
        ],
        "end_fiscal_year": end_fiscal_year,
        "product": PRODUCT,
        "schema_version": SCHEMA_VERSION,
        "source_snapshot_date": source_snapshot_date.isoformat(),
        "start_fiscal_year": start_fiscal_year,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()


def _derive_release_id(
    *,
    source_snapshot_date: date,
    start_fiscal_year: int,
    end_fiscal_year: int,
    archives: Mapping[int, ValidatedUSAspendingArchive],
) -> str:
    payload = _canonical_release_payload(
        source_snapshot_date=source_snapshot_date,
        start_fiscal_year=start_fiscal_year,
        end_fiscal_year=end_fiscal_year,
        archives=archives,
    )
    return hashlib.sha256(SOURCE_RELEASE_DOMAIN.encode() + b"\0" + payload).hexdigest()


def validate_usaspending_contract_source_bundle(
    manifest: Mapping[str, Any], *, base_dir: Path
) -> ValidatedUSAspendingBundle:
    """Verify a local contiguous set of closed-year Contracts Full archives."""

    if not isinstance(manifest, Mapping):
        raise USAspendingContractSourceError("manifest must be an object")
    version = _strict_int(manifest.get("schema_version"), label="schema_version")
    if version != SCHEMA_VERSION:
        raise USAspendingContractSourceError("unsupported schema_version")
    if manifest.get("product") != PRODUCT:
        raise USAspendingContractSourceError(f"product must be {PRODUCT}")
    snapshot = _iso_date(manifest.get("source_snapshot_date"), label="source_snapshot_date")
    if snapshot is None:
        raise AssertionError("required snapshot date was not parsed")
    start_fy = _strict_int(
        manifest.get("start_fiscal_year"), label="start_fiscal_year", positive=True
    )
    end_fy = _strict_int(manifest.get("end_fiscal_year"), label="end_fiscal_year", positive=True)
    if end_fy < start_fy:
        raise USAspendingContractSourceError("end_fiscal_year must not precede start_fiscal_year")
    latest_closed_fy = snapshot.year + (snapshot.month >= 10) - 1
    if end_fy > latest_closed_fy:
        raise USAspendingContractSourceError(f"FY{end_fy} is not closed as of source_snapshot_date")

    raw_archives = manifest.get("archives")
    if not isinstance(raw_archives, list):
        raise USAspendingContractSourceError("archives must be a list")
    expected_years = set(range(start_fy, end_fy + 1))
    if len(raw_archives) != len(expected_years):
        raise USAspendingContractSourceError(
            "archives must contain exactly one entry for every fiscal year"
        )

    archives: dict[int, ValidatedUSAspendingArchive] = {}
    for index, row in enumerate(raw_archives):
        if not isinstance(row, Mapping):
            raise USAspendingContractSourceError(f"archives[{index}] must be an object")
        fiscal_year = _strict_int(row.get("fiscal_year"), label=f"archives[{index}].fiscal_year")
        if fiscal_year not in expected_years:
            raise USAspendingContractSourceError(
                f"archive FY{fiscal_year} is outside the declared fiscal-year range"
            )
        if fiscal_year in archives:
            raise USAspendingContractSourceError(f"duplicate archive fiscal year: {fiscal_year}")
        updated = _iso_date(
            row.get("upstream_updated_date"),
            label=f"FY{fiscal_year} upstream_updated_date",
        )
        if updated is None:
            raise AssertionError("required upstream date was not parsed")
        if updated > snapshot:
            raise USAspendingContractSourceError(
                f"FY{fiscal_year} upstream_updated_date follows source_snapshot_date"
            )
        filename = _archive_filename(
            row.get("filename"),
            fiscal_year=fiscal_year,
            upstream_updated_date=updated,
        )
        source_url = _source_url(row.get("source_url"), fiscal_year=fiscal_year, filename=filename)
        path = _safe_local_path(base_dir, row.get("local_path"), fiscal_year=fiscal_year)
        declared_sha = _required_text(
            row.get("sha256"), label=f"FY{fiscal_year} sha256", exact=True
        )
        if not SHA256_RE.fullmatch(declared_sha):
            raise USAspendingContractSourceError(f"FY{fiscal_year} sha256 is invalid")
        declared_size = _strict_int(
            row.get("size_bytes"), label=f"FY{fiscal_year} size_bytes", positive=True
        )
        observed_sha, observed_size = _sha256_path(path)
        if observed_size != declared_size:
            raise USAspendingContractSourceError(
                f"FY{fiscal_year} archive size does not match its pin"
            )
        if observed_sha != declared_sha:
            raise USAspendingContractSourceError(
                f"FY{fiscal_year} archive SHA-256 does not match its pin"
            )
        members = _validate_archive_members(
            path,
            fiscal_year=fiscal_year,
            declared_members=row.get("members"),
        )
        archives[fiscal_year] = ValidatedUSAspendingArchive(
            fiscal_year=fiscal_year,
            upstream_updated_date=updated,
            filename=filename,
            source_url=source_url,
            path=path,
            sha256=observed_sha,
            size_bytes=observed_size,
            members=members,
        )

    if set(archives) != expected_years:
        raise USAspendingContractSourceError("archive fiscal years are not contiguous")
    release_id = _derive_release_id(
        source_snapshot_date=snapshot,
        start_fiscal_year=start_fy,
        end_fiscal_year=end_fy,
        archives=archives,
    )
    declared_release_id = manifest.get("source_release_id")
    if declared_release_id is not None and declared_release_id != release_id:
        raise USAspendingContractSourceError(
            "source_release_id does not match verified source content"
        )
    return ValidatedUSAspendingBundle(
        source_release_id=release_id,
        source_snapshot_date=snapshot,
        start_fiscal_year=start_fy,
        end_fiscal_year=end_fy,
        archives=dict(archives),
    )


def _optional_text(value: object, *, label: str) -> str | None:
    if value is None:
        return None
    text = str(value)
    if not text:
        return None
    if text != text.strip():
        raise USAspendingContractSourceError(f"{label} must not contain surrounding whitespace")
    return text


def _source_id(value: object, *, label: str) -> str:
    return _required_text(value, label=label, exact=True)


def _source_fiscal_year(value: object, *, label: str) -> int:
    text = _required_text(value, label=label, exact=True)
    if not ASCII_YEAR_RE.fullmatch(text):
        raise USAspendingContractSourceError(f"{label} must be a four-digit fiscal year")
    return int(text)


def _obligation(value: object, *, label: str) -> str | None:
    if value is None or value == "":
        return None
    text = str(value)
    if text != text.strip():
        raise USAspendingContractSourceError(f"{label} must be a canonical decimal")
    if not DECIMAL_RE.fullmatch(text):
        raise USAspendingContractSourceError(f"{label} must be a canonical decimal")
    try:
        number = Decimal(text)
    except InvalidOperation as exc:
        raise USAspendingContractSourceError(f"{label} must be a canonical decimal") from exc
    if not number.is_finite():
        raise USAspendingContractSourceError(f"{label} must be finite")
    return text


def _identifier(value: object, *, label: str, kind: str) -> str | None:
    text = _optional_text(value, label=label)
    if text is None:
        return None
    source_pattern = UEI_SOURCE_RE if kind == "UEI" else DUNS_SOURCE_RE
    if not source_pattern.fullmatch(text):
        raise USAspendingContractSourceError(f"{label} is not a valid {kind}")
    normalized = normalize_uei(text) if kind == "UEI" else normalize_duns(text)
    if normalized is None:
        raise USAspendingContractSourceError(f"{label} is not a valid {kind}")
    return normalized


def _iter_verified_rows(
    archive_file: ValidatedUSAspendingArchive,
) -> Iterator[tuple[str, dict[str, str]]]:
    observed_sha, observed_size = _sha256_path(archive_file.path)
    if observed_size != archive_file.size_bytes or observed_sha != archive_file.sha256:
        raise USAspendingContractSourceError(
            f"FY{archive_file.fiscal_year} archive changed after validation"
        )
    members = {member.member_name: member for member in archive_file.members}
    try:
        with zipfile.ZipFile(archive_file.path) as archive:
            infos = archive.infolist()
            if any(info.is_dir() for info in infos):
                raise USAspendingContractSourceError(
                    f"FY{archive_file.fiscal_year} members changed after validation"
                )
            names = [info.filename for info in infos]
            if len(names) != len(set(names)) or set(names) != set(members):
                raise USAspendingContractSourceError(
                    f"FY{archive_file.fiscal_year} members changed after validation"
                )
            for info in sorted(infos, key=lambda item: item.filename):
                member = members[info.filename]
                if info.file_size != member.size_bytes or info.CRC != member.crc32:
                    raise USAspendingContractSourceError(
                        f"FY{archive_file.fiscal_year} member metadata changed after validation"
                    )
                with archive.open(info) as raw:
                    with io.TextIOWrapper(
                        raw,
                        encoding="utf-8-sig",
                        errors="strict",
                        newline="",
                    ) as text:
                        reader = csv.DictReader(text, strict=True)
                        if tuple(reader.fieldnames or ()) != member.headers:
                            raise USAspendingContractSourceError(
                                f"FY{archive_file.fiscal_year} headers changed after validation"
                            )
                        for row in reader:
                            if None in row or any(value is None for value in row.values()):
                                raise USAspendingContractSourceError(
                                    f"FY{archive_file.fiscal_year} contains a malformed CSV row"
                                )
                            yield info.filename, dict(row)
    except (OSError, UnicodeDecodeError, csv.Error, zipfile.BadZipFile) as exc:
        raise USAspendingContractSourceError(
            f"FY{archive_file.fiscal_year} archive changed or became unreadable"
        ) from exc
    final_sha, final_size = _sha256_path(archive_file.path)
    if final_size != archive_file.size_bytes or final_sha != archive_file.sha256:
        raise USAspendingContractSourceError(
            f"FY{archive_file.fiscal_year} archive changed during materialization"
        )


def _validate_bundle_identity(bundle: ValidatedUSAspendingBundle) -> None:
    expected_years = set(range(bundle.start_fiscal_year, bundle.end_fiscal_year + 1))
    if set(bundle.archives) != expected_years:
        raise USAspendingContractSourceError(
            "validated USAspending bundle must contain its exact contiguous fiscal-year range"
        )
    for fiscal_year, archive in bundle.archives.items():
        if archive.fiscal_year != fiscal_year:
            raise USAspendingContractSourceError(
                f"validated USAspending bundle has invalid FY{fiscal_year} metadata"
            )
    expected_release = _derive_release_id(
        source_snapshot_date=bundle.source_snapshot_date,
        start_fiscal_year=bundle.start_fiscal_year,
        end_fiscal_year=bundle.end_fiscal_year,
        archives=bundle.archives,
    )
    if bundle.source_release_id != expected_release:
        raise USAspendingContractSourceError(
            "validated USAspending bundle source_release_id is stale"
        )


def materialize_usaspending_contract_action_events(
    bundle: ValidatedUSAspendingBundle,
) -> list[dict[str, Any]]:
    """Reduce a verified synthetic/small bundle to neutral contract actions."""

    _validate_bundle_identity(bundle)
    events: list[dict[str, Any]] = []
    transaction_keys: set[str] = set()
    for fiscal_year, archive in sorted(bundle.archives.items()):
        for member_name, row in _iter_verified_rows(archive):
            transaction_key = _source_id(
                row.get("contract_transaction_unique_key"),
                label=f"FY{fiscal_year} {member_name} transaction key",
            )
            if transaction_key in transaction_keys:
                raise USAspendingContractSourceError(
                    f"duplicate contract transaction key in release: {transaction_key}"
                )
            transaction_keys.add(transaction_key)
            award_key = _source_id(
                row.get("contract_award_unique_key"),
                label=f"transaction {transaction_key} award key",
            )
            action_date = _iso_date(
                row.get("action_date"), label=f"transaction {transaction_key} action_date"
            )
            if action_date is None:
                raise AssertionError("required action date was not parsed")
            derived_fy = action_date.year + (action_date.month >= 10)
            declared_fy = _source_fiscal_year(
                row.get("action_date_fiscal_year"),
                label=f"transaction {transaction_key} action_date_fiscal_year",
            )
            if derived_fy != fiscal_year or declared_fy != fiscal_year:
                raise USAspendingContractSourceError(
                    f"transaction {transaction_key} action date fiscal year disagrees with FY{fiscal_year}"
                )
            award_flag = _source_id(
                row.get("award_or_idv_flag"),
                label=f"transaction {transaction_key} award_or_idv_flag",
            )
            if award_flag not in {"AWARD", "IDV"}:
                raise USAspendingContractSourceError(
                    f"transaction {transaction_key} award_or_idv_flag must be AWARD or IDV"
                )
            performance_start = _iso_date(
                row.get("period_of_performance_start_date"),
                label=f"transaction {transaction_key} period_of_performance_start_date",
                optional=True,
            )
            event = {
                "action_date": action_date.isoformat(),
                "action_type_code": _optional_text(
                    row.get("action_type_code"),
                    label=f"transaction {transaction_key} action_type_code",
                ),
                "award_or_idv_flag": award_flag,
                "award_type_code": _optional_text(
                    row.get("award_type_code"),
                    label=f"transaction {transaction_key} award_type_code",
                ),
                "contract_award_unique_key": award_key,
                "contract_transaction_unique_key": transaction_key,
                "event_type": EVENT_TYPE,
                "federal_action_obligation": _obligation(
                    row.get("federal_action_obligation"),
                    label=f"transaction {transaction_key} federal_action_obligation",
                ),
                "idv_type_code": _optional_text(
                    row.get("idv_type_code"),
                    label=f"transaction {transaction_key} idv_type_code",
                ),
                "modification_number": _optional_text(
                    row.get("modification_number"),
                    label=f"transaction {transaction_key} modification_number",
                ),
                "period_of_performance_start_date": (
                    performance_start.isoformat() if performance_start else None
                ),
                "recipient_duns": _identifier(
                    row.get("recipient_duns"),
                    label=f"transaction {transaction_key} recipient_duns",
                    kind="DUNS",
                ),
                "recipient_uei": _identifier(
                    row.get("recipient_uei"),
                    label=f"transaction {transaction_key} recipient_uei",
                    kind="UEI",
                ),
                "schema_version": SCHEMA_VERSION,
                "source_fiscal_year": fiscal_year,
                "source_release_id": bundle.source_release_id,
            }
            if set(event) != EVENT_FIELDS:
                raise AssertionError("native USAspending action schema drifted")
            events.append(event)
    return sorted(
        events,
        key=lambda event: (
            event["source_fiscal_year"],
            event["contract_transaction_unique_key"],
        ),
    )
