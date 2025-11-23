#!/usr/bin/env python3
"""Verify connection to Neo4j Aura Free."""

import os
import sys
from neo4j import GraphDatabase


def main():
    """Test connection to Neo4j Aura Free."""
    uri = os.environ.get("NEO4J_URI", "")
    user = os.environ.get("NEO4J_USERNAME", "neo4j")
    password = os.environ.get("NEO4J_PASSWORD", "")

    if not uri or not password:
        print("⚠️  Warning: Neo4j Aura test credentials not configured in GitHub secrets")
        print(
            "   Please configure NEO4J_AURA_TEST_URI, NEO4J_AURA_TEST_USERNAME, NEO4J_AURA_TEST_PASSWORD"
        )
        print("   See docs/CI_AURA_SETUP.md for setup instructions")
        sys.exit(0)  # Don't fail the build, just warn

    try:
        print(f"Connecting to: {uri}")
        driver = GraphDatabase.driver(uri, auth=(user, password))
        with driver.session() as session:
            result = session.run("RETURN 1 as test")
            value = result.single()["test"]
            assert value == 1
        driver.close()
        print("✅ Neo4j Aura Free connection successful!")
    except Exception as e:
        print(f"❌ Neo4j Aura Free connection failed: {e}")
        print("   Tip: Check if your Aura instance is paused at console.neo4j.io")
        raise


if __name__ == "__main__":
    main()
