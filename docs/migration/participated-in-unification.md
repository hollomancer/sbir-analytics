# PARTICIPATED_IN Relationship Unification Guide

## Overview

This guide documents the unification of `RESEARCHED_BY` and `WORKED_ON` relationships into a single `PARTICIPATED_IN` relationship. This simplification reduces relationship type proliferation and makes queries more intuitive.

## Migration Date

**Migration Date**: [To be filled in when migration is executed]

## What Changed

### Relationship Types Consolidated

- **RESEARCHED_BY**: (Award) → (Individual) → **Removed**
- **WORKED_ON**: (Individual) → (Award) → **Removed**
- **PARTICIPATED_IN**: (Individual) → (Award) → **New unified relationship**

### Relationship Properties

The new `PARTICIPATED_IN` relationship includes:
- `role`: String (default: "RESEARCHER")
- `created_at`: DateTime
- `migrated_from`: String (for tracking: "RESEARCHED_BY" or "WORKED_ON")

## Migration Process

### Prerequisites

1. **Backup Database**: Ensure you have a recent backup of your Neo4j database
2. **Environment Variables**: Set `NEO4J_URI`, `NEO4J_USER`, and `NEO4J_PASSWORD`
3. **Review Plan**: Review this migration guide

### Running the Migration

1. **Dry Run** (recommended first step):
   ```bash
   python scripts/migration/unify_participated_in_relationship.py --dry-run
   ```

2. **Execute Migration**:
   ```bash
   python scripts/migration/unify_participated_in_relationship.py --yes
   ```

3. **Validate Migration**:
   The script automatically runs validation queries. Review the output to ensure:
   - All RESEARCHED_BY relationships migrated
   - All WORKED_ON relationships migrated
   - No duplicate PARTICIPATED_IN relationships created
   - All relationships have correct role property

### Migration Steps

The migration script performs the following steps:

1. **Migrate RESEARCHED_BY** → PARTICIPATED_IN (reverses direction)
2. **Migrate WORKED_ON** → PARTICIPATED_IN (renames, merges duplicates)
3. **Validate migration** completeness

## Query Migration Patterns

### Finding Researchers for an Award

**Before:**
```cypher
MATCH (a:Award {award_id: $award_id})-[:RESEARCHED_BY]->(i:Individual)
RETURN i
```

**After:**
```cypher
MATCH (i:Individual)-[:PARTICIPATED_IN]->(a:Award {award_id: $award_id})
RETURN i
```

### Finding Awards for a Researcher

**Before:**
```cypher
MATCH (i:Individual {researcher_id: $researcher_id})-[:WORKED_ON]->(a:Award)
RETURN a
```

**After:**
```cypher
MATCH (i:Individual {researcher_id: $researcher_id})-[:PARTICIPATED_IN]->(a:Award)
RETURN a
```

### Finding All Participants in Awards

**New Query:**
```cypher
MATCH (i:Individual)-[p:PARTICIPATED_IN]->(a:Award)
WHERE p.role = 'RESEARCHER'
RETURN i.name, count(a) as award_count
ORDER BY award_count DESC
```

## Backward Compatibility

- Old relationship types (`RESEARCHED_BY`, `WORKED_ON`) are removed during migration
- Queries using old relationship types will need to be updated
- The migration script preserves all relationship properties

## Rollback Procedure

If you need to rollback the migration:

1. **Restore from Backup**: Restore the database from a backup taken before migration
2. **Revert Code Changes**: Revert all code changes that use `PARTICIPATED_IN`

**Note**: The migration script removes old relationships, so rollback requires a database restore.

## Post-Migration Tasks

1. **Update All Queries**: Migrate all Cypher queries to use `PARTICIPATED_IN`
2. **Update Tests**: Update all unit/integration tests to use `PARTICIPATED_IN`
3. **Update Documentation**: Update any documentation that references old relationship types
4. **Monitor Performance**: Monitor query performance after migration

## Validation Queries

Run these queries to verify migration completeness:

```cypher
// Verify no RESEARCHED_BY relationships remain
MATCH (a:Award)-[r:RESEARCHED_BY]->(i:Individual) 
RETURN count(r) as remaining_researched_by
// Should be 0

// Verify no WORKED_ON relationships remain
MATCH (i:Individual)-[r:WORKED_ON]->(a:Award) 
RETURN count(r) as remaining_worked_on
// Should be 0

// Verify PARTICIPATED_IN relationships exist
MATCH (i:Individual)-[r:PARTICIPATED_IN]->(a:Award)
RETURN count(r) as participated_in_count

// Verify role property is set
MATCH (i:Individual)-[r:PARTICIPATED_IN]->(a:Award)
RETURN r.role, count(*) as count
ORDER BY count DESC
```

## Troubleshooting

### Issue: Duplicate PARTICIPATED_IN relationships

**Solution**: The migration script uses MERGE to prevent duplicates. If duplicates exist, manually remove them:
```cypher
MATCH (i:Individual)-[r1:PARTICIPATED_IN]->(a:Award)
MATCH (i)-[r2:PARTICIPATED_IN]->(a)
WHERE id(r1) < id(r2)
DELETE r2
```

### Issue: Missing role property

**Solution**: The migration script sets `role: "RESEARCHER"` by default. If missing, update:
```cypher
MATCH (i:Individual)-[r:PARTICIPATED_IN]->(a:Award)
WHERE r.role IS NULL
SET r.role = 'RESEARCHER'
```

## Support

For issues or questions about the migration:
1. Check the migration script logs
2. Review validation query results
3. Consult this migration guide
4. Contact the development team

## Related Documentation

- [Individual Schema](../schemas/individual-schema.md)
- [Neo4j Patterns](../../.kiro/steering/neo4j-patterns.md)

