#!/usr/bin/env python3
"""Migration script to consolidate Company, PatentEntity, ResearchInstitution into unified Organization nodes.

This script:
1. Migrates Company nodes → Organization (organization_type: "COMPANY")
2. Migrates PatentEntity nodes (non-individuals) → Organization, merging with existing Organizations
3. Migrates ResearchInstitution nodes → Organization
4. Creates Agency Organizations from Award/Contract agency data
5. Updates all relationships to point to Organization nodes
6. Creates FUNDED_BY and AWARDED_BY relationships for agencies

Usage:
    python scripts/migration/unified_organization_migration.py [--dry-run] [--yes]

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


def migrate_companies_to_organizations(driver, dry_run: bool = False) -> int:
    """Migrate Company nodes to Organization nodes.

    Args:
        driver: Neo4j driver
        dry_run: If True, don't execute queries

    Returns:
        Number of organizations created
    """
    logger.info("Step 1: Migrating Company nodes to Organization nodes")

    query = """
    MATCH (c:Company)
    WITH c
    MERGE (o:Organization {organization_id: 'org_company_' + coalesce(c.company_id, c.uei, c.duns, id(c))})
    SET o.name = c.name,
        o.normalized_name = coalesce(c.normalized_name, upper(c.name)),
        o.address = c.address_line_1,
        o.city = c.city,
        o.state = c.state,
        o.postcode = c.zip_code,
        o.country = coalesce(c.country, 'US'),
        o.organization_type = 'COMPANY',
        o.source_contexts = ['SBIR'],
        o.uei = c.uei,
        o.cage = c.cage,
        o.duns = c.duns,
        o.business_size = c.business_size,
        o.company_id = c.company_id,
        o.naics_primary = c.naics_primary,
        o.created_at = coalesce(c.created_at, datetime()),
        o.updated_at = datetime()
    RETURN count(o) as created
    """

    if dry_run:
        logger.info("DRY RUN: Would execute:\n%s", query)
        return 0

    # Use a session with extended timeout for long-running migration queries
    # The driver is already configured with extended timeouts in unified_schema_migration.py
    with driver.session(default_access_mode="WRITE") as session:
        # Execute query - timeout is handled at driver level
        result = session.run(query)
        count = result.single()["created"]
        logger.info("✓ Created %d Organization nodes from Company nodes", count)
        return count


def migrate_patent_entities_to_organizations(driver, dry_run: bool = False) -> int:
    """Migrate PatentEntity nodes (non-individuals) to Organization nodes, merging where appropriate.

    Args:
        driver: Neo4j driver
        dry_run: If True, don't execute queries

    Returns:
        Number of organizations created/updated
    """
    logger.info("Step 2: Migrating PatentEntity nodes (non-individuals) to Organization nodes")

    # First, try to merge with existing Organizations by UEI
    merge_by_uei_query = """
    MATCH (pe:PatentEntity)
    WHERE pe.entity_category IN ['COMPANY', 'UNIVERSITY', 'GOVERNMENT']
      AND pe.sbir_uei IS NOT NULL
      AND EXISTS {
        MATCH (o:Organization {uei: pe.sbir_uei})
      }
    MATCH (o:Organization {uei: pe.sbir_uei})
    SET o.entity_id = coalesce(o.entity_id, pe.entity_id),
        o.entity_category = coalesce(o.entity_category, pe.entity_category),
        o.num_assignments_as_assignee = coalesce(o.num_assignments_as_assignee, 0) + coalesce(pe.num_assignments_as_assignee, 0),
        o.num_assignments_as_assignor = coalesce(o.num_assignments_as_assignor, 0) + coalesce(pe.num_assignments_as_assignor, 0),
        o.num_patents_owned = coalesce(o.num_patents_owned, 0) + coalesce(pe.num_patents_owned, 0),
        o.is_sbir_company = coalesce(o.is_sbir_company, pe.is_sbir_company, false),
        o.source_contexts = CASE
            WHEN 'PATENT' IN o.source_contexts THEN o.source_contexts
            ELSE o.source_contexts + 'PATENT'
        END,
        o.updated_at = datetime()
    WITH pe, o
    // Update relationships from PatentEntity to Organization
    MATCH (pe)-[r1:ASSIGNED_TO]->(pa:PatentAssignment)
    MERGE (o)-[r2:ASSIGNED_TO]->(pa)
    SET r2 = properties(r1)
    WITH pe, o
    MATCH (pe)-[r1:ASSIGNED_FROM]->(pa:PatentAssignment)
    MERGE (o)-[r2:ASSIGNED_FROM]->(pa)
    SET r2 = properties(r1)
    RETURN count(DISTINCT o) as merged
    """

    # Then create new Organizations for PatentEntities that don't match
    create_new_query = """
    MATCH (pe:PatentEntity)
    WHERE pe.entity_category IN ['COMPANY', 'UNIVERSITY', 'GOVERNMENT']
      AND NOT EXISTS {
        MATCH (o:Organization)
        WHERE (pe.sbir_uei IS NOT NULL AND o.uei = pe.sbir_uei)
           OR (pe.normalized_name IS NOT NULL AND o.normalized_name = pe.normalized_name 
               AND pe.state IS NOT NULL AND o.state = pe.state 
               AND pe.postcode IS NOT NULL AND o.postcode = pe.postcode)
      }
    MERGE (o:Organization {organization_id: 'org_patent_' + coalesce(pe.entity_id, toString(id(pe)))})
    SET o.name = pe.name,
        o.normalized_name = coalesce(pe.normalized_name, upper(pe.name)),
        o.address = pe.address,
        o.city = pe.city,
        o.state = pe.state,
        o.postcode = pe.postcode,
        o.country = coalesce(pe.country, 'US'),
        o.organization_type = CASE pe.entity_category
            WHEN 'UNIVERSITY' THEN 'UNIVERSITY'
            WHEN 'GOVERNMENT' THEN 'GOVERNMENT'
            ELSE 'COMPANY'
        END,
        o.source_contexts = ['PATENT'],
        o.entity_id = pe.entity_id,
        o.entity_category = pe.entity_category,
        o.num_assignments_as_assignee = pe.num_assignments_as_assignee,
        o.num_assignments_as_assignor = pe.num_assignments_as_assignor,
        o.num_patents_owned = pe.num_patents_owned,
        o.is_sbir_company = pe.is_sbir_company,
        o.sbir_uei = pe.sbir_uei,
        o.sbir_company_id = pe.sbir_company_id,
        o.created_at = coalesce(pe.loaded_date, datetime()),
        o.updated_at = datetime()
    WITH pe, o
    // Update relationships from PatentEntity to Organization
    MATCH (pe)-[r1:ASSIGNED_TO]->(pa:PatentAssignment)
    MERGE (o)-[r2:ASSIGNED_TO]->(pa)
    SET r2 = properties(r1)
    WITH pe, o
    MATCH (pe)-[r1:ASSIGNED_FROM]->(pa:PatentAssignment)
    MERGE (o)-[r2:ASSIGNED_FROM]->(pa)
    SET r2 = properties(r1)
    RETURN count(DISTINCT o) as created
    """

    if dry_run:
        logger.info("DRY RUN: Would execute merge query:\n%s", merge_by_uei_query)
        logger.info("DRY RUN: Would execute create query:\n%s", create_new_query)
        return 0

    with driver.session() as session:
        # Merge with existing Organizations
        result1 = session.run(merge_by_uei_query)
        merged_count = result1.single()["merged"] if result1.peek() else 0
        logger.info("✓ Merged %d PatentEntity nodes with existing Organizations", merged_count)

        # Create new Organizations
        result2 = session.run(create_new_query)
        created_count = result2.single()["created"] if result2.peek() else 0
        logger.info("✓ Created %d new Organization nodes from PatentEntity nodes", created_count)

        return merged_count + created_count


def migrate_research_institutions_to_organizations(driver, dry_run: bool = False) -> int:
    """Migrate ResearchInstitution nodes to Organization nodes.

    Args:
        driver: Neo4j driver
        dry_run: If True, don't execute queries

    Returns:
        Number of organizations created/updated
    """
    logger.info("Step 3: Migrating ResearchInstitution nodes to Organization nodes")

    query = """
    MATCH (ri:ResearchInstitution)
    MERGE (o:Organization {organization_id: 'org_research_' + coalesce(ri.name, toString(id(ri)))})
    ON CREATE SET
        o.name = ri.name,
        o.normalized_name = upper(ri.name),
        o.address = ri.address,
        o.city = ri.city,
        o.state = ri.state,
        o.country = 'US',
        o.organization_type = 'UNIVERSITY',
        o.source_contexts = ['RESEARCH'],
        o.created_at = datetime(),
        o.updated_at = datetime()
    ON MATCH SET
        o.source_contexts = CASE
            WHEN 'RESEARCH' IN o.source_contexts THEN o.source_contexts
            ELSE o.source_contexts + 'RESEARCH'
        END,
        o.updated_at = datetime()
    RETURN count(o) as created
    """

    if dry_run:
        logger.info("DRY RUN: Would execute:\n%s", query)
        return 0

    with driver.session() as session:
        result = session.run(query)
        count = result.single()["created"] if result.peek() else 0
        logger.info("✓ Created/updated %d Organization nodes from ResearchInstitution nodes", count)
        return count


def create_agency_organizations(driver, dry_run: bool = False) -> int:
    """Create Agency Organizations from Award and Contract agency data.

    Args:
        driver: Neo4j driver
        dry_run: If True, don't execute queries

    Returns:
        Number of agency organizations created
    """
    logger.info("Step 4: Creating Agency Organizations from Award/Contract data")

    query = """
    // Extract unique agencies from Awards
    MATCH (a:Award)
    WHERE a.agency IS NOT NULL AND a.agency_name IS NOT NULL
    WITH DISTINCT a.agency as agency_code, a.agency_name as agency_name, 
         a.sub_agency as sub_agency_code, a.sub_agency_name as sub_agency_name
    MERGE (o:Organization {organization_id: 'org_agency_' + agency_code + 
           coalesce('_' + sub_agency_code, '')})
    SET o.name = agency_name,
        o.normalized_name = upper(agency_name),
        o.organization_type = 'AGENCY',
        o.source_contexts = ['AGENCY'],
        o.agency_code = agency_code,
        o.agency_name = agency_name,
        o.sub_agency_code = sub_agency_code,
        o.sub_agency_name = sub_agency_name,
        o.created_at = datetime(),
        o.updated_at = datetime()
    WITH o, agency_code, sub_agency_code
    
    // Also handle sub-agencies as separate organizations if they have distinct names
    WHERE sub_agency_code IS NOT NULL AND sub_agency_name IS NOT NULL
    MERGE (so:Organization {organization_id: 'org_agency_' + sub_agency_code})
    SET so.name = sub_agency_name,
        so.normalized_name = upper(sub_agency_name),
        so.organization_type = 'AGENCY',
        so.source_contexts = ['AGENCY'],
        so.agency_code = agency_code,
        so.agency_name = agency_name,
        so.sub_agency_code = sub_agency_code,
        so.sub_agency_name = sub_agency_name,
        so.created_at = datetime(),
        so.updated_at = datetime()
    
    RETURN count(DISTINCT o) + count(DISTINCT so) as created
    """

    if dry_run:
        logger.info("DRY RUN: Would execute:\n%s", query)
        return 0

    with driver.session() as session:
        result = session.run(query)
        count = result.single()["created"] if result.peek() else 0
        logger.info("✓ Created %d Agency Organization nodes", count)
        return count


def update_award_relationships(driver, dry_run: bool = False) -> int:
    """Update AWARDED_TO relationships and create FUNDED_BY relationships.

    Args:
        driver: Neo4j driver
        dry_run: If True, don't execute queries

    Returns:
        Number of relationships updated/created
    """
    logger.info("Step 5: Updating Award relationships")

    # Update AWARDED_TO relationships from Company to Organization
    update_awarded_to_query = """
    MATCH (a:Award)-[r:AWARDED_TO]->(c:Company)
    MATCH (o:Organization {company_id: c.company_id})
    MERGE (a)-[r2:AWARDED_TO]->(o)
    SET r2 = properties(r)
    DELETE r
    RETURN count(r2) as updated
    """

    # Create FUNDED_BY relationships from Award to Agency Organization
    create_funded_by_query = """
    MATCH (a:Award)
    WHERE a.agency IS NOT NULL
    MATCH (o:Organization {organization_type: 'AGENCY', agency_code: a.agency})
    MERGE (a)-[r:FUNDED_BY]->(o)
    SET r.created_at = datetime()
    RETURN count(r) as created
    """

    if dry_run:
        logger.info("DRY RUN: Would execute update query:\n%s", update_awarded_to_query)
        logger.info("DRY RUN: Would execute create query:\n%s", create_funded_by_query)
        return 0

    with driver.session() as session:
        # Update AWARDED_TO
        result1 = session.run(update_awarded_to_query)
        updated_count = result1.single()["updated"] if result1.peek() else 0
        logger.info("✓ Updated %d AWARDED_TO relationships", updated_count)

        # Create FUNDED_BY
        result2 = session.run(create_funded_by_query)
        created_count = result2.single()["created"] if result2.peek() else 0
        logger.info("✓ Created %d FUNDED_BY relationships", created_count)

        return updated_count + created_count


def update_contract_relationships(driver, dry_run: bool = False) -> int:
    """Update AWARDED_CONTRACT relationships and create AWARDED_BY relationships.

    Args:
        driver: Neo4j driver
        dry_run: If True, don't execute queries

    Returns:
        Number of relationships updated/created
    """
    logger.info("Step 6: Updating Contract relationships")

    # Update AWARDED_CONTRACT relationships from Company to Organization
    update_awarded_contract_query = """
    MATCH (c:Company)-[r:AWARDED_CONTRACT]->(contract:Contract)
    MATCH (o:Organization {uei: c.uei, organization_type: 'COMPANY'})
    MERGE (o)-[r2:AWARDED_CONTRACT]->(contract)
    SET r2 = properties(r)
    DELETE r
    RETURN count(r2) as updated
    """

    # Create AWARDED_BY relationships from Contract to Agency Organization
    create_awarded_by_query = """
    MATCH (c:Contract)
    WHERE c.agency IS NOT NULL
    MATCH (o:Organization {organization_type: 'AGENCY', agency_code: c.agency})
    MERGE (c)-[r:AWARDED_BY]->(o)
    SET r.created_at = datetime()
    RETURN count(r) as created
    """

    if dry_run:
        logger.info("DRY RUN: Would execute update query:\n%s", update_awarded_contract_query)
        logger.info("DRY RUN: Would execute create query:\n%s", create_awarded_by_query)
        return 0

    with driver.session() as session:
        # Update AWARDED_CONTRACT
        result1 = session.run(update_awarded_contract_query)
        updated_count = result1.single()["updated"] if result1.peek() else 0
        logger.info("✓ Updated %d AWARDED_CONTRACT relationships", updated_count)

        # Create AWARDED_BY
        result2 = session.run(create_awarded_by_query)
        created_count = result2.single()["created"] if result2.peek() else 0
        logger.info("✓ Created %d AWARDED_BY relationships", created_count)

        return updated_count + created_count


def update_other_relationships(driver, dry_run: bool = False) -> int:
    """Update other relationships (OWNS, SPECIALIZES_IN, ACHIEVED, etc.).

    Args:
        driver: Neo4j driver
        dry_run: If True, don't execute queries

    Returns:
        Number of relationships updated
    """
    logger.info("Step 7: Updating other relationships")

    queries = [
        # Update OWNS relationships
        """
        MATCH (c:Company)-[r:OWNS]->(p:Patent)
        MATCH (o:Organization {uei: c.uei, organization_type: 'COMPANY'})
        MERGE (o)-[r2:OWNS]->(p)
        SET r2 = properties(r)
        DELETE r
        RETURN count(r2) as updated
        """,
        # Update SPECIALIZES_IN relationships
        """
        MATCH (c:Company)-[r:SPECIALIZES_IN]->(cet:CETArea)
        MATCH (o:Organization {uei: c.uei, organization_type: 'COMPANY'})
        MERGE (o)-[r2:SPECIALIZES_IN]->(cet)
        SET r2 = properties(r)
        DELETE r
        RETURN count(r2) as updated
        """,
        # Update ACHIEVED relationships
        """
        MATCH (c:Company)-[r:ACHIEVED]->(tp:TransitionProfile)
        MATCH (o:Organization {uei: c.uei, organization_type: 'COMPANY'})
        MERGE (o)-[r2:ACHIEVED]->(tp)
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

    logger.info("✓ Updated %d other relationships", total_updated)
    return total_updated


def create_organization_constraints_and_indexes(driver, dry_run: bool = False) -> None:
    """Create constraints and indexes for Organization nodes.

    Args:
        driver: Neo4j driver
        dry_run: If True, don't execute queries
    """
    logger.info("Step 8: Creating Organization constraints and indexes")

    statements = [
        "CREATE CONSTRAINT IF NOT EXISTS FOR (o:Organization) REQUIRE o.organization_id IS UNIQUE",
        "CREATE INDEX IF NOT EXISTS FOR (o:Organization) ON (o.name)",
        "CREATE INDEX IF NOT EXISTS FOR (o:Organization) ON (o.normalized_name)",
        "CREATE INDEX IF NOT EXISTS FOR (o:Organization) ON (o.organization_type)",
        "CREATE INDEX IF NOT EXISTS FOR (o:Organization) ON (o.uei)",
        "CREATE INDEX IF NOT EXISTS FOR (o:Organization) ON (o.duns)",
        "CREATE INDEX IF NOT EXISTS FOR (o:Organization) ON (o.agency_code)",
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
    logger.info("Step 9: Validating migration")

    validation_queries = {
        "remaining_companies": "MATCH (c:Company) RETURN count(c) as count",
        "remaining_patent_entities": "MATCH (pe:PatentEntity) WHERE pe.entity_category IN ['COMPANY', 'UNIVERSITY', 'GOVERNMENT'] RETURN count(pe) as count",
        "remaining_research_institutions": "MATCH (ri:ResearchInstitution) RETURN count(ri) as count",
        "organizations_by_type": """
            MATCH (o:Organization)
            RETURN o.organization_type, count(*) as count
            ORDER BY count DESC
        """,
        "award_org_relationships": "MATCH (a:Award)-[r:AWARDED_TO]->(o:Organization) RETURN count(r) as count",
        "agency_funding_relationships": "MATCH (a:Award)-[r:FUNDED_BY]->(o:Organization {organization_type: 'AGENCY'}) RETURN count(r) as count",
        "contract_agency_relationships": "MATCH (c:Contract)-[r:AWARDED_BY]->(o:Organization {organization_type: 'AGENCY'}) RETURN count(r) as count",
    }

    results = {}
    with driver.session() as session:
        for key, query in validation_queries.items():
            try:
                result = session.run(query)
                if key == "organizations_by_type":
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
    logger.info("  Companies: %s", results.get("remaining_companies", "N/A"))
    logger.info("  PatentEntities (non-individuals): %s", results.get("remaining_patent_entities", "N/A"))
    logger.info("  ResearchInstitutions: %s", results.get("remaining_research_institutions", "N/A"))

    logger.info("\nOrganizations by type:")
    org_types = results.get("organizations_by_type", [])
    for org_type in org_types:
        logger.info("  %s: %d", org_type.get("o.organization_type", "UNKNOWN"), org_type.get("count", 0))

    logger.info("\nRelationships:")
    logger.info("  AWARDED_TO (Award → Organization): %s", results.get("award_org_relationships", "N/A"))
    logger.info("  FUNDED_BY (Award → Agency): %s", results.get("agency_funding_relationships", "N/A"))
    logger.info("  AWARDED_BY (Contract → Agency): %s", results.get("contract_agency_relationships", "N/A"))

    logger.info("\n" + "=" * 60)


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Migrate Company, PatentEntity, ResearchInstitution to unified Organization nodes."
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
        migrate_companies_to_organizations(driver, dry_run=args.dry_run)
        migrate_patent_entities_to_organizations(driver, dry_run=args.dry_run)
        migrate_research_institutions_to_organizations(driver, dry_run=args.dry_run)
        create_agency_organizations(driver, dry_run=args.dry_run)
        update_award_relationships(driver, dry_run=args.dry_run)
        update_contract_relationships(driver, dry_run=args.dry_run)
        update_other_relationships(driver, dry_run=args.dry_run)
        create_organization_constraints_and_indexes(driver, dry_run=args.dry_run)

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

