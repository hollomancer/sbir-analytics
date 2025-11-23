#!/usr/bin/env python3
"""CLI for running Neo4j migrations."""

import argparse
import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from neo4j import GraphDatabase

from migrations.runner import MigrationRunner


def main():
    parser = argparse.ArgumentParser(description="Neo4j schema migration tool")
    parser.add_argument(
        "command",
        choices=["upgrade", "downgrade", "current", "history"],
        help="Migration command",
    )
    parser.add_argument("--target", type=str, help="Target version (for upgrade/downgrade)")
    parser.add_argument("--dry-run", action="store_true", help="Dry run mode")

    args = parser.parse_args()

    # Get connection from environment
    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD")

    if not password:
        print("Error: NEO4J_PASSWORD not set")
        sys.exit(1)

    driver = GraphDatabase.driver(uri, auth=(user, password))
    runner = MigrationRunner(driver)

    try:
        if args.command == "upgrade":
            runner.upgrade(target_version=args.target, dry_run=args.dry_run)
        elif args.command == "downgrade":
            if not args.target:
                print("Error: --target required for downgrade")
                sys.exit(1)
            runner.downgrade(target_version=args.target, dry_run=args.dry_run)
        elif args.command == "current":
            print(f"Current version: {runner.current_version()}")
        elif args.command == "history":
            history = runner.history()
            for mig in history:
                status = "✓" if mig["applied"] else " "
                print(f"{status} {mig['version']}: {mig['description']}")
    finally:
        driver.close()


if __name__ == "__main__":
    main()
