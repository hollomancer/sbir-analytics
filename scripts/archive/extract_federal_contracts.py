#!/usr/bin/env python3
"""
Extract federal contracts from USAspending PostgreSQL dump.

This script extracts contracts for SBIR vendors only, filtering the
large USAspending dataset to manageable size.

Usage:
    # Extract from a locally-extracted subset dump
    python scripts/archive/extract_federal_contracts.py --subset

    # Extract from a locally-extracted full dump
    python scripts/archive/extract_federal_contracts.py --full

    # Stream the schema-verified FPDS transaction-search member straight from a
    # remote USAspending .zip over HTTP range — no full ~217GB download, nothing
    # staged on local disk (needs the 'streaming' extra: uv sync --extra streaming).
    python scripts/archive/extract_federal_contracts.py \\
        --remote-zip https://files.usaspending.gov/database_download/usaspending-db-subset_20240101.zip
"""

import argparse
import hashlib
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

from loguru import logger

from sbir_etl.config.loader import get_config
from sbir_etl.extractors.contract_extractor import ContractExtractor


SOURCE_PROVENANCE_VERSION = 1
SOURCE_PROVENANCE_KEYS = frozenset(
    {
        "canonical_table",
        "physical_table",
        "member",
        "ordered_columns_sha256",
        "column_count",
        "toc_sha256",
        "vendor_filter_sha256",
        "output_sha256",
        "provenance_version",
    }
)
PARALLEL_SOURCE_PROVENANCE_KEYS = frozenset(
    {
        "archive_url",
        "archive_replica_urls",
        "archive_etag",
        "archive_total_bytes",
        "member_crc32",
        "member_compressed_bytes",
        "member_uncompressed_bytes",
        "range_chunk_bytes",
        "range_workers",
    }
)


def _file_sha256(path: Path) -> str:
    """Hash a provenance input without loading it into memory."""

    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _valid_sha256(value: object) -> bool:
    return bool(
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value.lower())
    )


def _valid_positive_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _valid_https_url(value: object) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urlsplit(value)
    return bool(
        parsed.scheme == "https"
        and parsed.hostname
        and parsed.username is None
        and parsed.password is None
        and not parsed.fragment
    )


def write_contract_provenance_checks(
    *,
    extractor: ContractExtractor,
    output_file: Path,
    vendor_filter_file: Path,
    expected_vendor_filter_sha256: str,
    total_rows: int,
    source: Mapping[str, object],
) -> Path:
    """Atomically bind an extracted parquet to its verified source inputs."""

    output_file = Path(output_file)
    vendor_filter_file = Path(vendor_filter_file)
    current_vendor_sha256 = _file_sha256(vendor_filter_file)
    if current_vendor_sha256 != expected_vendor_filter_sha256:
        raise RuntimeError(
            "Vendor filter changed during contract extraction; refusing to write provenance"
        )

    provenance: dict[str, object] = dict(extractor.source_provenance)
    provenance.update(
        {
            "vendor_filter_sha256": current_vendor_sha256,
            "output_sha256": _file_sha256(output_file),
            "provenance_version": SOURCE_PROVENANCE_VERSION,
        }
    )
    missing = sorted(SOURCE_PROVENANCE_KEYS - set(provenance))
    if missing:
        raise RuntimeError(f"Verified contract provenance is missing fields: {missing}")
    if provenance.get("canonical_table") != "rpt.transaction_search":
        raise RuntimeError("Verified contract provenance has the wrong canonical table")
    if provenance.get("physical_table") not in {
        "rpt.transaction_search",
        "rpt.transaction_search_fpds",
    }:
        raise RuntimeError("Verified contract provenance has the wrong physical table")
    member = provenance.get("member")
    if not isinstance(member, str) or not member.endswith(".dat.gz"):
        raise RuntimeError("Verified contract provenance has an invalid archive member")
    column_count = provenance.get("column_count")
    if not isinstance(column_count, int) or isinstance(column_count, bool) or column_count <= 0:
        raise RuntimeError("Verified contract provenance has an invalid column count")
    for key in (
        "ordered_columns_sha256",
        "toc_sha256",
        "vendor_filter_sha256",
        "output_sha256",
    ):
        if not _valid_sha256(provenance.get(key)):
            raise RuntimeError(f"Verified contract provenance has an invalid {key}")
    member_sha256 = provenance.get("member_sha256")
    if member_sha256 is not None and not _valid_sha256(member_sha256):
        raise RuntimeError("Verified contract provenance has an invalid member_sha256")

    parallel_fields = PARALLEL_SOURCE_PROVENANCE_KEYS.intersection(provenance)
    if parallel_fields:
        required_parallel = PARALLEL_SOURCE_PROVENANCE_KEYS | {"member_sha256"}
        if missing_parallel := sorted(required_parallel - set(provenance)):
            raise RuntimeError(
                f"Verified parallel-range provenance is missing fields: {missing_parallel}"
            )
        archive_etag = provenance["archive_etag"]
        if (
            not isinstance(archive_etag, str)
            or not archive_etag.startswith('"')
            or not archive_etag.endswith('"')
            or archive_etag.lower().startswith("w/")
        ):
            raise RuntimeError("Verified parallel-range provenance has an invalid archive ETag")
        positive_int_fields = (
            "archive_total_bytes",
            "member_uncompressed_bytes",
            "range_chunk_bytes",
        )
        if any(not _valid_positive_int(provenance[field]) for field in positive_int_fields):
            raise RuntimeError("Verified parallel-range provenance has an invalid byte size")
        compressed_bytes = provenance["member_compressed_bytes"]
        if (
            not isinstance(compressed_bytes, int)
            or isinstance(compressed_bytes, bool)
            or compressed_bytes < 0
        ):
            raise RuntimeError("Verified parallel-range provenance has an invalid member size")
        workers = provenance["range_workers"]
        if not isinstance(workers, int) or isinstance(workers, bool) or not 1 <= workers <= 4:
            raise RuntimeError("Verified parallel-range provenance has an invalid worker count")
        member_crc32 = provenance["member_crc32"]
        if (
            not isinstance(member_crc32, str)
            or len(member_crc32) != 8
            or any(character not in "0123456789abcdef" for character in member_crc32.lower())
        ):
            raise RuntimeError("Verified parallel-range provenance has an invalid member CRC32")
        archive_url = provenance["archive_url"]
        replicas = provenance["archive_replica_urls"]
        if not _valid_https_url(archive_url):
            raise RuntimeError("Verified parallel-range provenance has an invalid archive URL")
        if not isinstance(replicas, list) or any(not _valid_https_url(url) for url in replicas):
            raise RuntimeError("Verified parallel-range provenance has invalid replica URLs")

    checks_path = output_file.with_suffix(".checks.json")
    checks = {
        "ok": True,
        "generated_at": datetime.now(UTC).isoformat(),
        "total_rows": total_rows,
        "extraction_stats": dict(extractor.stats),
        "source_provenance": provenance,
        "source": {
            **source,
            "vendor_filter_path": str(vendor_filter_file),
        },
    }
    checks_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = checks_path.with_name(f".{checks_path.name}.tmp")
    try:
        temporary_path.write_text(
            json.dumps(checks, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary_path.replace(checks_path)
    finally:
        temporary_path.unlink(missing_ok=True)
    return checks_path


def main():
    """Main execution."""
    parser = argparse.ArgumentParser(description="Extract federal contracts for SBIR vendors")
    parser.add_argument(
        "--subset", action="store_true", help="Extract from subset dump (17GB, for testing)"
    )
    parser.add_argument("--full", action="store_true", help="Extract from full dump (200GB)")
    parser.add_argument("--dump-dir", type=Path, help="Custom dump directory path")
    parser.add_argument("--output", type=Path, help="Custom output file path")
    parser.add_argument(
        "--remote-zip",
        type=str,
        help=(
            "Stream one member from a remote USAspending database .zip over HTTP range "
            "(no full download). Requires the 'streaming' extra; the member streamed is "
            "resolved from the archive TOC and verified as the FPDS transaction-search "
            "table."
        ),
    )
    parser.add_argument(
        "--member",
        type=str,
        default=None,
        help=(
            "Optional expected .dat.gz member inside --remote-zip. The value must match "
            "the unique FPDS transaction-search member resolved from the archive TOC; "
            "a mismatch fails closed."
        ),
    )
    parser.add_argument(
        "--parallel-range",
        action="store_true",
        help=(
            "Read the selected remote ZIP member through four bounded, fully validated "
            "parallel HTTP ranges. Archive metadata and payload share one strong ETag identity."
        ),
    )
    parser.add_argument(
        "--parallel-range-replica",
        action="append",
        default=[],
        metavar="HTTPS_URL",
        help=(
            "Explicit byte-identical replica used by --parallel-range after its strong ETag "
            "and total size match --remote-zip. Repeat for multiple replicas; URLs are never "
            "derived heuristically."
        ),
    )

    args = parser.parse_args()
    if args.parallel_range and not args.remote_zip:
        parser.error("--parallel-range requires --remote-zip")
    if args.parallel_range_replica and not args.parallel_range:
        parser.error("--parallel-range-replica requires --parallel-range")

    # Load configuration for default paths
    config = get_config()

    vendor_filter_file = config.paths.resolve_path("transition_vendor_filters")
    if not vendor_filter_file.exists():
        logger.error(f"Vendor filter file not found: {vendor_filter_file}")
        logger.info("Run: python scripts/archive/extract_sbir_vendors.py")
        return
    vendor_filter_sha256 = _file_sha256(vendor_filter_file)

    # Remote-zip streaming path: no local dump required.
    if args.remote_zip:
        output_file = args.output or config.paths.resolve_path("transition_contracts_output")
        logger.info("Initializing ContractExtractor (remote-zip streaming)...")
        extractor = ContractExtractor(
            vendor_filter_file=vendor_filter_file,
            batch_size=10000,
        )
        member_label = args.member or "(resolve from archive TOC)"
        logger.info(f"Streaming member {member_label} from {args.remote_zip}")
        logger.info(f"Output will be saved to {output_file}")
        try:
            num_contracts = extractor.extract_from_remote_zip(
                zip_url=args.remote_zip,
                member_name=args.member,
                output_file=output_file,
                parallel_range=args.parallel_range,
                replica_urls=args.parallel_range_replica,
            )
            checks_path = write_contract_provenance_checks(
                extractor=extractor,
                output_file=output_file,
                vendor_filter_file=vendor_filter_file,
                expected_vendor_filter_sha256=vendor_filter_sha256,
                total_rows=num_contracts,
                source={
                    "remote_zip": args.remote_zip,
                    "parallel_range": args.parallel_range,
                    "parallel_range_replicas": args.parallel_range_replica,
                },
            )
            logger.success(f"Extraction complete! {num_contracts:,} contracts extracted")
            logger.success(f"Provenance checks saved to {checks_path}")
        except Exception as e:
            logger.error(f"Remote-zip extraction failed: {e}")
            raise
        return

    # Determine paths
    if args.dump_dir:
        dump_dir = args.dump_dir
    elif args.subset:
        dump_dir = config.paths.resolve_path("transition_dump_dir")
    elif args.full:
        # Full dump directory (typically a parent of the subset)
        dump_dir = config.paths.resolve_path("transition_dump_dir").parent / "full_dump"
    else:
        logger.error("Please specify --subset or --full (or provide --dump-dir)")
        return

    if args.output:
        output_file = args.output
    else:
        output_file = config.paths.resolve_path("transition_contracts_output")

    # Validate inputs
    if not dump_dir.exists():
        logger.error(f"Dump directory not found: {dump_dir}")
        if not args.subset:
            logger.info("For subset extraction, the dump should be extracted to:")
            logger.info(f"  {dump_dir}")
        return

    # Initialize extractor
    logger.info("Initializing ContractExtractor...")
    extractor = ContractExtractor(
        vendor_filter_file=vendor_filter_file,
        batch_size=10000,
    )

    # Extract contracts
    logger.info(f"Extracting contracts from {dump_dir}")
    logger.info(f"Output will be saved to {output_file}")
    logger.info("This may take several hours for large dumps...")

    try:
        num_contracts = extractor.extract_from_dump(
            dump_dir=dump_dir,
            output_file=output_file,
        )

        checks_path = write_contract_provenance_checks(
            extractor=extractor,
            output_file=output_file,
            vendor_filter_file=vendor_filter_file,
            expected_vendor_filter_sha256=vendor_filter_sha256,
            total_rows=num_contracts,
            source={"dump_dir": str(dump_dir)},
        )

        logger.success(f"Extraction complete! {num_contracts:,} contracts extracted")
        logger.success(f"Provenance checks saved to {checks_path}")

    except Exception as e:
        logger.error(f"Extraction failed: {e}")
        raise


if __name__ == "__main__":
    main()
