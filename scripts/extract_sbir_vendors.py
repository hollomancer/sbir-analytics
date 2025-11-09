#!/usr/bin/env python3
"""
Extract unique vendor identifiers from SBIR awards data.

This script creates a vendor filter list for use in federal contracts extraction.
Outputs vendor identifiers (UEI, DUNS, company names) to be used for filtering
the 200GB USAspending dataset to only SBIR-relevant contracts.

Usage:
    poetry run python scripts/extract_sbir_vendors.py
"""

import json
from pathlib import Path

import pandas as pd
from loguru import logger


# Import config loader for default paths
try:
    from src.config.loader import get_config

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

    # Read awards data
    df = pd.read_csv(awards_file, low_memory=False)
    logger.info(f"Loaded {len(df):,} awards")

    # Extract vendor identifiers
    vendors = {
        "uei": set(),
        "duns": set(),
        "company_names": set(),
    }

    # Extract UEI (Unique Entity Identifier)
    if "UEI" in df.columns:
        uei_values = df["UEI"].dropna().astype(str).str.strip()
        uei_values = uei_values[uei_values != ""]
        vendors["uei"] = set(uei_values.unique())
        logger.info(f"Found {len(vendors['uei']):,} unique UEI values")

    # Extract DUNS
    if "Duns" in df.columns:
        duns_values = df["Duns"].dropna().astype(str).str.strip()
        duns_values = duns_values[duns_values != ""]
        vendors["duns"] = set(duns_values.unique())
        logger.info(f"Found {len(vendors['duns']):,} unique DUNS values")

    # Extract company names (for fuzzy matching fallback)
    if "Company" in df.columns:
        company_values = df["Company"].dropna().astype(str).str.strip()
        company_values = company_values[company_values != ""]
        # Normalize company names (uppercase)
        vendors["company_names"] = {name.upper() for name in company_values.unique()}
        logger.info(f"Found {len(vendors['company_names']):,} unique company names")

    # Prepare JSON-serializable output
    output_data = {
        "uei": sorted(vendors["uei"]),
        "duns": sorted(vendors["duns"]),
        "company_names": sorted(vendors["company_names"])[:1000],  # Limit names for file size
        "stats": {
            "total_awards": len(df),
            "unique_uei": len(vendors["uei"]),
            "unique_duns": len(vendors["duns"]),
            "unique_companies": len(vendors["company_names"]),
        },
    }

    # Write to file
    logger.info(f"Writing vendor filters to {output_file}")
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with open(output_file, "w") as f:
        json.dump(output_data, f, indent=2)

    logger.success(f"Vendor filter file created: {output_file}")
    logger.info(f"Total unique vendors: {len(vendors['uei']) + len(vendors['duns']):,}")

    return output_data["stats"]


def main():
    """Main execution."""
    # Paths
    project_root = Path(__file__).parent.parent
    awards_file = project_root / "data" / "raw" / "sbir" / "awards_data.csv"

    # Determine output file from config if available
    output_file = project_root / "data" / "transition" / "sbir_vendor_filters.json"
    if _config_available:
        try:
            config = get_config()
            output_file = config.paths.resolve_path("transition_vendor_filters")
        except Exception:
            pass  # Fall back to default

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
