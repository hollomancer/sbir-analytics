#!/usr/bin/env python3
"""Migration script to unify RESEARCHED_BY and WORKED_ON into PARTICIPATED_IN relationship.

This script:
1. Migrates RESEARCHED_BY (Award → Individual) relationships to PARTICIPATED_IN (Individual → Award)
2. Migrates WORKED_ON (Individual → Award) relationships to PARTICIPATED_IN (Individual → Award)
3. Removes duplicate relationships (if both existed)
4. Validates migration completeness

Usage:
    python scripts/migration/unify_participated_in_relationship.py [--dry-run] [--yes]

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


def migrate_researched_by_to_participated_in(driver, dry_run: bool = False) -> int:
    """Migrate RESEARCHED_BY relationships to PARTICIPATED_IN.

    Converts: (Award)-[RESEARCHED_BY]->(Individual)
    To:      (Individual)-[PARTICIPATED_IN]->(Award)

    Args:
        driver: Neo4j driver
        dry_run: If True, don't execute queries

    Returns:
        Number of relationships migrated
    """
    logger.info("Step 1: Migrating RESEARCHED_BY relationships to PARTICIPATED_IN")

    query = """
    MATCH (a:Award)-[r:RESEARCHED_BY]->(i:Individual)
    MERGE (i)-[p:PARTICIPATED_IN]->(a)
    SET p.role = 'RESEARCHER',
        p.created_at = coalesce(r.created_at, datetime()),
        p.migrated_from = 'RESEARCHED_BY'
    WITH r, p
    DELETE r
    WITH count(p) as migrated
    RETURN migrated
    """

    if dry_run:
        logger.info("DRY RUN: Would execute:\n%s", query)
        return 0

    with driver.session() as session:
        result = session.run(query)
        single_result = result.single()
        count = single_result["migrated"] if single_result else 0
        logger.info("✓ Migrated {} RESEARCHED_BY relationships to PARTICIPATED_IN", count)
        return count


def migrate_worked_on_to_participated_in(driver, dry_run: bool = False) -> int:
    """Migrate WORKED_ON relationships to PARTICIPATED_IN.

    Converts: (Individual)-[WORKED_ON]->(Award)
    To:      (Individual)-[PARTICIPATED_IN]->(Award)
    (Already correct direction, just rename and merge)

    Args:
        driver: Neo4j driver
        dry_run: If True, don't execute queries

    Returns:
        Number of relationships migrated
    """
    logger.info("Step 2: Migrating WORKED_ON relationships to PARTICIPATED_IN")

    query = """
    MATCH (i:Individual)-[w:WORKED_ON]->(a:Award)
    MERGE (i)-[p:PARTICIPATED_IN]->(a)
    SET p.role = coalesce(p.role, 'RESEARCHER'),
        p.created_at = coalesce(w.created_at, p.created_at, datetime()),
        p.migrated_from = coalesce(p.migrated_from, 'WORKED_ON')
    WITH w, p
    DELETE w
    RETURN count(p) as migrated
    """

    if dry_run:
        logger.info("DRY RUN: Would execute:\n%s", query)
        return 0

    with driver.session() as session:
        result = session.run(query)
        single_result = result.single()
        count = single_result["migrated"] if single_result else 0
        logger.info("✓ Migrated {} WORKED_ON relationships to PARTICIPATED_IN", count)
        return count


def validate_migration(driver) -> dict[str, Any]:
    """Run validation queries to verify migration completeness.

    Args:
        driver: Neo4j driver

    Returns:
        Dictionary with validation results
    """
    logger.info("Step 3: Validating migration")

    validation_queries = {
        "remaining_researched_by": "MATCH (a:Award)-[r:RESEARCHED_BY]->(i:Individual) RETURN count(r) as count",
        "remaining_worked_on": "MATCH (i:Individual)-[r:WORKED_ON]->(a:Award) RETURN count(r) as count",
        "participated_in_count": "MATCH (i:Individual)-[r:PARTICIPATED_IN]->(a:Award) RETURN count(r) as count",
        "participated_in_by_role": """
            MATCH (i:Individual)-[r:PARTICIPATED_IN]->(a:Award)
            RETURN r.role, count(*) as count
            ORDER BY count DESC
        """,
    }

    results = {}
    with driver.session() as session:
        for key, query in validation_queries.items():
            try:
                result = session.run(query)
                if key == "participated_in_by_role":
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

    logger.info("\nRemaining legacy relationships:")
    logger.info("  RESEARCHED_BY: %s", results.get("remaining_researched_by", "N/A"))
    logger.info("  WORKED_ON: %s", results.get("remaining_worked_on", "N/A"))

    logger.info("\nNew PARTICIPATED_IN relationships:")
    logger.info("  Total: %s", results.get("participated_in_count", "N/A"))

    logger.info("\nPARTICIPATED_IN by role:")
    roles = results.get("participated_in_by_role", [])
    for role_data in roles:
        logger.info("  %s: %d", role_data.get("r.role", "UNKNOWN"), role_data.get("count", 0))

    logger.info("\n" + "=" * 60)


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Unify RESEARCHED_BY and WORKED_ON into PARTICIPATED_IN relationship."
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
        migrate_researched_by_to_participated_in(driver, dry_run=args.dry_run)
        migrate_worked_on_to_participated_in(driver, dry_run=args.dry_run)

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

