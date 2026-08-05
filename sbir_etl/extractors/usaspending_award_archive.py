"""Memory-bounded ingestion for public USAspending Award Data Archive files."""

import csv
import hashlib
import io
import json
import re
import zipfile
from collections.abc import Iterator, Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO, Literal, cast
from urllib.parse import urlparse

import httpx
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.csv as pa_csv
from loguru import logger

from sbir_etl.models.transition_models import FederalContract

from .contract_extractor import ArchiveSchemaError, ContractExtractor, SourceDataError


ARCHIVE_API_URL = "https://api.usaspending.gov/api/v2/bulk_download/list_monthly_files/"
AWARD_ARCHIVE_SOURCE_KIND = "award_data_archive_contracts"
AWARD_ARCHIVE_PROVENANCE_VERSION = 2
_DOWNLOAD_HOST = "files.usaspending.gov"
_ARCHIVE_PATTERN = re.compile(
    r"^FY(?P<fiscal_year>\d{4})_(?P<agency>.+)_"
    r"(?P<award_type>Contracts|Assistance)_Full_(?P<updated>\d{8})\.zip$"
)

# Only these columns are decoded from each 297-column Contracts_Full CSV. Keeping
# the projection narrow makes Arrow's record batches small even for multi-GB members.
CONTRACT_ARCHIVE_COLUMNS = (
    "contract_transaction_unique_key",
    "contract_award_unique_key",
    "award_id_piid",
    "modification_number",
    "parent_award_agency_id",
    "parent_award_agency_name",
    "parent_award_id_piid",
    "federal_action_obligation",
    "action_date",
    "period_of_performance_start_date",
    "period_of_performance_current_end_date",
    "awarding_agency_name",
    "awarding_sub_agency_name",
    "funding_agency_name",
    "recipient_uei",
    "recipient_duns",
    "recipient_name",
    "cage_code",
    "recipient_parent_uei",
    "recipient_state_code",
    "award_or_idv_flag",
    "award_type_code",
    "award_type",
    "transaction_description",
    "product_or_service_code",
    "naics_code",
    "extent_competed",
    "research",
)


@dataclass(frozen=True)
class AwardArchiveFile:
    """One public archive returned by USAspending's monthly-file endpoint."""

    fiscal_year: int | None
    agency_name: str
    agency_acronym: str | None
    award_type: Literal["contracts", "assistance"]
    updated_date: str
    file_name: str
    url: str

    def __post_init__(self) -> None:
        parsed = urlparse(self.url)
        if self.award_type not in {"contracts", "assistance"}:
            raise SourceDataError(f"Unexpected USAspending archive type: {self.award_type!r}")
        if not self.file_name.endswith(".zip") or Path(self.file_name).name != self.file_name:
            raise SourceDataError(f"Unexpected USAspending archive filename: {self.file_name!r}")
        if (
            parsed.scheme != "https"
            or parsed.hostname != _DOWNLOAD_HOST
            or Path(parsed.path).name != self.file_name
        ):
            raise SourceDataError(f"Unexpected USAspending archive URL: {self.url!r}")

    @classmethod
    def from_api(cls, payload: Mapping[str, object]) -> "AwardArchiveFile":
        file_name = str(payload.get("file_name") or "")
        url = str(payload.get("url") or "")
        award_type = str(payload.get("type") or "").lower()
        if award_type not in {"contracts", "assistance"}:
            raise SourceDataError(f"Unexpected USAspending archive type: {award_type!r}")

        fiscal_year_value = payload.get("fiscal_year")
        if fiscal_year_value is None:
            fiscal_year = None
        elif isinstance(fiscal_year_value, (int, str)) and not isinstance(fiscal_year_value, bool):
            fiscal_year = int(fiscal_year_value)
        else:
            raise SourceDataError(f"Unexpected USAspending fiscal year: {fiscal_year_value!r}")
        return cls(
            fiscal_year=fiscal_year,
            agency_name=str(payload.get("agency_name") or ""),
            agency_acronym=(
                str(payload["agency_acronym"])
                if payload.get("agency_acronym") is not None
                else None
            ),
            award_type=award_type,  # type: ignore[arg-type]
            updated_date=str(payload.get("updated_date") or ""),
            file_name=file_name,
            url=url,
        )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json_atomic(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        temporary.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def discover_full_award_archive(
    fiscal_year: int,
    award_type: Literal["contracts", "assistance"],
    *,
    agency: int | Literal["all"] = "all",
    client: httpx.Client | None = None,
) -> AwardArchiveFile:
    """Return the current pre-generated full archive without authentication."""

    owns_client = client is None
    active_client = client or httpx.Client(timeout=30.0, follow_redirects=True)
    try:
        response = active_client.post(
            ARCHIVE_API_URL,
            json={"agency": agency, "fiscal_year": fiscal_year, "type": award_type},
            headers={"Accept": "application/json"},
        )
        response.raise_for_status()
        payload = response.json()
    finally:
        if owns_client:
            active_client.close()

    if not isinstance(payload, Mapping) or not isinstance(payload.get("monthly_files"), list):
        raise SourceDataError("USAspending archive listing returned an unexpected response")
    candidates = [
        AwardArchiveFile.from_api(item)
        for item in payload["monthly_files"]
        if isinstance(item, Mapping)
    ]
    full_archives = [
        item
        for item in candidates
        if item.fiscal_year == fiscal_year
        and item.award_type == award_type
        and _ARCHIVE_PATTERN.fullmatch(item.file_name)
    ]
    if len(full_archives) != 1:
        raise SourceDataError(
            f"Expected one FY{fiscal_year} {award_type} Full archive; found {len(full_archives)}"
        )
    return full_archives[0]


def _validated_archive_members(path: Path) -> list[zipfile.ZipInfo]:
    try:
        with zipfile.ZipFile(path) as archive:
            members = [info for info in archive.infolist() if not info.is_dir()]
    except (OSError, zipfile.BadZipFile) as error:
        raise SourceDataError(f"Downloaded file is not a valid ZIP archive: {path}") from error
    if not members or any(not info.filename.lower().endswith(".csv") for info in members):
        raise SourceDataError("USAspending award archive must contain only CSV members")
    return members


def download_award_archive(
    source: AwardArchiveFile,
    destination_dir: Path,
    *,
    force: bool = False,
    chunk_size: int = 8 * 1024 * 1024,
    client: httpx.Client | None = None,
) -> tuple[Path, dict[str, object]]:
    """Download an archive atomically, resuming a partial file when possible."""

    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than zero")
    destination_dir = Path(destination_dir)
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / source.file_name
    metadata_path = destination.with_suffix(".metadata.json")

    if destination.is_file() and metadata_path.is_file() and not force:
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            metadata = {}
        expected_hash = metadata.get("sha256")
        if (
            metadata.get("source_url") == source.url
            and metadata.get("size_bytes") == destination.stat().st_size
            and isinstance(expected_hash, str)
            and _sha256(destination) == expected_hash
        ):
            _validated_archive_members(destination)
            return destination, metadata

    partial = destination.with_name(f".{destination.name}.part")
    if force:
        partial.unlink(missing_ok=True)
    resume_offset = partial.stat().st_size if partial.exists() else 0
    headers = {"Accept": "application/zip, application/octet-stream", "Accept-Encoding": "identity"}
    if resume_offset:
        headers["Range"] = f"bytes={resume_offset}-"

    owns_client = client is None
    active_client = client or httpx.Client(timeout=httpx.Timeout(300.0, connect=30.0))
    digest = hashlib.sha256()
    if resume_offset:
        with partial.open("rb") as existing:
            for chunk in iter(lambda: existing.read(1024 * 1024), b""):
                digest.update(chunk)

    try:
        with active_client.stream("GET", source.url, headers=headers) as response:
            response.raise_for_status()
            append = resume_offset > 0 and response.status_code == 206
            if append:
                content_range = response.headers.get("content-range", "")
                if not content_range.startswith(f"bytes {resume_offset}-"):
                    raise SourceDataError(
                        f"USAspending returned an invalid resume range: {content_range!r}"
                    )
            elif resume_offset:
                resume_offset = 0
                digest = hashlib.sha256()

            mode = "ab" if append else "wb"
            with partial.open(mode) as target:
                for chunk in response.iter_bytes(chunk_size=chunk_size):
                    if chunk:
                        target.write(chunk)
                        digest.update(chunk)

            content_range = response.headers.get("content-range")
            if content_range and "/" in content_range:
                expected_size = int(content_range.rsplit("/", 1)[1])
            elif response.headers.get("content-length"):
                expected_size = resume_offset + int(response.headers["content-length"])
            else:
                expected_size = partial.stat().st_size
    finally:
        if owns_client:
            active_client.close()

    actual_size = partial.stat().st_size
    if actual_size != expected_size:
        raise SourceDataError(
            f"USAspending archive download is incomplete: {actual_size} of {expected_size} bytes"
        )
    with partial.open("rb") as stream:
        if stream.read(4) not in {b"PK\x03\x04", b"PK\x05\x06"}:
            raise SourceDataError("USAspending response is not a ZIP file")
    members = _validated_archive_members(partial)
    partial.replace(destination)

    metadata = {
        "source_url": source.url,
        "downloaded_at": datetime.now(UTC).isoformat(),
        "size_bytes": actual_size,
        "sha256": digest.hexdigest(),
        "member_count": len(members),
        "archive": asdict(source),
    }
    _write_json_atomic(metadata_path, metadata)
    return destination, metadata


def find_latest_local_contract_archive(directory: Path) -> Path | None:
    """Find the most recently generated Contracts_Full archive in a directory."""

    directory = Path(directory)
    if not directory.is_dir():
        return None
    candidates: list[tuple[str, Path]] = []
    for path in directory.glob("FY*_Contracts_Full_*.zip"):
        match = _ARCHIVE_PATTERN.fullmatch(path.name)
        if match and match["award_type"] == "Contracts":
            candidates.append((match["updated"], path))
    if not candidates:
        return None
    return max(candidates, key=lambda item: (item[0], item[1].name))[1]


class AwardArchiveContractExtractor(ContractExtractor):
    """Filter Contracts_Full CSV members into the canonical contract Parquet."""

    def __init__(
        self, vendor_filter_file: Path, batch_size: int = 10000, block_size: int = 8 << 20
    ):
        super().__init__(vendor_filter_file=vendor_filter_file, batch_size=batch_size)
        if not any(self.vendor_filters.values()):
            raise ValueError(
                "Award archive extraction requires a non-empty SBIR vendor filter; "
                "refusing to scan all contracts into memory or Parquet"
            )
        if block_size <= 0:
            raise ValueError("block_size must be greater than zero")
        self.block_size = block_size

    @staticmethod
    def _header(member: BinaryIO) -> tuple[str, ...]:
        text = io.TextIOWrapper(member, encoding="utf-8-sig", newline="")
        try:
            header = tuple(next(csv.reader(text)))
        except (StopIteration, csv.Error, UnicodeDecodeError) as error:
            raise ArchiveSchemaError("USAspending CSV member has no readable header") from error
        finally:
            text.close()
        if len(header) != len(set(header)):
            raise ArchiveSchemaError("USAspending CSV member has duplicate columns")
        if missing := sorted(set(CONTRACT_ARCHIVE_COLUMNS).difference(header)):
            raise ArchiveSchemaError(
                f"USAspending Contracts_Full CSV is missing columns: {', '.join(missing)}"
            )
        return header

    def _match_mask(self, batch: pa.RecordBatch) -> pa.Array:
        mask = pa.array([False] * batch.num_rows)
        filter_columns = (
            ("recipient_uei", self.vendor_filters["uei"], False),
            ("recipient_duns", self.vendor_filters["duns"], False),
            ("recipient_name", self.vendor_filters["company_names"], True),
        )
        for column, values, uppercase in filter_columns:
            if not values:
                continue
            normalized = pc.utf8_trim_whitespace(batch.column(column))
            if uppercase:
                normalized = pc.utf8_upper(normalized)
            matches = pc.is_in(normalized, value_set=pa.array(sorted(values), type=pa.string()))
            mask = pc.or_kleene(mask, pc.fill_null(matches, False))
        return pc.fill_null(mask, False)

    @staticmethod
    def _map_row(row: Mapping[str, str | None]) -> dict[str, str | None]:
        award_flag = (row.get("award_or_idv_flag") or "").strip().upper()
        award_type_code = (row.get("award_type_code") or "").strip()
        if award_flag == "IDV" and not award_type_code.upper().startswith("IDV"):
            award_type_code = f"IDV-{award_type_code}" if award_type_code else "IDV"
        return {
            "transaction_unique_id": row.get("contract_transaction_unique_key"),
            "generated_unique_award_id": row.get("contract_award_unique_key"),
            "piid": row.get("award_id_piid"),
            "modification_number": row.get("modification_number"),
            "parent_award_id": row.get("parent_award_id_piid"),
            "referenced_idv_agency_iden": (
                row.get("parent_award_agency_id") or row.get("parent_award_agency_name")
            ),
            "federal_action_obligation": row.get("federal_action_obligation"),
            "action_date": row.get("action_date"),
            "period_of_performance_start_date": row.get("period_of_performance_start_date"),
            "period_of_performance_current_end_date": row.get(
                "period_of_performance_current_end_date"
            ),
            "awarding_toptier_agency_name": row.get("awarding_agency_name"),
            "awarding_subtier_agency_name": row.get("awarding_sub_agency_name"),
            "funding_toptier_agency_name": row.get("funding_agency_name"),
            "recipient_uei": row.get("recipient_uei"),
            "recipient_unique_id": row.get("recipient_duns"),
            "recipient_name": row.get("recipient_name"),
            "cage_code": row.get("cage_code"),
            "parent_uei": row.get("recipient_parent_uei"),
            "recipient_location_state_code": row.get("recipient_state_code"),
            "contract_award_type": award_type_code or row.get("award_type"),
            "transaction_description": row.get("transaction_description"),
            "product_or_service_code": row.get("product_or_service_code"),
            "naics_code": row.get("naics_code"),
            "extent_competed": row.get("extent_competed"),
            "research": row.get("research"),
        }

    def _stream_member(
        self,
        archive: zipfile.ZipFile,
        info: zipfile.ZipInfo,
    ) -> Iterator[FederalContract]:
        with archive.open(info) as member:
            reader = pa_csv.open_csv(
                member,
                read_options=pa_csv.ReadOptions(block_size=self.block_size, use_threads=True),
                convert_options=pa_csv.ConvertOptions(
                    column_types=dict.fromkeys(CONTRACT_ARCHIVE_COLUMNS, pa.string()),
                    include_columns=list(CONTRACT_ARCHIVE_COLUMNS),
                    strings_can_be_null=True,
                ),
            )
            for batch in reader:
                self.stats["records_scanned"] += batch.num_rows
                self.stats["contracts_found"] += batch.num_rows
                matched = batch.filter(self._match_mask(batch))
                self.stats["vendor_matches"] += matched.num_rows
                for row in matched.to_pylist():
                    contract = self._parse_contract_row(self._map_row(row))
                    self.stats["records_extracted"] += 1
                    yield contract

    def extract_from_archive(self, archive_file: Path, output_file: Path) -> int:
        """Stream all CSV members and atomically write matched contracts to Parquet."""

        archive_file = Path(archive_file)
        if not archive_file.is_file():
            raise FileNotFoundError(f"USAspending award archive not found: {archive_file}")
        initial_stat = archive_file.stat()
        archive_sha256 = _sha256(archive_file)
        with zipfile.ZipFile(archive_file) as archive:
            members = sorted(
                (info for info in archive.infolist() if not info.is_dir()),
                key=lambda info: info.filename,
            )
            if not members or any(not info.filename.lower().endswith(".csv") for info in members):
                raise ArchiveSchemaError("USAspending award archive must contain only CSV members")

            headers: list[tuple[str, ...]] = []
            for info in members:
                with archive.open(info) as member:
                    headers.append(self._header(cast(BinaryIO, member)))
            if any(header != headers[0] for header in headers[1:]):
                raise ArchiveSchemaError("USAspending archive CSV members have different schemas")

            serialized_header = "\n".join(headers[0])
            manifest = "\n".join(
                f"{info.filename}\t{info.file_size}\t{info.CRC}" for info in members
            )
            self.source_provenance = {
                "source_kind": AWARD_ARCHIVE_SOURCE_KIND,
                "canonical_table": "award_data_archive.contracts_full",
                "physical_table": "award_data_archive.contracts_full",
                "archive_file": archive_file.name,
                "archive_sha256": archive_sha256,
                "archive_size_bytes": archive_file.stat().st_size,
                "member_count": len(members),
                "member_manifest_sha256": hashlib.sha256(manifest.encode()).hexdigest(),
                "ordered_columns_sha256": hashlib.sha256(serialized_header.encode()).hexdigest(),
                "column_count": len(headers[0]),
                "provenance_version": AWARD_ARCHIVE_PROVENANCE_VERSION,
            }

            def contracts() -> Iterator[FederalContract]:
                for info in members:
                    logger.info(
                        f"Scanning {info.filename} ({info.file_size / (1024**3):.2f} GiB uncompressed)"
                    )
                    yield from self._stream_member(archive, info)

            count = self._collect_and_write(contracts(), Path(output_file))

        final_stat = archive_file.stat()
        if (final_stat.st_size, final_stat.st_mtime_ns) != (
            initial_stat.st_size,
            initial_stat.st_mtime_ns,
        ):
            Path(output_file).unlink(missing_ok=True)
            raise SourceDataError(
                "USAspending award archive changed during extraction; output was removed"
            )
        return count


__all__ = [
    "ARCHIVE_API_URL",
    "AWARD_ARCHIVE_PROVENANCE_VERSION",
    "AWARD_ARCHIVE_SOURCE_KIND",
    "AwardArchiveContractExtractor",
    "AwardArchiveFile",
    "CONTRACT_ARCHIVE_COLUMNS",
    "discover_full_award_archive",
    "download_award_archive",
    "find_latest_local_contract_archive",
]
