#!/usr/bin/env python3
"""Setup script for congressional district analysis.

This script helps set up the data files needed for congressional district
resolution:
1. Downloads HUD ZIP-to-Congressional District crosswalk file
2. Processes and validates the crosswalk data
3. Provides instructions for Census API setup

Usage:
    python scripts/setup_congressional_districts.py [--skip-download]
"""

import argparse
import gzip
import shutil
from pathlib import Path

import pandas as pd
import requests
from loguru import logger


# HUD ZIP-to-Congressional District crosswalk
# Updated quarterly, use latest 118th Congress (2023-2025)
HUD_CROSSWALK_URL = (
    "https://www.huduser.gov/hudapi/public/usps?"
    "type=5&query=All"
)

# Alternative direct download (if API doesn't work)
HUD_DIRECT_DOWNLOAD = (
    "https://www.huduser.gov/portal/datasets/usps/"
    "ZIP_CD_122023.xlsx"
)


def download_hud_crosswalk(output_dir: Path, force: bool = False) -> Path:
    """Download HUD ZIP-to-Congressional District crosswalk file.

    Args:
        output_dir: Directory to save the crosswalk file
        force: Force re-download even if file exists

    Returns:
        Path to the downloaded file
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / "ZIP_CD_118.csv"

    if output_file.exists() and not force:
        logger.info(f"Crosswalk file already exists: {output_file}")
        return output_file

    logger.info("Downloading HUD ZIP-to-Congressional District crosswalk...")
    logger.info(f"Source: {HUD_DIRECT_DOWNLOAD}")

    try:
        # Try direct download of Excel file
        response = requests.get(HUD_DIRECT_DOWNLOAD, timeout=60)
        response.raise_for_status()

        # Save as Excel temporarily
        temp_excel = output_dir / "ZIP_CD_temp.xlsx"
        with open(temp_excel, "wb") as f:
            f.write(response.content)

        logger.info("Downloaded Excel file, converting to CSV...")

        # Read Excel and convert to CSV
        df = pd.read_excel(temp_excel)

        # Save as CSV
        df.to_csv(output_file, index=False)

        # Clean up temp file
        temp_excel.unlink()

        logger.info(f"✓ Downloaded and converted to CSV: {output_file}")
        logger.info(f"  {len(df):,} ZIP code mappings")

        return output_file

    except Exception as e:
        logger.error(f"Failed to download crosswalk: {e}")
        logger.warning(
            "Manual download instructions:\n"
            "  1. Visit: https://www.huduser.gov/portal/datasets/usps_crosswalk.html\n"
            "  2. Download the latest ZIP-to-Congressional District file\n"
            "  3. Save to: data/reference/ZIP_CD_118.csv"
        )
        raise


def validate_crosswalk(crosswalk_path: Path) -> dict:
    """Validate the crosswalk file format and content.

    Args:
        crosswalk_path: Path to crosswalk CSV file

    Returns:
        Dictionary with validation statistics
    """
    logger.info(f"Validating crosswalk file: {crosswalk_path}")

    df = pd.read_csv(crosswalk_path)

    # Expected columns (may vary by HUD file version)
    # Typical columns: ZIP, CD, TOT_RATIO, RES_RATIO, BUS_RATIO, OTH_RATIO, USPS
    required_cols = ["ZIP"]

    # Check for required columns
    missing = [col for col in required_cols if col not in df.columns]
    if missing:
        logger.warning(f"Missing expected columns: {missing}")
        logger.info(f"Available columns: {list(df.columns)}")

    # Identify CD column (might be CD, CD118, CD117, etc.)
    cd_cols = [col for col in df.columns if col.startswith("CD")]
    if not cd_cols:
        raise ValueError("No congressional district column found (expected 'CD' or 'CD118', etc.)")

    cd_col = cd_cols[0]  # Use first CD column found
    logger.info(f"Using congressional district column: {cd_col}")

    # Validation statistics
    stats = {
        "total_rows": len(df),
        "unique_zips": df["ZIP"].nunique(),
        "unique_districts": df[cd_col].nunique() if cd_col in df.columns else 0,
        "columns": list(df.columns),
        "cd_column": cd_col,
    }

    # Check for duplicates (some ZIPs span multiple districts)
    zip_counts = df["ZIP"].value_counts()
    multi_district_zips = zip_counts[zip_counts > 1]
    stats["multi_district_zips"] = len(multi_district_zips)
    stats["multi_district_pct"] = len(multi_district_zips) / stats["unique_zips"] * 100

    logger.info("Crosswalk validation:")
    logger.info(f"  Total mappings: {stats['total_rows']:,}")
    logger.info(f"  Unique ZIP codes: {stats['unique_zips']:,}")
    logger.info(f"  Unique districts: {stats['unique_districts']:,}")
    logger.info(
        f"  ZIPs spanning multiple districts: {stats['multi_district_zips']:,} "
        f"({stats['multi_district_pct']:.1f}%)"
    )

    # Sample some mappings
    logger.info("\nSample mappings:")
    for _, row in df.head(5).iterrows():
        zip_code = str(row["ZIP"]).zfill(5)
        cd = row[cd_col] if cd_col in row else "N/A"
        state = row.get("USPS", "N/A")
        logger.info(f"  ZIP {zip_code} → District {cd} ({state})")

    return stats


def create_example_config(output_dir: Path) -> None:
    """Create example configuration file for district analysis.

    Args:
        output_dir: Directory to save config file
    """
    config_file = output_dir / "district_analysis_config.yaml"

    config_content = """# Congressional District Analysis Configuration

# Congressional District Resolution
congressional_districts:
  # Method to use for resolving districts
  # Options: "auto", "zip_crosswalk", "census_api", "google_civic"
  method: "auto"

  # Path to HUD ZIP-to-Congressional District crosswalk file
  crosswalk_path: "data/reference/ZIP_CD_118.csv"

  # Census Geocoder API settings (if using census_api method)
  census_api:
    enabled: true
    delay_seconds: 0.2  # Rate limiting delay between requests
    timeout_seconds: 10
    max_retries: 3

  # Google Civic Information API settings (if using google_civic method)
  google_civic:
    enabled: false
    api_key: "${GOOGLE_CIVIC_API_KEY}"  # Set via environment variable

  # Confidence thresholds for district resolution
  quality_thresholds:
    min_confidence: 0.7  # Minimum confidence score to accept
    warn_below: 0.8      # Warn if confidence below this threshold

# Fiscal Impact Allocation
fiscal_allocation:
  # Method for allocating state impacts to districts
  # Currently: "proportional_by_awards"
  allocation_method: "proportional_by_awards"

  # Minimum allocation share to include in results
  # (filters out very small allocations that might be noise)
  min_allocation_share: 0.01  # 1%

  # Confidence scoring weights
  confidence_weights:
    district_resolution: 0.4   # Weight for district resolution confidence
    model_confidence: 0.4      # Weight for economic model confidence
    allocation_share: 0.2      # Weight for allocation share size

# Reporting Options
reporting:
  # Districts to highlight in reports (can be empty)
  highlight_districts:
    - "CA-12"  # Nancy Pelosi's district (example)
    - "TX-21"  # Chip Roy's district (example)

  # Number of top districts to show in summaries
  top_n_districts: 10

  # Include state-level summaries alongside district summaries
  include_state_summaries: true

  # Export formats
  export_formats:
    - csv
    - excel
    - json
"""

    with open(config_file, "w") as f:
        f.write(config_content)

    logger.info(f"✓ Created example configuration: {config_file}")


def print_setup_instructions() -> None:
    """Print instructions for completing setup."""
    print("\n" + "=" * 80)
    print("CONGRESSIONAL DISTRICT ANALYSIS SETUP")
    print("=" * 80)
    print()
    print("✅ SETUP COMPLETE!")
    print()
    print("Next Steps:")
    print()
    print("1. Test the ZIP crosswalk resolver:")
    print("   python -c \"")
    print("   from src.enrichers.congressional_district_resolver import CongressionalDistrictResolver")
    print("   resolver = CongressionalDistrictResolver(")
    print("       method='zip_crosswalk',")
    print("       crosswalk_path='data/reference/ZIP_CD_118.csv'")
    print("   )")
    print("   print('Resolver ready!')\"")
    print()
    print("2. Run the district analysis example:")
    print("   python examples/sbir_fiscal_impact_by_district_example.py")
    print()
    print("3. For production Census API usage (more accurate):")
    print("   - No API key required")
    print("   - Free but rate-limited")
    print("   - Use method='census_api' in CongressionalDistrictResolver")
    print()
    print("4. Optional: Google Civic Information API:")
    print("   - Get API key: https://console.developers.google.com/")
    print("   - Set environment variable: export GOOGLE_CIVIC_API_KEY=your_key")
    print("   - Use method='google_civic' in CongressionalDistrictResolver")
    print()
    print("Configuration file created at:")
    print("   data/reference/district_analysis_config.yaml")
    print()
    print("=" * 80)


def main():
    """Main setup function."""
    parser = argparse.ArgumentParser(
        description="Setup congressional district analysis data"
    )
    parser.add_argument(
        "--skip-download",
        action="store_true",
        help="Skip downloading crosswalk (use existing file)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-download even if file exists",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/reference"),
        help="Output directory for data files (default: data/reference)",
    )

    args = parser.parse_args()

    logger.info("Starting congressional district analysis setup...")

    try:
        # Step 1: Download crosswalk
        if not args.skip_download:
            crosswalk_path = download_hud_crosswalk(
                output_dir=args.output_dir,
                force=args.force,
            )
        else:
            crosswalk_path = args.output_dir / "ZIP_CD_118.csv"
            if not crosswalk_path.exists():
                logger.error(f"Crosswalk file not found: {crosswalk_path}")
                logger.info("Remove --skip-download to download the file")
                return 1

        # Step 2: Validate crosswalk
        stats = validate_crosswalk(crosswalk_path)

        # Step 3: Create example config
        create_example_config(args.output_dir)

        # Step 4: Print instructions
        print_setup_instructions()

        return 0

    except Exception as e:
        logger.error(f"Setup failed: {e}")
        return 1


if __name__ == "__main__":
    import sys

    sys.exit(main())
