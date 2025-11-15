#!/usr/bin/env python3
"""Migration script to consolidate relationships in Neo4j.

This script consolidates relationship types:
1. Renames AWARDED_TO → RECIPIENT_OF (FinancialTransaction → Organization)
2. Removes AWARDED_CONTRACT relationships (if they exist)
3. Removes FILED relationships (if they exist)
4. Renames FUNDED_BY (Patent → Award) → GENERATED_FROM (if they exist)

Usage:
    python scripts/migration/consolidate_relationships.py [--dry-run] [--yes]

Environment variables:
    NEO4J_URI: Neo4j connection URI (default: bolt://neo4j:7687)
    NEO4J_USER: Neo4j username (default: neo4j)
    NEO4J_PASSWORD: Neo4j password (required)
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Any

from loguru import logger

try:
    from neo4j import GraphDatabase
    from neo4j.exceptions import Neo4jError
except ImportError:
    GraphDatabase = None
    Neo4jError = Exception


def get_env_variable(name: str, default: str | None = None) -> str | None:
    """Get environment variable with optional default."""
    val = os.getenv(name, default)
    if val is None:
        logger.debug("Environment variable {} is not set and no default provided", name)
    return val


def connect(uri: str, user: str, password: str):
    """Create Neo4j driver connection."""
    if GraphDatabase is None:
        raise RuntimeError(
            "neo4j python driver not available. Install 'neo4j' package (pip install neo4j)."
        )
    logger.info("Connecting to Neo4j at {} as user {}", uri, user)
    driver = GraphDatabase.driver(uri, auth=(user, password))
    return driver


def migrate_awarded_to_to_recipient_of(driver, dry_run: bool = False) -> int:
    """Migrate AWARDED_TO relationships to RECIPIENT_OF.

    Converts: (FinancialTransaction)-[AWARDED_TO]->(Organization)
    To:      (FinancialTransaction)-[RECIPIENT_OF]->(Organization)
    
    Also handles legacy Award nodes if they exist:
    Converts: (Award)-[AWARDED_TO]->(Organization)
    To:      (Award)-[RECIPIENT_OF]->(Organization)

    Args:
        driver: Neo4j driver
        dry_run: If True, don't execute queries

    Returns:
        Number of relationships migrated
    """
    logger.info("Step 1: Migrating AWARDED_TO relationships to RECIPIENT_OF")

    # First, handle FinancialTransaction nodes
    query_ft = """
    MATCH (ft:FinancialTransaction)-[r:AWARDED_TO]->(o:Organization)
    MERGE (ft)-[new:RECIPIENT_OF]->(o)
    SET new.transaction_type = coalesce(ft.transaction_type, 'AWARD'),
        new.created_at = coalesce(r.created_at, datetime()),
        new.migrated_from = 'AWARDED_TO'
    WITH r, new
    DELETE r
    WITH count(new) as migrated
    RETURN migrated
    """
    
    # Also handle legacy Award nodes if they exist
    query_award = """
    MATCH (a:Award)-[r:AWARDED_TO]->(o:Organization)
    MERGE (a)-[new:RECIPIENT_OF]->(o)
    SET new.transaction_type = 'AWARD',
        new.created_at = coalesce(r.created_at, datetime()),
        new.migrated_from = 'AWARDED_TO'
    WITH r, new
    DELETE r
    WITH count(new) as migrated
    RETURN migrated
    """

    if dry_run:
        logger.info("DRY RUN: Would execute FinancialTransaction migration:\n{}", query_ft)
        logger.info("DRY RUN: Would execute Award migration:\n{}", query_award)
        return 0

    total_migrated = 0
    with driver.session() as session:
        # Migrate FinancialTransaction relationships
        result_ft = session.run(query_ft)
        count_ft = result_ft.single()["migrated"] if result_ft.peek() else 0
        total_migrated += count_ft
        
        # Migrate legacy Award relationships
        result_award = session.run(query_award)
        count_award = result_award.single()["migrated"] if result_award.peek() else 0
        total_migrated += count_award
        
        logger.info("✓ Migrated {} AWARDED_TO relationships to RECIPIENT_OF ({} FinancialTransaction, {} Award)", 
                   total_migrated, count_ft, count_award)
        return total_migrated


def remove_awarded_contract(driver, dry_run: bool = False) -> int:
    """Remove AWARDED_CONTRACT relationships (if they exist).

    These relationships should not exist if the code was already using AWARDED_TO,
    but we clean them up just in case. Handles both Contract and FinancialTransaction nodes.

    Args:
        driver: Neo4j driver
        dry_run: If True, don't execute queries

    Returns:
        Number of relationships removed
    """
    logger.info("Step 2: Removing AWARDED_CONTRACT relationships (if any exist)")

    # Handle Contract nodes
    query_contract = """
    MATCH (o:Organization)-[r:AWARDED_CONTRACT]->(c:Contract)
    WITH r, count(r) as to_delete
    DELETE r
    RETURN to_delete as deleted
    """
    
    # Handle FinancialTransaction nodes
    query_ft = """
    MATCH (o:Organization)-[r:AWARDED_CONTRACT]->(ft:FinancialTransaction)
    WITH r, count(r) as to_delete
    DELETE r
    RETURN to_delete as deleted
    """

    if dry_run:
        logger.info("DRY RUN: Would execute Contract removal:\n{}", query_contract)
        logger.info("DRY RUN: Would execute FinancialTransaction removal:\n{}", query_ft)
        return 0

    total_removed = 0
    with driver.session() as session:
        # Remove Contract relationships
        result_contract = session.run(query_contract)
        count_contract = result_contract.single()["deleted"] if result_contract.peek() else 0
        total_removed += count_contract
        
        # Remove FinancialTransaction relationships
        result_ft = session.run(query_ft)
        count_ft = result_ft.single()["deleted"] if result_ft.peek() else 0
        total_removed += count_ft
        
        if total_removed > 0:
            logger.info("✓ Removed {} AWARDED_CONTRACT relationships ({} Contract, {} FinancialTransaction)", 
                       total_removed, count_contract, count_ft)
        else:
            logger.info("✓ No AWARDED_CONTRACT relationships found (expected)")
        return total_removed


def remove_filed_relationships(driver, dry_run: bool = False) -> int:
    """Remove FILED relationships (if they exist).

    FILED relationships were never actually created in the codebase,
    but we clean them up if they somehow exist.

    Args:
        driver: Neo4j driver
        dry_run: If True, don't execute queries

    Returns:
        Number of relationships removed
    """
    logger.info("Step 3: Removing FILED relationships (if any exist)")

    query = """
    MATCH (c:Company)-[r:FILED]->(p:Patent)
    WITH r, count(r) as to_delete
    DELETE r
    RETURN to_delete as deleted
    """

    if dry_run:
        logger.info("DRY RUN: Would execute:\n{}", query)
        return 0

    with driver.session() as session:
        result = session.run(query)
        count = result.single()["deleted"] if result.peek() else 0
        if count > 0:
            logger.info("✓ Removed {} FILED relationships", count)
        else:
            logger.info("✓ No FILED relationships found (expected)")
        return count


def migrate_funded_by_to_generated_from(driver, dry_run: bool = False) -> int:
    """Migrate FUNDED_BY (Patent → Award) to GENERATED_FROM.

    Converts: (Patent)-[FUNDED_BY]->(Award)
    To:      (Patent)-[GENERATED_FROM]->(Award)

    Note: This only migrates Patent → Award relationships.
    FUNDED_BY relationships from FinancialTransaction → Organization (agencies) are kept.

    Args:
        driver: Neo4j driver
        dry_run: If True, don't execute queries

    Returns:
        Number of relationships migrated
    """
    logger.info("Step 4: Migrating FUNDED_BY (Patent → Award) to GENERATED_FROM")

    query = """
    MATCH (p:Patent)-[r:FUNDED_BY]->(a:Award)
    MERGE (p)-[new:GENERATED_FROM]->(a)
    SET new.linkage_method = coalesce(r.linkage_method, 'MIGRATED'),
        new.confidence_score = coalesce(r.confidence_score, 1.0),
        new.linked_date = coalesce(r.linked_date, datetime()),
        new.migrated_from = 'FUNDED_BY'
    WITH r, new
    DELETE r
    WITH count(new) as migrated
    RETURN migrated
    """

    if dry_run:
        logger.info("DRY RUN: Would execute:\n{}", query)
        return 0

    with driver.session() as session:
        result = session.run(query)
        count = result.single()["migrated"] if result.peek() else 0
        if count > 0:
            logger.info("✓ Migrated {} FUNDED_BY (Patent → Award) relationships to GENERATED_FROM", count)
        else:
            logger.info("✓ No FUNDED_BY (Patent → Award) relationships found (may already use GENERATED_FROM)")
        return count


def validate_migration(driver) -> dict[str, Any]:
    """Run validation queries to verify migration completeness.

    Args:
        driver: Neo4j driver

    Returns:
        Dictionary with validation results
    """
    logger.info("Step 5: Validating migration")

    validation_queries = {
        "remaining_awarded_to_ft": "MATCH (ft:FinancialTransaction)-[r:AWARDED_TO]->(o:Organization) RETURN count(r) as count",
        "remaining_awarded_to_award": "MATCH (a:Award)-[r:AWARDED_TO]->(o:Organization) RETURN count(r) as count",
        "remaining_awarded_contract_contract": "MATCH (o:Organization)-[r:AWARDED_CONTRACT]->(c:Contract) RETURN count(r) as count",
        "remaining_awarded_contract_ft": "MATCH (o:Organization)-[r:AWARDED_CONTRACT]->(ft:FinancialTransaction) RETURN count(r) as count",
        "remaining_filed": "MATCH (c:Company)-[r:FILED]->(p:Patent) RETURN count(r) as count",
        "remaining_funded_by_patent": "MATCH (p:Patent)-[r:FUNDED_BY]->(a:Award) RETURN count(r) as count",
        "recipient_of_count_ft": "MATCH (ft:FinancialTransaction)-[r:RECIPIENT_OF]->(o:Organization) RETURN count(r) as count",
        "recipient_of_count_award": "MATCH (a:Award)-[r:RECIPIENT_OF]->(o:Organization) RETURN count(r) as count",
        "generated_from_count": "MATCH (p:Patent)-[r:GENERATED_FROM]->(a:Award) RETURN count(r) as count",
        "recipient_of_by_type": """
            MATCH (ft:FinancialTransaction)-[r:RECIPIENT_OF]->(o:Organization)
            RETURN ft.transaction_type, count(*) as count
            ORDER BY count DESC
        """,
    }

    results = {}
    with driver.session() as session:
        for key, query in validation_queries.items():
            try:
                result = session.run(query)
                if key == "recipient_of_by_type":
                    records = [dict(record) for record in result]
                    results[key] = records
                else:
                    record = result.single()
                    results[key] = record["count"] if record else 0
            except Exception as e:
                logger.warning("Validation query failed for {}: {}", key, e)
                results[key] = None

    return results


def print_validation_results(results: dict[str, Any]) -> None:
    """Print validation results in a readable format."""
    logger.info("\n" + "=" * 60)
    logger.info("MIGRATION VALIDATION RESULTS")
    logger.info("=" * 60)

    logger.info("\nRemaining legacy relationships:")
    logger.info("  AWARDED_TO (FinancialTransaction): {}", results.get("remaining_awarded_to_ft", "N/A"))
    logger.info("  AWARDED_TO (Award): {}", results.get("remaining_awarded_to_award", "N/A"))
    logger.info("  AWARDED_CONTRACT (Contract): {}", results.get("remaining_awarded_contract_contract", "N/A"))
    logger.info("  AWARDED_CONTRACT (FinancialTransaction): {}", results.get("remaining_awarded_contract_ft", "N/A"))
    logger.info("  FILED: {}", results.get("remaining_filed", "N/A"))
    logger.info("  FUNDED_BY (Patent → Award): {}", results.get("remaining_funded_by_patent", "N/A"))

    logger.info("\nNew consolidated relationships:")
    logger.info("  RECIPIENT_OF (FinancialTransaction): {}", results.get("recipient_of_count_ft", "N/A"))
    logger.info("  RECIPIENT_OF (Award): {}", results.get("recipient_of_count_award", "N/A"))
    logger.info("  GENERATED_FROM: {}", results.get("generated_from_count", "N/A"))

    logger.info("\nRECIPIENT_OF by transaction type:")
    by_type = results.get("recipient_of_by_type", [])
    for type_data in by_type:
        tx_type = type_data.get("ft.transaction_type", "UNKNOWN")
        count = type_data.get("count", 0)
        logger.info("  {}: {}", tx_type, count)

    logger.info("\n" + "=" * 60)


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Consolidate relationship types: AWARDED_TO→RECIPIENT_OF, remove AWARDED_CONTRACT/FILED, FUNDED_BY→GENERATED_FROM."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print migration queries without executing them.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip confirmation prompts.",
    )
    parser.add_argument(
        "--skip-validation",
        action="store_true",
        help="Skip validation queries after migration.",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging.",
    )
    return parser.parse_args()


def main() -> int:
    """Main migration function."""
    args = parse_args()

    if args.verbose:
        logger.remove()
        logger.add(sys.stderr, level="DEBUG")

    # Get Neo4j connection details
    uri = get_env_variable("NEO4J_URI", "bolt://neo4j:7687")
    user = get_env_variable("NEO4J_USER", "neo4j")
    password = get_env_variable("NEO4J_PASSWORD", None)

    if not password and not args.dry_run:
        logger.error("NEO4J_PASSWORD is not set. Set it or run with --dry-run.")
        return 1

    if not args.dry_run and not args.yes:
        logger.warning("This will modify your Neo4j database. Press Ctrl+C to cancel.")
        try:
            input("Press Enter to continue...")
        except KeyboardInterrupt:
            logger.info("Migration cancelled.")
            return 0

    try:
        driver = connect(uri, user, password)
    except Exception as e:
        logger.exception("Failed to connect to Neo4j: {}", e)
        return 1

    try:
        # Run migration steps
        migrate_awarded_to_to_recipient_of(driver, dry_run=args.dry_run)
        remove_awarded_contract(driver, dry_run=args.dry_run)
        remove_filed_relationships(driver, dry_run=args.dry_run)
        migrate_funded_by_to_generated_from(driver, dry_run=args.dry_run)

        if not args.dry_run and not args.skip_validation:
            results = validate_migration(driver)
            print_validation_results(results)

        logger.info("✓ Migration completed successfully")
        return 0

    except Exception as e:
        logger.exception("Migration failed: {}", e)
        return 1

    finally:
        try:
            driver.close()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())

