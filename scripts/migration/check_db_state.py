#!/usr/bin/env python3
"""Quick script to check what node types exist in the database."""

import os
import sys

from loguru import logger

try:
    from neo4j import GraphDatabase
except ImportError:
    logger.error("neo4j package not available. Install with: pip install neo4j")
    sys.exit(1)


def main():
    uri = os.getenv("NEO4J_URI", "bolt://neo4j:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD")

    if not password:
        logger.error("NEO4J_PASSWORD not set")
        sys.exit(1)

    driver = GraphDatabase.driver(uri, auth=(user, password))

    try:
        with driver.session() as session:
            # Check for old node types
            old_nodes = session.run(
                """
                MATCH (n)
                WHERE n:Company OR n:Award OR n:Contract OR n:PatentEntity 
                   OR n:ResearchInstitution OR n:Researcher
                RETURN labels(n)[0] as label, count(*) as count 
                ORDER BY label
                """
            ).data()

            # Check for new node types
            new_nodes = session.run(
                """
                MATCH (n)
                WHERE n:Organization OR n:Individual OR n:FinancialTransaction
                RETURN labels(n)[0] as label, count(*) as count 
                ORDER BY label
                """
            ).data()

            logger.info("=== OLD NODE TYPES ===")
            if old_nodes:
                for r in old_nodes:
                    logger.info("{}: {}", r["label"], r["count"])
            else:
                logger.info("None found")

            logger.info("\n=== NEW NODE TYPES ===")
            if new_nodes:
                for r in new_nodes:
                    logger.info("{}: {}", r["label"], r["count"])
            else:
                logger.info("None found")

            # Check relationships
            logger.info("\n=== TOP RELATIONSHIPS ===")
            rels = (
                session.run(
                    """
                    MATCH ()-[r]->()
                    RETURN type(r) as rel_type, count(*) as count 
                    ORDER BY count DESC 
                    LIMIT 15
                    """
                ).data()
            )
            for r in rels:
                logger.info("{}: {}", r["rel_type"], r["count"])

    finally:
        driver.close()


if __name__ == "__main__":
    main()

