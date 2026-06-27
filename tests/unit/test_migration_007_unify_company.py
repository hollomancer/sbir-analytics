"""Tests for migration 007 (unify :Company into :Organization)."""

import importlib
from unittest.mock import MagicMock

import pytest


pytestmark = pytest.mark.fast

# The migration module name begins with a digit, so import it dynamically.
_module = importlib.import_module("migrations.versions.007_unify_company_into_organization")
UnifyCompanyIntoOrganization = _module.UnifyCompanyIntoOrganization


def _mock_driver_with_session():
    """Return (driver, session) where driver.session() is a context manager."""
    session = MagicMock()
    cm = MagicMock()
    cm.__enter__.return_value = session
    cm.__exit__.return_value = None
    driver = MagicMock()
    driver.session.return_value = cm
    return driver, session


def test_migration_metadata():
    migration = UnifyCompanyIntoOrganization()
    assert migration.version == "007"
    assert "Organization" in migration.description


def test_upgrade_rehomes_then_drops_legacy_schema():
    migration = UnifyCompanyIntoOrganization()
    driver, session = _mock_driver_with_session()

    # Orphan count query -> 0 orphans.
    orphan_record = MagicMock()
    orphan_record.__getitem__.side_effect = lambda key: {"n": 0}[key]
    orphan_result = MagicMock()
    orphan_result.single.return_value = orphan_record
    session.run.return_value = orphan_result

    # Re-home loop returns a batch with 0 rehomed so the loop terminates immediately.
    session.execute_write.return_value = {"rehomed": 0}

    migration.upgrade(driver)

    statements = [call.args[0] for call in session.run.call_args_list]

    # The legacy :Company constraint and indexes must be dropped.
    assert any("DROP CONSTRAINT company_id" in s for s in statements)
    assert any("DROP INDEX company_name" in s for s in statements)
    assert any("DROP INDEX company_sec_cik_idx" in s for s in statements)

    # The enrichment indexes must be re-homed onto :Organization.
    assert any("org_classification_idx" in s and ":Organization" in s for s in statements)
    assert any("org_sec_cik_idx" in s and ":Organization" in s for s in statements)


def test_rehome_batch_preserves_identity_and_drops_company_id():
    """The re-home Cypher preserves Organization identity and drops the legacy key."""
    tx = MagicMock()
    record = MagicMock()
    record.__getitem__.side_effect = lambda key: {"rehomed": 0}[key]
    result = MagicMock()
    result.single.return_value = record
    tx.run.return_value = result

    out = UnifyCompanyIntoOrganization._rehome_batch(tx)

    assert out == {"rehomed": 0}
    query = tx.run.call_args.args[0]
    # Matched by the non-key uei; never MERGEs the Organization.
    assert "MATCH (o:Organization {uei: c.uei})" in query
    assert "MERGE" not in query
    # Authoritative identity is restored and the legacy company_id is removed.
    assert "o.organization_id = o_organization_id" in query
    assert "REMOVE o.company_id" in query
    assert "DETACH DELETE c" in query


def test_downgrade_recreates_legacy_schema():
    migration = UnifyCompanyIntoOrganization()
    driver, session = _mock_driver_with_session()

    migration.downgrade(driver)

    statements = [call.args[0] for call in session.run.call_args_list]
    assert any("CREATE CONSTRAINT company_id" in s and ":Company" in s for s in statements)
    assert any("company_name" in s and ":Company" in s for s in statements)
    assert any("company_sec_cik_idx" in s and ":Company" in s for s in statements)
