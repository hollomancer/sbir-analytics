"""Tests for migration 006 (unify :Award into :FinancialTransaction)."""

import importlib
from unittest.mock import MagicMock

import pytest


pytestmark = pytest.mark.fast

# The migration module name begins with a digit, so import it dynamically.
_module = importlib.import_module(
    "migrations.versions.006_unify_award_into_financial_transaction"
)
UnifyAwardIntoFinancialTransaction = _module.UnifyAwardIntoFinancialTransaction


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
    migration = UnifyAwardIntoFinancialTransaction()
    assert migration.version == "006"
    assert "FinancialTransaction" in migration.description


def test_upgrade_rehomes_then_drops_legacy_schema():
    migration = UnifyAwardIntoFinancialTransaction()
    driver, session = _mock_driver_with_session()

    # Orphan count query -> 0 orphans.
    orphan_record = MagicMock()
    orphan_record.__getitem__.side_effect = lambda key: {"n": 0}[key]
    orphan_result = MagicMock()
    orphan_result.single.return_value = orphan_record
    session.run.return_value = orphan_result

    # Re-home loop returns a batch with 0 rehomed so the loop terminates immediately.
    session.execute_write.return_value = {
        "rehomed": 0,
        "applicable_to": 0,
        "generated_from": 0,
    }

    migration.upgrade(driver)

    # The legacy :Award constraint and indexes must be dropped.
    drop_statements = [call.args[0] for call in session.run.call_args_list]
    assert any("DROP CONSTRAINT award_id" in s for s in drop_statements)
    assert any("DROP INDEX award_date" in s for s in drop_statements)
    assert any("DROP INDEX award_topic_code" in s for s in drop_statements)


def test_downgrade_recreates_legacy_schema():
    migration = UnifyAwardIntoFinancialTransaction()
    driver, session = _mock_driver_with_session()

    migration.downgrade(driver)

    statements = [call.args[0] for call in session.run.call_args_list]
    assert any("CREATE CONSTRAINT award_id" in s and ":Award" in s for s in statements)
    assert any("award_date" in s and ":Award" in s for s in statements)
    assert any("award_topic_code" in s and ":Award" in s for s in statements)
