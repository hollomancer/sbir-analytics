#!/usr/bin/env python3
"""Test PatentsView API enrichment for SBIR companies.

This script queries the PatentsView API to identify which companies from the test CSV
filed patents and checks if any of those patents were later reassigned to other companies.

Usage:
    # Test first 10 companies (quick)
    poetry run python tests/validation/test_patentsview_enrichment.py --limit 10

    # Test all companies
    poetry run python tests/validation/test_patentsview_enrichment.py

    # Test with a different CSV file
    poetry run python tests/validation/test_patentsview_enrichment.py --dataset path/to/companies.csv

    # Test specific company by UEI
    poetry run python tests/validation/test_patentsview_enrichment.py --uei ABC123DEF456

    # Export results to CSV
    poetry run python tests/validation/test_patentsview_enrichment.py --output results.csv

    # Generate detailed markdown report
    poetry run python tests/validation/test_patentsview_enrichment.py --markdown-report report.md
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd
from loguru import logger

from src.enrichers.patentsview import (
    PatentsViewClient,
    check_patent_reassignments,
    retrieve_company_patents,
)


def load_validation_dataset(path: str | None = None) -> pd.DataFrame:
    """Load the high-volume SBIR companies validation dataset.

    Args:
        path: Optional path to CSV file (uses default if not provided)

    Returns:
        DataFrame with validation companies
    """
    if path is None:
        # Default path from spec
        path = "data/raw/sbir/over-100-awards-company_search_1763075384.csv"

    dataset_path = Path(path)
    if not dataset_path.exists():
        logger.error(f"Validation dataset not found: {dataset_path}")
        logger.info(
            "Expected location: data/raw/sbir/over-100-awards-company_search_1763075384.csv"
        )
        sys.exit(1)

    logger.info(f"Loading validation dataset from: {dataset_path}")
    df = pd.read_csv(dataset_path)
    logger.info(f"Loaded {len(df)} companies from validation dataset")

    return df


def process_company(
    company_name: str,
    uei: str | None = None,
    duns: str | None = None,
    client: PatentsViewClient | None = None,
) -> dict[str, Any]:
    """Process a single company to find patents and reassignments.

    Args:
        company_name: Company name
        uei: Optional UEI identifier
        duns: Optional DUNS identifier
        client: Optional PatentsViewClient instance

    Returns:
        Dictionary with patent and reassignment information
    """
    logger.info(f"\n{'=' * 80}")
    logger.info(f"Processing: {company_name}")
    if uei:
        logger.info(f"  UEI: {uei}")
    if duns:
        logger.info(f"  DUNS: {duns}")

    # Retrieve patents for this company
    try:
        patents_df = retrieve_company_patents(company_name, uei, duns, client)
        patent_count = len(patents_df)

        if patent_count == 0:
            logger.info(f"  No patents found for {company_name}")
            return {
                "company_name": company_name,
                "uei": uei,
                "duns": duns,
                "patent_count": 0,
                "patent_numbers": [],
                "reassigned_patents_count": 0,
                "reassigned_patent_details": [],
            }

        logger.info(f"  Found {patent_count} patents")

        # Extract patent numbers
        patent_numbers = patents_df["patent_number"].dropna().tolist()

        # Check for reassignments
        reassigned_patents = []
        if patent_numbers and client:
            reassignments_df = check_patent_reassignments(
                patent_numbers, company_name, client
            )

            # Filter to only reassigned patents
            reassigned_df = reassignments_df[reassignments_df["reassigned"]]
            reassigned_count = len(reassigned_df)

            if reassigned_count > 0:
                logger.info(f"  Found {reassigned_count} reassigned patents")
                for _, row in reassigned_df.iterrows():
                    reassigned_patents.append(
                        {
                            "patent_number": row["patent_number"],
                            "original_assignee": row["original_assignee"],
                            "current_assignee": row["current_assignee"],
                            "assignor": row.get("assignor"),
                        }
                    )
            else:
                logger.info("  No reassigned patents found")

        return {
            "company_name": company_name,
            "uei": uei,
            "duns": duns,
            "patent_count": patent_count,
            "patent_numbers": patent_numbers,
            "reassigned_patents_count": len(reassigned_patents),
            "reassigned_patent_details": reassigned_patents,
        }

    except Exception as e:
        logger.error(f"Error processing {company_name}: {e}")
        return {
            "company_name": company_name,
            "uei": uei,
            "duns": duns,
            "patent_count": 0,
            "patent_numbers": [],
            "reassigned_patents_count": 0,
            "reassigned_patent_details": [],
            "error": str(e),
        }


def enrich_companies(
    companies: pd.DataFrame,
    limit: int | None = None,
    specific_uei: str | None = None,
) -> pd.DataFrame:
    """Enrich companies with patent data from PatentsView.

    Args:
        companies: DataFrame with company data
        limit: Optional limit on number of companies to process
        specific_uei: Optional UEI to process only one company

    Returns:
        DataFrame with enrichment results
    """
    # Initialize PatentsView client (reused across companies)
    try:
        client = PatentsViewClient()
    except Exception as e:
        logger.error(f"Failed to initialize PatentsView client: {e}")
        logger.error("Make sure PATENTSVIEW_API_KEY environment variable is set")
        sys.exit(1)

    try:
        # Filter companies if needed
        if specific_uei:
            companies = companies[companies.get("UEI", "") == specific_uei]
            if len(companies) == 0:
                logger.error(f"Company with UEI {specific_uei} not found in dataset")
                sys.exit(1)
        elif limit:
            companies = companies.head(limit)

        logger.info(f"\nProcessing {len(companies)} companies...")

        results = []
        for idx, (_, row) in enumerate(companies.iterrows(), 1):
            company_name = row.get("Company Name") or row.get("company_name") or ""
            uei = row.get("UEI") or row.get("uei")
            duns = row.get("DUNs") or row.get("duns") or row.get("DUNS")

            if not company_name:
                logger.warning(f"Row {idx}: Missing company name, skipping")
                continue

            logger.info(f"\n[{idx}/{len(companies)}] Processing: {company_name}")

            result = process_company(company_name, uei, duns, client)
            results.append(result)

        return pd.DataFrame(results)

    finally:
        client.close()


def print_summary(results: pd.DataFrame) -> None:
    """Print summary statistics.

    Args:
        results: DataFrame with enrichment results
    """
    logger.info("\n" + "=" * 80)
    logger.info("SUMMARY")
    logger.info("=" * 80)

    total_companies = len(results)
    companies_with_patents = (results["patent_count"] > 0).sum()
    companies_with_patents_pct = (
        (companies_with_patents / total_companies * 100) if total_companies > 0 else 0
    )

    total_patents = results["patent_count"].sum()
    companies_with_reassignments = (results["reassigned_patents_count"] > 0).sum()
    companies_with_reassignments_pct = (
        (companies_with_reassignments / total_companies * 100)
        if total_companies > 0
        else 0
    )

    logger.info(f"\nTotal companies processed: {total_companies}")
    logger.info(
        f"Companies with patents filed: {companies_with_patents} ({companies_with_patents_pct:.1f}%)"
    )
    logger.info(f"Total patents found: {total_patents}")
    logger.info(
        f"Companies with reassigned patents: {companies_with_reassignments} ({companies_with_reassignments_pct:.1f}%)"
    )

    # Top 10 companies by patent count
    top_patent_companies = results.nlargest(10, "patent_count")
    if len(top_patent_companies) > 0:
        logger.info("\nTop 10 Companies by Patent Count:")
        logger.info("  " + "-" * 76)
        for idx, (_, row) in enumerate(top_patent_companies.iterrows(), 1):
            reassigned_marker = (
                " (has reassignments)" if row["reassigned_patents_count"] > 0 else ""
            )
            logger.info(
                f"  {idx}. {row['company_name'][:50]}: "
                f"{row['patent_count']} patents{reassigned_marker}"
            )

    # Companies with reassignments
    if companies_with_reassignments > 0:
        reassigned_companies = results[results["reassigned_patents_count"] > 0].copy()
        reassigned_companies = reassigned_companies.sort_values(
            "reassigned_patents_count", ascending=False
        )
        logger.info("\nCompanies with Reassigned Patents:")
        logger.info("  " + "-" * 76)
        for idx, (_, row) in enumerate(reassigned_companies.iterrows(), 1):
            logger.info(
                f"  {idx}. {row['company_name'][:50]}: "
                f"{row['reassigned_patents_count']} reassigned patents "
                f"(out of {row['patent_count']} total)"
            )


def export_results(results: pd.DataFrame, output_path: str) -> None:
    """Export results to CSV file.

    Args:
        results: DataFrame with enrichment results
        output_path: Path to output CSV file
    """
    # Create export DataFrame
    export_df = results.copy()

    # Format list columns as strings for CSV
    export_df["patent_numbers"] = export_df["patent_numbers"].apply(
        lambda x: ", ".join(map(str, x)) if isinstance(x, list) else ""
    )
    export_df["reassigned_patent_details"] = export_df["reassigned_patent_details"].apply(
        lambda x: json.dumps(x) if isinstance(x, list) else ""
    )

    # Rename columns
    rename_map = {
        "company_name": "Company Name",
        "uei": "UEI",
        "duns": "DUNS",
        "patent_count": "Patent Count",
        "patent_numbers": "Patent Numbers",
        "reassigned_patents_count": "Reassigned Patents Count",
        "reassigned_patent_details": "Reassigned Patent Details",
    }
    export_df = export_df.rename(columns=rename_map)

    export_df.to_csv(output_path, index=False)
    logger.info(f"\nResults exported to: {output_path}")
    logger.info(f"Exported {len(export_df)} companies with {len(export_df.columns)} columns")


def generate_markdown_report(results: pd.DataFrame, output_path: str) -> None:
    """Generate a detailed markdown report.

    Args:
        results: DataFrame with enrichment results
        output_path: Path to output markdown file
    """
    with open(output_path, "w") as f:
        # Header
        f.write("# PatentsView API Enrichment Report\n\n")
        f.write(
            "This report identifies companies from the test CSV that filed patents "
            "and tracks any patent reassignments.\n\n"
        )
        f.write("---\n\n")

        # Executive Summary
        f.write("## Executive Summary\n\n")
        total_companies = len(results)
        companies_with_patents = (results["patent_count"] > 0).sum()
        total_patents = results["patent_count"].sum()
        companies_with_reassignments = (results["reassigned_patents_count"] > 0).sum()

        f.write(f"- **Total Companies Analyzed**: {total_companies}\n")
        f.write(f"- **Companies with Patents Filed**: {companies_with_patents}\n")
        f.write(f"- **Total Patents Found**: {total_patents}\n")
        f.write(f"- **Companies with Reassigned Patents**: {companies_with_reassignments}\n\n")

        # Companies with Patents
        f.write("## Companies with Patents Filed\n\n")
        companies_with_patents_df = results[results["patent_count"] > 0].copy()
        companies_with_patents_df = companies_with_patents_df.sort_values(
            "patent_count", ascending=False
        )

        f.write("| Company | UEI | Patent Count | Reassigned Patents |\n")
        f.write("|---------|-----|-------------|-------------------|\n")

        for _, row in companies_with_patents_df.iterrows():
            company_name = row["company_name"]
            uei = row.get("uei", "")
            patent_count = row["patent_count"]
            reassigned_count = row["reassigned_patents_count"]
            f.write(f"| {company_name} | {uei} | {patent_count} | {reassigned_count} |\n")

        f.write("\n")

        # Reassigned Patents Details
        if companies_with_reassignments > 0:
            f.write("## Reassigned Patents Details\n\n")
            reassigned_companies = results[results["reassigned_patents_count"] > 0].copy()

            for _, row in reassigned_companies.iterrows():
                company_name = row["company_name"]
                reassigned_details = row["reassigned_patent_details"]

                f.write(f"### {company_name}\n\n")
                f.write(f"**Total Reassigned Patents**: {row['reassigned_patents_count']}\n\n")

                if isinstance(reassigned_details, list):
                    f.write("| Patent Number | Original Assignee | Current Assignee |\n")
                    f.write("|---------------|------------------|-----------------|\n")
                    for detail in reassigned_details:
                        patent_num = detail.get("patent_number", "")
                        original = detail.get("original_assignee", "")
                        current = detail.get("current_assignee", "")
                        f.write(f"| {patent_num} | {original} | {current} |\n")
                    f.write("\n")

        logger.info(f"\nMarkdown report generated: {output_path}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Test PatentsView API enrichment for SBIR companies"
    )
    parser.add_argument(
        "--dataset",
        "-d",
        type=str,
        dest="dataset",
        metavar="CSV_FILE",
        help="Path to company CSV file to process (default: data/raw/sbir/over-100-awards-company_search_1763075384.csv)",
    )
    parser.add_argument(
        "--csv",
        type=str,
        dest="dataset",
        metavar="CSV_FILE",
        help="Alias for --dataset: Path to company CSV file to process",
    )
    parser.add_argument(
        "--limit", type=int, help="Limit number of companies to process (default: all)"
    )
    parser.add_argument("--uei", type=str, help="Process specific company by UEI")
    parser.add_argument("--output", type=str, help="Export results to CSV file")
    parser.add_argument(
        "--markdown-report",
        type=str,
        help="Generate detailed markdown report",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")

    args = parser.parse_args()

    # Configure logging
    if args.verbose:
        logger.remove()
        logger.add(sys.stderr, level="DEBUG")
    else:
        logger.remove()
        logger.add(sys.stderr, level="INFO")

    # Load validation dataset
    companies = load_validation_dataset(args.dataset)

    try:
        # Enrich companies
        results = enrich_companies(companies, limit=args.limit, specific_uei=args.uei)

        # Print summary
        print_summary(results)

        # Export if requested
        if args.output:
            export_results(results, args.output)

        # Generate markdown report if requested
        if args.markdown_report:
            generate_markdown_report(results, args.markdown_report)

        logger.info("\n" + "=" * 80)
        logger.info("✓ PATENTSVIEW ENRICHMENT COMPLETE")
        logger.info("=" * 80)

    except KeyboardInterrupt:
        logger.warning("\nInterrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error during enrichment: {e}")
        raise


if __name__ == "__main__":
    main()

