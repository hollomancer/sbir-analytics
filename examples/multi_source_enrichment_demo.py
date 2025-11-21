#!/usr/bin/env python
"""
Multi-Source Data Enrichment Demonstration

This script demonstrates how to integrate SBIR, USAspending, and SAM.gov data
to create a comprehensive enriched dataset.

Usage:
    python examples/multi_source_enrichment_demo.py [--use-sample-data]

Options:
    --use-sample-data    Use sample test fixtures instead of real data
    --output-csv FILE    Save enriched data to CSV file
    --limit N            Process only first N SBIR awards
"""

import sys
from pathlib import Path

import pandas as pd
from loguru import logger

# Add repository root to path
repo_root = Path(__file__).parent.parent
sys.path.insert(0, str(repo_root))

from src.enrichers.usaspending import enrich_sbir_with_usaspending
from src.extractors.sam_gov import SAMGovExtractor
from src.extractors.sbir import SbirDuckDBExtractor


def create_sample_data():
    """Create sample data for demonstration."""
    logger.info("Creating sample data for demonstration...")

    sbir_awards = pd.DataFrame(
        [
            {
                "Company": "Quantum Dynamics Inc",
                "UEI": "Q1U2A3N4T5U6M7D8",
                "Duns": "111222333",
                "Contract": "W31P4Q-23-C-0001",
                "Agency": "DOD",
                "Award Amount": 150000.0,
                "Award Year": 2023,
                "Program": "SBIR",
                "Phase": "Phase I",
            },
            {
                "Company": "Neural Networks LLC",
                "UEI": "N2E3U4R5A6L7N8E9",
                "Duns": "444555666",
                "Contract": "NNX23CA01C",
                "Agency": "NASA",
                "Award Amount": 750000.0,
                "Award Year": 2023,
                "Program": "SBIR",
                "Phase": "Phase II",
            },
            {
                "Company": "BioMed Solutions Corp",
                "UEI": "B3I4O5M6E7D8S9O0",
                "Duns": "777888999",
                "Contract": "1R43GM123456-01",
                "Agency": "HHS",
                "Award Amount": 300000.0,
                "Award Year": 2024,
                "Program": "STTR",
                "Phase": "Phase I",
            },
        ]
    )

    usaspending_recipients = pd.DataFrame(
        [
            {
                "recipient_name": "Quantum Dynamics Incorporated",
                "recipient_uei": "Q1U2A3N4T5U6M7D8",
                "recipient_duns": "111222333",
                "recipient_city": "Arlington",
                "recipient_state": "VA",
                "recipient_zip": "22201",
                "business_types": "Small Business",
            },
            {
                "recipient_name": "Neural Networks LLC",
                "recipient_uei": "N2E3U4R5A6L7N8E9",
                "recipient_duns": "444555666",
                "recipient_city": "Pasadena",
                "recipient_state": "CA",
                "recipient_zip": "91101",
                "business_types": "Small Business|Woman Owned",
            },
            {
                "recipient_name": "BioMed Solutions Corporation",
                "recipient_uei": "B3I4O5M6E7D8S9O0",
                "recipient_duns": "777888999",
                "recipient_city": "Cambridge",
                "recipient_state": "MA",
                "recipient_zip": "02139",
                "business_types": "Small Business|Minority Owned",
            },
        ]
    )

    sam_gov_entities = pd.DataFrame(
        [
            {
                "unique_entity_id": "Q1U2A3N4T5U6M7D8",
                "cage_code": "1QD45",
                "legal_business_name": "QUANTUM DYNAMICS INC",
                "dba_name": "Quantum Dynamics",
                "primary_naics": "541712",
                "naics_code_string": "541712,541330",
                "business_type_string": "2X,A5",
            },
            {
                "unique_entity_id": "N2E3U4R5A6L7N8E9",
                "cage_code": "2NN67",
                "legal_business_name": "NEURAL NETWORKS LLC",
                "dba_name": "Neural Networks",
                "primary_naics": "541511",
                "naics_code_string": "541511,541512,541715",
                "business_type_string": "2X,8W",
            },
            {
                "unique_entity_id": "B3I4O5M6E7D8S9O0",
                "cage_code": "3BM89",
                "legal_business_name": "BIOMED SOLUTIONS CORP",
                "dba_name": "BioMed Solutions",
                "primary_naics": "541714",
                "naics_code_string": "541714,541380",
                "business_type_string": "2X,27",
            },
        ]
    )

    return sbir_awards, usaspending_recipients, sam_gov_entities


def enrich_with_sam_gov(df, sam_entities):
    """Enrich DataFrame with SAM.gov data by UEI."""
    logger.info("Enriching with SAM.gov data...")

    # Prepare SAM.gov data
    sam_data = sam_entities.copy()
    sam_data = sam_data.add_prefix("sam_")
    sam_data.rename(columns={"sam_unique_entity_id": "UEI"}, inplace=True)

    # Merge on UEI
    enriched = df.merge(sam_data, on="UEI", how="left", suffixes=("", "_sam"))

    # Count matches
    match_count = enriched["sam_cage_code"].notna().sum()
    logger.info(f"SAM.gov matches: {match_count}/{len(enriched)} ({match_count/len(enriched):.1%})")

    return enriched


def print_enrichment_summary(enriched_df):
    """Print summary of enrichment results."""
    logger.info("\n" + "=" * 80)
    logger.info("ENRICHMENT SUMMARY")
    logger.info("=" * 80)

    total_awards = len(enriched_df)
    logger.info(f"Total Awards: {total_awards}")

    # USAspending enrichment
    usa_matches = enriched_df["_usaspending_match_method"].notna().sum()
    usa_rate = usa_matches / total_awards
    logger.info(f"\nUSAspending Enrichment:")
    logger.info(f"  Matched: {usa_matches}/{total_awards} ({usa_rate:.1%})")

    # Match method breakdown
    if "_usaspending_match_method" in enriched_df.columns:
        method_counts = enriched_df["_usaspending_match_method"].value_counts()
        for method, count in method_counts.items():
            logger.info(f"    {method}: {count}")

    # SAM.gov enrichment
    sam_matches = enriched_df["sam_cage_code"].notna().sum()
    sam_rate = sam_matches / total_awards
    logger.info(f"\nSAM.gov Enrichment:")
    logger.info(f"  Matched: {sam_matches}/{total_awards} ({sam_rate:.1%})")
    logger.info(f"  CAGE Codes: {enriched_df['sam_cage_code'].notna().sum()}")
    logger.info(f"  NAICS Codes: {enriched_df['sam_primary_naics'].notna().sum()}")

    # Overall enrichment
    fully_enriched = (
        enriched_df["_usaspending_match_method"].notna()
        & enriched_df["sam_cage_code"].notna()
    ).sum()
    logger.info(f"\nFully Enriched: {fully_enriched}/{total_awards} ({fully_enriched/total_awards:.1%})")

    logger.info("=" * 80 + "\n")


def print_sample_records(enriched_df, n=3):
    """Print sample enriched records."""
    logger.info("\n" + "=" * 80)
    logger.info(f"SAMPLE ENRICHED RECORDS (showing first {n})")
    logger.info("=" * 80)

    for idx, row in enriched_df.head(n).iterrows():
        logger.info(f"\nRecord {idx + 1}:")
        logger.info(f"  Company: {row.get('Company', 'N/A')}")
        logger.info(f"  UEI: {row.get('UEI', 'N/A')}")
        logger.info(f"  Contract: {row.get('Contract', 'N/A')}")
        logger.info(f"  Award Amount: ${row.get('Award Amount', 0):,.2f}")

        logger.info(f"\n  USAspending Match:")
        logger.info(f"    Method: {row.get('_usaspending_match_method', 'N/A')}")
        logger.info(f"    Score: {row.get('_usaspending_match_score', 0)}")
        logger.info(f"    City: {row.get('usaspending_recipient_recipient_city', 'N/A')}")
        logger.info(f"    State: {row.get('usaspending_recipient_recipient_state', 'N/A')}")

        logger.info(f"\n  SAM.gov Data:")
        logger.info(f"    CAGE Code: {row.get('sam_cage_code', 'N/A')}")
        logger.info(f"    Legal Name: {row.get('sam_legal_business_name', 'N/A')}")
        logger.info(f"    Primary NAICS: {row.get('sam_primary_naics', 'N/A')}")

    logger.info("=" * 80 + "\n")


def main():
    """Main demonstration function."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Demonstrate multi-source SBIR data enrichment"
    )
    parser.add_argument(
        "--use-sample-data",
        action="store_true",
        help="Use sample test data instead of real data",
    )
    parser.add_argument("--output-csv", type=str, help="Save enriched data to CSV file")
    parser.add_argument("--limit", type=int, help="Process only first N awards")

    args = parser.parse_args()

    logger.info("=" * 80)
    logger.info("SBIR Multi-Source Data Enrichment Demonstration")
    logger.info("=" * 80)

    # Step 1: Load SBIR Awards
    logger.info("\nStep 1: Loading SBIR Awards Data...")

    if args.use_sample_data:
        sbir_awards, usaspending_recipients, sam_entities = create_sample_data()
        logger.info(f"Loaded {len(sbir_awards)} sample SBIR awards")
    else:
        logger.warning("Real data loading not implemented in this demo.")
        logger.warning("Using sample data instead. (Specify --use-sample-data to suppress this warning)")
        sbir_awards, usaspending_recipients, sam_entities = create_sample_data()

    if args.limit:
        sbir_awards = sbir_awards.head(args.limit)
        logger.info(f"Limited to first {args.limit} awards")

    # Step 2: Enrich with USAspending
    logger.info("\nStep 2: Enriching with USAspending Data...")
    enriched = enrich_sbir_with_usaspending(
        sbir_awards,
        usaspending_recipients,
        sbir_uei_col="UEI",
        sbir_duns_col="Duns",
        sbir_company_col="Company",
    )
    logger.info(f"USAspending enrichment complete")

    # Step 3: Enrich with SAM.gov
    logger.info("\nStep 3: Enriching with SAM.gov Data...")
    enriched = enrich_with_sam_gov(enriched, sam_entities)
    logger.info(f"SAM.gov enrichment complete")

    # Step 4: Display Results
    print_enrichment_summary(enriched)
    print_sample_records(enriched)

    # Step 5: Save to CSV if requested
    if args.output_csv:
        output_path = Path(args.output_csv)
        enriched.to_csv(output_path, index=False)
        logger.info(f"\nEnriched data saved to: {output_path}")
        logger.info(f"  Rows: {len(enriched)}")
        logger.info(f"  Columns: {len(enriched.columns)}")

    logger.info("\nDemonstration complete!")

    return enriched


if __name__ == "__main__":
    # Configure logging
    logger.remove()
    logger.add(sys.stderr, level="INFO", format="{message}")

    enriched_df = main()
