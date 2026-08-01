"""Tests for packaged Neo4j migration discovery and tracking compatibility."""

from unittest.mock import MagicMock, patch

import pytest

from sbir_graph.migrations.runner import MigrationRunner


pytestmark = pytest.mark.fast


def test_discover_migrations_from_sbir_graph_package() -> None:
    """All committed migrations are discoverable in stable version order."""
    migrations = MigrationRunner(MagicMock()).discover_migrations()
    versions = [migration.version for migration in migrations]

    assert versions == ["001", "002", "003", "004", "005", "006", "007"]
    assert len(versions) == len(set(versions))
    assert all(
        migration.__class__.__module__.startswith("sbir_graph.migrations.versions.")
        for migration in migrations
    )


def test_discovery_failure_is_fatal() -> None:
    """A broken packaged migration cannot be omitted from an apparently successful run."""
    runner = MigrationRunner(MagicMock())

    with (
        patch(
            "sbir_graph.migrations.runner.importlib.import_module",
            side_effect=ImportError("broken migration"),
        ),
        pytest.raises(RuntimeError, match="Failed to load migration") as exc_info,
    ):
        runner.discover_migrations()

    assert isinstance(exc_info.value.__cause__, ImportError)


def test_empty_migration_package_is_fatal(tmp_path) -> None:
    """A missing packaged versions tree cannot look like an up-to-date database."""
    runner = MigrationRunner(MagicMock())
    runner.migrations_dir = tmp_path

    with pytest.raises(RuntimeError, match="No migration files found"):
        runner.discover_migrations()


def test_upgrade_failure_is_fatal() -> None:
    """A failed explicit migration is not marked as applied or swallowed."""
    runner = MigrationRunner(MagicMock())
    migration = MagicMock(version="008", description="Failing migration")
    migration.upgrade.side_effect = RuntimeError("upgrade failed")

    with (
        patch.object(runner, "ensure_migration_tracking"),
        patch.object(runner, "get_applied_migrations", return_value=set()),
        patch.object(runner, "discover_migrations", return_value=[migration]),
        patch.object(runner, "mark_migration_applied") as mark_applied,
        pytest.raises(RuntimeError, match="upgrade failed"),
    ):
        runner.upgrade()

    mark_applied.assert_not_called()


def test_upgrade_dry_run_does_not_create_tracking() -> None:
    """Previewing an upgrade does not write migration-tracking state."""
    runner = MigrationRunner(MagicMock())
    migration = MagicMock(version="008", description="Pending migration")

    with (
        patch.object(runner, "ensure_migration_tracking") as ensure_tracking,
        patch.object(runner, "get_applied_migrations", return_value=set()),
        patch.object(runner, "discover_migrations", return_value=[migration]),
    ):
        runner.upgrade(dry_run=True)

    ensure_tracking.assert_not_called()
    migration.upgrade.assert_not_called()


def test_downgrade_dry_run_does_not_create_tracking() -> None:
    """Previewing a downgrade does not write migration-tracking state."""
    runner = MigrationRunner(MagicMock())
    migration = MagicMock(version="008", description="Applied migration")

    with (
        patch.object(runner, "ensure_migration_tracking") as ensure_tracking,
        patch.object(runner, "get_applied_migrations", return_value={"008"}),
        patch.object(runner, "discover_migrations", return_value=[migration]),
    ):
        runner.downgrade(target_version="007", dry_run=True)

    ensure_tracking.assert_not_called()
    migration.downgrade.assert_not_called()


def test_applied_version_tracking_is_namespace_independent() -> None:
    """Moving Python modules does not change the version strings stored in Neo4j."""
    result = MagicMock()
    result.single.return_value = {"versions": ["001", "003", "007"]}
    session = MagicMock()
    session.run.return_value = result
    session_context = MagicMock()
    session_context.__enter__.return_value = session
    session_context.__exit__.return_value = None
    driver = MagicMock()
    driver.session.return_value = session_context

    applied = MigrationRunner(driver).get_applied_migrations()

    assert applied == {"001", "003", "007"}
