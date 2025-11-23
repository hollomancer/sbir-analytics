"""Add indexes for Organization deduplication."""

from migrations.base import Migration
from neo4j import Driver


class AddOrganizationDeduplicationIndexes(Migration):
    """Add indexes for multi-key MERGE deduplication."""

    def __init__(self):
        super().__init__("002", "Add Organization deduplication indexes")

    def upgrade(self, driver: Driver) -> None:
        """Add indexes for deduplication queries."""
        statements = [
            # Indexes for multi-key MERGE lookups (these may already exist from 001, but ensure they're there)
            "CREATE INDEX organization_uei_lookup IF NOT EXISTS FOR (o:Organization) ON (o.uei)",
            "CREATE INDEX organization_duns_lookup IF NOT EXISTS FOR (o:Organization) ON (o.duns)",
            # Composite index for normalized name + type matching
            "CREATE INDEX organization_normalized_name_type IF NOT EXISTS FOR (o:Organization) ON (o.normalized_name, o.organization_type)",
        ]

        with driver.session() as session:
            for stmt in statements:
                try:
                    session.run(stmt)
                except Exception as e:
                    from loguru import logger

                    logger.debug(f"Index may already exist: {e}")

    def downgrade(self, driver: Driver) -> None:
        """Remove deduplication indexes."""
        statements = [
            "DROP INDEX organization_uei_lookup IF EXISTS",
            "DROP INDEX organization_duns_lookup IF EXISTS",
            "DROP INDEX organization_normalized_name_type IF EXISTS",
        ]

        with driver.session() as session:
            for stmt in statements:
                try:
                    session.run(stmt)
                except Exception:
                    pass
