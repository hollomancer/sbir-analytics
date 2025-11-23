"""Migration runner for Neo4j schema migrations."""

import importlib
from typing import Any

from loguru import logger
from neo4j import Driver

from migrations.base import Migration
from migrations.config import MIGRATIONS_DIR, TRACKING_ID, TRACKING_LABEL


class MigrationRunner:
    """Manages Neo4j schema migrations."""

    def __init__(self, driver: Driver):
        self.driver = driver
        self.migrations_dir = MIGRATIONS_DIR

    def ensure_migration_tracking(self) -> None:
        """Create migration tracking node if it doesn't exist."""
        query = f"""
        MERGE (m:{TRACKING_LABEL} {{id: $tracking_id}})
        ON CREATE SET m.current_version = '000', m.updated_at = datetime()
        RETURN m
        """

        with self.driver.session() as session:
            session.run(query, tracking_id=TRACKING_ID)

    def get_applied_migrations(self) -> set[str]:
        """Get set of applied migration versions."""
        query = f"""
        MATCH (m:{TRACKING_LABEL} {{id: $tracking_id}})
        RETURN m.applied_versions as versions
        """

        with self.driver.session() as session:
            result = session.run(query, tracking_id=TRACKING_ID)
            record = result.single()
            if record and record["versions"]:
                return set(record["versions"])
            return set()

    def mark_migration_applied(self, version: str) -> None:
        """Mark a migration as applied."""
        query = f"""
        MATCH (m:{TRACKING_LABEL} {{id: $tracking_id}})
        WITH m, coalesce(m.applied_versions, []) as current
        SET m.applied_versions = current + [$version],
            m.current_version = $version,
            m.updated_at = datetime()
        """

        with self.driver.session() as session:
            session.run(query, tracking_id=TRACKING_ID, version=version)

    def mark_migration_rolled_back(self, version: str) -> None:
        """Mark a migration as rolled back."""
        query = f"""
        MATCH (m:{TRACKING_LABEL} {{id: $tracking_id}})
        WITH m, [v IN m.applied_versions WHERE v <> $version] as updated
        SET m.applied_versions = updated,
            m.current_version = CASE WHEN size(updated) > 0 THEN updated[-1] ELSE '000' END,
            m.updated_at = datetime()
        """

        with self.driver.session() as session:
            session.run(query, tracking_id=TRACKING_ID, version=version)

    def discover_migrations(self) -> list[Migration]:
        """Discover all migration classes in versions directory."""
        migrations = []

        # Get all Python files in versions directory
        for file_path in sorted(self.migrations_dir.glob("*.py")):
            if file_path.name == "__init__.py":
                continue

            module_name = f"migrations.versions.{file_path.stem}"
            try:
                module = importlib.import_module(module_name)
                # Find Migration subclass
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if isinstance(attr, type) and issubclass(attr, Migration) and attr != Migration:
                        migrations.append(attr())
            except Exception as e:
                logger.warning(f"Failed to load migration from {file_path}: {e}")

        # Sort by version
        migrations.sort(key=lambda m: m.version)
        return migrations

    def upgrade(self, target_version: str | None = None, dry_run: bool = False) -> None:
        """Apply pending migrations."""
        self.ensure_migration_tracking()
        applied = self.get_applied_migrations()
        migrations = self.discover_migrations()

        pending = [m for m in migrations if m.version not in applied]

        if target_version:
            pending = [m for m in pending if m.version <= target_version]

        if not pending:
            logger.info("No pending migrations")
            return

        logger.info(f"Found {len(pending)} pending migrations")

        for migration in pending:
            logger.info(f"Applying migration {migration.version}: {migration.description}")

            if dry_run:
                logger.info(f"[DRY RUN] Would apply: {migration.version}")
                continue

            try:
                migration.upgrade(self.driver)
                self.mark_migration_applied(migration.version)
                logger.info(f"✓ Applied migration {migration.version}")
            except Exception as e:
                logger.error(f"✗ Failed to apply migration {migration.version}: {e}")
                raise

    def downgrade(self, target_version: str, dry_run: bool = False) -> None:
        """Rollback migrations."""
        self.ensure_migration_tracking()
        applied = self.get_applied_migrations()
        migrations = self.discover_migrations()

        # Get migrations to rollback (in reverse order)
        to_rollback = [
            m for m in reversed(migrations) if m.version in applied and m.version > target_version
        ]

        if not to_rollback:
            logger.info("No migrations to rollback")
            return

        logger.info(f"Rolling back {len(to_rollback)} migrations")

        for migration in to_rollback:
            logger.info(f"Rolling back migration {migration.version}: {migration.description}")

            if dry_run:
                logger.info(f"[DRY RUN] Would rollback: {migration.version}")
                continue

            try:
                migration.downgrade(self.driver)
                self.mark_migration_rolled_back(migration.version)
                logger.info(f"✓ Rolled back migration {migration.version}")
            except Exception as e:
                logger.error(f"✗ Failed to rollback migration {migration.version}: {e}")
                raise

    def current_version(self) -> str:
        """Get current migration version."""
        query = f"""
        MATCH (m:{TRACKING_LABEL} {{id: $tracking_id}})
        RETURN m.current_version as version
        """

        with self.driver.session() as session:
            result = session.run(query, tracking_id=TRACKING_ID)
            record = result.single()
            return record["version"] if record else "000"

    def history(self) -> list[dict[str, Any]]:
        """Get migration history."""
        applied = self.get_applied_migrations()
        migrations = self.discover_migrations()

        history = []
        for migration in migrations:
            history.append(
                {
                    "version": migration.version,
                    "description": migration.description,
                    "applied": migration.version in applied,
                }
            )

        return history
