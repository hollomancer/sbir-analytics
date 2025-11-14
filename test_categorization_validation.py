#!/usr/bin/env python3
"""Test company categorization against high-volume SBIR companies dataset.

This script validates the categorization system against the 200+ company validation
dataset with known high award volumes. It analyzes non-SBIR/STTR federal contract
revenue to determine whether companies are primarily Product or Service oriented.

IMPORTANT: SBIR/STTR awards are excluded from the analysis to focus on other federal
contract revenue that reflects the company's product vs service business model.

Usage:
    # Test first 10 companies (quick)
    poetry run python test_categorization_validation.py --limit 10

    # Test all companies
    poetry run python test_categorization_validation.py

    # Test with a different CSV file (all equivalent):
    poetry run python test_categorization_validation.py --dataset path/to/companies.csv
    poetry run python test_categorization_validation.py -d path/to/companies.csv
    poetry run python test_categorization_validation.py --csv path/to/companies.csv

    # Test specific company by UEI
    poetry run python test_categorization_validation.py --uei ABC123DEF456

    # Export results to CSV
    poetry run python test_categorization_validation.py --output results.csv

    # Generate detailed markdown report
    poetry run python test_categorization_validation.py --markdown-report report.md

    # Load to Neo4j after categorization
    poetry run python test_categorization_validation.py --load-neo4j
"""

import argparse
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from loguru import logger

from src.config.loader import get_config
from src.enrichers.company_categorization import (
    retrieve_company_contracts,
    retrieve_company_contracts_api,
    retrieve_sbir_awards,
    retrieve_sbir_awards_api,
)
from src.extractors.usaspending import DuckDBUSAspendingExtractor
from src.transformers.company_categorization import (
    aggregate_company_classification,
    classify_contract,
    is_cost_based_contract,
    is_service_based_contract,
)


def _extract_year_from_date(date_str: str | None) -> int | None:
    """Extract year from date string in various formats.
    
    Args:
        date_str: Date string (ISO format, YYYY-MM-DD, or YYYYMMDD)
        
    Returns:
        Year as integer, or None if date cannot be parsed
    """
    if not date_str:
        return None
    
    try:
        # Try ISO format first (YYYY-MM-DD)
        if isinstance(date_str, str) and "-" in date_str:
            dt = datetime.fromisoformat(date_str.split("T")[0])
            return dt.year
        # Try YYYYMMDD format
        elif isinstance(date_str, str) and len(date_str) >= 4:
            year_str = date_str[:4]
            if year_str.isdigit():
                year = int(year_str)
                # Sanity check: year should be reasonable
                if 1900 <= year <= 2100:
                    return year
    except (ValueError, AttributeError):
        pass
    
    return None


def _analyze_consecutive_product_years(
    contract_dicts: list[dict], classified_contracts: list[dict]
) -> list[int] | None:
    """Analyze year-by-year revenue to identify consecutive years where product > service.
    
    Args:
        contract_dicts: Original contract dictionaries with date and amount info
        classified_contracts: Classified contracts with Product/Service classification
        
    Returns:
        List of consecutive years where product revenue exceeded service revenue,
        or None if no consecutive years found
    """
    if not contract_dicts or not classified_contracts:
        return None
    
    # Create a mapping from award_id to classification for quick lookup
    classification_map = {c.get("award_id"): c.get("classification") for c in classified_contracts}
    
    # Group contracts by year
    year_revenue: dict[int, dict[str, float]] = defaultdict(lambda: {"product": 0.0, "service": 0.0})
    
    for contract in contract_dicts:
        award_id = contract.get("award_id")
        classification = classification_map.get(award_id)
        amount = contract.get("award_amount") or 0.0
        
        if not classification or amount <= 0:
            continue
        
        # Extract year from action_date
        action_date = contract.get("action_date")
        year = _extract_year_from_date(action_date)
        
        if year and classification in ("Product", "Service"):
            year_revenue[year][classification.lower()] += amount
    
    if not year_revenue:
        return None
    
    # Identify years where product > service
    product_dominant_years = []
    for year in sorted(year_revenue.keys()):
        revenue = year_revenue[year]
        product_total = revenue.get("product", 0.0)
        service_total = revenue.get("service", 0.0)
        
        if product_total > service_total and product_total > 0:
            product_dominant_years.append(year)
    
    # Find consecutive years
    if len(product_dominant_years) < 2:
        return None
    
    consecutive_years = []
    current_sequence = [product_dominant_years[0]]
    
    for i in range(1, len(product_dominant_years)):
        if product_dominant_years[i] == product_dominant_years[i-1] + 1:
            current_sequence.append(product_dominant_years[i])
        else:
            if len(current_sequence) >= 2:
                consecutive_years.extend(current_sequence)
            current_sequence = [product_dominant_years[i]]
    
    # Check final sequence
    if len(current_sequence) >= 2:
        consecutive_years.extend(current_sequence)
    
    return sorted(set(consecutive_years)) if consecutive_years else None


def print_contract_justifications(
    company_name: str, classified_contracts: list[dict], detailed: bool = False, agency_breakdown: dict[str, float] | None = None
) -> None:
    """Print detailed contract classification justifications.

    Args:
        company_name: Name of the company
        classified_contracts: List of classified contract dictionaries
        detailed: If True, show additional details
    """
    if not classified_contracts:
        return

    logger.info("\n  " + "=" * 76)
    logger.info(f"  CONTRACT CLASSIFICATION DETAILS: {company_name}")
    logger.info("  " + "=" * 76)

    # Top 5 contracts by dollar value
    logger.info("\n  Top 5 Contracts by Dollar Value:")
    logger.info("  " + "-" * 76)

    sorted_contracts = sorted(classified_contracts, key=lambda x: x.get("award_amount", 0), reverse=True)

    for idx, contract in enumerate(sorted_contracts[:5], 1):
        amount = contract.get("award_amount", 0)
        classification = contract.get("classification", "Unknown")
        psc = contract.get("psc") or "None"
        contract_type = contract.get("contract_type") or "None"
        sbir_phase = contract.get("sbir_phase") or "None"
        method = contract.get("method", "unknown")
        confidence = contract.get("confidence", 0.0)

        logger.info(f"\n  #{idx}: ${amount:,.0f} → {classification}")
        logger.info(f"      PSC: {psc} | Type: {contract_type} | SBIR Phase: {sbir_phase}")
        logger.info(f"      Method: {method} | Confidence: {confidence:.2f}")

        # Show justification based on method
        if method == "psc_numeric":
            logger.info(f"      → Numeric PSC code indicates tangible product")
        elif method == "psc_alphabetic":
            logger.info(f"      → Alphabetic PSC code indicates service")
        elif method == "contract_type_override":
            logger.info(f"      → Contract type {contract_type} overrides PSC classification")
        elif method == "sbir_phase_adjustment":
            logger.info(f"      → SBIR Phase {sbir_phase} adjusted classification")
        elif method == "description_inference":
            logger.info(f"      → Product keywords detected in description")
        elif method == "default_no_psc":
            logger.info(f"      → Default classification (no PSC or insufficient data)")

    # Count by classification
    product_contracts = [c for c in classified_contracts if c.get("classification") == "Product"]
    service_contracts = [c for c in classified_contracts if c.get("classification") == "Service"]

    # Show detailed lists if requested
    if detailed or len(classified_contracts) <= 20:
        if service_contracts:
            logger.info(f"\n  Service Contracts ({len(service_contracts)} total):")
            logger.info("  " + "-" * 76)
            for idx, contract in enumerate(service_contracts[:3], 1):
                amount = contract.get("award_amount", 0)
                psc = contract.get("psc") or "None"
                method = contract.get("method", "unknown")
                desc = (contract.get("description") or "N/A")[:60]
                logger.info(f"      {idx}. ${amount:,.0f} | PSC: {psc} | Method: {method}")
                logger.info(f"         {desc}...")

    # Method breakdown
    logger.info("\n  Classification Method Breakdown:")
    logger.info("  " + "-" * 76)

    method_counts = {}
    for contract in classified_contracts:
        method = contract.get("method", "unknown")
        method_counts[method] = method_counts.get(method, 0) + 1

    for method, count in sorted(method_counts.items(), key=lambda x: x[1], reverse=True):
        pct = (count / len(classified_contracts)) * 100
        logger.info(f"      {method}: {count} contracts ({pct:.1f}%)")

    # Dollar-weighted breakdown
    logger.info("\n  Dollar-Weighted Breakdown:")
    logger.info("  " + "-" * 76)

    product_dollars = sum(c.get("award_amount", 0) for c in product_contracts)
    service_dollars = sum(c.get("award_amount", 0) for c in service_contracts)
    total_dollars = product_dollars + service_dollars

    if total_dollars > 0:
        logger.info(f"      Product: ${product_dollars:,.0f} ({product_dollars/total_dollars*100:.1f}%)")
        logger.info(f"      Service: ${service_dollars:,.0f} ({service_dollars/total_dollars*100:.1f}%)")

    # Agency breakdown if provided
    if agency_breakdown:
        logger.info("\n  Agency Revenue Breakdown:")
        logger.info("  " + "-" * 76)
        for agency, pct in sorted(agency_breakdown.items(), key=lambda x: x[1], reverse=True):
            logger.info(f"      {agency}: {pct:.1f}%")

    logger.info("  " + "=" * 76 + "\n")


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


def categorize_companies(
    companies: pd.DataFrame,
    extractor: DuckDBUSAspendingExtractor | None = None,
    limit: int | None = None,
    specific_uei: str | None = None,
    use_api: bool = False,
    detailed: bool = False,
    max_workers: int = 1,
) -> pd.DataFrame:
    """Categorize companies from the validation dataset.

    Args:
        companies: Validation dataset DataFrame
        extractor: USAspending extractor (required if use_api=False)
        limit: Optional limit on number of companies to process
        specific_uei: Optional specific UEI to process
        use_api: If True, use USAspending API instead of DuckDB
        detailed: If True, print detailed contract classifications
        max_workers: Number of parallel workers (1 = sequential, >1 = parallel)

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
    
    # Helper function to process a single company
    def process_company(idx_and_company: tuple[int, tuple]) -> dict[str, Any] | None:
        """Process a single company and return result dict."""
        idx, (_, company) = idx_and_company
        try:
            uei = company.get("UEI")
            name = company.get("Company Name", "Unknown")
            sbir_awards = company.get("SBIR Awards", 0)

            # Convert pandas NaN to None/default values for Pydantic compatibility
            if pd.isna(uei):
                uei = None
            if pd.isna(sbir_awards):
                sbir_awards = 0

            logger.info(
                f"\n[{idx}/{len(companies)}] Processing: {name} (UEI: {uei})"
            )

            # Retrieve USAspending contracts (non-SBIR/STTR for categorization)
            if use_api:
                contracts_df = retrieve_company_contracts_api(uei=uei, company_name=name)
            else:
                if extractor is None:
                    raise ValueError("extractor is required when use_api=False")
                contracts_df = retrieve_company_contracts(extractor, uei=uei)

            # Retrieve SBIR/STTR awards separately for reporting (NOT used in categorization)
            if use_api:
                sbir_df = retrieve_sbir_awards_api(uei=uei, company_name=name)
            else:
                sbir_df = retrieve_sbir_awards(extractor, uei=uei)

            # Calculate SBIR statistics
            sbir_award_count = len(sbir_df) if not sbir_df.empty else 0
            sbir_dollars = sbir_df["award_amount"].sum() if not sbir_df.empty else 0.0
            non_sbir_dollars = contracts_df["award_amount"].sum() if not contracts_df.empty else 0.0
            total_usaspending_dollars = sbir_dollars + non_sbir_dollars
            sbir_pct_of_total = (
                (sbir_dollars / total_usaspending_dollars * 100) if total_usaspending_dollars > 0 else 0.0
            )

            # Log SBIR statistics for debugging
            logger.info(
                f"  USAspending breakdown: {len(contracts_df)} non-SBIR contracts (${non_sbir_dollars:,.0f}), "
                f"{sbir_award_count} SBIR/STTR awards (${sbir_dollars:,.0f}, {sbir_pct_of_total:.1f}% of total)"
            )

            if contracts_df.empty:
                logger.warning(f"  No non-SBIR/STTR USAspending contracts found for {name}")
                return {
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
                    "product_dollars": 0.0,
                    "service_dollars": 0.0,
                    "override_reason": "no_contracts_found",
                    "sbir_award_count": sbir_award_count,
                    "sbir_dollars": sbir_dollars,
                    "sbir_pct_of_total": sbir_pct_of_total,
                    "non_sbir_dollars": 0.0,
                    "non_sbir_contracts": 0,
                    "cost_based_contracts": 0,
                    "service_based_contracts": 0,
                    "justification": "No non-SBIR contracts found",
                }

            # Classify individual contracts
            # Keep original dicts for agency breakdown calculation
            contract_dicts = []
            classified_contracts = []
            cost_based_count = 0
            service_based_count = 0
            
            for _, contract in contracts_df.iterrows():
                contract_dict = contract.to_dict()
                contract_dicts.append(contract_dict)  # Keep original for agency info
                classified = classify_contract(contract_dict)
                classified_contracts.append(classified.model_dump())
                
                # Track cost-based and service-based contracts
                contract_type = contract_dict.get("contract_type", "")
                pricing = contract_dict.get("pricing", "")
                if is_cost_based_contract(contract_type, pricing):
                    cost_based_count += 1
                if is_service_based_contract(contract_type, pricing):
                    service_based_count += 1

            # Count classifications
            product_count = sum(1 for c in classified_contracts if c["classification"] == "Product")
            service_count = sum(1 for c in classified_contracts if c["classification"] == "Service")

            logger.info(
                f"  Contract breakdown: {product_count} Product, {service_count} Service"
            )

            # Analyze year-by-year revenue to identify consecutive product-dominant years
            consecutive_product_years = _analyze_consecutive_product_years(contract_dicts, classified_contracts)

            # Aggregate to company level (pass original dicts for agency breakdown)
            company_result = aggregate_company_classification(
                contract_dicts, company_uei=uei, company_name=name
            )
            
            logger.info(
                f"  Dollar breakdown: Product: {company_result.product_pct:.1f}%, "
                f"Service: {company_result.service_pct:.1f}%"
            )

            # Log agency breakdown if available
            if company_result.agency_breakdown:
                agency_parts = []
                for agency, pct in sorted(company_result.agency_breakdown.items(), key=lambda x: x[1], reverse=True):
                    agency_parts.append(f"{agency}: {pct:.1f}%")
                logger.info(f"  Agency breakdown: {', '.join(agency_parts)}")

            # Log consecutive product-dominant years if found
            if consecutive_product_years:
                years_str = ", ".join(map(str, consecutive_product_years))
                logger.info(f"  ⚠️  Consecutive product-dominant years: {years_str} (Product > Service for 2+ consecutive years)")

            # Print detailed justifications if requested (after aggregation so we have agency breakdown)
            if detailed:
                print_contract_justifications(name, classified_contracts, detailed=detailed, agency_breakdown=company_result.agency_breakdown)

            logger.info(
                f"  Result: {company_result.classification} "
                f"({company_result.product_pct:.1f}% Product, {company_result.service_pct:.1f}% Service) - "
                f"{company_result.confidence} confidence"
            )

            # Generate justification
            justification_parts = []
            if company_result.override_reason:
                if company_result.override_reason == "high_psc_diversity":
                    justification_parts.append(f"High PSC diversity ({company_result.psc_family_count} families)")
                elif company_result.override_reason == "insufficient_awards":
                    justification_parts.append("Insufficient awards for reliable classification")
                elif company_result.override_reason == "no_contracts_found":
                    justification_parts.append("No non-SBIR contracts found")
            else:
                if company_result.product_pct >= 51:
                    justification_parts.append(f"{company_result.product_pct:.0f}% product contracts")
                if company_result.service_pct >= 51:
                    justification_parts.append(f"{company_result.service_pct:.0f}% service contracts")
                # Check for balanced portfolio (no category >= 51%)
                if (company_result.product_pct < 51 and company_result.service_pct < 51):
                    justification_parts.append("Balanced portfolio across categories")
                if company_result.psc_family_count > 5:
                    justification_parts.append(f"{company_result.psc_family_count} PSC families")
                if company_result.award_count > 50:
                    justification_parts.append(f"{company_result.award_count} contracts")
            
            justification = ", ".join(justification_parts) if justification_parts else "See metrics"

            # Return result dict
            return {
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
                "service_dollars": company_result.service_dollars,
                "override_reason": company_result.override_reason,
                "sbir_award_count": sbir_award_count,
                "sbir_dollars": sbir_dollars,
                "sbir_pct_of_total": sbir_pct_of_total,
                "non_sbir_dollars": non_sbir_dollars,
                "non_sbir_contracts": company_result.award_count,
                "cost_based_contracts": cost_based_count,
                "service_based_contracts": service_based_count,
                "justification": justification,
                "consecutive_product_years": consecutive_product_years if consecutive_product_years else None,
            }
        except Exception as e:
            logger.error(f"Error processing company {company.get('Company Name', 'Unknown')}: {e}")
            return None

    # Process companies sequentially or in parallel
    if max_workers > 1 and use_api:
        # Parallel processing (only for API mode, respects shared rate limiter)
        logger.info(f"Processing {len(companies)} companies in parallel with {max_workers} workers")
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(process_company, (idx, company)): idx
                for idx, company in enumerate(companies.iterrows(), 1)
            }
            for future in as_completed(futures):
                result = future.result()
                if result is not None:
                    results.append(result)
    else:
        # Sequential processing
        for idx, (_, company) in enumerate(companies.iterrows(), 1):
            result = process_company((idx, (_, company)))
            if result is not None:
                results.append(result)

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

    # List companies with no non-SBIR/STTR contracts
    no_contracts = results[results['award_count'] == 0]
    if len(no_contracts) > 0:
        logger.info(f"\nCompanies with NO Non-SBIR/STTR USAspending Contracts ({len(no_contracts)} total):")
        logger.info("-" * 80)
        logger.info("  (These companies received SBIR awards but have no other federal contract revenue)")
        for idx, (_, row) in enumerate(no_contracts.iterrows(), 1):
            company_name = row['company_name']
            uei = row['company_uei']
            sbir_awards = row['sbir_awards']
            sbir_award_count = row.get('sbir_award_count', 0)
            sbir_dollars = row.get('sbir_dollars', 0)
            logger.info(
                f"  {idx}. {company_name} (UEI: {uei}, SBIR Awards from dataset: {sbir_awards}, "
                f"SBIR in USAspending: {sbir_award_count} awards / ${sbir_dollars:,.0f})"
            )
        logger.info("-" * 80)

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

    # SBIR/STTR Award Statistics (for debugging - NOT used in categorization)
    logger.info("\nSBIR/STTR Award Statistics (for debugging only):")
    logger.info("  " + "-" * 76)
    total_sbir_awards = results["sbir_award_count"].sum()
    total_sbir_dollars = results["sbir_dollars"].sum()
    companies_with_sbir = (results["sbir_award_count"] > 0).sum()
    avg_sbir_pct = results["sbir_pct_of_total"].mean()

    logger.info(f"  Total SBIR/STTR awards found in USAspending: {total_sbir_awards:,.0f}")
    logger.info(f"  Total SBIR/STTR dollars: ${total_sbir_dollars:,.0f}")
    logger.info(f"  Companies with SBIR awards in USAspending: {companies_with_sbir}/{len(results)}")
    logger.info(f"  Avg SBIR % of total USAspending revenue: {avg_sbir_pct:.1f}%")

    # Show companies where SBIR dominates
    high_sbir_pct = results[results["sbir_pct_of_total"] > 80]
    if len(high_sbir_pct) > 0:
        logger.info(f"\n  Companies with >80% SBIR/STTR revenue ({len(high_sbir_pct)} total):")
        for idx, (_, row) in enumerate(high_sbir_pct.head(10).iterrows(), 1):
            logger.info(
                f"    {idx}. {row['company_name'][:40]}: {row['sbir_pct_of_total']:.1f}% SBIR "
                f"(${row['sbir_dollars']:,.0f} SBIR / ${row['sbir_dollars'] + row['total_dollars']:,.0f} total)"
            )
        if len(high_sbir_pct) > 10:
            logger.info(f"    ... and {len(high_sbir_pct) - 10} more")

    # Average metrics
    with_contracts = results[results["award_count"] > 0]
    if len(with_contracts) > 0:
        logger.info("\nNon-SBIR Contract Metrics (companies with non-SBIR contracts):")
        logger.info(f"  Avg contracts per company: {with_contracts['award_count'].mean():.1f}")
        logger.info(f"  Avg PSC families: {with_contracts['psc_family_count'].mean():.1f}")
        logger.info(f"  Avg total dollars: ${with_contracts['total_dollars'].mean():,.0f}")
        logger.info(f"  Avg product %: {with_contracts['product_pct'].mean():.1f}%")
        logger.info(f"  Avg service %: {with_contracts['service_pct'].mean():.1f}%")

    # Companies with consecutive product-dominant years
    if "consecutive_product_years" in results.columns:
        consecutive_product_companies = results[results["consecutive_product_years"].notna()]
        if len(consecutive_product_companies) > 0:
            logger.info("\nCompanies with Consecutive Product-Dominant Years (Product > Service for 2+ consecutive years):")
            logger.info("  " + "-" * 76)
            for idx, (_, row) in enumerate(consecutive_product_companies.iterrows(), 1):
                years = row["consecutive_product_years"]
                if isinstance(years, list):
                    years_str = ", ".join(map(str, years))
                else:
                    years_str = str(years)
                logger.info(
                    f"  {idx}. {row['company_name'][:40]}: Years {years_str} "
                    f"({row['product_pct']:.1f}% Product overall, {row['award_count']} contracts)"
                )
            logger.info(f"\n  Total: {len(consecutive_product_companies)} companies")

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
    """Export results to CSV file with all requested fields.

    Args:
        results: DataFrame with categorization results
        output_path: Path to output CSV file
    """
    # Select and order the columns as requested
    export_columns = [
        "company_name",
        "sbir_award_count",
        "sbir_dollars",
        "non_sbir_dollars",
        "non_sbir_contracts",
        "cost_based_contracts",
        "service_based_contracts",
        "product_pct",
        "service_pct",
        "product_dollars",
        "service_dollars",
        "classification",
        "justification",
        "confidence",
    ]
    
    # Add consecutive_product_years if available
    if "consecutive_product_years" in results.columns:
        export_columns.append("consecutive_product_years")
    
    # Create export DataFrame with only requested columns (handle missing columns)
    available_columns = [col for col in export_columns if col in results.columns]
    export_df = results[available_columns].copy()
    
    # Format consecutive_product_years as string for CSV
    if "consecutive_product_years" in export_df.columns:
        export_df["consecutive_product_years"] = export_df["consecutive_product_years"].apply(
            lambda x: ", ".join(map(str, x)) if isinstance(x, list) else (str(x) if x is not None else "")
        )
    
    # Rename columns to match user's requested format
    rename_map = {
        "company_name": "Company Name",
        "sbir_award_count": "# of SBIR Awards Received",
        "sbir_dollars": "# of SBIR Dollars Received",
        "non_sbir_dollars": "Number of Non-SBIR Dollars Received",
        "non_sbir_contracts": "Number of Non-SBIR Government Contracts Received",
        "cost_based_contracts": "Number of Non-SBIR Cost-Based Contracts Received",
        "service_based_contracts": "Number of Non-SBIR Service-Based Contracts Received",
        "product_pct": "Product %",
        "service_pct": "Service %",
        "product_dollars": "Product Dollars",
        "service_dollars": "Service Dollars",
        "classification": "Classification",
        "justification": "Justification",
        "confidence": "Confidence",
    }
    
    # Add rename for consecutive_product_years if present
    if "consecutive_product_years" in export_df.columns:
        rename_map["consecutive_product_years"] = "Consecutive Product-Dominant Years"
    
    export_df = export_df.rename(columns=rename_map)
    
    export_df.to_csv(output_path, index=False)
    logger.info(f"\nResults exported to: {output_path}")
    logger.info(f"Exported {len(export_df)} companies with {len(export_df.columns)} columns")


def generate_markdown_report(results: pd.DataFrame, output_path: str) -> None:
    """Generate a detailed markdown report with categorization insights.

    Args:
        results: DataFrame with categorization results
        output_path: Path to output markdown file
    """
    with open(output_path, "w") as f:
        # Header
        f.write("# Company Categorization Analysis Report\n\n")
        f.write("This report analyzes SBIR companies based on their **non-SBIR/STTR** federal contract revenue ")
        f.write("to determine whether they are primarily Product or Service oriented.\n\n")
        f.write("**Important**: SBIR/STTR awards are tracked for reference but NOT included in categorization.\n\n")
        f.write("---\n\n")

        # Executive Summary
        f.write("## Executive Summary\n\n")
        f.write(f"- **Total Companies Analyzed**: {len(results)}\n")
        f.write(f"- **Companies with Non-SBIR Contracts**: {(results['award_count'] > 0).sum()}\n")
        f.write(f"- **Companies with ONLY SBIR Revenue**: {(results['award_count'] == 0).sum()}\n\n")

        # Classification breakdown
        f.write("### Classification Breakdown\n\n")
        class_dist = results["classification"].value_counts()
        for classification, count in class_dist.items():
            pct = (count / len(results)) * 100
            f.write(f"- **{classification}**: {count} companies ({pct:.1f}%)\n")
        f.write("\n")

        # Confidence breakdown
        f.write("### Confidence Distribution\n\n")
        conf_dist = results["confidence"].value_counts()
        for confidence, count in conf_dist.items():
            pct = (count / len(results)) * 100
            f.write(f"- **{confidence}**: {count} companies ({pct:.1f}%)\n")
        f.write("\n---\n\n")

        # SBIR Statistics
        f.write("## SBIR/STTR Revenue Statistics\n\n")
        f.write("*For debugging purposes - these revenues are NOT used in categorization*\n\n")
        total_sbir_awards = results["sbir_award_count"].sum()
        total_sbir_dollars = results["sbir_dollars"].sum()
        total_non_sbir_dollars = results["total_dollars"].sum()
        companies_with_sbir = (results["sbir_award_count"] > 0).sum()
        avg_sbir_pct = results["sbir_pct_of_total"].mean()

        f.write(f"- **Total SBIR/STTR Awards Found**: {total_sbir_awards:,.0f}\n")
        f.write(f"- **Total SBIR/STTR Dollars**: ${total_sbir_dollars:,.0f}\n")
        f.write(f"- **Total Non-SBIR Contract Dollars**: ${total_non_sbir_dollars:,.0f}\n")
        f.write(f"- **Companies with SBIR in USAspending**: {companies_with_sbir}/{len(results)}\n")
        f.write(f"- **Average SBIR % of Total Revenue**: {avg_sbir_pct:.1f}%\n\n")
        f.write("---\n\n")
        
        # Companies with consecutive product-dominant years
        if "consecutive_product_years" in results.columns:
            consecutive_product_companies = results[results["consecutive_product_years"].notna()]
            if len(consecutive_product_companies) > 0:
                f.write("## Companies with Consecutive Product-Dominant Years\n\n")
                f.write("Companies that received more product revenue than service revenue for **2+ consecutive years**.\n\n")
                f.write("| Company | Years | Product % | Service % | Contracts | Total $ |\n")
                f.write("|---------|------|-----------|-----------|-----------|--------|\n")
                
                for _, row in consecutive_product_companies.iterrows():
                    company = row["company_name"][:40]
                    years = row["consecutive_product_years"]
                    if isinstance(years, list):
                        years_str = ", ".join(map(str, years))
                    else:
                        years_str = str(years)
                    product_pct = row["product_pct"]
                    service_pct = row["service_pct"]
                    contracts = row["award_count"]
                    total_dollars = row["total_dollars"]
                    
                    f.write(f"| {company} | {years_str} | {product_pct:.1f}% | {service_pct:.1f}% | {contracts} | ${total_dollars:,.0f} |\n")
                
                f.write(f"\n**Total**: {len(consecutive_product_companies)} companies\n\n")
                f.write("---\n\n")

        # Product-Focused Companies
        product_companies = results[results["classification"] == "Product"].copy()
        if len(product_companies) > 0:
            product_companies = product_companies.sort_values("total_dollars", ascending=False)
            f.write(f"## Product-Focused Companies ({len(product_companies)} total)\n\n")
            f.write("Companies primarily selling tangible products to the federal government.\n\n")

            # Group by confidence
            for confidence in ["High", "Medium", "Low"]:
                conf_companies = product_companies[product_companies["confidence"] == confidence]
                if len(conf_companies) > 0:
                    f.write(f"### {confidence} Confidence ({len(conf_companies)} companies)\n\n")
                    f.write("| Company | Product % | Contracts | Total $ | SBIR % | Justification |\n")
                    f.write("|---------|-----------|-----------|---------|--------|---------------|\n")

                    for _, row in conf_companies.iterrows():
                        company = row["company_name"][:40]
                        product_pct = row["product_pct"]
                        contracts = row["award_count"]
                        total_dollars = row["total_dollars"]
                        sbir_pct = row["sbir_pct_of_total"]

                        # Generate justification
                        justification = []
                        if product_pct > 80:
                            justification.append(f"{product_pct:.0f}% product contracts")
                        if row["psc_family_count"] > 5:
                            justification.append(f"{row['psc_family_count']} PSC families")
                        if contracts > 50:
                            justification.append(f"{contracts} contracts")

                        just_str = ", ".join(justification) if justification else "See metrics"

                        f.write(f"| {company} | {product_pct:.1f}% | {contracts} | ${total_dollars:,.0f} | {sbir_pct:.1f}% | {just_str} |\n")
                    f.write("\n")

        # Service-Focused Companies
        service_companies = results[results["classification"] == "Service"].copy()
        if len(service_companies) > 0:
            service_companies = service_companies.sort_values("total_dollars", ascending=False)
            f.write(f"## Service-Focused Companies ({len(service_companies)} total)\n\n")
            f.write("Companies primarily providing services to the federal government.\n\n")

            # Group by confidence
            for confidence in ["High", "Medium", "Low"]:
                conf_companies = service_companies[service_companies["confidence"] == confidence]
                if len(conf_companies) > 0:
                    f.write(f"### {confidence} Confidence ({len(conf_companies)} companies)\n\n")
                    f.write("| Company | Service % | Contracts | Total $ | SBIR % | Justification |\n")
                    f.write("|---------|-----------|-----------|---------|--------|---------------|\n")

                    for _, row in conf_companies.iterrows():
                        company = row["company_name"][:40]
                        service_pct = row["service_pct"]
                        contracts = row["award_count"]
                        total_dollars = row["total_dollars"]
                        sbir_pct = row["sbir_pct_of_total"]

                        # Generate justification
                        justification = []
                        if service_pct > 80:
                            justification.append(f"{service_pct:.0f}% service/R&D contracts")
                        if row["psc_family_count"] > 5:
                            justification.append(f"{row['psc_family_count']} PSC families")
                        if contracts > 50:
                            justification.append(f"{contracts} contracts")

                        just_str = ", ".join(justification) if justification else "See metrics"

                        f.write(f"| {company} | {service_pct:.1f}% | {contracts} | ${total_dollars:,.0f} | {sbir_pct:.1f}% | {just_str} |\n")
                    f.write("\n")

        # Mixed Companies
        mixed_companies = results[results["classification"] == "Mixed"].copy()
        if len(mixed_companies) > 0:
            mixed_companies = mixed_companies.sort_values("total_dollars", ascending=False)
            f.write(f"## Mixed Product/Service Companies ({len(mixed_companies)} total)\n\n")
            f.write("Companies with balanced product and service portfolios.\n\n")

            # Group by confidence
            for confidence in ["High", "Medium", "Low"]:
                conf_companies = mixed_companies[mixed_companies["confidence"] == confidence]
                if len(conf_companies) > 0:
                    f.write(f"### {confidence} Confidence ({len(conf_companies)} companies)\n\n")
                    f.write("| Company | Product % | Service % | Contracts | Total $ | SBIR % | Justification |\n")
                    f.write("|---------|-----------|-----------|-----------|---------|--------|---------------|\n")

                    for _, row in conf_companies.iterrows():
                        company = row["company_name"][:40]
                        product_pct = row["product_pct"]
                        service_pct = row["service_pct"]
                        contracts = row["award_count"]
                        total_dollars = row["total_dollars"]
                        sbir_pct = row["sbir_pct_of_total"]

                        # Generate justification
                        justification = []
                        justification.append(f"Balanced: {product_pct:.0f}% prod / {service_pct:.0f}% svc")
                        if row["psc_family_count"] > 5:
                            justification.append(f"{row['psc_family_count']} PSC families")

                        just_str = ", ".join(justification) if justification else "See metrics"

                        f.write(f"| {company} | {product_pct:.1f}% | {service_pct:.1f}% | {contracts} | ${total_dollars:,.0f} | {sbir_pct:.1f}% | {just_str} |\n")
                    f.write("\n")

        # Uncertain/No Contracts
        uncertain_companies = results[
            (results["classification"] == "Uncertain") | (results["award_count"] == 0)
        ].copy()
        if len(uncertain_companies) > 0:
            uncertain_companies = uncertain_companies.sort_values("sbir_dollars", ascending=False)
            f.write(f"## Companies with No Non-SBIR Contracts ({len(uncertain_companies)} total)\n\n")
            f.write("These companies have SBIR awards but no other federal contract revenue in USAspending.\n\n")
            f.write("| Company | UEI | SBIR Awards (Dataset) | SBIR in USAspending | SBIR $ |\n")
            f.write("|---------|-----|----------------------|---------------------|--------|\n")

            for _, row in uncertain_companies.iterrows():
                company = row["company_name"][:40]
                uei = row["company_uei"]
                sbir_awards_dataset = row["sbir_awards"]
                sbir_award_count = row.get("sbir_award_count", 0)
                sbir_dollars = row.get("sbir_dollars", 0)

                f.write(f"| {company} | {uei} | {sbir_awards_dataset} | {sbir_award_count} | ${sbir_dollars:,.0f} |\n")
            f.write("\n")

        # Footer
        f.write("---\n\n")
        f.write("## Methodology\n\n")
        f.write("**Categorization Criteria:**\n\n")
        f.write("- **Product-leaning**: ≥51% of contract dollars from product-related PSC codes (numeric PSCs)\n")
        f.write("- **Service-leaning**: ≥51% of contract dollars from service-related PSC codes (alphabetic PSCs)\n")
        f.write("- **R&D-leaning**: ≥51% of contract dollars from R&D contracts\n")
        f.write("- **Mixed**: No category reaches 51% threshold (balanced portfolio)\n\n")
        f.write("**Confidence Levels:**\n\n")
        f.write("- **High**: 20+ contracts across 3+ PSC families with >80% in one category\n")
        f.write("- **Medium**: 10+ contracts or clear majority (>70%) in one category\n")
        f.write("- **Low**: Few contracts (<10) or borderline classification\n\n")
        f.write("**SBIR Exclusion:**\n\n")
        f.write("SBIR/STTR awards are excluded from categorization because they are R&D grants ")
        f.write("and do not reflect the company's product vs service business model. They are ")
        f.write("tracked separately for debugging and comparison purposes.\n")

    logger.info(f"\nMarkdown report generated: {output_path}")


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
        help="Generate detailed markdown report with categorization insights",
    )
    parser.add_argument(
        "--load-neo4j", action="store_true", help="Load results to Neo4j after categorization"
    )
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    parser.add_argument(
        "--use-api",
        action="store_true",
        help="Use USAspending API instead of DuckDB for contract retrieval",
    )
    parser.add_argument(
        "--detailed",
        action="store_true",
        help="Show detailed contract classification justifications",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=1,
        help="Number of parallel workers for API mode (default: 1 = sequential). "
             "Recommended: 3-5 workers to maximize throughput while respecting rate limits.",
    )

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

    # Initialize USAspending extractor if not using API
    extractor = None
    if args.use_api:
        logger.info("Using USAspending API for contract retrieval")
    else:
        config = get_config()
        db_path = config.duckdb.database_path
        logger.info(f"Using DuckDB database: {db_path}")
        extractor = DuckDBUSAspendingExtractor(db_path)

    try:
        # Categorize companies
        results = categorize_companies(
            companies,
            extractor,
            limit=args.limit,
            specific_uei=args.uei,
            use_api=args.use_api,
            detailed=args.detailed,
            max_workers=args.max_workers,
        )

        # Print summary
        print_summary(results)

        # Export if requested
        if args.output:
            export_results(results, args.output)

        # Generate markdown report if requested
        if args.markdown_report:
            generate_markdown_report(results, args.markdown_report)

        # Load to Neo4j if requested
        if args.load_neo4j:
            load_to_neo4j(results)

        logger.info("\n" + "=" * 80)
        logger.info("✓ VALIDATION TESTING COMPLETE")
        logger.info("=" * 80)

    finally:
        if extractor is not None:
            extractor.close()


if __name__ == "__main__":
    main()
