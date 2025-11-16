#!/usr/bin/env python3
"""Clear all data from Neo4j database.

WARNING: This will delete ALL nodes and relationships in the database.
This is irreversible!

Usage:
    python scripts/neo4j/clear_database.py [--yes]

Environment variables:
    NEO4J_URI: Neo4j connection URI (default: bolt://neo4j:7687)
    NEO4J_USER: Neo4j username (default: neo4j)
    NEO4J_PASSWORD: Neo4j password (required)
    NEO4J_DATABASE: Neo4j database name (default: neo4j)
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Any

from loguru import logger

# Load environment variables from .env file if it exists
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    from neo4j import GraphDatabase
except ImportError:
    GraphDatabase = None


def get_env_variable(name: str, default: str | None = None) -> str | None:
    """Get environment variable with optional default."""
    val = os.getenv(name, default)
    if val is None:
        logger.debug("Environment variable {} is not set and no default provided", name)
    return val


def connect(uri: str, user: str, password: str) -> Any:
    """Create Neo4j driver connection."""
    if GraphDatabase is None:
        raise RuntimeError(
            "neo4j python driver not available. Install 'neo4j' package (pip install neo4j)."
        )
    logger.info("Connecting to Neo4j at {} as user {}", uri, user)
    driver = GraphDatabase.driver(uri, auth=(user, password))  # type: ignore[misc]
    return driver


def clear_database(driver: Any, database: str = "neo4j", dry_run: bool = False) -> None:
    """Delete all nodes and relationships from Neo4j database.
    
    Args:
        driver: Neo4j driver
        database: Database name
        dry_run: If True, don't execute queries
    """
    if dry_run:
        logger.warning("DRY RUN: Would execute: MATCH (n) DETACH DELETE n")
        return
    
    logger.warning("=" * 60)
    logger.warning("WARNING: This will delete ALL nodes and relationships!")
    logger.warning("=" * 60)
    
    with driver.session(database=database) as session:
        # Count nodes before deletion
        count_result = session.run("MATCH (n) RETURN count(n) as total")
        count_record = count_result.single()
        total_nodes = count_record["total"] if count_record else 0
        
        logger.info("Found {} nodes to delete", total_nodes)
        
        if total_nodes == 0:
            logger.info("Database is already empty")
            return
        
        # Delete all nodes and relationships
        logger.info("Deleting all nodes and relationships...")
        delete_result = session.run("MATCH (n) DETACH DELETE n RETURN count(n) as deleted")
        delete_record = delete_result.single()
        deleted_count = delete_record["deleted"] if delete_record else 0
        
        logger.info("✓ Deleted {} nodes and all relationships", deleted_count)
        
        # Verify deletion
        verify_result = session.run("MATCH (n) RETURN count(n) as remaining")
        verify_record = verify_result.single()
        remaining = verify_record["remaining"] if verify_record else 0
        
        if remaining == 0:
            logger.info("✓ Database cleared successfully")
        else:
            logger.warning("⚠ Warning: {} nodes still remain", remaining)


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Clear all data from Neo4j database."
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip confirmation prompts.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be deleted without executing.",
    )
    parser.add_argument(
        "--database",
        type=str,
        default=None,
        help="Database name (default: from NEO4J_DATABASE env var or 'neo4j').",
    )
    return parser.parse_args()


def main() -> int:
    """Main function."""
    args = parse_args()

    # Get Neo4j connection details
    uri = get_env_variable("NEO4J_URI", "bolt://neo4j:7687") or "bolt://neo4j:7687"
    user = get_env_variable("NEO4J_USER", "neo4j") or "neo4j"
    password = get_env_variable("NEO4J_PASSWORD", None)
    database = args.database or get_env_variable("NEO4J_DATABASE", "neo4j") or "neo4j"

    if not password and not args.dry_run:
        logger.error("NEO4J_PASSWORD is not set. Set it or run with --dry-run.")
        return 1

    if not args.dry_run and not args.yes:
        logger.error("=" * 60)
        logger.error("WARNING: This will DELETE ALL DATA from Neo4j database '{}'!", database)
        logger.error("This action is IRREVERSIBLE!")
        logger.error("=" * 60)
        try:
            response = input(f"Type 'DELETE {database}' to confirm: ")
            if response != f"DELETE {database}":
                logger.info("Operation cancelled.")
                return 0
        except KeyboardInterrupt:
            logger.info("Operation cancelled.")
            return 0

    try:
        driver = connect(uri, user, password or "")
    except Exception as e:
        logger.exception("Failed to connect to Neo4j: {}", e)
        return 1

    try:
        clear_database(driver, database=database, dry_run=args.dry_run)
        logger.info("✓ Database clearing completed")
        return 0

    except Exception as e:
        logger.exception("Failed to clear database: {}", e)
        return 1

    finally:
        try:
            driver.close()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())

