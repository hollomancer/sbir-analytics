#!/usr/bin/env python3
"""Test company categorization against high-volume SBIR companies dataset.

This script validates the categorization system against the 200+ company validation
dataset with known high award volumes. It provides detailed output for spot-checking
and quality validation.

Usage:
    # Test first 10 companies (quick)
    poetry run python test_categorization_validation.py --limit 10

    # Test all companies
    poetry run python test_categorization_validation.py

    # Test specific company by UEI with detailed justifications
    poetry run python test_categorization_validation.py --uei ABC123DEF456 --detailed

    # Test with detailed contract-level justifications
    poetry run python test_categorization_validation.py --limit 5 --detailed

    # Export results to CSV
    poetry run python test_categorization_validation.py --output results.csv

    # Load to Neo4j after categorization
    poetry run python test_categorization_validation.py --load-neo4j
"""

import argparse
import sys
from pathlib import Path

import pandas as pd
from loguru import logger

from src.enrichers.company_categorization import retrieve_company_contracts
from src.transformers.company_categorization import (
    aggregate_company_classification,
    classify_contract,
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


def print_contract_justifications(
    classified_contracts: list[dict],
    company_name: str,
    show_top_n: int = 5,
) -> None:
    """Print detailed justifications for contract classifications.

    Args:
        classified_contracts: List of classified contract dictionaries
        company_name: Name of the company
        show_top_n: Number of top contracts to show per category
    """
    if not classified_contracts:
        return

    logger.info(f"\n  {'=' * 76}")
    logger.info(f"  CONTRACT CLASSIFICATION DETAILS: {company_name}")
    logger.info(f"  {'=' * 76}")

    # Sort by award amount (highest first)
    sorted_contracts = sorted(
        classified_contracts, key=lambda x: x.get("award_amount", 0), reverse=True
    )

    # Show top contracts by dollar value
    logger.info(f"\n  Top {show_top_n} Contracts by Dollar Value:")
    logger.info(f"  {'-' * 76}")
    for i, contract in enumerate(sorted_contracts[:show_top_n], 1):
        amount = contract.get("award_amount", 0)
        classification = contract.get("classification", "Unknown")
        method = contract.get("method", "unknown")
        confidence = contract.get("confidence", 0)
        psc = contract.get("psc", "N/A")
        contract_type = contract.get("contract_type", "N/A")
        sbir_phase = contract.get("sbir_phase", "N/A")

        logger.info(f"\n  #{i}: ${amount:,.0f} → {classification}")
        logger.info(f"      PSC: {psc} | Type: {contract_type} | SBIR Phase: {sbir_phase}")
        logger.info(f"      Method: {method} | Confidence: {confidence:.2f}")

        # Show reason based on method
        if "_confirmed" in method:
            logger.info(f"      → HIGH AGREEMENT: PSC and pricing confirm each other")
        elif "_conflict" in method or "_ambiguous" in method:
            logger.info(f"      → LOW AGREEMENT: PSC and pricing don't align (lower confidence)")
        elif method == "psc_numeric":
            logger.info(f"      → Numeric PSC code indicates Product")
        elif method == "psc_alphabetic":
            logger.info(f"      → Alphabetic PSC code indicates Service")
        elif method == "psc_rd":
            logger.info(f"      → PSC starts with A/B indicates R&D")
        elif method == "psc_def_ffp":
            logger.info(f"      → PSC D/E/F (IT/telecom/space) + FFP → Product")
        elif method == "psc_def_service":
            logger.info(f"      → PSC D/E/F (IT/telecom/space) → Service")
        elif "description_inference" in method:
            logger.info(f"      → Product keywords in description (integrator resolution)")
        elif "sbir" in method:
            logger.info(f"      → SBIR Phase I/II adjustment")
        elif "default" in method:
            logger.info(f"      → Default classification (no PSC or insufficient data)")

    # Show samples from each category
    for category in ["Product", "Service", "R&D"]:
        category_contracts = [c for c in sorted_contracts if c.get("classification") == category]
        if not category_contracts:
            continue

        logger.info(f"\n  {category} Contracts ({len(category_contracts)} total):")
        logger.info(f"  {'-' * 76}")

        # Show top 3 by amount for this category
        for i, contract in enumerate(category_contracts[:3], 1):
            amount = contract.get("award_amount", 0)
            method = contract.get("method", "unknown")
            psc = contract.get("psc", "N/A")
            desc = contract.get("description", "")[:50] + "..." if contract.get("description") else "N/A"

            logger.info(f"      {i}. ${amount:,.0f} | PSC: {psc} | Method: {method}")
            logger.info(f"         {desc}")

    # Classification method breakdown
    logger.info(f"\n  Classification Method Breakdown:")
    logger.info(f"  {'-' * 76}")
    method_counts = {}
    for contract in classified_contracts:
        method = contract.get("method", "unknown")
        method_counts[method] = method_counts.get(method, 0) + 1

    for method, count in sorted(method_counts.items(), key=lambda x: x[1], reverse=True):
        pct = (count / len(classified_contracts)) * 100
        logger.info(f"      {method}: {count} contracts ({pct:.1f}%)")

    # Dollar-weighted breakdown
    logger.info(f"\n  Dollar-Weighted Breakdown:")
    logger.info(f"  {'-' * 76}")
    total_dollars = sum(c.get("award_amount", 0) for c in classified_contracts)
    for category in ["Product", "Service", "R&D"]:
        category_dollars = sum(
            c.get("award_amount", 0) for c in classified_contracts if c.get("classification") == category
        )
        if total_dollars > 0:
            pct = (category_dollars / total_dollars) * 100
            logger.info(f"      {category}: ${category_dollars:,.0f} ({pct:.1f}%)")

    logger.info(f"  {'=' * 76}\n")


def categorize_companies(
    companies: pd.DataFrame,
    limit: int | None = None,
    specific_uei: str | None = None,
    show_detailed: bool = False,
) -> pd.DataFrame:
    """Categorize companies from the validation dataset.

    Args:
        companies: Validation dataset DataFrame
        limit: Optional limit on number of companies to process
        specific_uei: Optional specific UEI to process
        show_detailed: Show detailed contract justifications

    Returns:
        DataFrame with categorization results
    """
    # Filter to specific UEI if provided
    if specific_uei:
        companies = companies[companies["UEI"] == specific_uei]
        if companies.empty:
            logger.error(f"UEI not found in dataset: {specific_uei}")
            sys.exit(1)
        logger.info(f"Processing single company: {specific_uei}")
    elif limit:
        companies = companies.head(limit)
        logger.info(f"Processing first {limit} companies")
    else:
        logger.info(f"Processing all {len(companies)} companies")

    results = []

    for idx, (_, company) in enumerate(companies.iterrows(), 1):
        uei = company.get("UEI")
        name = company.get("Company Name", "Unknown")
        sbir_awards = company.get("SBIR Awards", 0)

        logger.info(
            f"\n[{idx}/{len(companies)}] Processing: {name} (UEI: {uei}, SBIR Awards: {sbir_awards})"
        )

        # Retrieve USAspending contracts via API
        contracts_df = retrieve_company_contracts(uei=uei, use_api=True)

        if contracts_df.empty:
            logger.warning(f"  No USAspending contracts found for {name}")
            results.append(
                {
                    "company_uei": uei,
                    "company_name": name,
                    "sbir_awards": sbir_awards,
                    "classification": "Uncertain",
                    "product_pct": 0.0,
                    "service_pct": 0.0,
                    "confidence": "Low",
                    "award_count": 0,
                    "psc_family_count": 0,
                    "total_dollars": 0.0,
                    "override_reason": "no_contracts_found",
                }
            )
            continue

        logger.info(f"  Retrieved {len(contracts_df)} USAspending contracts")

        # Classify individual contracts
        classified_contracts = []
        for _, contract in contracts_df.iterrows():
            contract_dict = contract.to_dict()
            classified = classify_contract(contract_dict)
            classified_contracts.append(classified.model_dump())

        # Count classifications
        product_count = sum(1 for c in classified_contracts if c["classification"] == "Product")
        service_count = sum(1 for c in classified_contracts if c["classification"] == "Service")
        rd_count = sum(1 for c in classified_contracts if c["classification"] == "R&D")

        logger.info(
            f"  Contract breakdown: {product_count} Product, {service_count} Service, {rd_count} R&D"
        )

        # Show detailed justifications for classifications (if requested)
        if show_detailed:
            print_contract_justifications(classified_contracts, name, show_top_n=5)

        # Aggregate to company level
        company_result = aggregate_company_classification(
            classified_contracts, company_uei=uei, company_name=name
        )

        logger.info(
            f"  Result: {company_result.classification} "
            f"({company_result.product_pct:.1f}% Product, {company_result.service_pct:.1f}% Service) "
            f"- {company_result.confidence} confidence"
        )

        # Add to results with SBIR award count for comparison
        result_dict = {
            "company_uei": company_result.company_uei,
            "company_name": company_result.company_name,
            "sbir_awards": sbir_awards,
            "classification": company_result.classification,
            "product_pct": company_result.product_pct,
            "service_pct": company_result.service_pct,
            "confidence": company_result.confidence,
            "award_count": company_result.award_count,
            "psc_family_count": company_result.psc_family_count,
            "total_dollars": company_result.total_dollars,
            "product_dollars": company_result.product_dollars,
            "service_rd_dollars": company_result.service_rd_dollars,
            "override_reason": company_result.override_reason,
        }
        results.append(result_dict)

    return pd.DataFrame(results)


def print_summary(results: pd.DataFrame) -> None:
    """Print summary statistics for categorization results.

    Args:
        results: DataFrame with categorization results
    """
    logger.info("\n" + "=" * 80)
    logger.info("CATEGORIZATION SUMMARY")
    logger.info("=" * 80)

    # Overall stats
    logger.info(f"\nTotal companies processed: {len(results)}")
    logger.info(f"Companies with contracts: {(results['award_count'] > 0).sum()}")
    logger.info(f"Companies without contracts: {(results['award_count'] == 0).sum()}")

    # Classification distribution
    logger.info("\nClassification Distribution:")
    class_dist = results["classification"].value_counts()
    for classification, count in class_dist.items():
        pct = (count / len(results)) * 100
        logger.info(f"  {classification}: {count} ({pct:.1f}%)")

    # Confidence distribution
    logger.info("\nConfidence Distribution:")
    conf_dist = results["confidence"].value_counts()
    for confidence, count in conf_dist.items():
        pct = (count / len(results)) * 100
        logger.info(f"  {confidence}: {count} ({pct:.1f}%)")

    # Average metrics
    with_contracts = results[results["award_count"] > 0]
    if len(with_contracts) > 0:
        logger.info("\nAverage Metrics (companies with contracts):")
        logger.info(f"  Avg contracts per company: {with_contracts['award_count'].mean():.1f}")
        logger.info(f"  Avg PSC families: {with_contracts['psc_family_count'].mean():.1f}")
        logger.info(f"  Avg total dollars: ${with_contracts['total_dollars'].mean():,.0f}")
        logger.info(f"  Avg product %: {with_contracts['product_pct'].mean():.1f}%")
        logger.info(f"  Avg service %: {with_contracts['service_pct'].mean():.1f}%")

    # Top 10 by contract volume
    logger.info("\nTop 10 Companies by Contract Count:")
    top_10 = results.nlargest(10, "award_count")[
        ["company_name", "classification", "award_count", "total_dollars", "confidence"]
    ]
    for idx, (_, row) in enumerate(top_10.iterrows(), 1):
        logger.info(
            f"  {idx}. {row['company_name'][:40]}: {row['classification']} "
            f"({row['award_count']} contracts, ${row['total_dollars']:,.0f}, {row['confidence']} conf)"
        )


def export_results(results: pd.DataFrame, output_path: str) -> None:
    """Export results to CSV file.

    Args:
        results: DataFrame with categorization results
        output_path: Path to output CSV file
    """
    results.to_csv(output_path, index=False)
    logger.info(f"\nResults exported to: {output_path}")
    logger.info(f"Columns: {', '.join(results.columns)}")


def load_to_neo4j(results: pd.DataFrame) -> None:
    """Load categorization results to Neo4j.

    Args:
        results: DataFrame with categorization results
    """
    from src.loaders.neo4j import (
        CompanyCategorizationLoader,
        CompanyCategorizationLoaderConfig,
        Neo4jClient,
        Neo4jConfig,
    )

    config = get_config()
    neo4j_cfg = config.neo4j

    logger.info("\n" + "=" * 80)
    logger.info("LOADING TO NEO4J")
    logger.info("=" * 80)

    # Initialize Neo4j client
    client_config = Neo4jConfig(
        uri=neo4j_cfg.uri,
        username=neo4j_cfg.username,
        password=neo4j_cfg.password,
        database=neo4j_cfg.database,
        batch_size=neo4j_cfg.batch_size,
    )

    client = Neo4jClient(client_config)

    try:
        # Initialize categorization loader
        loader_config = CompanyCategorizationLoaderConfig(
            batch_size=neo4j_cfg.batch_size,
            create_indexes=neo4j_cfg.create_indexes,
            update_existing_only=True,
        )

        loader = CompanyCategorizationLoader(client, loader_config)

        # Create indexes
        if loader_config.create_indexes:
            logger.info("Creating Neo4j indexes...")
            loader.create_indexes()

        # Load categorizations
        categorization_records = results.to_dict(orient="records")
        logger.info(f"Loading {len(categorization_records)} categorizations to Neo4j...")

        metrics = loader.load_categorizations(categorization_records)

        # Report results
        successful = metrics.nodes_updated.get("Company", 0)
        total = len(categorization_records)
        success_rate = (successful / total * 100) if total > 0 else 0

        logger.info(
            f"\nNeo4j load complete: {successful}/{total} companies updated "
            f"({success_rate:.1f}% success rate)"
        )
        if metrics.errors > 0:
            logger.warning(f"Errors encountered: {metrics.errors}")

    finally:
        client.close()


def main():
    """Main entry point for validation testing."""
    parser = argparse.ArgumentParser(
        description="Test company categorization against validation dataset"
    )
    parser.add_argument(
        "--dataset",
        type=str,
        help="Path to validation dataset CSV (default: data/raw/sbir/over-100-awards-company_search_1763075384.csv)",
    )
    parser.add_argument(
        "--limit", type=int, help="Limit number of companies to process (default: all)"
    )
    parser.add_argument("--uei", type=str, help="Process specific company by UEI")
    parser.add_argument("--output", type=str, help="Export results to CSV file")
    parser.add_argument(
        "--load-neo4j", action="store_true", help="Load results to Neo4j after categorization"
    )
    parser.add_argument(
        "--detailed",
        action="store_true",
        help="Show detailed contract justifications for each company",
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

    logger.info("Using USAspending API for contract retrieval")

    # Categorize companies
    results = categorize_companies(
        companies, limit=args.limit, specific_uei=args.uei, show_detailed=args.detailed
    )

    # Print summary
    print_summary(results)

    # Export if requested
    if args.output:
        export_results(results, args.output)

    # Load to Neo4j if requested
    if args.load_neo4j:
        load_to_neo4j(results)

    logger.info("\n" + "=" * 80)
    logger.info("✓ VALIDATION TESTING COMPLETE")
    logger.info("=" * 80)


if __name__ == "__main__":
    main()
