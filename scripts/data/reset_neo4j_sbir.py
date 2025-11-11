#!/usr/bin/env python3
"""Reset Neo4j database by deleting SBIR-related nodes before loading."""

from __future__ import annotations

import argparse
import sys
from typing import Any

from neo4j import GraphDatabase

from src.config.loader import get_config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Reset Neo4j database for SBIR smoke tests.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be deleted without actually deleting.",
    )
    return parser.parse_args()


def reset_neo4j(uri: str, username: str, password: str, database: str, dry_run: bool = False) -> int:
    """Delete SBIR-related nodes and relationships from Neo4j."""
    driver = GraphDatabase.driver(uri, auth=(username, password))

    try:
        with driver.session(database=database) as session:
            if dry_run:
                # Count what would be deleted
                award_count = session.run("MATCH (a:Award) RETURN count(a) as count").single()["count"]
                company_count = session.run("MATCH (c:Company) RETURN count(c) as count").single()["count"]
                rel_count = session.run(
                    "MATCH (a:Award)-[r:AWARDS]->(c:Company) RETURN count(r) as count"
                ).single()["count"]
                print(f"Would delete: {award_count} Awards, {company_count} Companies, {rel_count} AWARDS relationships")
                return 0

            # Delete AWARDS relationships first
            rel_result = session.run(
                """
                MATCH (a:Award)-[r:AWARDS]->(c:Company)
                DELETE r
                RETURN count(r) as deleted
                """
            )
            rel_deleted = rel_result.single()["deleted"]
            print(f"Deleted {rel_deleted} AWARDS relationships")

            # Delete Award nodes
            award_result = session.run(
                """
                MATCH (a:Award)
                DELETE a
                RETURN count(a) as deleted
                """
            )
            awards_deleted = award_result.single()["deleted"]
            print(f"Deleted {awards_deleted} Award nodes")

            # Delete Company nodes (only those not connected to other entities)
            # Note: We're being conservative - only delete Companies that aren't connected
            # to Patents, Transitions, etc. In a full reset, you might want to delete all Companies.
            company_result = session.run(
                """
                MATCH (c:Company)
                WHERE NOT (c)<-[:AWARDS]-()
                DELETE c
                RETURN count(c) as deleted
                """
            )
            companies_deleted = company_result.single()["deleted"]
            print(f"Deleted {companies_deleted} Company nodes (unconnected)")

            print("Neo4j reset complete")
            return 0

    except Exception as e:
        print(f"Error resetting Neo4j: {e}", file=sys.stderr)
        return 1
    finally:
        driver.close()


def main() -> int:
    args = parse_args()

    config = get_config()
    neo4j_config = config.neo4j

    return reset_neo4j(
        uri=neo4j_config.uri,
        username=neo4j_config.username,
        password=neo4j_config.password,
        database=neo4j_config.database,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    raise SystemExit(main())

