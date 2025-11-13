"""Dagster assets for company categorization pipeline.

This module implements the company categorization system that classifies SBIR
companies as Product, Service, or Mixed based on their federal contract portfolios
from USAspending.
"""

import pandas as pd
from dagster import (
    AssetCheckExecutionContext,
    AssetCheckResult,
    AssetCheckSeverity,
    AssetExecutionContext,
    MetadataValue,
    Output,
    asset,
    asset_check,
)
from loguru import logger

from ..config.loader import get_config
from ..enrichers.company_categorization import retrieve_company_contracts
from ..extractors.usaspending import DuckDBUSAspendingExtractor
from ..transformers.company_categorization import (
    aggregate_company_classification,
    classify_contract,
)


@asset(
    description="SBIR companies with Product/Service/Mixed categorization based on USAspending contract portfolios",
    group_name="company_categorization",
    compute_kind="transformation",
)
def enriched_sbir_companies_with_categorization(
    context: AssetExecutionContext, validated_sbir_awards: pd.DataFrame
) -> Output[pd.DataFrame]:
    """Categorize SBIR companies based on their complete federal contract portfolio.

    This asset retrieves all federal contracts from USAspending for each SBIR company,
    classifies individual contracts as Product/Service/R&D, and aggregates to company-level
    classifications with confidence scores.

    Args:
        validated_sbir_awards: Validated SBIR awards DataFrame with company identifiers

    Returns:
        DataFrame with company categorizations including:
            - company_uei: Company UEI
            - company_name: Company name
            - classification: Product-leaning, Service-leaning, Mixed, or Uncertain
            - product_pct: Percentage of dollars from product contracts
            - service_pct: Percentage of dollars from service/R&D contracts
            - confidence: Low, Medium, or High
            - award_count: Total number of contracts
            - psc_family_count: Number of distinct PSC families
            - total_dollars: Total contract dollars
            - product_dollars: Product contract dollars
            - service_rd_dollars: Service/R&D contract dollars
            - override_reason: Reason for override if applied
    """
    # Get configuration
    config = get_config()
    usaspending_table = config.extraction.usaspending.get("table_name", "usaspending_awards")

    context.log.info(
        f"Starting company categorization for {len(validated_sbir_awards)} SBIR awards",
        extra={"usaspending_table": usaspending_table},
    )

    # Initialize USAspending extractor
    db_path = config.duckdb.database_path
    extractor = DuckDBUSAspendingExtractor(db_path)

    try:
        # Get unique companies from validated awards
        company_columns = ["company_uei", "company_name"]
        # Check which columns are available
        available_columns = [col for col in company_columns if col in validated_sbir_awards.columns]

        if not available_columns:
            context.log.error("No company identifier columns found in validated_sbir_awards")
            return Output(
                value=pd.DataFrame(),
                metadata={
                    "num_companies": 0,
                    "error": "No company identifier columns found",
                },
            )

        # Extract unique companies
        companies = validated_sbir_awards[available_columns].drop_duplicates()
        companies = companies.dropna(subset=["company_uei"] if "company_uei" in companies.columns else [])

        context.log.info(f"Identified {len(companies)} unique companies to categorize")

        # Track statistics
        results = []
        companies_processed = 0
        companies_with_contracts = 0
        total_contracts_retrieved = 0

        # Process each company
        for idx, (_, company) in enumerate(companies.iterrows()):
            uei = company.get("company_uei") if "company_uei" in company else None
            name = company.get("company_name", "Unknown") if "company_name" in company else "Unknown"

            if not uei:
                context.log.warning(f"Skipping company {idx + 1} - no UEI available")
                continue

            # Log progress every 10 companies
            if (idx + 1) % 10 == 0:
                context.log.info(
                    f"Progress: {idx + 1}/{len(companies)} companies processed "
                    f"({companies_with_contracts} with contracts, {total_contracts_retrieved} total contracts)"
                )

            # Retrieve contracts from USAspending
            contracts_df = retrieve_company_contracts(
                extractor, uei=uei, table_name=usaspending_table
            )

            companies_processed += 1

            if contracts_df.empty:
                # No contracts found - classify as Uncertain
                context.log.debug(f"No USAspending contracts found for company {uei}")
                results.append(
                    {
                        "company_uei": uei,
                        "company_name": name,
                        "classification": "Uncertain",
                        "product_pct": 0.0,
                        "service_pct": 0.0,
                        "confidence": "Low",
                        "award_count": 0,
                        "psc_family_count": 0,
                        "total_dollars": 0.0,
                        "product_dollars": 0.0,
                        "service_rd_dollars": 0.0,
                        "override_reason": "no_contracts_found",
                    }
                )
                continue

            companies_with_contracts += 1
            total_contracts_retrieved += len(contracts_df)

            # Classify individual contracts
            classified_contracts = []
            for _, contract in contracts_df.iterrows():
                contract_dict = contract.to_dict()
                classified = classify_contract(contract_dict)
                classified_contracts.append(classified.model_dump())

            # Aggregate to company level
            company_classification = aggregate_company_classification(
                classified_contracts, company_uei=uei, company_name=name
            )

            # Add to results
            results.append(
                {
                    "company_uei": company_classification.company_uei,
                    "company_name": company_classification.company_name,
                    "classification": company_classification.classification,
                    "product_pct": company_classification.product_pct,
                    "service_pct": company_classification.service_pct,
                    "confidence": company_classification.confidence,
                    "award_count": company_classification.award_count,
                    "psc_family_count": company_classification.psc_family_count,
                    "total_dollars": company_classification.total_dollars,
                    "product_dollars": company_classification.product_dollars,
                    "service_rd_dollars": company_classification.service_rd_dollars,
                    "override_reason": company_classification.override_reason,
                }
            )

        # Convert results to DataFrame
        result_df = pd.DataFrame(results)

        context.log.info(
            f"Categorization complete: {len(result_df)} companies categorized",
            extra={
                "companies_processed": companies_processed,
                "companies_with_contracts": companies_with_contracts,
                "total_contracts_retrieved": total_contracts_retrieved,
            },
        )

        # Calculate classification distribution
        classification_dist = result_df["classification"].value_counts().to_dict()
        confidence_dist = result_df["confidence"].value_counts().to_dict()

        # Calculate average metrics
        avg_award_count = result_df["award_count"].mean()
        avg_psc_families = result_df["psc_family_count"].mean()

        # Create metadata for Dagster UI
        metadata = {
            "num_companies": len(result_df),
            "companies_with_contracts": companies_with_contracts,
            "total_contracts_retrieved": total_contracts_retrieved,
            "classification_distribution": MetadataValue.json(classification_dist),
            "confidence_distribution": MetadataValue.json(confidence_dist),
            "avg_award_count": round(avg_award_count, 2),
            "avg_psc_families": round(avg_psc_families, 2),
            "preview": MetadataValue.md(result_df.head(10).to_markdown()),
        }

        return Output(value=result_df, metadata=metadata)

    finally:
        # Clean up extractor connection
        extractor.close()


@asset_check(
    asset=enriched_sbir_companies_with_categorization,
    description="Verify categorization completeness and quality",
)
def company_categorization_completeness_check(
    context: AssetCheckExecutionContext,
    enriched_sbir_companies_with_categorization: pd.DataFrame,
) -> AssetCheckResult:
    """Verify categorization completeness and quality.

    Checks:
    1. Uncertain classifications are below threshold (<20%)
    2. High confidence classifications are above threshold (>50%)
    3. All required fields are present
    4. No null values in critical fields

    Args:
        enriched_sbir_companies_with_categorization: Categorized companies DataFrame

    Returns:
        AssetCheckResult with pass/fail status and diagnostics
    """
    df = enriched_sbir_companies_with_categorization

    if df.empty:
        return AssetCheckResult(
            passed=False,
            severity=AssetCheckSeverity.ERROR,
            description="No companies categorized",
            metadata={"num_companies": 0},
        )

    # Check 1: Uncertain percentage
    total = len(df)
    uncertain = (df["classification"] == "Uncertain").sum()
    uncertain_pct = (uncertain / total * 100) if total > 0 else 0

    # Check 2: High confidence percentage
    high_confidence = (df["confidence"] == "High").sum()
    high_confidence_pct = (high_confidence / total * 100) if total > 0 else 0

    # Check 3: Required fields
    required_fields = [
        "company_uei",
        "company_name",
        "classification",
        "product_pct",
        "service_pct",
        "confidence",
        "award_count",
    ]
    missing_fields = [f for f in required_fields if f not in df.columns]

    # Check 4: Null values in critical fields
    critical_fields = ["company_uei", "classification", "confidence"]
    null_counts = {f: df[f].isna().sum() for f in critical_fields if f in df.columns}

    # Determine pass/fail
    checks_passed = []
    checks_failed = []

    if uncertain_pct < 20.0:
        checks_passed.append(f"Uncertain rate {uncertain_pct:.1f}% < 20% threshold")
    else:
        checks_failed.append(f"Uncertain rate {uncertain_pct:.1f}% >= 20% threshold")

    if high_confidence_pct > 50.0:
        checks_passed.append(f"High confidence rate {high_confidence_pct:.1f}% > 50% threshold")
    else:
        checks_failed.append(
            f"High confidence rate {high_confidence_pct:.1f}% <= 50% threshold"
        )

    if not missing_fields:
        checks_passed.append("All required fields present")
    else:
        checks_failed.append(f"Missing fields: {missing_fields}")

    if sum(null_counts.values()) == 0:
        checks_passed.append("No null values in critical fields")
    else:
        checks_failed.append(f"Null values found: {null_counts}")

    # Overall pass/fail
    passed = len(checks_failed) == 0

    # Create description
    if passed:
        description = "All quality checks passed. " + " | ".join(checks_passed)
    else:
        description = "Quality checks failed: " + " | ".join(checks_failed)

    # Classification distribution
    classification_dist = df["classification"].value_counts().to_dict()

    return AssetCheckResult(
        passed=passed,
        severity=AssetCheckSeverity.WARN if not passed else AssetCheckSeverity.INFO,
        description=description,
        metadata={
            "total_companies": total,
            "uncertain_count": int(uncertain),
            "uncertain_pct": round(uncertain_pct, 2),
            "high_confidence_count": int(high_confidence),
            "high_confidence_pct": round(high_confidence_pct, 2),
            "classification_distribution": classification_dist,
            "checks_passed": checks_passed,
            "checks_failed": checks_failed,
        },
    )


@asset_check(
    asset=enriched_sbir_companies_with_categorization,
    description="Verify confidence level distribution is reasonable",
)
def company_categorization_confidence_check(
    context: AssetCheckExecutionContext,
    enriched_sbir_companies_with_categorization: pd.DataFrame,
) -> AssetCheckResult:
    """Verify confidence level distribution is reasonable.

    Checks that confidence levels align with award counts:
    - Low confidence: <2 awards
    - Medium confidence: 2-5 awards
    - High confidence: >5 awards

    Args:
        enriched_sbir_companies_with_categorization: Categorized companies DataFrame

    Returns:
        AssetCheckResult with confidence distribution diagnostics
    """
    df = enriched_sbir_companies_with_categorization

    if df.empty:
        return AssetCheckResult(
            passed=False,
            severity=AssetCheckSeverity.WARN,
            description="No companies to check",
            metadata={"num_companies": 0},
        )

    # Calculate confidence distribution
    confidence_dist = df["confidence"].value_counts().to_dict()

    # Verify confidence levels match award counts
    low_conf = df[df["confidence"] == "Low"]
    medium_conf = df[df["confidence"] == "Medium"]
    high_conf = df[df["confidence"] == "High"]

    # Check alignment
    checks = []

    # Low confidence should have <=2 awards
    low_misaligned = (low_conf["award_count"] > 2).sum()
    if low_misaligned == 0:
        checks.append("Low confidence alignment: OK")
    else:
        checks.append(f"Low confidence misaligned: {low_misaligned} companies")

    # Medium confidence should have 2-5 awards
    medium_misaligned = ((medium_conf["award_count"] <= 2) | (medium_conf["award_count"] > 5)).sum()
    if medium_misaligned == 0:
        checks.append("Medium confidence alignment: OK")
    else:
        checks.append(f"Medium confidence misaligned: {medium_misaligned} companies")

    # High confidence should have >5 awards
    high_misaligned = (high_conf["award_count"] <= 5).sum()
    if high_misaligned == 0:
        checks.append("High confidence alignment: OK")
    else:
        checks.append(f"High confidence misaligned: {high_misaligned} companies")

    total_misaligned = low_misaligned + medium_misaligned + high_misaligned
    passed = total_misaligned == 0

    description = " | ".join(checks)

    return AssetCheckResult(
        passed=passed,
        severity=AssetCheckSeverity.INFO if passed else AssetCheckSeverity.WARN,
        description=description,
        metadata={
            "confidence_distribution": confidence_dist,
            "low_confidence_count": len(low_conf),
            "medium_confidence_count": len(medium_conf),
            "high_confidence_count": len(high_conf),
            "total_misaligned": int(total_misaligned),
        },
    )
