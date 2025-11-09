#!/usr/bin/env python3
"""
sbir-etl/scripts/neo4j/apply_schema.py

Minimal scaffold to apply Neo4j schema artifacts (indexes/constraints) in an idempotent
way for the SBIR ETL project.

This script is intentionally conservative:
 - It attempts to create constraints/indexes and tolerates errors if they already exist.
 - It supports a dry-run mode to print planned statements without executing them.
 - Connection details are read from environment variables:
     NEO4J_URI (e.g. bolt://neo4j:7687)
     NEO4J_USER
     NEO4J_PASSWORD

Usage:
    python sbir-etl/scripts/neo4j/apply_schema.py [--dry-run] [--yes]

Notes:
 - This is a scaffold and may need adjustments for specific Neo4j server versions and
   syntax differences. Review the statements in `SCHEMA_STATEMENTS` and adjust to match
   your Neo4j version (CREATE CONSTRAINT/INDEX syntax evolved across versions).
"""

from __future__ import annotations

import argparse
import os
import sys

from loguru import logger


try:
    from neo4j import GraphDatabase
    from neo4j.exceptions import Neo4jError
except Exception:  # pragma: no cover - graceful fallback if dependency missing
    GraphDatabase = None
    Neo4jError = Exception  # type: ignore


# Minimal list of schema statements that are useful for the project.
# Review and adapt these statements to match your Neo4j version's supported syntax.
# We use relatively standard "IF NOT EXISTS" where available; if your Neo4j version
# doesn't support it, the script will attempt the statement and ignore "already exists" errors.
SCHEMA_STATEMENTS: list[str] = [
    # Example unique constraint on Company by UEI (adapt label and property as needed)
    # Modern Neo4j (4.4+) syntax:
    # "CREATE CONSTRAINT IF NOT EXISTS FOR (c:Company) REQUIRE c.uei IS UNIQUE",
    # Older Neo4j (3.x) syntax would be different; adapt as needed.
    "CREATE CONSTRAINT IF NOT EXISTS FOR (c:Company) REQUIRE c.uei IS UNIQUE",
    # Unique constraint on award id if present in domain
    "CREATE CONSTRAINT IF NOT EXISTS FOR (a:Award) REQUIRE a.award_id IS UNIQUE",
    # Example index for frequently queried property (e.g., company name)
    "CREATE INDEX IF NOT EXISTS FOR (c:Company) ON (c.name)",
    # Add any additional constraints/indexes your schema requires here
]


def get_env_variable(name: str, default: str | None = None) -> str | None:
    val = os.getenv(name, default)
    if val is None:
        logger.debug("Environment variable %s is not set and no default provided", name)
    return val


def connect(uri: str, user: str, password: str):
    if GraphDatabase is None:
        raise RuntimeError(
            "neo4j python driver not available. Install 'neo4j' package (pip install neo4j)."
        )
    logger.debug("Creating Neo4j driver for URI=%s user=%s", uri, user)
    driver = GraphDatabase.driver(uri, auth=(user, password))
    return driver


def run_statements(driver, statements: list[str], dry_run: bool = False) -> int:
    """
    Execute a list of Cypher statements using a write transaction.
    Returns the number of statements successfully applied (best-effort).
    """
    if dry_run:
        logger.info("Dry-run mode: the following statements would be executed:")
        for s in statements:
            print(s)
        return 0

    applied = 0
    with driver.session() as session:
        for stmt in statements:
            try:
                logger.info("Executing schema statement:\n%s", stmt)
                # run in a write transaction so server-side planning/locking is handled properly
                result = session.write_transaction(lambda tx, q: tx.run(q), stmt)
                # consume result to ensure execution and potential server-side errors surface
                try:
                    # Some statements return no rows; iterating will be a no-op
                    _ = list(result)
                except Exception:
                    # ignore iteration errors (not critical)
                    pass
                applied += 1
            except Neo4jError as e:
                # If the error indicates the constraint/index already exists, skip; otherwise log and continue.
                msg = str(e)
                logger.warning("Neo4jError while executing statement: %s", msg)
                # Heuristics: server error messages for "already exists" differ by version;
                # do not abort on such errors.
                lowered = msg.lower()
                if (
                    "already exists" in lowered
                    or "already an index" in lowered
                    or "exists with name" in lowered
                ):
                    logger.info("Schema artifact already exists; continuing to next statement.")
                    continue
                else:
                    logger.error("Failed to apply statement. Error: %s", msg)
                    # Continue to next statement rather than aborting entirely
                    continue
            except Exception as e:  # pragma: no cover - defensive
                logger.exception("Unexpected exception while applying schema: %s", e)
                continue
    return applied


def parse_args():
    parser = argparse.ArgumentParser(
        description="Apply Neo4j schema (indexes/constraints) for SBIR ETL."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print schema statements without executing them.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Assume yes for any interactive prompts (not used in minimal scaffold).",
    )
    parser.add_argument(
        "--statements-file",
        type=str,
        default="",
        help="Optional path to a file containing additional Cypher statements (one per line) to apply.",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging.",
    )
    return parser.parse_args()


def load_statements_from_file(path: str) -> list[str]:
    try:
        with open(path, encoding="utf-8") as fh:
            lines = [
                line.strip() for line in fh if line.strip() and not line.strip().startswith("#")
            ]
        logger.info("Loaded %d statements from %s", len(lines), path)
        return lines
    except Exception as e:
        logger.error("Failed to load statements from %s: %s", path, e)
        return []


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )

    # Resolve connection args from environment
    uri = get_env_variable("NEO4J_URI", "bolt://neo4j:7687")
    user = get_env_variable("NEO4J_USER", "neo4j")
    password = get_env_variable("NEO4J_PASSWORD", None)

    if not password and not args.dry_run:
        logger.error(
            "NEO4J_PASSWORD is not set in environment. For safety, set it or run with --dry-run."
        )
        return 2

    # Build final statements list; allow extending via file
    statements = list(SCHEMA_STATEMENTS)
    if args.statements_file:
        statements += load_statements_from_file(args.statements_file)

    if not statements:
        logger.info("No schema statements to apply; exiting.")
        return 0

    if args.dry_run:
        logger.info("Dry-run: listing planned schema statements")
        for s in statements:
            print(s)
        return 0

    try:
        driver = connect(uri, user, password)  # may raise
    except Exception as exc:  # pragma: no cover - connection error path
        logger.exception("Failed to create Neo4j driver: %s", exc)
        return 3

    try:
        applied = run_statements(driver, statements, dry_run=args.dry_run)
        logger.info(
            "Schema apply completed: attempted %d statements, applied (or attempted) %d",
            len(statements),
            applied,
        )
    finally:
        try:
            driver.close()
        except Exception:
            pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
