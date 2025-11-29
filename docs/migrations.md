---
Type: Reference
Owner: docs@project
Last-Reviewed: 2025-01-XX
Status: active

---

# Neo4j Migrations

This directory contains Neo4j schema migrations managed using a custom migration system.

## Overview

Migrations are versioned Python files that define schema changes (constraints, indexes) and data migrations. They are automatically applied when `Neo4jClient` is initialized (if `auto_migrate=True`), or can be run manually via CLI.

## Migration Files

Migrations are located in `migrations/versions/` and follow the naming pattern:
- `001_initial_schema.py` - Initial constraints and indexes
- `002_add_organization_deduplication_indexes.py` - Indexes for deduplication
- `003_merge_existing_duplicate_organizations.py` - One-time data cleanup

## Running Migrations

### Automatic (Default)

Migrations run automatically when `Neo4jClient` is initialized if `auto_migrate=True` (default).

### Manual CLI

```bash
# Upgrade to latest
python scripts/neo4j/migrate.py upgrade

# Upgrade to specific version
python scripts/neo4j/migrate.py upgrade --target 002

# Check current version
python scripts/neo4j/migrate.py current

# View migration history
python scripts/neo4j/migrate.py history

# Downgrade to specific version
python scripts/neo4j/migrate.py downgrade --target 001

# Dry run (preview changes)
python scripts/neo4j/migrate.py upgrade --dry-run
```

Environment variables:
- `NEO4J_URI` - Neo4j connection URI (default: `bolt://localhost:7687`)
- `NEO4J_USER` - Username (default: `neo4j`)
- `NEO4J_PASSWORD` - Password (required)

## Creating New Migrations

1. Create a new file in `migrations/versions/`:
   ```python
   from migrations.base import Migration
   from neo4j import Driver

   class MyNewMigration(Migration):
       def __init__(self):
           super().__init__("004", "Description of migration")

       def upgrade(self, driver: Driver) -> None:
           """Apply migration."""
           with driver.session() as session:
               session.run("CREATE INDEX ...")

       def downgrade(self, driver: Driver) -> None:
           """Rollback migration."""
           with driver.session() as session:
               session.run("DROP INDEX ...")
   ```

2. Use version numbers sequentially (004, 005, etc.)
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
