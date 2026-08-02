#!/usr/bin/env python3
"""
Extract unique vendor identifiers from SBIR awards data.

This script creates a vendor filter list for use in federal contracts extraction.
Outputs vendor identifiers (UEI, DUNS, company names) to be used for filtering
the 200GB USAspending dataset to only SBIR-relevant contracts.

Usage:
    python scripts/archive/extract_sbir_vendors.py
    python scripts/archive/extract_sbir_vendors.py --awards-file data/raw/sbir/award_data.csv
"""

import argparse
import json
from pathlib import Path

import pandas as pd
from loguru import logger


# Import config loader for default paths
try:
    from sbir_etl.config.loader import get_config

    _config_available = True
except ImportError:
    _config_available = False


def extract_vendors(
    awards_file: Path,
    output_file: Path,
) -> dict:
    """
    Extract unique vendor identifiers from SBIR awards.

    Args:
        awards_file: Path to SBIR awards CSV
        output_file: Path to output JSON file with vendor filters

    Returns:
        Dictionary with vendor filter statistics
    """
    logger.info(f"Reading SBIR awards from {awards_file}")

    # Extract vendor identifiers
    vendors: dict[str, set[str]] = {
        "uei": set(),
        "duns": set(),
        "company_names": set(),
    }

    header = pd.read_csv(awards_file, nrows=0).columns
    columns = [column for column in ("UEI", "Duns", "Company") if column in header]
    if not columns:
        raise ValueError("SBIR awards CSV has none of the vendor columns: UEI, Duns, Company")

    total_awards = 0
    for chunk in pd.read_csv(
        awards_file,
        usecols=columns,
        dtype="string",
        chunksize=100_000,
        low_memory=False,
    ):
        total_awards += len(chunk)
        for column, key in (("UEI", "uei"), ("Duns", "duns")):
            if column in chunk:
                values = chunk[column].dropna().str.strip()
                vendors[key].update(values[values != ""].tolist())
        if "Company" in chunk:
            names = chunk["Company"].dropna().str.strip()
            vendors["company_names"].update(name.upper() for name in names[names != ""].tolist())
    logger.info(f"Loaded {total_awards:,} awards")
    logger.info(f"Found {len(vendors['uei']):,} unique UEI values")
    logger.info(f"Found {len(vendors['duns']):,} unique DUNS values")
    logger.info(f"Found {len(vendors['company_names']):,} unique company names")

    # Prepare JSON-serializable output
    stats = {
        "total_awards": total_awards,
        "unique_uei": len(vendors["uei"]),
        "unique_duns": len(vendors["duns"]),
        "unique_companies": len(vendors["company_names"]),
    }
    output_data = {
        "uei": sorted(vendors["uei"]),
        "duns": sorted(vendors["duns"]),
        "company_names": sorted(vendors["company_names"]),
        "stats": stats,
    }

    # Write to file
    logger.info(f"Writing vendor filters to {output_file}")
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with open(output_file, "w") as f:
        json.dump(output_data, f, indent=2)

    logger.success(f"Vendor filter file created: {output_file}")
    logger.info(f"Total unique vendors: {len(vendors['uei']) + len(vendors['duns']):,}")

    return stats


def main():
    """Main execution."""
    parser = argparse.ArgumentParser(description="Build the SBIR vendor filter")
    parser.add_argument("--awards-file", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    # Paths
    project_root = Path(__file__).resolve().parents[2]
    awards_file = project_root / "data" / "raw" / "sbir" / "award_data.csv"

    # Determine paths from config if available (output + awards input)
    output_file = project_root / "data" / "transition" / "sbir_vendor_filters.json"
    if _config_available:
        try:
            config = get_config()
            output_file = config.paths.resolve_path("transition_vendor_filters")
            awards_file = project_root / config.extraction.sbir.csv_path
        except Exception:
            pass  # Fall back to default

    awards_file = args.awards_file or awards_file
    output_file = args.output or output_file

    # Check if awards file exists
    if not awards_file.exists():
        logger.error(f"Awards file not found: {awards_file}")
        logger.info("Please ensure SBIR awards data is available")
        return

    # Extract vendors
    stats = extract_vendors(awards_file, output_file)

    # Print summary
    logger.info("\n" + "=" * 60)
    logger.info("SBIR Vendor Extraction Summary")
    logger.info("=" * 60)
    for key, value in stats.items():
        logger.info(f"  {key}: {value:,}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
