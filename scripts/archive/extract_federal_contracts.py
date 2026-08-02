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

from loguru import logger

from sbir_etl.config.loader import get_config
from sbir_etl.extractors.contract_extractor import ContractExtractor
from sbir_etl.extractors.usaspending_award_archive import (
    AWARD_ARCHIVE_PROVENANCE_VERSION,
    AWARD_ARCHIVE_SOURCE_KIND,
    AwardArchiveContractExtractor,
)


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
AWARD_ARCHIVE_PROVENANCE_KEYS = frozenset(
    {
        "source_kind",
        "canonical_table",
        "physical_table",
        "archive_file",
        "archive_sha256",
        "archive_size_bytes",
        "member_count",
        "member_manifest_sha256",
        "ordered_columns_sha256",
        "column_count",
        "vendor_filter_sha256",
        "output_sha256",
        "provenance_version",
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


def write_contract_provenance_checks(
    *,
    extractor: ContractExtractor,
    output_file: Path,
    vendor_filter_file: Path,
    expected_vendor_filter_sha256: str,
    total_rows: int,
    source: Mapping[str, str],
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
        }
    )
    source_kind = provenance.get("source_kind", "database_dump")
    if source_kind == AWARD_ARCHIVE_SOURCE_KIND:
        required_keys = AWARD_ARCHIVE_PROVENANCE_KEYS
        expected_version = AWARD_ARCHIVE_PROVENANCE_VERSION
        expected_table = "award_data_archive.contracts_full"
    else:
        required_keys = SOURCE_PROVENANCE_KEYS
        expected_version = SOURCE_PROVENANCE_VERSION
        expected_table = "rpt.transaction_search"
        provenance["provenance_version"] = SOURCE_PROVENANCE_VERSION

    missing = sorted(required_keys - set(provenance))
    if missing:
        raise RuntimeError(f"Verified contract provenance is missing fields: {missing}")
    if provenance.get("provenance_version") != expected_version:
        raise RuntimeError("Verified contract provenance has the wrong version")
    if provenance.get("canonical_table") != expected_table:
        raise RuntimeError("Verified contract provenance has the wrong canonical table")
    if source_kind == AWARD_ARCHIVE_SOURCE_KIND:
        if provenance.get("physical_table") != expected_table:
            raise RuntimeError("Verified contract provenance has the wrong physical table")
        archive_file = provenance.get("archive_file")
        if not isinstance(archive_file, str) or not archive_file.endswith(".zip"):
            raise RuntimeError("Verified contract provenance has an invalid archive file")
    else:
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
        "vendor_filter_sha256",
        "output_sha256",
    ):
        if not _valid_sha256(provenance.get(key)):
            raise RuntimeError(f"Verified contract provenance has an invalid {key}")
    source_hash_keys = (
        ("archive_sha256", "member_manifest_sha256")
        if source_kind == AWARD_ARCHIVE_SOURCE_KIND
        else ("toc_sha256",)
    )
    for key in source_hash_keys:
        if not _valid_sha256(provenance.get(key)):
            raise RuntimeError(f"Verified contract provenance has an invalid {key}")

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
        "--award-archive",
        type=Path,
        help=(
            "Stream a local USAspending Contracts_Full Award Data Archive ZIP, "
            "filtering to the configured SBIR vendor frame."
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

    args = parser.parse_args()
    selected_modes = sum(
        bool(value)
        for value in (args.subset, args.full, args.dump_dir, args.remote_zip, args.award_archive)
    )
    if selected_modes != 1:
        parser.error(
            "select exactly one source: --subset, --full, --dump-dir, --remote-zip, "
            "or --award-archive"
        )

    # Load configuration for default paths
    config = get_config()

    vendor_filter_file = config.paths.resolve_path("transition_vendor_filters")
    if not vendor_filter_file.exists():
        logger.error(f"Vendor filter file not found: {vendor_filter_file}")
        logger.info("Run: python scripts/archive/extract_sbir_vendors.py")
        return
    vendor_filter_sha256 = _file_sha256(vendor_filter_file)

    if args.award_archive:
        output_file = args.output or config.paths.resolve_path("transition_contracts_output")
        extractor = AwardArchiveContractExtractor(
            vendor_filter_file=vendor_filter_file,
            batch_size=10000,
        )
        logger.info(f"Streaming USAspending award archive {args.award_archive}")
        logger.info(f"Output will be saved to {output_file}")
        num_contracts = extractor.extract_from_archive(args.award_archive, output_file)
        checks_path = write_contract_provenance_checks(
            extractor=extractor,
            output_file=output_file,
            vendor_filter_file=vendor_filter_file,
            expected_vendor_filter_sha256=vendor_filter_sha256,
            total_rows=num_contracts,
            source={"award_archive": str(args.award_archive)},
        )
        logger.success(f"Extraction complete! {num_contracts:,} contracts extracted")
        logger.success(f"Provenance checks saved to {checks_path}")
        return

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
            )
            checks_path = write_contract_provenance_checks(
                extractor=extractor,
                output_file=output_file,
                vendor_filter_file=vendor_filter_file,
                expected_vendor_filter_sha256=vendor_filter_sha256,
                total_rows=num_contracts,
                source={"remote_zip": args.remote_zip},
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
