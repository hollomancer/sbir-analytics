"""Federal contract extraction from schema-verified USAspending dumps.

The production path reads ``rpt.transaction_search`` (or its FPDS partition).
The archive TOC identifies the changing data-member id, while pg_restore's
explicit COPY list supplies the serialized column order.
"""

import gzip
import hashlib
import io
import json
import re
import shutil
import subprocess
import tempfile
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath

import pandas as pd
from loguru import logger
from sbir_etl.models.transition_models import CompetitionType, FederalContract


CANONICAL_RELATION = "rpt.transaction_search"
FPDS_RELATION = "rpt.transaction_search_fpds"
REQUIRED_SOURCE_COLUMNS = frozenset(
    {
        "is_fpds",
        "piid",
        "transaction_unique_id",
        "generated_unique_award_id",
        "action_date",
        "federal_action_obligation",
        "recipient_uei",
        "recipient_name",
        "awarding_toptier_agency_name",
        "awarding_subtier_agency_name",
        "extent_competed",
        "research",
        "naics_code",
        "product_or_service_code",
    }
)


class ArchiveSchemaError(RuntimeError):
    """The dump cannot prove the required USAspending source schema."""


class SourceDataError(RuntimeError):
    """A serialized source row violates a fail-closed extraction invariant."""


@dataclass(frozen=True)
class TransactionSource:
    member_name: str
    columns: tuple[str, ...]
    relation: str
    fpds_only: bool


@dataclass(frozen=True)
class _TableEntry:
    dump_id: str
    schema: str
    table: str


_TABLE_DATA_RE = re.compile(
    r"^\s*(\d+);\s+\d+\s+\d+\s+TABLE DATA\s+(\S+)\s+(\S+)(?:\s+|$)",
    re.IGNORECASE,
)
_COPY_RE = re.compile(
    r'COPY\s+(?:ONLY\s+)?(?P<schema>"?[\w]+"?)\.(?P<table>"?[\w]+"?)\s*'
    r"\((?P<columns>.*?)\)\s+FROM\s+stdin\s*;",
    re.IGNORECASE | re.DOTALL,
)


def _unquote(value: str) -> str:
    return value.strip().strip('"').replace('""', '"')


def _select_table_entry(toc_text: str, schema_sql: str) -> tuple[_TableEntry, bool]:
    entries: list[_TableEntry] = []
    for line in toc_text.splitlines():
        if match := _TABLE_DATA_RE.match(line):
            entries.append(_TableEntry(match[1], _unquote(match[2]), _unquote(match[3])))

    leaves = [
        entry
        for entry in entries
        if entry.schema == "rpt" and entry.table == "transaction_search_fpds"
    ]
    parents = [
        entry for entry in entries if entry.schema == "rpt" and entry.table == "transaction_search"
    ]
    if len(leaves) > 1:
        raise ArchiveSchemaError(f"Expected one {FPDS_RELATION} TABLE DATA entry")

    normalized_schema = re.sub(r"\s+", " ", schema_sql.replace('"', "")).lower()
    if "create table rpt.transaction_search (" not in normalized_schema:
        raise ArchiveSchemaError(f"Archive schema does not define {CANONICAL_RELATION}")
    if leaves:
        partition_pattern = (
            r"(?:partition of rpt\.transaction_search|attach partition "
            r"rpt\.transaction_search_fpds).*?for values in\s*\(\s*"
            r"(?:true|'true'|'t')\s*\)"
        )
        if not re.search(partition_pattern, normalized_schema):
            raise ArchiveSchemaError(
                f"Archive schema does not prove {FPDS_RELATION} is the TRUE FPDS partition"
            )
        return leaves[0], True
    if len(parents) != 1:
        raise ArchiveSchemaError(
            f"Expected one {FPDS_RELATION} or {CANONICAL_RELATION} TABLE DATA entry"
        )
    return parents[0], False


def _resolve_source(toc_text: str, schema_sql: str, copy_sql: str) -> TransactionSource:
    entry, fpds_only = _select_table_entry(toc_text, schema_sql)
    matches = list(_COPY_RE.finditer(copy_sql))
    if len(matches) != 1:
        raise ArchiveSchemaError(f"Expected one explicit COPY column list; found {len(matches)}")
    copy_match = matches[0]
    copy_schema = _unquote(copy_match["schema"])
    copy_table = _unquote(copy_match["table"])
    allowed_tables = {entry.table}
    if fpds_only:
        # pg_restore may route a leaf through its partition root.
        allowed_tables.add("transaction_search")
    if copy_schema != "rpt" or copy_table not in allowed_tables:
        raise ArchiveSchemaError(
            f"TABLE DATA for {entry.schema}.{entry.table} produced unexpected "
            f"COPY target {copy_schema}.{copy_table}"
        )

    columns = tuple(_unquote(item) for item in copy_match["columns"].split(","))
    if not columns or any(not column or re.search(r"\s", column) for column in columns):
        raise ArchiveSchemaError("COPY list contains an invalid column identifier")
    if len(columns) != len(set(columns)):
        raise ArchiveSchemaError("COPY list contains duplicate columns")
    if missing := sorted(REQUIRED_SOURCE_COLUMNS.difference(columns)):
        raise ArchiveSchemaError(
            f"{CANONICAL_RELATION} is missing required columns: {', '.join(missing)}"
        )
    return TransactionSource(
        member_name=f"{entry.dump_id}.dat.gz",
        columns=columns,
        relation=f"{entry.schema}.{entry.table}",
        fpds_only=fpds_only,
    )


def _copy_value(value: str) -> str | None:
    """Decode the COPY escapes relevant to projected text fields."""
    if value == r"\N":
        return None
    return re.sub(
        r"\\([bfnrtv\\])",
        lambda match: {
            "b": "\b",
            "f": "\f",
            "n": "\n",
            "r": "\r",
            "t": "\t",
            "v": "\v",
            "\\": "\\",
        }[match[1]],
        value,
    )


def _pg_bool(value: str | None) -> bool:
    normalized = value.strip().lower() if value is not None else ""
    if normalized in {"t", "true", "1"}:
        return True
    if normalized in {"f", "false", "0"}:
        return False
    raise SourceDataError(f"Invalid or NULL is_fpds value: {value!r}")


class ContractExtractor:
    """
    Extract federal contracts from USAspending PostgreSQL dump files.

    Features:
    - Streaming processing of large .dat.gz files
    - Vendor-based filtering (only extract SBIR vendor contracts)
    - Memory-efficient batch processing
    - Direct FederalContract model output

    Example:
        ```python
        extractor = ContractExtractor(vendor_filter_file="sbir_vendor_filters.json")

        # Extract from dump directory
        contracts = extractor.extract_from_dump(
            dump_dir="/path/to/pruned_data_store_api_dump",
            output_file="filtered_contracts.parquet"
        )
        ```
    """

    def __init__(
        self,
        vendor_filter_file: Path | None = None,
        batch_size: int = 10000,
    ):
        """
        Initialize contract extractor.

        Args:
            vendor_filter_file: Path to JSON file with SBIR vendor filters
            batch_size: Number of records to process per batch
        """
        self.batch_size = batch_size
        self.vendor_filters = self._load_vendor_filters(vendor_filter_file)

        # Statistics
        self.stats = {
            "records_scanned": 0,
            "contracts_found": 0,
            "vendor_matches": 0,
            "records_extracted": 0,
            "parent_relationships": 0,
            "child_relationships": 0,
            "idv_parents": 0,
            "unique_parent_ids": 0,
            "unique_idv_parents": 0,
        }
        self._parent_ids_seen: set[str] = set()
        self._idv_parent_ids_seen: set[str] = set()
        self.source_provenance: dict[str, str | int] = {}

    def _load_vendor_filters(self, filter_file: Path | None) -> dict[str, set[str]]:
        """Load vendor filter sets from JSON file."""
        if not filter_file or not Path(filter_file).exists():
            logger.warning("No vendor filter file provided, will extract all contracts")
            return {"uei": set(), "duns": set(), "company_names": set()}

        logger.info(f"Loading vendor filters from {filter_file}")
        with open(filter_file) as f:
            data = json.load(f)

        filters = {
            "uei": set(data.get("uei", [])),
            "duns": set(data.get("duns", [])),
            "company_names": {name.upper() for name in data.get("company_names", [])},
        }

        logger.info(
            f"Loaded {len(filters['uei'])} UEI, {len(filters['duns'])} DUNS, "
            f"{len(filters['company_names'])} company name filters"
        )

        return filters

    def _is_contract_type(self, type_code: str, award_type_code: str = None) -> bool:
        """
        Check if transaction type is a contract (not grant, loan, etc.).

        USAspending type codes (column 4):
        - 'A': Award (mixed - could be contract or grant)
        - 'B': IDV (Indefinite Delivery Vehicle - contract)
        - 'C': Grant/Assistance (NOT a contract)
        - 'D': Direct Payment (NOT a contract)

        USAspending award_type_code (column 6):
        - '02', '03', '04', '05': Grants/assistance
        - 'A', 'B', 'C', 'D': Procurement contracts
        - 'IDV-A', 'IDV-B', etc.: IDV contracts

        Returns True only for procurement contracts.
        """
        if not type_code:
            return False

        # Type 'B' is always IDV (contract)
        if type_code == "B":
            return True

        # Type 'C' and 'D' are grants/assistance
        if type_code in {"C", "D"}:
            return False

        # Type 'A' is mixed - check award_type_code
        if type_code == "A" and award_type_code:
            # Award type codes starting with digits are grants
            if award_type_code and award_type_code[0].isdigit():
                return False
            # Award type codes that are letters or contain 'IDV' are contracts
            if award_type_code.startswith(("A", "B", "C", "D", "IDV")):
                return True

        # Default to False for safety (only include confirmed contracts)
        return False

    def _parse_competition_type(self, extent_competed: str | None) -> CompetitionType:
        """
        Parse USAspending extent_competed field to CompetitionType enum.

        USAspending extent_competed codes:
        - 'A&A': Full and open competition after exclusion of sources
        - 'CDO': Competitive Delivery Order
        - 'FSS': Full and open competition (Federal Supply Schedule)
        - 'FULL': Full and open competition
        - 'NDO': Non-competitive Delivery Order
        - 'NONE': Not competed
        - 'Not Available': Unknown
        - NULL/empty: Unknown

        Returns:
            CompetitionType enum value
        """
        if not extent_competed or extent_competed == "\\N" or extent_competed == "Not Available":
            return CompetitionType.OTHER

        extent_competed = extent_competed.strip().upper()

        # Full and open competition
        if extent_competed in {"FULL", "FSS", "A&A", "CDO"}:
            return CompetitionType.FULL_AND_OPEN

        # No competition (sole source)
        if extent_competed in {"NONE", "NDO"}:
            return CompetitionType.SOLE_SOURCE

        # Limited competition patterns
        if "LIMITED" in extent_competed or "RESTRICTED" in extent_competed:
            return CompetitionType.LIMITED

        return CompetitionType.OTHER

    def _matches_vendor_filter(self, row: Mapping[str, str | None]) -> bool:
        """Return whether a named transaction row matches the vendor frame."""
        if not any(self.vendor_filters.values()):
            return True
        uei = row.get("recipient_uei")
        if uei and uei.strip() in self.vendor_filters["uei"]:
            return True
        legacy_id = row.get("recipient_unique_id")
        if legacy_id and legacy_id.strip() in (
            self.vendor_filters["uei"] | self.vendor_filters["duns"]
        ):
            return True
        name = row.get("recipient_name")
        return bool(name and name.strip().upper() in self.vendor_filters["company_names"])

    def _parse_contract_row(self, row: Mapping[str, str | None]) -> FederalContract:
        """Build a FederalContract using source field names, never fixed indexes."""
        from sbir_etl.utils.date_utils import parse_date

        transaction_id = row.get("transaction_unique_id")
        award_id = row.get("generated_unique_award_id")
        if not transaction_id or not award_id:
            missing = "transaction_unique_id" if not transaction_id else "generated_unique_award_id"
            raise SourceDataError(f"Matched FPDS row is missing {missing}")

        action_date = parse_date(row.get("action_date"), allow_8digit=True, strict=False)
        start_date = parse_date(
            row.get("period_of_performance_start_date"), allow_8digit=True, strict=False
        )
        end_date = parse_date(
            row.get("period_of_performance_current_end_date"), allow_8digit=True, strict=False
        )
        start_date = start_date or action_date
        obligation_text = row.get("federal_action_obligation")
        try:
            obligation = float(obligation_text) if obligation_text else None
        except (TypeError, ValueError):
            obligation = None

        recipient_uei = row.get("recipient_uei")
        legacy_id = row.get("recipient_unique_id")
        vendor_uei = recipient_uei if recipient_uei and len(recipient_uei) == 12 else None
        if not vendor_uei and legacy_id and len(legacy_id) == 12:
            vendor_uei = legacy_id
        vendor_duns = (
            legacy_id if legacy_id and len(legacy_id) == 9 and legacy_id.isdigit() else None
        )

        parent_id = row.get("parent_award_id") or row.get("referenced_idv_piid")
        parent_agency = row.get("referenced_idv_agency_iden")
        award_type = row.get("contract_award_type")
        relationship_type = "standalone"
        if parent_id:
            relationship_type = "child_of_idv"
            self.stats["parent_relationships"] += 1
            self.stats["child_relationships"] += 1
            self._parent_ids_seen.add(parent_id)
        elif award_type and (
            award_type.strip().upper().startswith("IDV")
            or award_type.strip().upper() in {"BPA", "BOA", "IDIQ"}
        ):
            relationship_type = "idv_parent"
            self.stats["idv_parents"] += 1

        extent_competed = row.get("extent_competed")
        contract = FederalContract(
            contract_id=row.get("piid") or award_id,
            piid=row.get("piid"),
            transaction_unique_id=transaction_id,
            generated_unique_award_id=award_id,
            agency=row.get("awarding_toptier_agency_name"),
            sub_agency=row.get("awarding_subtier_agency_name"),
            vendor_name=row.get("recipient_name"),
            vendor_uei=vendor_uei,
            vendor_cage=row.get("cage_code"),
            vendor_duns=vendor_duns,
            action_date=action_date,
            start_date=start_date,
            end_date=end_date,
            obligation_amount=obligation,
            is_deobligation=obligation is not None and obligation < 0,
            competition_type=self._parse_competition_type(extent_competed),
            description=row.get("transaction_description"),
            parent_contract_id=parent_id,
            parent_contract_agency=parent_agency,
            contract_award_type=award_type,
            research=row.get("research"),
            naics_code=row.get("naics_code"),
            product_or_service_code=row.get("product_or_service_code"),
            metadata={
                "transaction_id": transaction_id,
                "award_id": award_id,
                "modification_number": row.get("modification_number"),
                "action_date": action_date.isoformat() if action_date else None,
                "funding_agency": row.get("funding_toptier_agency_name"),
                "parent_uei": row.get("parent_uei"),
                "recipient_state": row.get("recipient_location_state_code"),
                "business_categories": row.get("business_categories"),
                "extent_competed": extent_competed,
                "contract_award_type": award_type,
                "parent_idv_piid": parent_id,
                "referenced_idv_agency": parent_agency,
                "parent_relationship_type": relationship_type,
                "research": row.get("research"),
                "naics_code": row.get("naics_code"),
                "product_or_service_code": row.get("product_or_service_code"),
            },
        )
        if relationship_type == "idv_parent":
            self._idv_parent_ids_seen.add(contract.contract_id)
        return contract

    def _parse_lines(
        self,
        lines: Iterable[str],
        source_name: str,
        columns: Sequence[str],
        *,
        fpds_only: bool,
    ) -> Iterator[FederalContract]:
        """Parse rows with a name-to-index projection derived from the COPY list."""
        if missing := sorted(REQUIRED_SOURCE_COLUMNS.difference(columns)):
            raise ArchiveSchemaError(f"Verified source columns missing: {', '.join(missing)}")
        projected_names = REQUIRED_SOURCE_COLUMNS | {
            "recipient_unique_id",
            "piid",
            "period_of_performance_start_date",
            "period_of_performance_current_end_date",
            "cage_code",
            "parent_award_id",
            "referenced_idv_piid",
            "referenced_idv_agency_iden",
            "contract_award_type",
            "transaction_description",
            "modification_number",
            "funding_toptier_agency_name",
            "parent_uei",
            "recipient_location_state_code",
            "business_categories",
        }
        indexes = {name: index for index, name in enumerate(columns) if name in projected_names}
        for line_num, line in enumerate(lines, 1):
            self.stats["records_scanned"] += 1

            # Progress logging
            if line_num % 100000 == 0:
                logger.info(
                    f"  [{source_name}] processed {line_num:,} records, "
                    f"found {self.stats['records_extracted']} contracts"
                )

            values = line.rstrip("\r\n").split("\t")
            if len(values) != len(columns):
                raise SourceDataError(
                    f"{source_name} row {line_num} has {len(values)} fields; "
                    f"COPY declares {len(columns)}"
                )
            row = {name: _copy_value(values[index]) for name, index in indexes.items()}
            is_fpds = _pg_bool(row["is_fpds"])
            if fpds_only and not is_fpds:
                raise SourceDataError(f"Non-FPDS row found in {FPDS_RELATION}")
            if not is_fpds:
                continue
            self.stats["contracts_found"] += 1
            if not self._matches_vendor_filter(row):
                continue
            self.stats["vendor_matches"] += 1
            contract = self._parse_contract_row(row)
            self.stats["records_extracted"] += 1
            yield contract

    @staticmethod
    def _run_pg_restore(dump_dir: Path, *arguments: str) -> str:
        executable = shutil.which("pg_restore")
        if executable is None:
            raise ArchiveSchemaError(
                "pg_restore is required to verify the USAspending dump; "
                "refusing positional extraction"
            )
        try:
            result = subprocess.run(
                [executable, *arguments, str(dump_dir)],
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
        except subprocess.CalledProcessError as error:
            detail = error.stderr.strip() or error.stdout.strip() or str(error)
            raise ArchiveSchemaError(
                f"pg_restore could not inspect {dump_dir}: {detail}"
            ) from error
        return result.stdout

    @classmethod
    def _restore_copy_statement(cls, toc_file: Path, entry: _TableEntry) -> str:
        """Render COPY metadata against an empty selected member, never source rows."""
        with tempfile.TemporaryDirectory(prefix="usaspending-copy-") as temp_name:
            archive_dir = Path(temp_name) / "archive"
            archive_dir.mkdir()
            shutil.copyfile(toc_file, archive_dir / "toc.dat")
            with gzip.open(archive_dir / f"{entry.dump_id}.dat.gz", "wb"):
                pass
            return cls._run_pg_restore(
                archive_dir,
                "--data-only",
                f"--schema={entry.schema}",
                f"--table={entry.table}",
                "--strict-names",
                "--file=-",
            )

    @staticmethod
    def _provenance(source: TransactionSource) -> dict[str, str | int]:
        serialized = json.dumps(source.columns, separators=(",", ":"))
        return {
            "canonical_table": CANONICAL_RELATION,
            "physical_table": source.relation,
            "member": source.member_name,
            "ordered_columns_sha256": hashlib.sha256(serialized.encode()).hexdigest(),
            "column_count": len(source.columns),
        }

    @classmethod
    def _resolve_local_source(cls, dump_dir: Path) -> TransactionSource:
        toc_file = dump_dir / "toc.dat"
        if not toc_file.is_file():
            raise ArchiveSchemaError(f"USAspending directory archive has no toc.dat: {dump_dir}")
        toc_text = cls._run_pg_restore(dump_dir, "--list")
        schema_sql = cls._run_pg_restore(dump_dir, "--schema-only", "--file=-")
        entry, _ = _select_table_entry(toc_text, schema_sql)
        copy_sql = cls._restore_copy_statement(toc_file, entry)
        source = _resolve_source(toc_text, schema_sql, copy_sql)
        if not (dump_dir / source.member_name).is_file():
            raise ArchiveSchemaError(
                f"TOC selected {source.relation}, but {source.member_name} is absent"
            )
        return source

    @classmethod
    def _resolve_remote_source(cls, zip_url: str) -> TransactionSource:
        try:
            from remotezip import RemoteZip
        except ImportError as error:  # pragma: no cover - import guard
            raise ImportError(
                "Remote zip streaming requires the optional 'streaming' extra "
                "(uv sync --extra streaming / pip install 'sbir-etl[streaming]')."
            ) from error

        with RemoteZip(zip_url) as remote_zip:
            names = [info.filename for info in remote_zip.infolist()]
            toc_members = [name for name in names if PurePosixPath(name).name == "toc.dat"]
            if len(toc_members) != 1:
                raise ArchiveSchemaError(
                    f"Remote archive must contain exactly one toc.dat; found {len(toc_members)}"
                )
            toc_member = toc_members[0]
            with tempfile.TemporaryDirectory(prefix="usaspending-toc-") as temp_name:
                archive_dir = Path(temp_name) / "archive"
                archive_dir.mkdir()
                with (
                    remote_zip.open(toc_member) as source_file,
                    open(archive_dir / "toc.dat", "wb") as target_file,
                ):
                    shutil.copyfileobj(source_file, target_file)
                toc_text = cls._run_pg_restore(archive_dir, "--list")
                schema_sql = cls._run_pg_restore(archive_dir, "--schema-only", "--file=-")
                entry, _ = _select_table_entry(toc_text, schema_sql)
                copy_sql = cls._restore_copy_statement(archive_dir / "toc.dat", entry)
                source = _resolve_source(toc_text, schema_sql, copy_sql)

            member = str(PurePosixPath(toc_member).parent / source.member_name)
            if member not in names:
                raise ArchiveSchemaError(f"TOC selected {source.relation}, but {member} is absent")
            return replace(source, member_name=member)

    def stream_dat_gz_file(
        self,
        dat_file: Path,
        columns: Sequence[str],
        *,
        fpds_only: bool,
    ) -> Iterator[FederalContract]:
        """Stream a local member using its verified COPY column order."""
        logger.info(f"Processing {dat_file.name}...")
        with gzip.open(dat_file, "rt", encoding="utf-8", errors="replace") as f:
            yield from self._parse_lines(f, dat_file.name, columns, fpds_only=fpds_only)
        logger.info(
            f"Completed {dat_file.name}: {self.stats['records_extracted']} contracts extracted"
        )

    @classmethod
    def find_transaction_member(cls, zip_url: str) -> str:
        """Return the member selected from archive-owned TOC and COPY metadata."""
        return cls._resolve_remote_source(zip_url).member_name

    def stream_remote_zip_member(
        self,
        zip_url: str,
        member_name: str,
        columns: Sequence[str],
        *,
        fpds_only: bool,
    ) -> Iterator[FederalContract]:
        """Stream-parse one ``.dat.gz`` member directly from a remote ``.zip``.

        Uses HTTP Range requests (via ``remotezip``) to read **only** the bytes of
        verified ``transaction_search`` member out of the
        USAspending database zip — never downloading the full ~217GB archive, and
        without staging it on local disk. The member is itself gzip-compressed
        (``.dat.gz``), so it is decompressed on the fly as bytes arrive.

        Requires the server to support HTTP Range (``files.usaspending.gov`` does)
        and the optional ``remotezip`` dependency.

        Args:
            zip_url: ``https://`` URL of the database zip (e.g.
                ``https://files.usaspending.gov/database_download/usaspending-db-subset_YYYYMMDD.zip``).
            member_name: Path of the ``.dat.gz`` member inside the zip.

        Yields:
            FederalContract instances that match vendor filters.
        """
        try:
            from remotezip import RemoteZip
        except ImportError as e:  # pragma: no cover - exercised via import guard
            raise ImportError(
                "Remote zip streaming requires the optional 'streaming' extra "
                "(uv sync --extra streaming / pip install 'sbir-etl[streaming]')."
            ) from e

        logger.info(f"Streaming member {member_name} from {zip_url} (HTTP range)")
        with (
            RemoteZip(zip_url) as remote_zip,
            remote_zip.open(member_name) as member,
            # `member` yields the gzip-compressed .dat.gz bytes; decompress streaming.
            gzip.GzipFile(fileobj=member) as gz,
            io.TextIOWrapper(gz, encoding="utf-8", errors="replace") as text,
        ):
            yield from self._parse_lines(text, member_name, columns, fpds_only=fpds_only)
        logger.info(
            f"Completed streaming {member_name}: "
            f"{self.stats['records_extracted']} contracts extracted"
        )

    def extract_from_dump(
        self,
        dump_dir: Path,
        output_file: Path,
        table_files: list[str] | None = None,
    ) -> int:
        """
        Extract contracts from PostgreSQL dump directory.

        Args:
            dump_dir: Path to pruned_data_store_api_dump directory
            output_file: Path to output Parquet file
            table_files: Optional configured member; it must match the TOC result.

        Returns:
            Number of contracts extracted
        """
        dump_dir = Path(dump_dir)
        if not dump_dir.exists():
            raise FileNotFoundError(f"Dump directory not found: {dump_dir}")

        source = self._resolve_local_source(dump_dir)
        self.source_provenance = self._provenance(source)
        if table_files is not None and [Path(name).name for name in table_files] != [
            source.member_name
        ]:
            raise ArchiveSchemaError(
                f"Configured table_files {table_files!r} do not match TOC-selected "
                f"member {source.member_name!r}"
            )
        contracts = self.stream_dat_gz_file(
            dump_dir / source.member_name,
            source.columns,
            fpds_only=source.fpds_only,
        )
        return self._collect_and_write(contracts, output_file)

    def extract_from_remote_zip(
        self,
        zip_url: str,
        member_name: str | None,
        output_file: Path,
    ) -> int:
        """Extract SBIR-relevant contracts by streaming one member from a remote zip.

        The remote counterpart to :meth:`extract_from_dump`: verifies the archive
        TOC and COPY metadata, then streams only the selected FPDS member.

        Args:
            zip_url: ``https://`` URL of the USAspending database zip.
            member_name: Optional configured member; it must match the TOC result.
            output_file: Parquet output path.

        Returns:
            Number of contracts extracted.
        """
        source = self._resolve_remote_source(zip_url)
        self.source_provenance = self._provenance(source)
        if member_name is not None and member_name != source.member_name:
            raise ArchiveSchemaError(
                f"Requested member {member_name!r} does not match TOC-selected "
                f"member {source.member_name!r}"
            )
        return self._collect_and_write(
            self.stream_remote_zip_member(
                zip_url,
                source.member_name,
                source.columns,
                fpds_only=source.fpds_only,
            ),
            Path(output_file),
        )

    def _collect_and_write(
        self,
        contracts: Iterable[FederalContract],
        output_file: Path,
    ) -> int:
        """Materialize matched contracts, write Parquet, log stats. Returns row count.

        The source table is *scanned* streaming (line by line); only the matched,
        vendor-filtered contracts accumulate here — a tiny fraction of the input — so
        holding them in memory before a single Parquet write is safe even for the
        full dump.
        """
        rows: list[dict] = []
        for contract in contracts:
            rows.append(contract.model_dump())
            if len(rows) % self.batch_size == 0:
                logger.info(f"Accumulated {len(rows):,} matched contracts")

        from sbir_etl.utils.data.file_io import save_dataframe_parquet

        output_file = Path(output_file)
        df = (
            pd.DataFrame(rows) if rows else pd.DataFrame(columns=list(FederalContract.model_fields))
        )
        temp_file = output_file.with_name(f".{output_file.stem}.tmp{output_file.suffix}")
        try:
            save_dataframe_parquet(
                df,
                temp_file,
                index=False,
                compression="snappy",
                fallback_to_ndjson=False,
            )
            temp_file.replace(output_file)
        finally:
            temp_file.unlink(missing_ok=True)
        if rows:
            logger.success(f"Contracts saved to {output_file}")
        else:
            logger.warning(f"Wrote empty contracts artifact to replace stale output: {output_file}")

        # Log statistics
        self.stats["unique_parent_ids"] = len(self._parent_ids_seen)
        self.stats["unique_idv_parents"] = len(self._idv_parent_ids_seen)
        logger.info("\n" + "=" * 60)
        logger.info("Extraction Statistics:")
        logger.info("=" * 60)
        for key, value in self.stats.items():
            logger.info(f"  {key}: {value:,}")
        logger.info("=" * 60)

        return len(rows)


__all__ = ["ArchiveSchemaError", "ContractExtractor", "SourceDataError", "TransactionSource"]
