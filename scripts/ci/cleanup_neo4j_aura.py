#!/usr/bin/env python3
"""Clean up Neo4j Aura Free test data."""
import os
import sys
from neo4j import GraphDatabase


def main():
    """Clean up test data from Neo4j Aura Free."""
    uri = os.environ.get("NEO4J_URI", "")
    user = os.environ.get("NEO4J_USERNAME", "neo4j")
    password = os.environ.get("NEO4J_PASSWORD", "")
    
    if not uri or not password:
        print("⚠️  Skipping cleanup - no Aura credentials")
        sys.exit(0)
    
    try:
        driver = GraphDatabase.driver(uri, auth=(user, password))
        
        # Get count before cleanup
        with driver.session() as session:
            before = session.run("MATCH (n) RETURN count(n) as count").single()["count"]
            print(f"📊 Nodes before cleanup: {before:,}")
        
        # Delete test data (with batching for safety)
        with driver.session() as session:
            # Delete in batches to avoid memory issues
            batch_size = 10000
            total_deleted = 0
            while True:
                result = session.run(f"""
                    MATCH (n)
                    WITH n LIMIT {batch_size}
                    DETACH DELETE n
                    RETURN count(n) as deleted
                """)
                deleted = result.single()["deleted"]
                total_deleted += deleted
                if deleted == 0:
                    break
                print(f"  Deleted {deleted:,} nodes (total: {total_deleted:,})")
        
        # Verify cleanup
        with driver.session() as session:
            after = session.run("MATCH (n) RETURN count(n) as count").single()["count"]
            print(f"✅ Cleanup complete! Nodes after: {after:,}")
        
        driver.close()
    except Exception as e:
        print(f"⚠️  Cleanup warning: {e}")
        print("   You may need to manually clean up: MATCH (n) DETACH DELETE n")
        # Don't fail the workflow on cleanup errors
        sys.exit(0)


if __name__ == '__main__':
    main()

