#!/usr/bin/env python3
"""Unified migration script to consolidate all Neo4j schema changes.

This script runs all migrations in the correct order:
1. Organization Migration (Company, PatentEntity, ResearchInstitution → Organization)
2. Individual Migration (Researcher, PatentEntity individuals → Individual)
3. FinancialTransaction Migration (Award, Contract → FinancialTransaction)
4. Participated_in Unification (RESEARCHED_BY, WORKED_ON → PARTICIPATED_IN)
5. TransitionProfile Consolidation (TransitionProfile → Organization properties)
6. Relationship Consolidation (AWARDED_TO → RECIPIENT_OF, etc.)

Usage:
    python scripts/migration/unified_schema_migration.py [--dry-run] [--yes] [--skip-steps STEP1,STEP2]

Environment variables:
    NEO4J_URI: Neo4j connection URI (default: bolt://neo4j:7687)
    NEO4J_USER: Neo4j username (default: neo4j)
    NEO4J_PASSWORD: Neo4j password (required)

Examples:
    # Dry run to see what would happen
    python scripts/migration/unified_schema_migration.py --dry-run

    # Run all migrations
    python scripts/migration/unified_schema_migration.py --yes

    # Skip specific steps (e.g., if already run)
    python scripts/migration/unified_schema_migration.py --yes --skip-steps 1,2
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

# Import individual migration functions
# Note: We import the modules and call their main functions, or import specific functions
# Since the modules have their own main() functions, we'll import them as modules
import importlib.util

def load_module(path: str, name: str):
    """Dynamically load a module from a file path."""
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load module {name} from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

# Load migration modules
try:
    org_migration = load_module(
        "scripts/migration/unified_organization_migration.py",
        "unified_organization_migration"
    )
    individual_migration = load_module(
        "scripts/migration/unified_individual_migration.py",
        "unified_individual_migration"
    )
    ft_migration = load_module(
        "scripts/migration/unified_financial_transaction_migration.py",
        "unified_financial_transaction_migration"
    )
    participated_migration = load_module(
        "scripts/migration/unify_participated_in_relationship.py",
        "unify_participated_in_relationship"
    )
    transition_profile_migration = load_module(
        "scripts/migration/consolidate_transition_profile_to_organization.py",
        "consolidate_transition_profile_to_organization"
    )
    relationship_migration = load_module(
        "scripts/migration/consolidate_relationships.py",
        "consolidate_relationships"
    )
except Exception as e:
    logger.error("Failed to import migration modules: {}", e)
    logger.error("Make sure you're running from the project root directory")
    sys.exit(1)


def get_env_variable(name: str, default: str | None = None) -> str | None:
    """Get environment variable with optional default."""
    val = os.getenv(name, default)
    if val is None:
        logger.debug("Environment variable {} is not set and no default provided", name)
    return val


def connect(uri: str, user: str, password: str):
    """Create Neo4j driver connection with extended timeouts for long-running migrations.
    
    Note: For very large datasets, consider processing in batches or increasing
    Neo4j server-side query timeout settings.
    """
    if GraphDatabase is None:
        raise RuntimeError(
            "neo4j python driver not available. Install 'neo4j' package (pip install neo4j)."
        )
    logger.info("Connecting to Neo4j at {} as user {}", uri, user)
    
    # Configure timeouts for long-running migration queries
    # These settings help prevent connection timeouts during large migrations
    driver_config = {
        "max_connection_lifetime": 3600 * 2,  # 2 hours
        "max_connection_pool_size": 10,
        "connection_acquisition_timeout": 300.0,  # 5 minutes to get connection from pool
        "connection_timeout": 60.0,  # 1 minute to establish connection
    }
    
    # Only add parameters that are supported by the driver version
    try:
        driver = GraphDatabase.driver(uri, auth=(user, password), **driver_config)
    except TypeError:
        # Fallback if some parameters aren't supported
        logger.warning("Some timeout parameters may not be supported by this driver version")
        driver = GraphDatabase.driver(uri, auth=(user, password))
    
    logger.info("Driver configured with extended timeouts for long-running migrations")
    return driver


def run_organization_migration(driver, dry_run: bool) -> bool:
    """Run organization migration steps."""
    try:
        org_migration.migrate_companies_to_organizations(driver, dry_run=dry_run)
        org_migration.migrate_patent_entities_to_organizations(driver, dry_run=dry_run)
        org_migration.migrate_research_institutions_to_organizations(driver, dry_run=dry_run)
        org_migration.create_agency_organizations(driver, dry_run=dry_run)
        org_migration.update_award_relationships(driver, dry_run=dry_run)
        org_migration.update_contract_relationships(driver, dry_run=dry_run)
        org_migration.update_other_relationships(driver, dry_run=dry_run)
        org_migration.create_organization_constraints_and_indexes(driver, dry_run=dry_run)
        return True
    except Exception as e:
        logger.exception("Organization migration failed: {}", e)
        return False


def run_individual_migration(driver, dry_run: bool) -> bool:
    """Run individual migration steps."""
    try:
        individual_migration.migrate_researchers_to_individuals(driver, dry_run=dry_run)
        individual_migration.migrate_patent_individuals_to_individuals(driver, dry_run=dry_run)
        individual_migration.update_researcher_relationships(driver, dry_run=dry_run)
        individual_migration.create_individual_constraints_and_indexes(driver, dry_run=dry_run)
        return True
    except Exception as e:
        logger.exception("Individual migration failed: {}", e)
        return False


def run_financial_transaction_migration(driver, dry_run: bool) -> bool:
    """Run financial transaction migration steps."""
    try:
        ft_migration.migrate_awards_to_financial_transactions(driver, dry_run=dry_run)
        ft_migration.migrate_contracts_to_financial_transactions(driver, dry_run=dry_run)
        ft_migration.update_award_relationships(driver, dry_run=dry_run)
        ft_migration.update_contract_relationships(driver, dry_run=dry_run)
        ft_migration.update_transition_nodes(driver, dry_run=dry_run)
        ft_migration.create_financial_transaction_constraints_and_indexes(driver, dry_run=dry_run)
        return True
    except Exception as e:
        logger.exception("FinancialTransaction migration failed: {}", e)
        return False


def run_participated_in_migration(driver, dry_run: bool) -> bool:
    """Run participated_in unification steps."""
    try:
        participated_migration.migrate_researched_by_to_participated_in(driver, dry_run=dry_run)
        participated_migration.migrate_worked_on_to_participated_in(driver, dry_run=dry_run)
        return True
    except Exception as e:
        logger.exception("Participated_in migration failed: {}", e)
        return False


def run_transition_profile_migration(driver, dry_run: bool) -> bool:
    """Run transition profile consolidation steps."""
    try:
        transition_profile_migration.migrate_transition_profiles_to_organization(driver, dry_run=dry_run)
        transition_profile_migration.remove_achieved_relationships(driver, dry_run=dry_run)
        transition_profile_migration.remove_transition_profile_nodes(driver, dry_run=dry_run)
        transition_profile_migration.create_organization_transition_indexes(driver, dry_run=dry_run)
        return True
    except Exception as e:
        logger.exception("TransitionProfile migration failed: {}", e)
        return False


def run_relationship_consolidation(driver, dry_run: bool) -> bool:
    """Run relationship consolidation steps."""
    try:
        relationship_migration.migrate_awarded_to_to_recipient_of(driver, dry_run=dry_run)
        relationship_migration.remove_awarded_contract(driver, dry_run=dry_run)
        relationship_migration.remove_filed_relationships(driver, dry_run=dry_run)
        relationship_migration.migrate_funded_by_to_generated_from(driver, dry_run=dry_run)
        return True
    except Exception as e:
        logger.exception("Relationship consolidation failed: {}", e)
        return False


def parse_skip_steps(skip_str: str | None) -> set[int]:
    """Parse comma-separated list of step numbers to skip."""
    if not skip_str:
        return set()
    try:
        return {int(s.strip()) for s in skip_str.split(",")}
    except ValueError:
        logger.warning("Invalid skip-steps format: {}. Ignoring.", skip_str)
        return set()


def main() -> int:
    """Main migration function."""
    parser = argparse.ArgumentParser(
        description="Unified migration script for Neo4j schema consolidation."
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
        "--skip-steps",
        type=str,
        help="Comma-separated list of step numbers to skip (e.g., '1,2,3')",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging.",
    )
    args = parser.parse_args()

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

    skip_steps = parse_skip_steps(args.skip_steps)

    if not args.dry_run and not args.yes:
        logger.warning("This will modify your Neo4j database.")
        logger.warning("Recommended: Create a backup first!")
        logger.warning("Press Ctrl+C to cancel.")
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

    success_count = 0
    total_steps = 6

    try:
        # Step 1: Organization Migration
        if 1 not in skip_steps:
            logger.info("\n" + "=" * 70)
            logger.info("STEP 1: Organization Migration")
            logger.info("=" * 70)
            if run_organization_migration(driver, args.dry_run):
                success_count += 1
        else:
            logger.info("Skipping Step 1: Organization Migration")

        # Step 2: Individual Migration
        if 2 not in skip_steps:
            logger.info("\n" + "=" * 70)
            logger.info("STEP 2: Individual Migration")
            logger.info("=" * 70)
            if run_individual_migration(driver, args.dry_run):
                success_count += 1
        else:
            logger.info("Skipping Step 2: Individual Migration")

        # Step 3: FinancialTransaction Migration
        if 3 not in skip_steps:
            logger.info("\n" + "=" * 70)
            logger.info("STEP 3: FinancialTransaction Migration")
            logger.info("=" * 70)
            if run_financial_transaction_migration(driver, args.dry_run):
                success_count += 1
        else:
            logger.info("Skipping Step 3: FinancialTransaction Migration")

        # Step 4: Participated_in Unification
        if 4 not in skip_steps:
            logger.info("\n" + "=" * 70)
            logger.info("STEP 4: Participated_in Relationship Unification")
            logger.info("=" * 70)
            if run_participated_in_migration(driver, args.dry_run):
                success_count += 1
        else:
            logger.info("Skipping Step 4: Participated_in Unification")

        # Step 5: TransitionProfile Consolidation
        if 5 not in skip_steps:
            logger.info("\n" + "=" * 70)
            logger.info("STEP 5: TransitionProfile Consolidation")
            logger.info("=" * 70)
            if run_transition_profile_migration(driver, args.dry_run):
                success_count += 1
        else:
            logger.info("Skipping Step 5: TransitionProfile Consolidation")

        # Step 6: Relationship Consolidation
        if 6 not in skip_steps:
            logger.info("\n" + "=" * 70)
            logger.info("STEP 6: Relationship Consolidation")
            logger.info("=" * 70)
            if run_relationship_consolidation(driver, args.dry_run):
                success_count += 1
        else:
            logger.info("Skipping Step 6: Relationship Consolidation")

        # Summary
        logger.info("\n" + "=" * 70)
        logger.info("MIGRATION SUMMARY")
        logger.info("=" * 70)
        logger.info("Steps completed: {}/{}", success_count, total_steps - len(skip_steps))
        logger.info("Steps skipped: {}", len(skip_steps))

        if success_count == (total_steps - len(skip_steps)):
            logger.info("✓ All migrations completed successfully!")
            return 0
        else:
            logger.warning("⚠ Some migrations failed. Review the logs above.")
            return 1

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

