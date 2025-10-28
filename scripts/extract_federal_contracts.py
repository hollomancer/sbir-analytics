#!/usr/bin/env python3
"""
Extract federal contracts from USAspending PostgreSQL dump.

This script extracts contracts for SBIR vendors only, filtering the
large USAspending dataset to manageable size.

Usage:
    # Extract from subset (17GB)
    poetry run python scripts/extract_federal_contracts.py --subset

    # Extract from full dataset (200GB)
    poetry run python scripts/extract_federal_contracts.py --full
"""

import argparse
from pathlib import Path
from loguru import logger

from src.extractors.contract_extractor import ContractExtractor


def main():
    """Main execution."""
    parser = argparse.ArgumentParser(description="Extract federal contracts for SBIR vendors")
    parser.add_argument(
        "--subset", action="store_true", help="Extract from subset dump (17GB, for testing)"
    )
    parser.add_argument("--full", action="store_true", help="Extract from full dump (200GB)")
    parser.add_argument("--dump-dir", type=Path, help="Custom dump directory path")
    parser.add_argument("--output", type=Path, help="Custom output file path")

    args = parser.parse_args()

    # Determine paths
    if args.dump_dir:
        dump_dir = args.dump_dir
    elif args.subset:
        dump_dir = Path("/Volumes/X10 Pro/projects/sbir-etl-data/pruned_data_store_api_dump")
    elif args.full:
        dump_dir = Path(
            "/Volumes/X10 Pro/projects/sbir-etl-data/full_dump"
        )  # Will extract full zip
    else:
        logger.error("Please specify --subset or --full (or provide --dump-dir)")
        return

    if args.output:
        output_file = args.output
    else:
        output_file = Path("/Volumes/X10 Pro/projects/sbir-etl-data/filtered_contracts.parquet")

    vendor_filter_file = Path("/Volumes/X10 Pro/projects/sbir-etl-data/sbir_vendor_filters.json")

    # Validate inputs
    if not dump_dir.exists():
        logger.error(f"Dump directory not found: {dump_dir}")
        if not args.subset:
            logger.info("For subset extraction, the dump should be extracted to:")
            logger.info(f"  {dump_dir}")
        return

    if not vendor_filter_file.exists():
        logger.error(f"Vendor filter file not found: {vendor_filter_file}")
        logger.info("Run: poetry run python scripts/extract_sbir_vendors.py")
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

        logger.success(f"Extraction complete! {num_contracts:,} contracts extracted")

    except Exception as e:
        logger.error(f"Extraction failed: {e}")
        raise


if __name__ == "__main__":
    main()
