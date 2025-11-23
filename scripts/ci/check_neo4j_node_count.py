#!/usr/bin/env python3
"""Check Neo4j Aura Free node count before tests."""

import os
import sys
from neo4j import GraphDatabase


def main():
    """Check and report Neo4j node count."""
    uri = os.environ.get("NEO4J_URI", "")
    user = os.environ.get("NEO4J_USERNAME", "neo4j")
    password = os.environ.get("NEO4J_PASSWORD", "")

    if not uri or not password:
        print("⚠️  Skipping node count check - no Aura credentials")
        sys.exit(0)

    try:
        driver = GraphDatabase.driver(uri, auth=(user, password))
        with driver.session() as session:
            result = session.run("MATCH (n) RETURN count(n) as count")
            count = result.single()["count"]
            print(f"📊 Current node count: {count:,}")
            if count > 95000:
                print(f"⚠️  WARNING: Node count ({count:,}) approaching Aura Free limit (100,000)")
                print("   Consider cleaning up test data: MATCH (n) DETACH DELETE n")
        driver.close()
    except Exception as e:
        print(f"Note: Could not check node count: {e}")


if __name__ == "__main__":
    main()
