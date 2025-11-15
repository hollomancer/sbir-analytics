# Unified Organization Node Migration Guide

## Overview

This guide documents the migration from separate `Company`, `PatentEntity`, and `ResearchInstitution` node types to a unified `Organization` node type. This migration simplifies entity resolution, reduces duplication, and enables unified queries across all organizational entities.

## Migration Date

**Migration Date**: [To be filled in when migration is executed]

## What Changed

### Node Types Consolidated

- **Company** → `Organization` with `organization_type: "COMPANY"`
- **PatentEntity** (non-individuals) → `Organization` with `organization_type: "COMPANY"`, `"UNIVERSITY"`, or `"GOVERNMENT"`
- **ResearchInstitution** → `Organization` with `organization_type: "UNIVERSITY"`
- **Agency** (new) → `Organization` with `organization_type: "AGENCY"`

### New Node Type

- **Organization**: Unified node type for all organizational entities

### New Relationships

- `FUNDED_BY`: (Award) → (Organization {organization_type: "AGENCY"})
- `AWARDED_BY`: (Contract) → (Organization {organization_type: "AGENCY"})

### Updated Relationships

All relationships that previously pointed to `Company`, `PatentEntity`, or `ResearchInstitution` now point to `Organization`:

- `AWARDED_TO`: (Award) → (Organization)
- `AWARDED_CONTRACT`: (Organization) → (Contract)
- `ASSIGNED_TO`: (PatentAssignment) → (Organization)
- `ASSIGNED_FROM`: (PatentAssignment) → (Organization)
- `OWNS`: (Organization) → (Patent)
- `SPECIALIZES_IN`: (Organization) → (CETArea)
- `ACHIEVED`: (Organization) → (TransitionProfile)
- `WORKED_AT`: (Researcher) → (Organization)
- `CONDUCTED_AT`: (Award) → (Organization)

## Migration Process

### Prerequisites

1. **Backup Database**: Ensure you have a recent backup of your Neo4j database
2. **Environment Variables**: Set `NEO4J_URI`, `NEO4J_USER`, and `NEO4J_PASSWORD`
3. **Review Plan**: Review the migration plan in `unified-organization-migration.plan.md`

### Running the Migration

1. **Dry Run** (recommended first step):
   ```bash
   python scripts/migration/unified_organization_migration.py --dry-run
   ```

2. **Execute Migration**:
   ```bash
   python scripts/migration/unified_organization_migration.py --yes
   ```

3. **Validate Migration**:
   The script automatically runs validation queries. Review the output to ensure:
   - All Company nodes migrated
   - All PatentEntity nodes (non-individuals) migrated
   - All ResearchInstitution nodes migrated
   - Agency Organizations created
   - All relationships updated correctly

### Migration Steps

The migration script performs the following steps:

1. **Migrate Company nodes** → Organization (organization_type: "COMPANY")
2. **Migrate PatentEntity nodes** (non-individuals) → Organization, merging with existing Organizations where matches found
3. **Migrate ResearchInstitution nodes** → Organization (organization_type: "UNIVERSITY")
4. **Create Agency Organizations** from Award/Contract agency data
5. **Update Award relationships** (AWARDED_TO, FUNDED_BY)
6. **Update Contract relationships** (AWARDED_CONTRACT, AWARDED_BY)
7. **Update other relationships** (OWNS, SPECIALIZES_IN, ACHIEVED, etc.)
8. **Create constraints and indexes** for Organization nodes
9. **Validate migration** completeness

## Query Migration Patterns

### Finding Companies

**Before:**
```cypher
MATCH (c:Company {uei: $uei})
RETURN c
```

**After:**
```cypher
MATCH (o:Organization {uei: $uei, organization_type: "COMPANY"})
RETURN o
```

### Finding Organizations with Patents

**Before:**
```cypher
MATCH (c:Company)-[:OWNS]->(p:Patent)
RETURN c.name, count(p) as patent_count
```

**After:**
```cypher
MATCH (o:Organization {organization_type: "COMPANY"})-[:OWNS]->(p:Patent)
RETURN o.name, count(p) as patent_count
```

### Finding Funding Agencies

**New Query:**
```cypher
MATCH (a:Award)-[:FUNDED_BY]->(o:Organization {organization_type: "AGENCY"})
RETURN o.agency_name, count(a) as award_count
ORDER BY award_count DESC
```

### Finding Organizations Across Multiple Contexts

**New Query:**
```cypher
MATCH (o:Organization)
WHERE size(o.source_contexts) > 1
RETURN o.name, o.organization_type, o.source_contexts
```

## Backward Compatibility

### Legacy Properties Preserved

- `company_id`: Preserved on Organization nodes for backward compatibility
- `entity_id`: Preserved on Organization nodes for patent queries
- Old node types remain in database until explicitly removed (for rollback safety)

### Migration Period

During the migration period:
- Old node types (`Company`, `PatentEntity`, `ResearchInstitution`) remain in the database
- New code uses `Organization` nodes
- Old queries continue to work (but may return stale data)
- Gradually migrate queries to use `Organization` nodes

## Rollback Procedure

If you need to rollback the migration:

1. **Revert Code Changes**: Revert all code changes that use `Organization` nodes
2. **Old Nodes Still Exist**: The migration script does NOT delete old nodes, so they remain available
3. **Restore Relationships**: If needed, restore relationships from backup

**Note**: The migration script creates new nodes without deleting old ones, so rollback is safe.

## Post-Migration Tasks

1. **Update All Queries**: Migrate all Cypher queries to use `Organization` nodes
2. **Update Tests**: Update all unit/integration tests to use `Organization` nodes
3. **Update Documentation**: Update any documentation that references old node types
4. **Monitor Performance**: Monitor query performance after migration
5. **Remove Old Nodes** (optional, after validation period): Once confident in migration, can remove old node types

## Validation Queries

Run these queries to verify migration completeness:

```cypher
// Verify all Companies migrated
MATCH (c:Company) RETURN count(c) as remaining_companies
// Should be 0

// Verify Organizations created
MATCH (o:Organization) 
RETURN o.organization_type, count(*) as count
ORDER BY count DESC

// Verify relationships updated
MATCH (a:Award)-[r:AWARDED_TO]->(o:Organization)
RETURN count(r) as award_org_relationships

// Verify agency relationships
MATCH (a:Award)-[r:FUNDED_BY]->(o:Organization {organization_type: "AGENCY"})
RETURN count(r) as agency_funding_relationships
```

## Troubleshooting

### Issue: Some Company nodes not migrated

**Solution**: Check for companies without `company_id`, `uei`, or `duns`. The migration script generates `organization_id` from these fields.

### Issue: Duplicate Organizations created

**Solution**: The migration script merges PatentEntity nodes with existing Organizations by `normalized_name` + `state` + `postcode` or `uei`. If duplicates exist, manually merge them.

### Issue: Relationships not updated

**Solution**: Check that the migration script completed successfully. Re-run the relationship update steps if needed.

## Support

For issues or questions about the migration:
1. Check the migration script logs
2. Review validation query results
3. Consult the migration plan document
4. Contact the development team

## Related Documentation

- [Organization Schema](../schemas/organization-schema.md)
- [Migration Plan](../../unified-organization-node-migration.plan.md)
- [Neo4j Patterns](../../.kiro/steering/neo4j-patterns.md)

