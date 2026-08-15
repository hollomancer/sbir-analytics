#!/usr/bin/env python3
"""Pin local USAspending All Contracts Full archives in a validated source bundle."""

import argparse
import csv
import hashlib
import io
import json
import os
import tempfile
import zipfile
from collections.abc import Sequence
from datetime import date, datetime
from pathlib import Path
from typing import Any

from sbir_analytics.assets.agency_private_capital import usaspending_contract_source as contract


class BundleBuildError(ValueError):
    """Raised when local archives cannot form a valid source bundle."""


def _parse_iso_date(value: str) -> date:
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("date must use canonical YYYY-MM-DD form") from exc
    if parsed.isoformat() != value:
        raise argparse.ArgumentTypeError("date must use canonical YYYY-MM-DD form")
    return parsed


def _archive_metadata(path: Path) -> tuple[int, date]:
    match = contract.ARCHIVE_FILENAME_RE.fullmatch(path.name)
    if match is None:
        raise BundleBuildError(
            f"archive filename does not identify an official All Contracts Full product: {path.name}"
        )
    fiscal_year = int(match["fiscal_year"])
    raw_updated = match["updated"]
    try:
        updated = datetime.strptime(raw_updated, "%Y%m%d").date()
    except ValueError as exc:
        raise BundleBuildError(f"archive filename has an invalid update date: {path.name}") from exc
    if updated.strftime("%Y%m%d") != raw_updated:
        raise BundleBuildError(f"archive filename has a noncanonical update date: {path.name}")
    return fiscal_year, updated


def _sha256_path(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as source:
        for block in iter(lambda: source.read(8 * 1024 * 1024), b""):
            digest.update(block)
            size += len(block)
    return digest.hexdigest(), size


def _read_header(archive: zipfile.ZipFile, info: zipfile.ZipInfo) -> list[str]:
    if info.flag_bits & 0x1:
        raise BundleBuildError(f"encrypted archive member is not supported: {info.filename}")
    try:
        with archive.open(info) as raw:
            with io.TextIOWrapper(raw, encoding="utf-8-sig", errors="strict", newline="") as text:
                try:
                    return next(csv.reader(text, strict=True))
                except StopIteration as exc:
                    raise BundleBuildError(f"archive member is empty: {info.filename}") from exc
    except (OSError, RuntimeError, UnicodeDecodeError, csv.Error, zipfile.BadZipFile) as exc:
        raise BundleBuildError(
            f"archive member does not have a readable UTF-8 CSV header: {info.filename}"
        ) from exc


def _member_pins(path: Path) -> list[dict[str, Any]]:
    try:
        with zipfile.ZipFile(path) as archive:
            infos = sorted(archive.infolist(), key=lambda info: info.filename)
            if not infos:
                raise BundleBuildError(f"archive is empty: {path.name}")
            return [
                {
                    "crc32": info.CRC,
                    "headers": _read_header(archive, info),
                    "member_name": info.filename,
                    "size_bytes": info.file_size,
                }
                for info in infos
            ]
    except (OSError, zipfile.BadZipFile) as exc:
        raise BundleBuildError(f"archive is not a readable ZIP: {path.name}") from exc


def _requested_fiscal_years(fiscal_years: Sequence[int]) -> tuple[int, ...]:
    if not fiscal_years:
        raise BundleBuildError("at least one fiscal year must be requested")
    if any(
        isinstance(year, bool) or not isinstance(year, int) or year <= 0 for year in fiscal_years
    ):
        raise BundleBuildError("requested fiscal years must be positive integers")
    if len(fiscal_years) != len(set(fiscal_years)):
        raise BundleBuildError("each fiscal year must be requested exactly once")
    requested = tuple(sorted(fiscal_years))
    if requested != tuple(range(requested[0], requested[-1] + 1)):
        raise BundleBuildError("requested fiscal years must be contiguous")
    return requested


def _discover_archives(
    archive_dir: Path, *, fiscal_years: tuple[int, ...]
) -> list[tuple[Path, int, date]]:
    if not archive_dir.is_dir():
        raise BundleBuildError(f"archive directory does not exist: {archive_dir}")
    requested = set(fiscal_years)
    selected: dict[int, tuple[Path, date]] = {}
    for archive in sorted(archive_dir.iterdir(), key=lambda entry: entry.name):
        if archive.suffix.casefold() != ".zip":
            continue
        match = contract.ARCHIVE_FILENAME_RE.fullmatch(archive.name)
        if match is None:
            if any(archive.name.startswith(f"FY{year}_") for year in requested):
                _archive_metadata(archive)
            continue
        fiscal_year = int(match["fiscal_year"])
        if fiscal_year not in requested:
            continue
        if archive.is_symlink():
            raise BundleBuildError(f"archive must not be a symbolic link: {archive.name}")
        if not archive.is_file():
            raise BundleBuildError(f"archive path is not a regular file: {archive.name}")
        _, updated = _archive_metadata(archive)
        if fiscal_year in selected:
            raise BundleBuildError(f"multiple archives found for FY{fiscal_year}")
        selected[fiscal_year] = (archive, updated)
    if missing := sorted(requested - set(selected)):
        raise BundleBuildError(f"requested fiscal-year archives are missing: {missing}")
    return [(selected[year][0], year, selected[year][1]) for year in fiscal_years]


def _canonical_json(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def build_source_bundle(
    *,
    source_snapshot_date: date,
    fiscal_years: Sequence[int],
    archive_dir: Path,
    output: Path,
) -> dict[str, Any]:
    """Build, validate, content-address, and atomically publish a source manifest."""

    archive_dir = archive_dir.resolve()
    requested = _requested_fiscal_years(fiscal_years)
    parsed = _discover_archives(archive_dir, fiscal_years=requested)
    resolved_output = output.resolve()
    if any(path == resolved_output for path, _, _ in parsed):
        raise BundleBuildError("output must not overwrite a source archive")
    latest_closed_fiscal_year = source_snapshot_date.year + (source_snapshot_date.month >= 10) - 1
    if requested[-1] > latest_closed_fiscal_year:
        raise BundleBuildError(
            f"FY{requested[-1]} is not closed as of {source_snapshot_date.isoformat()}"
        )
    if any(updated > source_snapshot_date for _, _, updated in parsed):
        raise BundleBuildError("archive update date follows the source snapshot date")

    archive_rows: list[dict[str, Any]] = []
    for path, fiscal_year, updated in sorted(parsed, key=lambda item: item[1]):
        sha256, size_bytes = _sha256_path(path)
        archive_rows.append(
            {
                "filename": path.name,
                "fiscal_year": fiscal_year,
                "local_path": path.name,
                "members": _member_pins(path),
                "sha256": sha256,
                "size_bytes": size_bytes,
                "source_url": (f"https://files.usaspending.gov/award_data_archive/{path.name}"),
                "upstream_updated_date": updated.isoformat(),
            }
        )

    manifest: dict[str, Any] = {
        "archives": archive_rows,
        "end_fiscal_year": requested[-1],
        "product": contract.PRODUCT,
        "schema_version": contract.SCHEMA_VERSION,
        "source_snapshot_date": source_snapshot_date.isoformat(),
        "start_fiscal_year": requested[0],
    }
    validated = contract.validate_usaspending_contract_source_bundle(manifest, base_dir=archive_dir)
    manifest["source_release_id"] = validated.source_release_id
    _atomic_write(output, _canonical_json(manifest))
    return manifest


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-snapshot-date", required=True, type=_parse_iso_date)
    parser.add_argument(
        "--fiscal-year", dest="fiscal_years", action="append", required=True, type=int
    )
    parser.add_argument("--archive-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    manifest = build_source_bundle(
        source_snapshot_date=args.source_snapshot_date,
        fiscal_years=args.fiscal_years,
        archive_dir=args.archive_dir,
        output=args.output,
    )
    print(
        json.dumps(
            {
                "archive_count": len(manifest["archives"]),
                "end_fiscal_year": manifest["end_fiscal_year"],
                "output": str(args.output),
                "source_release_id": manifest["source_release_id"],
                "start_fiscal_year": manifest["start_fiscal_year"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
