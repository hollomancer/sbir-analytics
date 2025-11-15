# TransitionProfile Consolidation Migration Guide

## Overview

This guide documents the consolidation of `TransitionProfile` nodes into `Organization` node properties. Transition metrics are now stored directly on Organization nodes, simplifying the graph model and improving query performance.

## Migration Date

**Migration Date**: [To be filled in when migration is executed]

## What Changed

### Node Types Consolidated

- **TransitionProfile**: Separate node → **Removed**
- **Organization**: Now includes transition metrics as properties → **Updated**

### Properties Migrated

The following properties were moved from `TransitionProfile` to `Organization`:

- `total_awards` → `transition_total_awards`
- `total_transitions` → `transition_total_transitions`
- `success_rate` → `transition_success_rate`
- `avg_likelihood_score` → `transition_avg_likelihood_score`
- `updated_date` → `transition_profile_updated_at`

### Relationships Removed

- **ACHIEVED**: (Organization) → (TransitionProfile) → **Removed**

## Migration Process

### Prerequisites

1. **Backup Database**: Ensure you have a recent backup of your Neo4j database
2. **Environment Variables**: Set `NEO4J_URI`, `NEO4J_USER`, and `NEO4J_PASSWORD`
3. **Review Plan**: Review this migration guide

### Running the Migration

1. **Dry Run** (recommended first step):
   ```bash
   python scripts/migration/consolidate_transition_profile_to_organization.py --dry-run
   ```

2. **Execute Migration**:
   ```bash
   python scripts/migration/consolidate_transition_profile_to_organization.py --yes
   ```

3. **Validate Migration**:
   The script automatically runs validation queries. Review the output to ensure:
   - All TransitionProfile properties migrated to Organization nodes
   - All ACHIEVED relationships removed
   - All TransitionProfile nodes removed
   - Transition metrics are accessible on Organization nodes

### Migration Steps

The migration script performs the following steps:

1. **Migrate Properties**: Copy TransitionProfile properties to Organization nodes
2. **Remove Relationships**: Delete ACHIEVED relationships
3. **Remove Nodes**: Delete TransitionProfile nodes
4. **Create Indexes**: Create indexes on Organization transition properties
5. **Validate**: Verify migration completeness

## Query Migration Patterns

### Finding Companies by Success Rate

**Before:**
```cypher
MATCH (o:Organization)-[:ACHIEVED]->(prof:TransitionProfile)
WHERE prof.success_rate > 0.5
RETURN o.name, prof.success_rate
```

**After:**
```cypher
MATCH (o:Organization {organization_type: "COMPANY"})
WHERE o.transition_success_rate > 0.5
RETURN o.name, o.transition_success_rate
```

### Getting Company Transition Metrics

**Before:**
```cypher
MATCH (o:Organization {organization_id: $org_id})-[:ACHIEVED]->(prof:TransitionProfile)
RETURN prof.total_awards, prof.total_transitions, prof.success_rate
```

**After:**
```cypher
MATCH (o:Organization {organization_id: $org_id})
WHERE o.transition_total_awards IS NOT NULL
RETURN o.transition_total_awards, o.transition_total_transitions, o.transition_success_rate
```

### Top Companies by Success Rate

**Before:**
```cypher
MATCH (o:Organization)-[:ACHIEVED]->(prof:TransitionProfile)
RETURN o.name, prof.success_rate
ORDER BY prof.success_rate DESC
LIMIT 10
```

**After:**
```cypher
MATCH (o:Organization {organization_type: "COMPANY"})
WHERE o.transition_success_rate IS NOT NULL
RETURN o.name, o.transition_success_rate
ORDER BY o.transition_success_rate DESC
LIMIT 10
```

## Benefits

- **Simpler Model**: One less node type to manage
- **Better Performance**: No relationship traversal needed
- **Direct Access**: `org.transition_success_rate` instead of traversing `ACHIEVED`
- **Fewer Nodes**: Reduced graph complexity
- **Easier Queries**: Filter and sort directly on Organization properties

## Backward Compatibility

- Old TransitionProfile nodes are removed during migration
- Queries using TransitionProfile will need to be updated
- The migration script preserves all transition metrics

## Rollback Procedure

If you need to rollback the migration:

1. **Restore from Backup**: Restore the database from a backup taken before migration
2. **Revert Code Changes**: Revert all code changes that use Organization transition properties

**Note**: The migration script removes TransitionProfile nodes, so rollback requires a database restore.

## Post-Migration Tasks

1. **Update All Queries**: Migrate all Cypher queries to use Organization properties
2. **Update Tests**: Update all unit/integration tests to use Organization properties
3. **Update Documentation**: Update any documentation that references TransitionProfile
4. **Monitor Performance**: Monitor query performance after migration

## Validation Queries

Run these queries to verify migration completeness:

```cypher
// Verify no TransitionProfile nodes remain
MATCH (p:TransitionProfile) 
RETURN count(p) as remaining_profiles
// Should be 0

// Verify no ACHIEVED relationships remain
MATCH (o:Organization)-[r:ACHIEVED]->(p:TransitionProfile) 
RETURN count(r) as remaining_rels
// Should be 0

// Verify Organizations have transition metrics
MATCH (o:Organization {organization_type: "COMPANY"})
WHERE o.transition_total_awards IS NOT NULL
RETURN count(o) as orgs_with_metrics

// Verify metrics are correct
MATCH (o:Organization {organization_type: "COMPANY"})
WHERE o.transition_total_awards IS NOT NULL
RETURN 
    avg(o.transition_success_rate) as avg_success_rate,
    sum(o.transition_total_awards) as total_awards,
    sum(o.transition_total_transitions) as total_transitions
```

## Troubleshooting

### Issue: Missing transition metrics on Organization nodes

**Solution**: Re-run the transition profile computation:
```cypher
MATCH (o:Organization {organization_type: "COMPANY"})<-[:AWARDED_TO]-(ft:FinancialTransaction {transaction_type: 'AWARD'})
OPTIONAL MATCH (ft)-[tt:TRANSITIONED_TO]->(t:Transition)
WITH o, 
     count(distinct ft) as total_awards,
     count(distinct case when tt IS NOT NULL then ft.transaction_id end) as total_transitions,
     avg(case when tt IS NOT NULL then tt.likelihood_score else null end) as avg_likelihood_score
WHERE total_awards > 0
SET o.transition_total_awards = total_awards,
    o.transition_total_transitions = total_transitions,
    o.transition_success_rate = (toFloat(total_transitions) / toFloat(total_awards)),
    o.transition_avg_likelihood_score = avg_likelihood_score,
    o.transition_profile_updated_at = datetime()
```

## Support

For issues or questions about the migration:
1. Check the migration script logs
2. Review validation query results
3. Consult this migration guide
4. Contact the development team

## Related Documentation

- [Organization Schema](../schemas/organization-schema.md)
- [Transition Graph Schema](../schemas/transition-graph-schema.md)

