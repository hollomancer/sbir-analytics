#!/usr/bin/env python3
"""Migration script to consolidate Award and Contract into unified FinancialTransaction nodes.

This script:
1. Migrates Award nodes → FinancialTransaction (transaction_type: "AWARD")
2. Migrates Contract nodes → FinancialTransaction (transaction_type: "CONTRACT")
3. Updates all relationships to point to FinancialTransaction nodes
4. Updates Transition nodes to reference FinancialTransaction

Usage:
    python scripts/migration/unified_financial_transaction_migration.py [--dry-run] [--yes]

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

# Batch size for processing nodes (reduced to 500 for better timeout handling)
BATCH_SIZE = 500


def execute_batch_with_retry(
    session, query: str, params: dict[str, Any], max_retries: int = 3, batch_num: int = 0, total_batches: int = 0
) -> Any:
    """Execute a batch query with retry logic for connection timeouts.
    
    Args:
        session: Neo4j session
        query: Cypher query to execute
        params: Query parameters
        max_retries: Maximum retry attempts
        batch_num: Batch number for logging
        total_batches: Total batches for logging
        
    Returns:
        Query result
        
    Raises:
        Exception: If query fails after all retries
    """
    import time
    
    for attempt in range(max_retries):
        try:
            result = session.run(query, **params)
            return result
        except Exception as e:
            error_str = str(e).lower()
            is_timeout = "timeout" in error_str or "SessionExpired" in str(type(e).__name__)
            if attempt < max_retries - 1 and is_timeout:
                wait_seconds = 2 ** attempt
                logger.warning(
                    "Batch {}/{} failed (attempt {}/{}): {}. Retrying in {}s...",
                    batch_num,
                    total_batches,
                    attempt + 1,
                    max_retries,
                    e,
                    wait_seconds,
                )
                time.sleep(wait_seconds)
            else:
                logger.error(
                    "Batch {}/{} failed after {} attempts: {}",
                    batch_num,
                    total_batches,
                    max_retries,
                    e,
                )
                raise


def get_env_variable(name: str, default: str | None = None) -> str | None:
    """Get environment variable with optional default."""
    val = os.getenv(name, default)
    if val is None:
        logger.debug("Environment variable %s is not set and no default provided", name)
    return val


def connect(uri: str, user: str, password: str):
    """Create Neo4j driver connection."""
    if GraphDatabase is None:
        raise RuntimeError(
            "neo4j python driver not available. Install 'neo4j' package (pip install neo4j)."
        )
    logger.info("Connecting to Neo4j at %s as user %s", uri, user)
    driver = GraphDatabase.driver(uri, auth=(user, password))
    return driver


def migrate_awards_to_financial_transactions(driver, dry_run: bool = False, batch_size: int = BATCH_SIZE) -> int:
    """Migrate Award nodes to FinancialTransaction nodes in batches.

    Args:
        driver: Neo4j driver
        dry_run: If True, don't execute queries
        batch_size: Number of nodes to process per batch

    Returns:
        Number of transactions created
    """
    logger.info("Step 1: Migrating Award nodes to FinancialTransaction nodes")

    count_query = "MATCH (a:Award) RETURN count(a) as total"

    if dry_run:
        logger.info("DRY RUN: Would migrate Award nodes in batches of {}", batch_size)
        return 0

    with driver.session(default_access_mode="WRITE") as session:
        # Get total count
        count_result = session.run(count_query)
        total_count = count_result.single()["total"]
        logger.info("Found {} Award nodes to migrate", total_count)
        
        if total_count == 0:
            logger.info("No Award nodes to migrate")
            return 0

        batch_query = """
        MATCH (a:Award)
        WITH a SKIP $skip LIMIT $batch_size
        MERGE (ft:FinancialTransaction {transaction_id: 'txn_award_' + a.award_id})
        SET ft.transaction_type = 'AWARD',
            ft.award_id = a.award_id,
            ft.agency = a.agency,
            ft.agency_name = a.agency_name,
            ft.sub_agency = a.branch,
            ft.recipient_name = a.company_name,
            ft.recipient_uei = a.company_uei,
            ft.recipient_duns = a.company_duns,
            ft.amount = a.award_amount,
            ft.transaction_date = a.award_date,
            ft.completion_date = a.completion_date,
            ft.start_date = a.contract_start_date,
            ft.end_date = a.contract_end_date,
            ft.title = a.award_title,
            ft.description = a.abstract,
            ft.phase = a.phase,
            ft.program = a.program,
            ft.principal_investigator = a.principal_investigator,
            ft.research_institution = a.research_institution,
            ft.cet_area = a.cet_area,
            ft.award_year = a.award_year,
            ft.fiscal_year = a.fiscal_year,
            ft.naics_code = a.naics_primary,
            ft.created_at = coalesce(a.created_at, datetime()),
            ft.updated_at = datetime()
        RETURN count(ft) as created
        """

        total_created = 0
        skip = 0
        batch_num = 1
        total_batches = (total_count + batch_size - 1) // batch_size

        while skip < total_count:
            logger.info(
                "Processing batch {}/{} (nodes {}-{} of {})...",
                batch_num,
                total_batches,
                skip + 1,
                min(skip + batch_size, total_count),
                total_count,
            )
            
            result = execute_batch_with_retry(
                session, batch_query, {"skip": skip, "batch_size": batch_size},
                batch_num=batch_num, total_batches=total_batches
            )
            single_result = result.single()
            batch_created = single_result["created"] if single_result else 0
            total_created += batch_created
            
            logger.info(
                "✓ Batch {}/{} complete: Created {} FinancialTransaction nodes (Total: {}/{})",
                batch_num,
                total_batches,
                batch_created,
                total_created,
                total_count,
            )
            
            skip += batch_size
            batch_num += 1

        logger.info("✓ Migration complete: Created {} FinancialTransaction nodes from Award nodes", total_created)
        return total_created


def migrate_contracts_to_financial_transactions(driver, dry_run: bool = False, batch_size: int = BATCH_SIZE) -> int:
    """Migrate Contract nodes to FinancialTransaction nodes in batches.

    Args:
        driver: Neo4j driver
        dry_run: If True, don't execute queries
        batch_size: Number of nodes to process per batch

    Returns:
        Number of transactions created
    """
    logger.info("Step 2: Migrating Contract nodes to FinancialTransaction nodes")

    count_query = "MATCH (c:Contract) RETURN count(c) as total"

    if dry_run:
        logger.info("DRY RUN: Would migrate Contract nodes in batches of {}", batch_size)
        return 0

    with driver.session(default_access_mode="WRITE") as session:
        # Get total count
        count_result = session.run(count_query)
        total_count = count_result.single()["total"]
        logger.info("Found {} Contract nodes to migrate", total_count)
        
        if total_count == 0:
            logger.info("No Contract nodes to migrate")
            return 0

        batch_query = """
        MATCH (c:Contract)
        WITH c SKIP $skip LIMIT $batch_size
        MERGE (ft:FinancialTransaction {transaction_id: 'txn_contract_' + c.contract_id})
        SET ft.transaction_type = 'CONTRACT',
            ft.contract_id = c.contract_id,
            ft.agency = c.agency,
            ft.agency_name = c.agency_name,
            ft.sub_agency = c.sub_agency,
            ft.sub_agency_name = c.sub_agency_name,
            ft.recipient_name = c.vendor_name,
            ft.recipient_uei = c.vendor_uei,
            ft.amount = c.obligated_amount,
            ft.base_and_all_options_value = c.base_and_all_options_value,
            ft.transaction_date = c.action_date,
            ft.start_date = c.start_date,
            ft.end_date = c.end_date,
            ft.title = c.description,
            ft.description = c.description,
            ft.competition_type = c.competition_type,
            ft.piid = c.piid,
            ft.fain = c.fain,
            ft.psc_code = c.psc_code,
            ft.place_of_performance = c.place_of_performance,
            ft.naics_code = c.naics_code,
            ft.created_at = coalesce(c.created_at, datetime()),
            ft.updated_at = datetime()
        RETURN count(ft) as created
        """

        total_created = 0
        skip = 0
        batch_num = 1
        total_batches = (total_count + batch_size - 1) // batch_size

        while skip < total_count:
            logger.info(
                "Processing batch {}/{} (nodes {}-{} of {})...",
                batch_num,
                total_batches,
                skip + 1,
                min(skip + batch_size, total_count),
                total_count,
            )
            
            result = execute_batch_with_retry(
                session, batch_query, {"skip": skip, "batch_size": batch_size},
                batch_num=batch_num, total_batches=total_batches
            )
            single_result = result.single()
            batch_created = single_result["created"] if single_result else 0
            total_created += batch_created
            
            logger.info(
                "✓ Batch {}/{} complete: Created {} FinancialTransaction nodes (Total: {}/{})",
                batch_num,
                total_batches,
                batch_created,
                total_created,
                total_count,
            )
            
            skip += batch_size
            batch_num += 1

        logger.info("✓ Migration complete: Created {} FinancialTransaction nodes from Contract nodes", total_created)
        return total_created


def update_award_relationships(driver, dry_run: bool = False) -> int:
    """Update relationships from Award nodes to FinancialTransaction.

    Args:
        driver: Neo4j driver
        dry_run: If True, don't execute queries

    Returns:
        Number of relationships updated
    """
    logger.info("Step 3: Updating Award relationships")

    queries = [
        # Update AWARDED_TO relationships
        """
        MATCH (a:Award)-[r:AWARDED_TO]->(o:Organization)
        MATCH (ft:FinancialTransaction {award_id: a.award_id})
        MERGE (ft)-[r2:AWARDED_TO]->(o)
        SET r2 = properties(r)
        DELETE r
        RETURN count(r2) as updated
        """,
        # Update FUNDED_BY relationships
        """
        MATCH (a:Award)-[r:FUNDED_BY]->(o:Organization)
        MATCH (ft:FinancialTransaction {award_id: a.award_id})
        MERGE (ft)-[r2:FUNDED_BY]->(o)
        SET r2 = properties(r)
        DELETE r
        RETURN count(r2) as updated
        """,
        # Update PARTICIPATED_IN relationships
        """
        MATCH (i:Individual)-[r:PARTICIPATED_IN]->(a:Award)
        MATCH (ft:FinancialTransaction {award_id: a.award_id})
        MERGE (i)-[r2:PARTICIPATED_IN]->(ft)
        SET r2 = properties(r)
        DELETE r
        RETURN count(r2) as updated
        """,
        # Update CONDUCTED_AT relationships
        """
        MATCH (a:Award)-[r:CONDUCTED_AT]->(o:Organization)
        MATCH (ft:FinancialTransaction {award_id: a.award_id})
        MERGE (ft)-[r2:CONDUCTED_AT]->(o)
        SET r2 = properties(r)
        DELETE r
        RETURN count(r2) as updated
        """,
        # Update FOLLOWS relationships (Award -> Award)
        """
        MATCH (a1:Award)-[r:FOLLOWS]->(a2:Award)
        MATCH (ft1:FinancialTransaction {award_id: a1.award_id})
        MATCH (ft2:FinancialTransaction {award_id: a2.award_id})
        MERGE (ft1)-[r2:FOLLOWS]->(ft2)
        SET r2 = properties(r)
        DELETE r
        RETURN count(r2) as updated
        """,
        # Update TRANSITIONED_TO relationships
        """
        MATCH (a:Award)-[r:TRANSITIONED_TO]->(t:Transition)
        MATCH (ft:FinancialTransaction {award_id: a.award_id})
        MERGE (ft)-[r2:TRANSITIONED_TO]->(t)
        SET r2 = properties(r)
        DELETE r
        RETURN count(r2) as updated
        """,
        # Update GENERATED_FROM relationships (Patent -> Award)
        """
        MATCH (p:Patent)-[r:GENERATED_FROM]->(a:Award)
        MATCH (ft:FinancialTransaction {award_id: a.award_id})
        MERGE (p)-[r2:GENERATED_FROM]->(ft)
        SET r2 = properties(r)
        DELETE r
        RETURN count(r2) as updated
        """,
    ]

    if dry_run:
        for query in queries:
            logger.info("DRY RUN: Would execute:\n%s", query)
        return 0

    total_updated = 0
    with driver.session() as session:
        for query in queries:
            try:
                result = session.run(query)
                single_result = result.single()
                count = single_result["updated"] if single_result else 0
                total_updated += count
            except Exception as e:
                logger.warning("Failed to update relationship: %s", e)

    logger.info("✓ Updated %d Award relationships", total_updated)
    return total_updated


def update_contract_relationships(driver, dry_run: bool = False) -> int:
    """Update relationships from Contract nodes to FinancialTransaction.

    Args:
        driver: Neo4j driver
        dry_run: If True, don't execute queries

    Returns:
        Number of relationships updated
    """
    logger.info("Step 4: Updating Contract relationships")

    queries = [
        # Update AWARDED_CONTRACT relationships
        """
        MATCH (o:Organization)-[r:AWARDED_CONTRACT]->(c:Contract)
        MATCH (ft:FinancialTransaction {contract_id: c.contract_id})
        MERGE (o)-[r2:AWARDED_CONTRACT]->(ft)
        SET r2 = properties(r)
        DELETE r
        RETURN count(r2) as updated
        """,
        # Update AWARDED_BY relationships
        """
        MATCH (c:Contract)-[r:AWARDED_BY]->(o:Organization)
        MATCH (ft:FinancialTransaction {contract_id: c.contract_id})
        MERGE (ft)-[r2:AWARDED_BY]->(o)
        SET r2 = properties(r)
        DELETE r
        RETURN count(r2) as updated
        """,
        # Update RESULTED_IN relationships (Transition -> Contract)
        """
        MATCH (t:Transition)-[r:RESULTED_IN]->(c:Contract)
        MATCH (ft:FinancialTransaction {contract_id: c.contract_id})
        MERGE (t)-[r2:RESULTED_IN]->(ft)
        SET r2 = properties(r)
        DELETE r
        RETURN count(r2) as updated
        """,
    ]

    if dry_run:
        for query in queries:
            logger.info("DRY RUN: Would execute:\n%s", query)
        return 0

    total_updated = 0
    with driver.session() as session:
        for query in queries:
            try:
                result = session.run(query)
                single_result = result.single()
                count = single_result["updated"] if single_result else 0
                total_updated += count
            except Exception as e:
                logger.warning("Failed to update relationship: %s", e)

    logger.info("✓ Updated %d Contract relationships", total_updated)
    return total_updated


def update_transition_nodes(driver, dry_run: bool = False) -> int:
    """Update Transition nodes to reference FinancialTransaction instead of Award/Contract.

    Args:
        driver: Neo4j driver
        dry_run: If True, don't execute queries

    Returns:
        Number of transitions updated
    """
    logger.info("Step 5: Updating Transition nodes")

    query = """
    MATCH (t:Transition)
    WHERE t.award_id IS NOT NULL OR t.contract_id IS NOT NULL
    WITH t
    OPTIONAL MATCH (ft_award:FinancialTransaction {award_id: t.award_id})
    OPTIONAL MATCH (ft_contract:FinancialTransaction {contract_id: t.contract_id})
    SET t.award_transaction_id = ft_award.transaction_id,
        t.contract_transaction_id = ft_contract.transaction_id
    RETURN count(t) as updated
    """

    if dry_run:
        logger.info("DRY RUN: Would execute:\n%s", query)
        return 0

    with driver.session() as session:
        result = session.run(query)
        count = result.single()["updated"] if result.peek() else 0
        logger.info("✓ Updated %d Transition nodes", count)
        return count


def create_financial_transaction_constraints_and_indexes(driver, dry_run: bool = False) -> None:
    """Create constraints and indexes for FinancialTransaction nodes.

    Args:
        driver: Neo4j driver
        dry_run: If True, don't execute queries
    """
    logger.info("Step 6: Creating FinancialTransaction constraints and indexes")

    statements = [
        "CREATE CONSTRAINT IF NOT EXISTS FOR (ft:FinancialTransaction) REQUIRE ft.transaction_id IS UNIQUE",
        "CREATE INDEX IF NOT EXISTS FOR (ft:FinancialTransaction) ON (ft.transaction_type)",
        "CREATE INDEX IF NOT EXISTS FOR (ft:FinancialTransaction) ON (ft.transaction_date)",
        "CREATE INDEX IF NOT EXISTS FOR (ft:FinancialTransaction) ON (ft.agency)",
        "CREATE INDEX IF NOT EXISTS FOR (ft:FinancialTransaction) ON (ft.award_id)",
        "CREATE INDEX IF NOT EXISTS FOR (ft:FinancialTransaction) ON (ft.contract_id)",
        "CREATE INDEX IF NOT EXISTS FOR (ft:FinancialTransaction) ON (ft.recipient_uei)",
    ]

    if dry_run:
        for stmt in statements:
            logger.info("DRY RUN: Would execute:\n%s", stmt)
        return

    with driver.session() as session:
        for stmt in statements:
            try:
                session.run(stmt)
                logger.info("✓ Created constraint/index: %s", stmt.split()[2:5])
            except Neo4jError as e:
                if "already exists" in str(e).lower():
                    logger.info("Constraint/index already exists, skipping")
                else:
                    logger.warning("Failed to create constraint/index: %s", e)


def validate_migration(driver) -> dict[str, Any]:
    """Run validation queries to verify migration completeness.

    Args:
        driver: Neo4j driver

    Returns:
        Dictionary with validation results
    """
    logger.info("Step 7: Validating migration")

    validation_queries = {
        "remaining_awards": "MATCH (a:Award) RETURN count(a) as count",
        "remaining_contracts": "MATCH (c:Contract) RETURN count(c) as count",
        "financial_transactions_by_type": """
            MATCH (ft:FinancialTransaction)
            RETURN ft.transaction_type, count(*) as count
            ORDER BY count DESC
        """,
        "awarded_to_relationships": "MATCH (ft:FinancialTransaction)-[r:AWARDED_TO]->(o:Organization) RETURN count(r) as count",
        "funded_by_relationships": "MATCH (ft:FinancialTransaction)-[r:FUNDED_BY]->(o:Organization) RETURN count(r) as count",
        "transitioned_to_relationships": "MATCH (ft:FinancialTransaction)-[r:TRANSITIONED_TO]->(t:Transition) RETURN count(r) as count",
        "resulted_in_relationships": "MATCH (t:Transition)-[r:RESULTED_IN]->(ft:FinancialTransaction) RETURN count(r) as count",
    }

    results = {}
    with driver.session() as session:
        for key, query in validation_queries.items():
            try:
                result = session.run(query)
                if key == "financial_transactions_by_type":
                    records = [dict(record) for record in result]
                    results[key] = records
                else:
                    record = result.single()
                    results[key] = record["count"] if record else 0
            except Exception as e:
                logger.warning("Validation query failed for %s: %s", key, e)
                results[key] = None

    return results


def print_validation_results(results: dict[str, Any]) -> None:
    """Print validation results in a readable format."""
    logger.info("\n" + "=" * 60)
    logger.info("MIGRATION VALIDATION RESULTS")
    logger.info("=" * 60)

    logger.info("\nRemaining legacy nodes:")
    logger.info("  Awards: %s", results.get("remaining_awards", "N/A"))
    logger.info("  Contracts: %s", results.get("remaining_contracts", "N/A"))

    logger.info("\nFinancialTransactions by type:")
    tx_types = results.get("financial_transactions_by_type", [])
    for tx_type in tx_types:
        logger.info("  %s: %d", tx_type.get("ft.transaction_type", "UNKNOWN"), tx_type.get("count", 0))

    logger.info("\nRelationships:")
    logger.info("  AWARDED_TO: %s", results.get("awarded_to_relationships", "N/A"))
    logger.info("  FUNDED_BY: %s", results.get("funded_by_relationships", "N/A"))
    logger.info("  TRANSITIONED_TO: %s", results.get("transitioned_to_relationships", "N/A"))
    logger.info("  RESULTED_IN: %s", results.get("resulted_in_relationships", "N/A"))

    logger.info("\n" + "=" * 60)


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Migrate Award and Contract to unified FinancialTransaction nodes."
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
        logger.exception("Failed to connect to Neo4j: %s", e)
        return 1

    try:
        # Run migration steps
        migrate_awards_to_financial_transactions(driver, dry_run=args.dry_run)
        migrate_contracts_to_financial_transactions(driver, dry_run=args.dry_run)
        update_award_relationships(driver, dry_run=args.dry_run)
        update_contract_relationships(driver, dry_run=args.dry_run)
        update_transition_nodes(driver, dry_run=args.dry_run)
        create_financial_transaction_constraints_and_indexes(driver, dry_run=args.dry_run)

        if not args.dry_run and not args.skip_validation:
            results = validate_migration(driver)
            print_validation_results(results)

        logger.info("✓ Migration completed successfully")
        return 0

    except Exception as e:
        logger.exception("Migration failed: %s", e)
        return 1

    finally:
        try:
            driver.close()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())

