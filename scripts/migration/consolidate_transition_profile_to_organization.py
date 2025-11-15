#!/usr/bin/env python3
"""Migration script to consolidate TransitionProfile properties into Organization nodes.

This script:
1. Migrates TransitionProfile properties to Organization nodes
2. Removes TransitionProfile nodes
3. Removes ACHIEVED relationships
4. Validates migration completeness

Usage:
    python scripts/migration/consolidate_transition_profile_to_organization.py [--dry-run] [--yes]

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


def migrate_transition_profiles_to_organization(driver, dry_run: bool = False) -> int:
    """Migrate TransitionProfile properties to Organization nodes.

    Args:
        driver: Neo4j driver
        dry_run: If True, don't execute queries

    Returns:
        Number of organizations updated
    """
    logger.info("Step 1: Migrating TransitionProfile properties to Organization nodes")

    query = """
    MATCH (o:Organization {organization_type: "COMPANY"})-[r:ACHIEVED]->(p:TransitionProfile)
    SET o.transition_total_awards = p.total_awards,
        o.transition_total_transitions = p.total_transitions,
        o.transition_success_rate = p.success_rate,
        o.transition_avg_likelihood_score = p.avg_likelihood_score,
        o.transition_profile_updated_at = coalesce(p.updated_date, p.created_date, datetime())
    RETURN count(o) as updated
    """

    if dry_run:
        logger.info("DRY RUN: Would execute:\n%s", query)
        return 0

    with driver.session() as session:
        result = session.run(query)
        count = result.single()["updated"] if result.peek() else 0
        logger.info("✓ Updated %d Organization nodes with transition profile properties", count)
        return count


def remove_achieved_relationships(driver, dry_run: bool = False) -> int:
    """Remove ACHIEVED relationships from Organization to TransitionProfile.

    Args:
        driver: Neo4j driver
        dry_run: If True, don't execute queries

    Returns:
        Number of relationships removed
    """
    logger.info("Step 2: Removing ACHIEVED relationships")

    query = """
    MATCH (o:Organization)-[r:ACHIEVED]->(p:TransitionProfile)
    DELETE r
    RETURN count(r) as deleted
    """

    if dry_run:
        logger.info("DRY RUN: Would execute:\n%s", query)
        return 0

    with driver.session() as session:
        result = session.run(query)
        count = result.single()["deleted"] if result.peek() else 0
        logger.info("✓ Removed %d ACHIEVED relationships", count)
        return count


def remove_transition_profile_nodes(driver, dry_run: bool = False) -> int:
    """Remove TransitionProfile nodes.

    Args:
        driver: Neo4j driver
        dry_run: If True, don't execute queries

    Returns:
        Number of nodes removed
    """
    logger.info("Step 3: Removing TransitionProfile nodes")

    query = """
    MATCH (p:TransitionProfile)
    DELETE p
    RETURN count(p) as deleted
    """

    if dry_run:
        logger.info("DRY RUN: Would execute:\n%s", query)
        return 0

    with driver.session() as session:
        result = session.run(query)
        count = result.single()["deleted"] if result.peek() else 0
        logger.info("✓ Removed %d TransitionProfile nodes", count)
        return count


def create_organization_transition_indexes(driver, dry_run: bool = False) -> None:
    """Create indexes on Organization transition properties.

    Args:
        driver: Neo4j driver
        dry_run: If True, don't execute queries
    """
    logger.info("Step 4: Creating indexes on Organization transition properties")

    statements = [
        "CREATE INDEX IF NOT EXISTS FOR (o:Organization) ON (o.transition_success_rate)",
        "CREATE INDEX IF NOT EXISTS FOR (o:Organization) ON (o.transition_total_transitions)",
        "CREATE INDEX IF NOT EXISTS FOR (o:Organization) ON (o.transition_total_awards)",
    ]

    if dry_run:
        for stmt in statements:
            logger.info("DRY RUN: Would execute:\n%s", stmt)
        return

    with driver.session() as session:
        for stmt in statements:
            try:
                session.run(stmt)
                logger.info("✓ Created index: %s", stmt.split()[5:7])
            except Neo4jError as e:
                if "already exists" in str(e).lower():
                    logger.info("Index already exists, skipping")
                else:
                    logger.warning("Failed to create index: %s", e)


def validate_migration(driver) -> dict[str, Any]:
    """Run validation queries to verify migration completeness.

    Args:
        driver: Neo4j driver

    Returns:
        Dictionary with validation results
    """
    logger.info("Step 5: Validating migration")

    validation_queries = {
        "remaining_profiles": "MATCH (p:TransitionProfile) RETURN count(p) as count",
        "remaining_achieved_rels": "MATCH (o:Organization)-[r:ACHIEVED]->(p:TransitionProfile) RETURN count(r) as count",
        "organizations_with_transition_metrics": """
            MATCH (o:Organization {organization_type: "COMPANY"})
            WHERE o.transition_total_awards IS NOT NULL
            RETURN count(o) as count
        """,
        "transition_metrics_summary": """
            MATCH (o:Organization {organization_type: "COMPANY"})
            WHERE o.transition_total_awards IS NOT NULL
            RETURN 
                avg(o.transition_success_rate) as avg_success_rate,
                sum(o.transition_total_awards) as total_awards,
                sum(o.transition_total_transitions) as total_transitions,
                count(o) as companies_with_metrics
        """,
    }

    results = {}
    with driver.session() as session:
        for key, query in validation_queries.items():
            try:
                result = session.run(query)
                if key == "transition_metrics_summary":
                    record = result.single()
                    results[key] = dict(record) if record else {}
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

    logger.info("\nRemaining legacy nodes/relationships:")
    logger.info("  TransitionProfile nodes: %s", results.get("remaining_profiles", "N/A"))
    logger.info("  ACHIEVED relationships: %s", results.get("remaining_achieved_rels", "N/A"))

    logger.info("\nOrganizations with transition metrics:")
    logger.info("  Count: %s", results.get("organizations_with_transition_metrics", "N/A"))

    summary = results.get("transition_metrics_summary", {})
    if summary:
        logger.info("\nTransition metrics summary:")
        logger.info("  Companies with metrics: %s", summary.get("companies_with_metrics", "N/A"))
        logger.info("  Total awards: %s", summary.get("total_awards", "N/A"))
        logger.info("  Total transitions: %s", summary.get("total_transitions", "N/A"))
        logger.info("  Average success rate: %s", summary.get("avg_success_rate", "N/A"))

    logger.info("\n" + "=" * 60)


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Consolidate TransitionProfile properties into Organization nodes."
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
        migrate_transition_profiles_to_organization(driver, dry_run=args.dry_run)
        remove_achieved_relationships(driver, dry_run=args.dry_run)
        remove_transition_profile_nodes(driver, dry_run=args.dry_run)
        create_organization_transition_indexes(driver, dry_run=args.dry_run)

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

