# Relationship Consolidation Migration Guide

## Overview

This migration consolidates relationship types in Neo4j to simplify the graph schema:

1. **AWARDED_TO → RECIPIENT_OF**: Unified relationship for organizations receiving financial transactions
2. **Remove AWARDED_CONTRACT**: Cleanup unused relationship type
3. **Remove FILED**: Cleanup unused relationship type  
4. **FUNDED_BY (Patent → Award) → GENERATED_FROM**: Consolidate patent-to-award relationships

## Changes

### Relationship Renames

- `AWARDED_TO` → `RECIPIENT_OF`
  - Direction: `(FinancialTransaction)` → `(Organization)`
  - Also handles legacy `(Award)` → `(Organization)` relationships
  - Properties preserved: `transaction_type`, `created_at`

- `FUNDED_BY` (Patent → Award) → `GENERATED_FROM`
  - Direction: `(Patent)` → `(Award)`
  - Properties preserved: `linkage_method`, `confidence_score`, `linked_date`
  - Note: `FUNDED_BY` relationships from `FinancialTransaction` → `Organization` (agencies) are kept

### Relationship Removals

- `AWARDED_CONTRACT`: Removed (was never used in code)
- `FILED`: Removed (was never created in codebase)

## Migration Steps

### Prerequisites

1. **Backup Neo4j database**:
   ```bash
   # Using the backup script
   ./scripts/neo4j/backup.sh --db neo4j
   
   # Or manually
   docker exec sbir-neo4j neo4j-admin database dump neo4j --to-path=/backups
   ```

2. **Set environment variables**:
   ```bash
   export NEO4J_URI="bolt://localhost:7687"  # or your Neo4j URI
   export NEO4J_USER="neo4j"
   export NEO4J_PASSWORD="your_password"
   ```

### Running the Migration

1. **Dry run first** (recommended):
   ```bash
   python scripts/migration/consolidate_relationships.py --dry-run
   ```
   
   This will show you what queries will be executed without making any changes.

2. **Run the migration**:
   ```bash
   # With confirmation prompt
   python scripts/migration/consolidate_relationships.py
   
   # Or skip confirmation
   python scripts/migration/consolidate_relationships.py --yes
   ```

3. **Verify migration**:
   The script automatically runs validation queries after migration. Check the output for:
   - Zero remaining `AWARDED_TO` relationships
   - Zero remaining `AWARDED_CONTRACT` relationships
   - Zero remaining `FILED` relationships
   - Zero remaining `FUNDED_BY` (Patent → Award) relationships
   - Counts of new `RECIPIENT_OF` and `GENERATED_FROM` relationships

### Post-Migration Steps

1. **Test the pipeline**:
   ```bash
   # Run SBIR loading to verify new relationships are created correctly
   poetry run dagster asset materialize -m src.assets.sbir_neo4j_loading sbir_neo4j_loading
   ```

2. **Verify in Neo4j Browser**:
   ```cypher
   // Check RECIPIENT_OF relationships
   MATCH (ft:FinancialTransaction)-[r:RECIPIENT_OF]->(o:Organization)
   RETURN count(r) as recipient_count
   
   // Check no AWARDED_TO remain
   MATCH (ft:FinancialTransaction)-[r:AWARDED_TO]->(o:Organization)
   RETURN count(r) as remaining
   ```

3. **Update any custom queries**:
   - Replace `AWARDED_TO` with `RECIPIENT_OF` in any custom Cypher queries
   - Replace `FILED` with `GENERATED_FROM` in patent queries (if used)
   - Remove references to `AWARDED_CONTRACT`

## Rollback

If you need to rollback:

1. **Restore from backup**:
   ```bash
   ./scripts/neo4j/restore.sh --backup-path /path/to/backup.dump --db neo4j
   ```

2. **Or manually revert relationships** (not recommended):
   ```cypher
   // Revert RECIPIENT_OF to AWARDED_TO
   MATCH (ft:FinancialTransaction)-[r:RECIPIENT_OF]->(o:Organization)
   WHERE r.migrated_from = 'AWARDED_TO'
   CREATE (ft)-[new:AWARDED_TO]->(o)
   SET new.created_at = r.created_at
   DELETE r
   ```

## Impact

- **Breaking Changes**: Queries using `AWARDED_TO` will need to be updated to `RECIPIENT_OF`
- **Backward Compatibility**: The loader code uses `MERGE`, so re-running the pipeline will create new relationships correctly
- **Performance**: No significant performance impact expected

## Related Documentation

- Schema documentation: `docs/schemas/transition-graph-schema.md`
- Organization schema: `docs/schemas/organization-schema.md`
- Patent schema: `docs/schemas/patent-neo4j-schema.md`

