#!/usr/bin/env python3
"""Migration script to consolidate Researcher and PatentEntity (INDIVIDUAL) into unified Individual nodes.

This script:
1. Migrates Researcher nodes → Individual (individual_type: "RESEARCHER")
2. Migrates PatentEntity nodes (entity_category: "INDIVIDUAL") → Individual, merging with existing Individuals
3. Updates all relationships to point to Individual nodes

Usage:
    python scripts/migration/unified_individual_migration.py [--dry-run] [--yes]

Environment variables:
    NEO4J_URI: Neo4j connection URI (default: bolt://neo4j:7687)
    NEO4J_USER: Neo4j username (default: neo4j)
    NEO4J_PASSWORD: Neo4j password (required)
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from typing import Any

from loguru import logger

try:
    from neo4j import GraphDatabase
    from neo4j.exceptions import Neo4jError
except ImportError:
    GraphDatabase = None
    Neo4jError = Exception

# Batch size for processing nodes (reduced to 500 for better timeout handling with large datasets)
BATCH_SIZE = 500


def execute_batch_with_retry(
    session, query: str, params: dict[str, Any], max_retries: int = 3, batch_num: int = 0, total_batches: int = 0
) -> Any:
    """Execute a batch query with retry logic for connection timeouts.
    
    Args:
        session: Neo4j session
        query: Cypher query to execute
        params: Query parameters
        max_retries: Maximum retry attempts
        batch_num: Batch number for logging
        total_batches: Total batches for logging
        
    Returns:
        Query result
        
    Raises:
        Exception: If query fails after all retries
    """
    import time
    
    for attempt in range(max_retries):
        try:
            result = session.run(query, **params)
            return result
        except Exception as e:
            error_str = str(e).lower()
            is_timeout = "timeout" in error_str or "SessionExpired" in str(type(e).__name__)
            if attempt < max_retries - 1 and is_timeout:
                wait_seconds = 2 ** attempt
                logger.warning(
                    "Batch {}/{} failed (attempt {}/{}): {}. Retrying in {}s...",
                    batch_num,
                    total_batches,
                    attempt + 1,
                    max_retries,
                    e,
                    wait_seconds,
                )
                time.sleep(wait_seconds)
            else:
                logger.error(
                    "Batch {}/{} failed after {} attempts: {}",
                    batch_num,
                    total_batches,
                    max_retries,
                    e,
                )
                raise


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


def migrate_researchers_to_individuals(driver, dry_run: bool = False, batch_size: int = BATCH_SIZE) -> int:
    """Migrate Researcher nodes to Individual nodes in batches.

    Args:
        driver: Neo4j driver
        dry_run: If True, don't execute queries
        batch_size: Number of nodes to process per batch

    Returns:
        Number of individuals created
    """
    logger.info("Step 1: Migrating Researcher nodes to Individual nodes")

    count_query = "MATCH (r:Researcher) RETURN count(r) as total"

    if dry_run:
        logger.info("DRY RUN: Would migrate Researcher nodes in batches of {}", batch_size)
        return 0

    with driver.session(default_access_mode="WRITE") as session:
        # Get total count
        count_result = session.run(count_query)
        total_count = count_result.single()["total"]
        logger.info("Found {} Researcher nodes to migrate", total_count)
        
        if total_count == 0:
            logger.info("No Researcher nodes to migrate")
            return 0

        batch_query = """
        MATCH (r:Researcher)
        WITH r SKIP $skip LIMIT $batch_size
        MERGE (i:Individual {individual_id: 'ind_researcher_' + coalesce(r.researcher_id, elementId(r))})
        SET i.name = r.name,
            i.normalized_name = upper(r.name),
            i.email = r.email,
            i.phone = r.phone,
            i.individual_type = 'RESEARCHER',
            i.source_contexts = ['SBIR'],
            i.researcher_id = r.researcher_id,
            i.institution = r.institution,
            i.department = r.department,
            i.title = r.title,
            i.expertise = r.expertise,
            i.bio = r.bio,
            i.website = r.website,
            i.orcid = r.orcid,
            i.linkedin = r.linkedin,
            i.google_scholar = r.google_scholar,
            i.created_at = datetime(),
            i.updated_at = datetime()
        RETURN count(i) as created
        """

        total_created = 0
        skip = 0
        batch_num = 1
        total_batches = (total_count + batch_size - 1) // batch_size

        while skip < total_count:
            logger.info(
                "Processing batch {}/{} (nodes {}-{} of {})...",
                batch_num,
                total_batches,
                skip + 1,
                min(skip + batch_size, total_count),
                total_count,
            )
            
            result = execute_batch_with_retry(
                session, batch_query, {"skip": skip, "batch_size": batch_size},
                batch_num=batch_num, total_batches=total_batches
            )
            single_result = result.single()
            batch_created = single_result["created"] if single_result else 0
            total_created += batch_created
            
            logger.info(
                "✓ Batch {}/{} complete: Created {} Individual nodes (Total: {}/{})",
                batch_num,
                total_batches,
                batch_created,
                total_created,
                total_count,
            )
            
            skip += batch_size
            batch_num += 1

        logger.info("✓ Migration complete: Created {} Individual nodes from Researcher nodes", total_created)
        return total_created


def migrate_patent_individuals_to_individuals(driver, dry_run: bool = False) -> int:
    """Migrate PatentEntity nodes (INDIVIDUAL) to Individual nodes, merging where appropriate.

    Args:
        driver: Neo4j driver
        dry_run: If True, don't execute queries

    Returns:
        Number of individuals created/updated
    """
    logger.info("Step 2: Migrating PatentEntity nodes (INDIVIDUAL) to Individual nodes")

    # First, try to merge with existing Individuals by normalized_name + email or normalized_name + address
    merge_query = """
    MATCH (pe:PatentEntity)
    WHERE pe.entity_category = 'INDIVIDUAL'
      AND EXISTS {
        MATCH (i:Individual)
        WHERE (pe.normalized_name IS NOT NULL AND i.normalized_name = pe.normalized_name
               AND ((pe.email IS NOT NULL AND i.email = pe.email) OR 
                    (pe.address IS NOT NULL AND i.address = pe.address AND pe.city = i.city)))
      }
    MATCH (i:Individual)
    WHERE pe.normalized_name IS NOT NULL AND i.normalized_name = pe.normalized_name
      AND ((pe.email IS NOT NULL AND i.email = pe.email) OR 
           (pe.address IS NOT NULL AND i.address = pe.address AND pe.city = i.city))
    SET i.entity_id = coalesce(i.entity_id, pe.entity_id),
        i.entity_type = coalesce(i.entity_type, pe.entity_type),
        i.address = coalesce(i.address, pe.address),
        i.city = coalesce(i.city, pe.city),
        i.state = coalesce(i.state, pe.state),
        i.postcode = coalesce(i.postcode, pe.postal_code),
        i.country = coalesce(i.country, pe.country, 'US'),
        i.num_assignments_as_assignee = coalesce(i.num_assignments_as_assignee, 0) + coalesce(pe.num_assignments_as_assignee, 0),
        i.num_assignments_as_assignor = coalesce(i.num_assignments_as_assignor, 0) + coalesce(pe.num_assignments_as_assignor, 0),
        i.source_contexts = CASE
            WHEN 'PATENT' IN i.source_contexts THEN i.source_contexts
            ELSE i.source_contexts + 'PATENT'
        END,
        i.individual_type = CASE
            WHEN i.individual_type = 'RESEARCHER' THEN 'RESEARCHER'
            WHEN pe.entity_type = 'ASSIGNEE' THEN 'PATENT_ASSIGNEE'
            WHEN pe.entity_type = 'ASSIGNOR' THEN 'PATENT_ASSIGNOR'
            ELSE 'PATENT_ASSIGNEE'
        END,
        i.updated_at = datetime()
    WITH pe, i
    // Update relationships from PatentEntity to Individual
    MATCH (pe)-[r1:ASSIGNED_TO]->(pa:PatentAssignment)
    MERGE (i)-[r2:ASSIGNED_TO]->(pa)
    SET r2 = properties(r1)
    WITH pe, i
    MATCH (pe)-[r1:ASSIGNED_FROM]->(pa:PatentAssignment)
    MERGE (i)-[r2:ASSIGNED_FROM]->(pa)
    SET r2 = properties(r1)
    RETURN count(DISTINCT i) as merged
    """

    # Then create new Individuals for PatentEntities that don't match
    create_new_query = """
    MATCH (pe:PatentEntity)
    WHERE pe.entity_category = 'INDIVIDUAL'
      AND NOT EXISTS {
        MATCH (i:Individual)
        WHERE (pe.normalized_name IS NOT NULL AND i.normalized_name = pe.normalized_name
               AND ((pe.email IS NOT NULL AND i.email = pe.email) OR 
                    (pe.address IS NOT NULL AND i.address = pe.address AND pe.city = i.city)))
      }
    MERGE (i:Individual {individual_id: 'ind_patent_' + coalesce(pe.entity_id, elementId(pe))})
    SET i.name = pe.name,
        i.normalized_name = coalesce(pe.normalized_name, upper(pe.name)),
        i.address = pe.address,
        i.city = pe.city,
        i.state = pe.state,
        i.postcode = pe.postal_code,
        i.country = coalesce(pe.country, 'US'),
        i.individual_type = CASE pe.entity_type
            WHEN 'ASSIGNEE' THEN 'PATENT_ASSIGNEE'
            WHEN 'ASSIGNOR' THEN 'PATENT_ASSIGNOR'
            ELSE 'PATENT_ASSIGNEE'
        END,
        i.source_contexts = ['PATENT'],
        i.entity_id = pe.entity_id,
        i.entity_type = pe.entity_type,
        i.num_assignments_as_assignee = pe.num_assignments_as_assignee,
        i.num_assignments_as_assignor = pe.num_assignments_as_assignor,
        i.created_at = coalesce(pe.loaded_date, datetime()),
        i.updated_at = datetime()
    WITH pe, i
    // Update relationships from PatentEntity to Individual
    MATCH (pe)-[r1:ASSIGNED_TO]->(pa:PatentAssignment)
    MERGE (i)-[r2:ASSIGNED_TO]->(pa)
    SET r2 = properties(r1)
    WITH pe, i
    MATCH (pe)-[r1:ASSIGNED_FROM]->(pa:PatentAssignment)
    MERGE (i)-[r2:ASSIGNED_FROM]->(pa)
    SET r2 = properties(r1)
    RETURN count(DISTINCT i) as created
    """

    if dry_run:
        logger.info("DRY RUN: Would execute merge query:\n%s", merge_query)
        logger.info("DRY RUN: Would execute create query:\n%s", create_new_query)
        return 0

    with driver.session() as session:
        # Merge with existing Individuals
        result1 = session.run(merge_query)
        merged_count = result1.single()["merged"] if result1.peek() else 0
        logger.info("✓ Merged %d PatentEntity nodes with existing Individuals", merged_count)

        # Create new Individuals
        result2 = session.run(create_new_query)
        created_count = result2.single()["created"] if result2.peek() else 0
        logger.info("✓ Created %d new Individual nodes from PatentEntity nodes", created_count)

        return merged_count + created_count


def update_researcher_relationships(driver, dry_run: bool = False) -> int:
    """Update Researcher relationships to Individual.

    Args:
        driver: Neo4j driver
        dry_run: If True, don't execute queries

    Returns:
        Number of relationships updated
    """
    logger.info("Step 3: Updating Researcher relationships")

    queries = [
        # Update RESEARCHED_BY relationships (Award -> Researcher -> Individual)
        """
        MATCH (a:Award)-[r:RESEARCHED_BY]->(res:Researcher)
        MATCH (i:Individual {researcher_id: res.researcher_id})
        MERGE (a)-[r2:RESEARCHED_BY]->(i)
        SET r2 = properties(r)
        DELETE r
        RETURN count(r2) as updated
        """,
        # Update WORKED_ON relationships (Researcher -> Award -> Individual)
        """
        MATCH (res:Researcher)-[r:WORKED_ON]->(a:Award)
        MATCH (i:Individual {researcher_id: res.researcher_id})
        MERGE (i)-[r2:WORKED_ON]->(a)
        SET r2 = properties(r)
        DELETE r
        RETURN count(r2) as updated
        """,
        # Update WORKED_AT relationships (Researcher -> Organization -> Individual)
        """
        MATCH (res:Researcher)-[r:WORKED_AT]->(o:Organization)
        MATCH (i:Individual {researcher_id: res.researcher_id})
        MERGE (i)-[r2:WORKED_AT]->(o)
        SET r2 = properties(r)
        DELETE r
        RETURN count(r2) as updated
        """,
    ]

    if dry_run:
        for query in queries:
            logger.info("DRY RUN: Would execute:\n%s", query)
        return 0

    total_updated = 0
    with driver.session() as session:
        for query in queries:
            result = session.run(query)
            count = result.single()["updated"] if result.peek() else 0
            total_updated += count

    logger.info("✓ Updated %d Researcher relationships", total_updated)
    return total_updated


def create_individual_constraints_and_indexes(driver, dry_run: bool = False) -> None:
    """Create constraints and indexes for Individual nodes.

    Args:
        driver: Neo4j driver
        dry_run: If True, don't execute queries
    """
    logger.info("Step 4: Creating Individual constraints and indexes")

    statements = [
        "CREATE CONSTRAINT IF NOT EXISTS FOR (i:Individual) REQUIRE i.individual_id IS UNIQUE",
        "CREATE INDEX IF NOT EXISTS FOR (i:Individual) ON (i.name)",
        "CREATE INDEX IF NOT EXISTS FOR (i:Individual) ON (i.normalized_name)",
        "CREATE INDEX IF NOT EXISTS FOR (i:Individual) ON (i.individual_type)",
        "CREATE INDEX IF NOT EXISTS FOR (i:Individual) ON (i.email)",
        "CREATE INDEX IF NOT EXISTS FOR (i:Individual) ON (i.researcher_id)",
        "CREATE INDEX IF NOT EXISTS FOR (i:Individual) ON (i.entity_id)",
    ]

    if dry_run:
        for stmt in statements:
            logger.info("DRY RUN: Would execute:\n%s", stmt)
        return

    with driver.session() as session:
        for stmt in statements:
            try:
                session.run(stmt)
                logger.info("✓ Created constraint/index: %s", stmt.split()[2:5])
            except Neo4jError as e:
                if "already exists" in str(e).lower():
                    logger.info("Constraint/index already exists, skipping")
                else:
                    logger.warning("Failed to create constraint/index: %s", e)


def validate_migration(driver) -> dict[str, Any]:
    """Run validation queries to verify migration completeness.

    Args:
        driver: Neo4j driver

    Returns:
        Dictionary with validation results
    """
    logger.info("Step 5: Validating migration")

    validation_queries = {
        "remaining_researchers": "MATCH (r:Researcher) RETURN count(r) as count",
        "remaining_patent_individuals": "MATCH (pe:PatentEntity) WHERE pe.entity_category = 'INDIVIDUAL' RETURN count(pe) as count",
        "individuals_by_type": """
            MATCH (i:Individual)
            RETURN i.individual_type, count(*) as count
            ORDER BY count DESC
        """,
        "researched_by_relationships": "MATCH (a:Award)-[r:RESEARCHED_BY]->(i:Individual) RETURN count(r) as count",
        "worked_on_relationships": "MATCH (i:Individual)-[r:WORKED_ON]->(a:Award) RETURN count(r) as count",
        "worked_at_relationships": "MATCH (i:Individual)-[r:WORKED_AT]->(o:Organization) RETURN count(r) as count",
    }

    results = {}
    with driver.session() as session:
        for key, query in validation_queries.items():
            try:
                result = session.run(query)
                if key == "individuals_by_type":
                    records = [dict(record) for record in result]
                    results[key] = records
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

    logger.info("\nRemaining legacy nodes:")
    logger.info("  Researchers: %s", results.get("remaining_researchers", "N/A"))
    logger.info("  PatentEntities (individuals): %s", results.get("remaining_patent_individuals", "N/A"))

    logger.info("\nIndividuals by type:")
    ind_types = results.get("individuals_by_type", [])
    for ind_type in ind_types:
        logger.info("  %s: %d", ind_type.get("i.individual_type", "UNKNOWN"), ind_type.get("count", 0))

    logger.info("\nRelationships:")
    logger.info("  RESEARCHED_BY (Award → Individual): %s", results.get("researched_by_relationships", "N/A"))
    logger.info("  WORKED_ON (Individual → Award): %s", results.get("worked_on_relationships", "N/A"))
    logger.info("  WORKED_AT (Individual → Organization): %s", results.get("worked_at_relationships", "N/A"))

    logger.info("\n" + "=" * 60)


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Migrate Researcher and PatentEntity (INDIVIDUAL) to unified Individual nodes."
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
        migrate_researchers_to_individuals(driver, dry_run=args.dry_run)
        migrate_patent_individuals_to_individuals(driver, dry_run=args.dry_run)
        update_researcher_relationships(driver, dry_run=args.dry_run)
        create_individual_constraints_and_indexes(driver, dry_run=args.dry_run)

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

