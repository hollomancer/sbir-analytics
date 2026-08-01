---
Type: Reference
Owner: docs@project
Last-Reviewed: 2026-08-01
Status: active

---

# Neo4j Migrations

Neo4j schema and data migrations are packaged with `sbir-graph` and managed using a custom
migration system.

## Overview

Migrations are versioned Python files that define schema changes (constraints and indexes) and
data migrations. Normal `Neo4jClient` construction does not apply them: `auto_migrate` defaults to
`False`, so an operator must run the repository CLI wrapper. Because the migration package is part
of the `sbir-graph` distribution, the same definitions are available in checkout, container, and
installed-package environments.

## Migration Files

Migrations are located in
`packages/sbir-graph/sbir_graph/migrations/versions/` and follow the naming pattern:

- `001_initial_schema.py` - Initial constraints and indexes
- `002_add_organization_deduplication_indexes.py` - Indexes for deduplication
- `003_merge_existing_duplicate_organizations.py` - One-time data cleanup
- `004_vector_indexes.py` - Vector/cross-reference indexes
- `005_drop_lightrag_vector_indexes.py` - Drop LightRAG-era vector indexes
  (`award_embedding`, `patent_embedding`)
- `006_unify_award_into_financial_transaction.py` - Unify legacy Award nodes into
  FinancialTransaction
- `007_unify_company_into_organization.py` - Unify legacy Company nodes into Organization

## Running Migrations

### Manual CLI (Default)

Install `sbir-graph` (or the full `sbir-analytics` package) before using the repository CLI
wrapper:

```bash
pip install sbir-graph
```

```bash
# Check current version
python scripts/neo4j/migrate.py current

# View migration history
python scripts/neo4j/migrate.py history

# Preview pending migrations without applying them
python scripts/neo4j/migrate.py upgrade --dry-run

# Upgrade to latest after reviewing the plan
python scripts/neo4j/migrate.py upgrade

# Upgrade to a specific version
python scripts/neo4j/migrate.py upgrade --target 002

# Downgrade to a specific version
python scripts/neo4j/migrate.py downgrade --target 001
```

Before upgrading a production graph, take and verify a backup using the procedure in the
[Neo4j operations runbook](deployment/neo4j-runbook.md). Review data migrations particularly
carefully: 003 merges duplicate organizations, 006 re-homes legacy `Award` nodes into
`FinancialTransaction`, and 007 re-homes legacy `Company` nodes into `Organization`.

Migration discovery, module import, and execution are fail-closed. A failure exits the command
without marking the failed migration as applied; correct the problem before retrying.

### Automatic (Opt-in)

Direct `sbir_graph` callers may explicitly construct `Neo4jConfig(auto_migrate=True)` in managed
environments where client construction is the intended migration gate. The same fail-closed
behavior applies: a discovery or execution failure aborts `Neo4jClient` initialization instead of
leaving the application running against a partially migrated graph.

Environment variables:

- `NEO4J_URI` - Neo4j connection URI (default: `bolt://localhost:7687`)
- `NEO4J_USER` - Username (default: `neo4j`)
- `NEO4J_PASSWORD` - Password (required)

## Creating New Migrations

1. Create a new file in `packages/sbir-graph/sbir_graph/migrations/versions/`:

   ```python
   from neo4j import Driver
   from sbir_graph.migrations.base import Migration


   class MyNewMigration(Migration):
       def __init__(self):
           super().__init__("008", "Description of migration")

       def upgrade(self, driver: Driver) -> None:
           """Apply migration."""
           with driver.session() as session:
               session.run("CREATE INDEX ...")

       def downgrade(self, driver: Driver) -> None:
           """Rollback migration."""
           with driver.session() as session:
               session.run("DROP INDEX ...")
   ```

2. Use version numbers sequentially (`008` is next at the time of writing)
3. Implement both `upgrade()` and `downgrade()` methods
4. Use `IF NOT EXISTS` / `IF EXISTS` clauses for idempotency

## Migration Tracking

Migrations are tracked in Neo4j using a `__MigrationTracking` node that stores:

- `applied_versions`: List of applied migration versions
- `current_version`: Latest applied version
- `updated_at`: Last update timestamp

## Best Practices

1. **Idempotency**: Use `IF NOT EXISTS` / `IF EXISTS` clauses
2. **Rollback**: Always implement `downgrade()` method
3. **Testing**: Test migrations on a copy of production data
4. **Documentation**: Document why the migration is needed
5. **Data Migrations**: For data changes, track merge history for reversibility

## Rollback Considerations

- **Schema migrations**: Fully reversible via `downgrade()`
- **Data migrations**: Not automatically reversible, but merge history is tracked in node properties (`__merged_from`, `__merge_history`)
