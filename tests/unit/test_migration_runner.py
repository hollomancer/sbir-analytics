"""Tests for packaged Neo4j migration discovery and tracking compatibility."""

from unittest.mock import MagicMock

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
