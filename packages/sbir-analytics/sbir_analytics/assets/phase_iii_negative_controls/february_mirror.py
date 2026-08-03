"""Pinned exact-key extraction from the February 2026 USAspending mirror."""

import gzip
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

import pandas as pd

from sbir_etl.extractors.contract_extractor import ArchiveSchemaError, SourceDataError

from .identity import IdentityRecoveryError
from .source_keys import (
    USA_FAIN_ADAPTER,
    USA_PIID_ADAPTER,
    USA_URI_ADAPTER,
    canonicalize_agency,
    canonicalize_fain_or_uri,
    canonicalize_piid,
)


AWARD_SEARCH_RELATION = "rpt.award_search"
FEBRUARY_2026_ARCHIVE_URL = (
    "https://ia601503.us.archive.org/19/items/gov_backup_niema/usaspending-db_20260206.zip"
)
FEBRUARY_2026_REPLICA_URLS = (
    "https://ia801503.us.archive.org/19/items/gov_backup_niema/usaspending-db_20260206.zip",
)

_REQUIRED_COLUMNS = frozenset(
    {
        "award_id",
        "generated_unique_award_id",
        "piid",
        "fain",
        "uri",
        "recipient_unique_id",
        "recipient_uei",
        "awarding_toptier_agency_name",
    }
)
_ATTEMPT_COLUMNS = frozenset({"adapter", "agency_key", "canonical_award_key"})
_USA_ADAPTERS = frozenset({USA_PIID_ADAPTER, USA_FAIN_ADAPTER, USA_URI_ADAPTER})
_TABLE_DATA_RE = re.compile(
    r"^\s*(\d+);\s+\d+\s+\d+\s+TABLE DATA\s+(\S+)\s+(\S+)(?:\s+|$)",
    re.IGNORECASE,
)
_COPY_RE = re.compile(
    r'COPY\s+(?:ONLY\s+)?(?P<schema>"?[\w]+"?)\.(?P<table>"?[\w]+"?)\s*'
    r"\((?P<columns>.*?)\)\s+FROM\s+stdin\s*;",
    re.IGNORECASE | re.DOTALL,
)
_NULL_TEXT = frozenset({"", "<NA>", "NAN", "NAT", "NONE", "NULL", r"\N"})

_AWK_AWARD_KEY_PREFILTER = r"""
BEGIN {
    FS = "\t"
    OFS = "\t"
    progress_marker = sprintf("%c", 30) "SBIR_AWARD_KEY_PROGRESS"
}

function fail(message) {
    print message > error_file
    close(error_file)
    failed = 1
    exit 65
}

function pgdecode(value, result, position, character, escaped) {
    if (value == "\\N") return ""
    if (!index(value, "\\")) return value
    result = ""
    for (position = 1; position <= length(value); position++) {
        character = substr(value, position, 1)
        if (character == "\\" && position < length(value)) {
            escaped = substr(value, position + 1, 1)
            if (escaped == "b") result = result sprintf("%c", 8)
            else if (escaped == "f") result = result sprintf("%c", 12)
            else if (escaped == "n") result = result "\n"
            else if (escaped == "r") result = result "\r"
            else if (escaped == "t") result = result "\t"
            else if (escaped == "v") result = result sprintf("%c", 11)
            else if (escaped == "\\") result = result "\\"
            else {
                result = result character
                continue
            }
            position++
        } else result = result character
    }
    return result
}

function stripped(value) {
    sub(/^[[:space:]]+/, "", value)
    sub(/[[:space:]]+$/, "", value)
    return value
}

FILENAME == piid_file { piid[$0] = 1; next }
FILENAME == fain_file { fain[$0] = 1; next }
FILENAME == uri_file { uri[$0] = 1; next }
FILENAME != "-" { fail("prefilter received an unexpected input file") }

{
    source_line++
    record = $0
    sub(/\r+$/, "", record)
    if (copy_terminated) {
        if (record != "") fail("line " source_line " has data after COPY terminator")
        next
    }
    if (record == "\\.") { copy_terminated = 1; next }
    scanned++
    if (scanned % 100000 == 0) {
        print progress_marker, scanned, emitted
        fflush()
    }
    if (NF != expected_fields) {
        fail("row " scanned " has " NF " fields; COPY declares " expected_fields)
    }
    sub(/\r+$/, "", $NF)

    raw_piid = $(piid_index)
    raw_fain = $(fain_index)
    raw_uri = $(uri_index)
    if (raw_piid ~ /[^ -~]/ || raw_fain ~ /[^ -~]/ || raw_uri ~ /[^ -~]/) {
        print $0
        emitted++
        next
    }

    piid_key = toupper(pgdecode(raw_piid))
    gsub(/[^A-Z0-9]/, "", piid_key)
    fain_key = toupper(stripped(pgdecode(raw_fain)))
    sub(/^,+/, "", fain_key)
    sub(/,+$/, "", fain_key)
    gsub(/[[:space:]]+/, " ", fain_key)
    uri_key = toupper(stripped(pgdecode(raw_uri)))
    sub(/^,+/, "", uri_key)
    sub(/,+$/, "", uri_key)
    gsub(/[[:space:]]+/, " ", uri_key)

    if ((length(piid_key) && piid_key in piid) ||
        (length(fain_key) && fain_key in fain) ||
        (length(uri_key) && uri_key in uri)) {
        print $0
        emitted++
    }
}

END {
    printf "%d\t%d\n", scanned, emitted > stats_file
    close(stats_file)
    if (failed) exit 65
}
"""


@dataclass(frozen=True)
class AwardSearchMirrorPin:
    """Immutable facts required to accept one database-mirror relation."""

    snapshot_date: str
    archive_url: str
    replica_urls: tuple[str, ...]
    archive_total_bytes: int
    archive_etag: str
    toc_sha256: str
    dump_id: str
    member_crc32: str
    member_bytes: int
    ordered_columns_sha256: str


FEBRUARY_2026_PIN = AwardSearchMirrorPin(
    snapshot_date="2026-02-06",
    archive_url=FEBRUARY_2026_ARCHIVE_URL,
    replica_urls=FEBRUARY_2026_REPLICA_URLS,
    archive_total_bytes=167_887_503_123,
    archive_etag='"69935c7e-2716dfff13"',
    toc_sha256="142c834a2fc98c9bb3b914e115eee8b3b37399f4e135acbf13fa71ee5abca54c",
    dump_id="5923",
    member_crc32="2af5c14c",
    member_bytes=40_724_040_516,
    ordered_columns_sha256="48a00db7e4b55c34b7ebb2011f147e1dfa39b7ed5ef0390e519920914dff060a",
)


@dataclass(frozen=True)
class AwardSearchSource:
    """Schema-verified serialized relation selected from the mirror."""

    member_name: str
    columns: tuple[str, ...]
    toc_sha256: str


def _text(value: Any) -> str:
    if value is None or value is pd.NA or value is pd.NaT:
        return ""
    try:
        if bool(pd.isna(value)):
            return ""
    except (TypeError, ValueError):
        pass
    normalized = str(value).strip()
    return "" if normalized.upper() in _NULL_TEXT else normalized


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _copy_value(value: str) -> str | None:
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


def _unquote(value: str) -> str:
    return value.strip().strip('"').replace('""', '"')


def _ordered_columns_sha256(columns: Sequence[str]) -> str:
    serialized = json.dumps(tuple(columns), separators=(",", ":"))
    return hashlib.sha256(serialized.encode()).hexdigest()


class _DigestingReader:
    def __init__(self, source: object) -> None:
        self.source = source
        self.digest = hashlib.sha256()
        self.bytes_read = 0

    def read(self, size: int = -1) -> bytes:
        data = self.source.read(size)  # type: ignore[attr-defined]
        self.digest.update(data)
        self.bytes_read += len(data)
        return data

    def seek(self, offset: int) -> object:
        if offset != self.bytes_read:
            raise OSError("Digesting ZIP member reader cannot seek across hashed bytes")
        return self.source.seek(offset)  # type: ignore[attr-defined]


class FebruaryAwardSearchExtractor:
    """Stream only exact requested award keys from the pinned mirror relation."""

    def __init__(
        self,
        attempts: pd.DataFrame,
        *,
        pin: AwardSearchMirrorPin = FEBRUARY_2026_PIN,
    ) -> None:
        if missing := sorted(_ATTEMPT_COLUMNS - set(attempts.columns)):
            raise IdentityRecoveryError(f"USAspending attempts missing columns: {missing}")
        usa_attempts = attempts.loc[attempts["adapter"].isin(_USA_ADAPTERS)].copy()
        if usa_attempts.empty:
            raise IdentityRecoveryError("No USAspending exact-key attempts were supplied")
        if usa_attempts[list(_ATTEMPT_COLUMNS)].map(_text).eq("").any().any():
            raise IdentityRecoveryError("USAspending exact-key attempts contain blank keys")

        self.pin = pin
        self.request_keys = {
            adapter: {
                (_text(row.agency_key).upper(), _text(row.canonical_award_key).upper())
                for row in usa_attempts.loc[usa_attempts["adapter"].eq(adapter)].itertuples()
            }
            for adapter in sorted(_USA_ADAPTERS)
        }
        self.stats = {"records_scanned": 0, "prefilter_matches": 0, "exact_matches": 0}
        self.provenance: dict[str, Any] = {}

    @staticmethod
    def _run_pg_restore(dump_dir: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
        executable = shutil.which("pg_restore")
        if executable is None:
            raise ArchiveSchemaError("pg_restore is required for award-search schema verification")
        return subprocess.run(
            [executable, *arguments, str(dump_dir)],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

    @classmethod
    def _resolve_source(cls, toc_file: Path, pin: AwardSearchMirrorPin) -> AwardSearchSource:
        toc_digest = _file_sha256(toc_file)
        if toc_digest != pin.toc_sha256:
            raise ArchiveSchemaError(f"February mirror toc.dat digest mismatch: {toc_digest}")
        with tempfile.TemporaryDirectory(prefix="award-search-schema-") as temp_name:
            archive_dir = Path(temp_name)
            shutil.copyfile(toc_file, archive_dir / "toc.dat")
            listing = cls._run_pg_restore(archive_dir, "--list")
            entries = []
            for line in listing.stdout.splitlines():
                if match := _TABLE_DATA_RE.match(line):
                    if _unquote(match[2]) == "rpt" and _unquote(match[3]) == "award_search":
                        entries.append(match[1])
            if entries != [pin.dump_id]:
                raise ArchiveSchemaError(
                    f"Expected one pinned {AWARD_SEARCH_RELATION} TABLE DATA entry; found {entries}"
                )
            with gzip.open(archive_dir / f"{pin.dump_id}.dat.gz", "wb"):
                pass
            restored = cls._run_pg_restore(
                archive_dir,
                "--data-only",
                "--schema=rpt",
                "--table=award_search",
                "--strict-names",
                "--file=-",
            )
            matches = list(_COPY_RE.finditer(restored.stdout))
            if len(matches) != 1:
                raise ArchiveSchemaError(
                    f"Expected one award_search COPY statement; found {len(matches)}"
                )
            match = matches[0]
            if _unquote(match["schema"]) != "rpt" or _unquote(match["table"]) != "award_search":
                raise ArchiveSchemaError("Pinned TABLE DATA produced an unexpected COPY target")
            columns = tuple(_unquote(item) for item in match["columns"].split(","))

        if missing := sorted(_REQUIRED_COLUMNS - set(columns)):
            raise ArchiveSchemaError(
                f"{AWARD_SEARCH_RELATION} is missing required columns: {missing}"
            )
        columns_digest = _ordered_columns_sha256(columns)
        if columns_digest != pin.ordered_columns_sha256:
            raise ArchiveSchemaError(
                f"February award_search column order mismatch: {columns_digest}"
            )
        return AwardSearchSource(f"{pin.dump_id}.dat.gz", columns, toc_digest)

    def _matches(self, row: dict[str, str | None]) -> tuple[str, ...]:
        agency = canonicalize_agency(row["awarding_toptier_agency_name"])
        if agency is None:
            return ()
        candidates = {
            USA_PIID_ADAPTER: canonicalize_piid(row["piid"]),
            USA_FAIN_ADAPTER: canonicalize_fain_or_uri(row["fain"]),
            USA_URI_ADAPTER: canonicalize_fain_or_uri(row["uri"]),
        }
        return tuple(
            adapter
            for adapter, key in candidates.items()
            if key is not None and (agency, key) in self.request_keys[adapter]
        )

    def _parse_candidates(
        self,
        lines: Iterator[str],
        columns: Sequence[str],
    ) -> Iterator[dict[str, Any]]:
        projected = _REQUIRED_COLUMNS
        indexes = {name: index for index, name in enumerate(columns) if name in projected}
        for line_number, line in enumerate(lines, 1):
            serialized = line.rstrip("\r\n")
            values = serialized.split("\t")
            if len(values) != len(columns):
                raise SourceDataError(
                    f"award_search candidate {line_number} has {len(values)} fields; "
                    f"COPY declares {len(columns)}"
                )
            row = {name: _copy_value(values[index]) for name, index in indexes.items()}
            matched_adapters = self._matches(row)
            if not matched_adapters:
                continue
            record_id = _text(row["generated_unique_award_id"]) or _text(row["award_id"])
            if not record_id:
                raise SourceDataError("An exact award_search match has no official record ID")
            self.stats["exact_matches"] += 1
            yield {
                "official_record_id": record_id,
                "awarding_agency": row["awarding_toptier_agency_name"],
                "piid": row["piid"],
                "fain": row["fain"],
                "uri": row["uri"],
                "recipient_uei": row["recipient_uei"],
                "recipient_duns": row["recipient_unique_id"],
                "matched_adapters": matched_adapters,
            }

    @staticmethod
    def _write_key_file(path: Path, values: set[str]) -> None:
        path.write_text("".join(f"{value}\n" for value in sorted(values)), encoding="ascii")

    def _prefilter_lines(
        self,
        source: gzip.GzipFile,
        columns: Sequence[str],
        *,
        awk_path: str,
    ) -> Iterator[str]:
        indexes = {name: index + 1 for index, name in enumerate(columns)}
        with tempfile.TemporaryDirectory(prefix="award-key-prefilter-") as temp_name:
            temp_dir = Path(temp_name)
            program_file = temp_dir / "prefilter.awk"
            piid_file = temp_dir / "piid.txt"
            fain_file = temp_dir / "fain.txt"
            uri_file = temp_dir / "uri.txt"
            stats_file = temp_dir / "stats.txt"
            error_file = temp_dir / "error.txt"
            stderr_file = temp_dir / "stderr.txt"
            program_file.write_text(_AWK_AWARD_KEY_PREFILTER, encoding="ascii")
            self._write_key_file(
                piid_file,
                {key for _, key in self.request_keys[USA_PIID_ADAPTER]},
            )
            self._write_key_file(
                fain_file,
                {key for _, key in self.request_keys[USA_FAIN_ADAPTER]},
            )
            self._write_key_file(
                uri_file,
                {key for _, key in self.request_keys[USA_URI_ADAPTER]},
            )
            command = [
                awk_path,
                "-v",
                f"piid_file={piid_file}",
                "-v",
                f"fain_file={fain_file}",
                "-v",
                f"uri_file={uri_file}",
                "-v",
                f"stats_file={stats_file}",
                "-v",
                f"error_file={error_file}",
                "-v",
                f"expected_fields={len(columns)}",
                "-v",
                f"piid_index={indexes['piid']}",
                "-v",
                f"fain_index={indexes['fain']}",
                "-v",
                f"uri_index={indexes['uri']}",
                "-f",
                str(program_file),
                str(piid_file),
                str(fain_file),
                str(uri_file),
                "-",
            ]
            environment = os.environ.copy()
            environment["LC_ALL"] = "C"
            feed_errors: list[BaseException] = []
            candidates_seen = 0
            completed = False

            with stderr_file.open("wb") as stderr:
                process = subprocess.Popen(
                    command,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=stderr,
                    env=environment,
                )
                assert process.stdin is not None
                assert process.stdout is not None

                def feed_source() -> None:
                    try:
                        shutil.copyfileobj(source, process.stdin, length=1024 * 1024)
                    except BrokenPipeError:
                        pass
                    except BaseException as error:  # pragma: no cover - remote I/O
                        feed_errors.append(error)
                    finally:
                        try:
                            process.stdin.close()
                        except BrokenPipeError:
                            pass

                feeder = threading.Thread(target=feed_source, daemon=True)
                feeder.start()
                try:
                    with io.TextIOWrapper(
                        process.stdout,
                        encoding="utf-8",
                        errors="replace",
                    ) as candidates:
                        for line in candidates:
                            progress = line.rstrip("\r\n").split("\t")
                            if len(progress) == 3 and progress[0] == (
                                "\x1eSBIR_AWARD_KEY_PROGRESS"
                            ):
                                continue
                            candidates_seen += 1
                            yield line
                    feeder.join()
                    return_code = process.wait()
                    if feed_errors:
                        raise SourceDataError(
                            "Could not stream award_search into the exact-key prefilter"
                        ) from feed_errors[0]
                    parsed_stats: tuple[int, int] | None = None
                    if stats_file.is_file():
                        values = stats_file.read_text(encoding="ascii").strip().split("\t")
                        if len(values) == 2:
                            try:
                                scanned, emitted = (int(value) for value in values)
                            except ValueError:
                                pass
                            else:
                                if scanned >= emitted >= 0 and emitted == candidates_seen:
                                    parsed_stats = scanned, emitted
                    if return_code != 0:
                        detail = (
                            error_file.read_text(encoding="utf-8", errors="replace").strip()
                            if error_file.is_file()
                            else ""
                        )
                        if not detail and stderr_file.is_file():
                            detail = stderr_file.read_text(
                                encoding="utf-8", errors="replace"
                            ).strip()
                        raise SourceDataError(
                            "Award-key prefilter failed closed: "
                            f"{detail or f'exit status {return_code}'}"
                        )
                    if parsed_stats is None:
                        raise SourceDataError(
                            "Award-key prefilter produced inconsistent scan statistics"
                        )
                    self.stats["records_scanned"], self.stats["prefilter_matches"] = parsed_stats
                    completed = True
                finally:
                    if not completed and process.poll() is None:
                        process.terminate()
                    if feeder.is_alive():
                        source.close()
                        feeder.join()
                    if process.poll() is None:
                        process.wait()

    @staticmethod
    def _validate_archive_identity(remote_zip: object, pin: AwardSearchMirrorPin) -> None:
        identity = remote_zip.identity  # type: ignore[attr-defined]
        if int(identity.total_bytes) != pin.archive_total_bytes:
            raise ArchiveSchemaError("February mirror archive byte length changed")
        if _text(identity.etag) != pin.archive_etag:
            raise ArchiveSchemaError("February mirror archive ETag changed")

    def extract(self) -> pd.DataFrame:
        """Run the full pinned remote scan and return exact official matches."""

        from sbir_etl.extractors.parallel_range_reader import ValidatedParallelRemoteZip

        awk_path = next(
            (path for name in ("mawk", "gawk", "awk") if (path := shutil.which(name))),
            None,
        )
        if awk_path is None:
            raise RuntimeError("A POSIX awk executable is required for the mirror scan")

        with ValidatedParallelRemoteZip(
            self.pin.archive_url,
            self.pin.replica_urls,
        ) as remote_zip:
            self._validate_archive_identity(remote_zip, self.pin)
            toc_infos = [
                info
                for info in remote_zip.infolist()
                if PurePosixPath(info.filename).name == "toc.dat"
            ]
            if len(toc_infos) != 1:
                raise ArchiveSchemaError(
                    f"February mirror must contain one toc.dat; found {len(toc_infos)}"
                )
            with tempfile.TemporaryDirectory(prefix="award-search-toc-") as temp_name:
                toc_file = Path(temp_name) / "toc.dat"
                with remote_zip.open(toc_infos[0]) as source, toc_file.open("wb") as target:
                    shutil.copyfileobj(source, target)
                relation = self._resolve_source(toc_file, self.pin)

            member_infos = [
                info for info in remote_zip.infolist() if info.filename == relation.member_name
            ]
            if len(member_infos) != 1:
                raise ArchiveSchemaError(
                    f"Expected one {relation.member_name}; found {len(member_infos)}"
                )
            member_info = member_infos[0]
            if f"{member_info.CRC:08x}" != self.pin.member_crc32:
                raise ArchiveSchemaError("February award_search member CRC changed")
            if int(member_info.file_size) != self.pin.member_bytes:
                raise ArchiveSchemaError("February award_search member byte length changed")

            self.provenance = {
                "snapshot_date": self.pin.snapshot_date,
                "archive_url": remote_zip.range_file.canonical_url,
                "archive_replica_urls": list(remote_zip.range_file.replica_urls),
                "archive_etag": remote_zip.identity.etag,
                "archive_total_bytes": remote_zip.identity.total_bytes,
                "relation": AWARD_SEARCH_RELATION,
                "member": relation.member_name,
                "member_crc32": f"{member_info.CRC:08x}",
                "member_bytes": member_info.file_size,
                "toc_sha256": relation.toc_sha256,
                "ordered_columns_sha256": _ordered_columns_sha256(relation.columns),
                "request_keys_sha256": hashlib.sha256(
                    json.dumps(
                        {
                            adapter: sorted(keys)
                            for adapter, keys in sorted(self.request_keys.items())
                        },
                        separators=(",", ":"),
                    ).encode()
                ).hexdigest(),
            }
            remote_zip.enable_parallel_prefetch()
            with remote_zip.open(member_info) as member:
                digesting_member = _DigestingReader(member)
                with gzip.GzipFile(fileobj=digesting_member) as decompressed:
                    candidates = self._prefilter_lines(
                        decompressed,
                        relation.columns,
                        awk_path=awk_path,
                    )
                    records = list(self._parse_candidates(candidates, relation.columns))
                while digesting_member.read(1024 * 1024):
                    pass
                if digesting_member.bytes_read != int(member_info.file_size):
                    raise SourceDataError("February award_search member did not reach EOF")
                self.provenance["member_sha256"] = digesting_member.digest.hexdigest()
            remote_zip.range_file.validate_pending()

        self.provenance["extraction_stats"] = dict(self.stats)
        return pd.DataFrame.from_records(
            records,
            columns=[
                "official_record_id",
                "awarding_agency",
                "piid",
                "fain",
                "uri",
                "recipient_uei",
                "recipient_duns",
                "matched_adapters",
            ],
        )

    def extract_to_parquet(self, output_path: Path) -> int:
        """Atomically publish exact matches and a sidecar provenance manifest."""

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        result = self.extract()
        with tempfile.NamedTemporaryFile(
            dir=output_path.parent,
            prefix=f".{output_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
        try:
            result.to_parquet(temporary_path, index=False)
            os.replace(temporary_path, output_path)
        finally:
            temporary_path.unlink(missing_ok=True)
        output_digest = _file_sha256(output_path)
        manifest = {**self.provenance, "output_sha256": output_digest, "rows": len(result)}
        manifest_path = output_path.with_suffix(".manifest.json")
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return len(result)
